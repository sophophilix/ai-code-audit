"""The file review: briefs, one checked pass per unit, and reuse (ADR 0007).

`kit units` writes a brief per unit (D1, D2). `kit review` runs one headless
pass per unit, checks the JSON it returns (D3), sends it back once with the
failed checks listed, and writes the record only when it passes. A unit pass
doesn't checkpoint (D4): it's short, and if it fails the kit runs it again.
Every attempt goes in the pass ledger (D8). A unit whose text, kit version and
skill sections are unchanged keeps its record, or takes an earlier audit's (D7).
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from audit_kit import brief, file_record, gates, ledger, scan_rows, skill_sections
from audit_kit.brief import BriefMeta
from audit_kit.console import ok, say, skip, warn
from audit_kit.errors import AuditKitError
from audit_kit.headless import PassRunner, Reply, call_claude
from audit_kit.models_config import ModelsConfig, Pass
from audit_kit.runner import CommandError, git, run
from audit_kit.settings import KitSettings
from audit_kit.units import OUTPUT as UNITS
from audit_kit.units import Unit
from audit_kit.units import parse as parse_units
from audit_kit.validation import MODELS
from audit_kit.validation import OUTPUT as VALIDATION
from audit_kit.verification import PILOT, Searcher
from audit_kit.workspace import Workspace
from audit_kit.workspaces import Located, locate, snapshot_commit, utc_minute

WORK = brief.WORK
SYSTEM_PROMPT = "core/agents/file-reviewer.md"
# A first answer, then up to two repairs (a crash is run again instead).
ATTEMPTS = 3
# A failed pass waits about this long, with jitter, before it runs again.
RETRY_SECONDS = 5.0
_JITTER = secrets.SystemRandom()
Pause = Callable[[float], None]
STAGE = "1a"
PassStatus = Literal["done", "gate-failed", "pending"]


@dataclass(frozen=True)
class Prepared:
    """How many briefs `prepare` wrote, and their size."""

    briefs: int
    bytes: int


def prepare(ws: Workspace, units: list[Unit], kit_home: Path, version: str) -> Prepared:
    """Write every unit's brief.md and brief.json.

    The index reads each scan file once, and the rules are chosen once per kind.
    """
    index = scan_rows.build_index(ws, {u.path for u in units})
    profiles = brief.profiles_of(ws)
    # Compact in the brief: the same schema in about 40% fewer tokens.
    schema = json.dumps(json.loads(file_record.schema()), separators=(",", ":"))
    rules: dict[str, list[skill_sections.Section]] = {}
    total = 0
    for u in units:
        kind = skill_sections.kind_of(u)
        if kind not in rules:
            rules[kind] = skill_sections.sections_for(kind, kit_home, profiles)
        built = brief.build_brief(
            ws, u, index, rules[kind], gates.unit_gates(index, u), schema, version
        )
        brief.write(ws, built)
        total += len(built.text.encode("utf-8"))
    return Prepared(len(units), total)


def repair_prompt(brief_text: str, previous: str, failed: list[str]) -> str:
    """Return the brief again, then the previous answer and what failed (D3.3).

    The brief comes first and unchanged, so the provider's prompt cache reuses it.
    """
    runs = (len(m) for m in re.findall(r"`+", previous))
    fence = "`" * max(3, max(runs, default=0) + 1)
    problems = "\n".join(f"- {p}" for p in failed)
    return (
        f"{brief_text}\n\n## Your previous answer failed the kit's checks\n\n"
        "Fix every problem below and return the whole corrected JSON object, and "
        "nothing else. Copy excerpts from the numbered code without the line "
        "numbers; keep every location inside the unit's lines.\n\n"
        f"{problems}\n\nPrevious answer:\n\n{fence}json\n{previous.strip()}\n{fence}\n"
    )


def pick_pass(passes: list[Pass], lines: int) -> Pass | None:
    """Return the pass with the smallest max_unit_lines that fits, else an unlimited one."""
    sized = sorted(
        (p for p in passes if p.max_unit_lines and p.max_unit_lines >= lines),
        key=lambda p: p.max_unit_lines or 0,
    )
    if sized:
        return sized[0]
    return next((p for p in passes if p.max_unit_lines is None), None)


def load_models(ws: Workspace) -> ModelsConfig:
    """Return models.yaml, once `kit validate` has passed it.

    Raises:
        AuditKitError: If validation hasn't passed or the file doesn't parse.
    """
    if not ws.is_file(VALIDATION) or "result: pass" not in ws.read_text(VALIDATION):
        raise AuditKitError(
            f"{VALIDATION} doesn't say 'result: pass'; run kit validate"
        )
    try:
        return ModelsConfig.model_validate(yaml.safe_load(ws.read_text(MODELS)))
    except (yaml.YAMLError, ValidationError) as exc:
        raise AuditKitError(f"{MODELS}: {exc}; run kit validate") from exc


def selected(
    cfg: ModelsConfig, units: list[Unit], only: list[str] | None
) -> list[Unit]:
    """Return the units this run reviews: --units, else the pilot, else all of them.

    Raises:
        AuditKitError: If --units names an unknown unit, or the file review is off.
    """
    if only:
        unknown = sorted(set(only) - {u.id for u in units})
        if unknown:
            raise AuditKitError(f"not in {UNITS}: {', '.join(unknown[:5])}")
        return [u for u in units if u.id in only]
    if cfg.file_review.mode == "off":
        raise AuditKitError(
            "file_review.mode is off in models.yaml; set pilot or full, or name --units"
        )
    if cfg.file_review.mode == "pilot":
        return [u for u in units if u.id in cfg.file_review.pilot_units]
    return units


def system_prompt(kit_home: Path) -> str:
    """Return the file-reviewer definition without its front matter."""
    text = (kit_home / SYSTEM_PROMPT).read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip() + "\n"


@dataclass(frozen=True)
class Reuse:
    """Whether an earlier audit's record was reused, and if not, why not."""

    status: Literal["none", "reused", "rejected"]
    problems: tuple[str, ...] = ()


def reuse(
    ws: Workspace,
    old: Workspace,
    unit: Unit,
    meta: BriefMeta,
    base: file_record.Provenance,
) -> Reuse:
    """Copy an earlier audit's record for an unchanged unit (D7).

    Its excerpts are checked again against this audit's files before it's written.
    """
    try:
        record = file_record.read(old, unit)
    except file_record.InvalidRecordError as exc:
        return Reuse("rejected", (str(exc),))
    if record is None or not record.made_from(unit, meta):
        return Reuse("none")
    problems = file_record.problems(
        ws, unit, record.output, Searcher(ws), meta.check_ids
    )
    if problems:
        return Reuse("rejected", tuple(problems))
    then = record.provenance
    prov = then.model_copy(
        update={
            "repository": base.repository,
            "commit": base.commit,
            "branch": base.branch,
            "reused_from": f"{then.commit} ({old.root.name})",
        }
    )
    # Gates, scan counts and the summary come from this audit's brief.
    reused = file_record.build(unit, record.output, prov, meta)
    file_record.write(ws, unit, reused, str(brief.brief_paths(unit.id)[0]))
    return Reuse("reused")


class RateLimitedError(AuditKitError):
    """The model provider refused a pass for a usage or rate limit."""


class _Run:
    """One `kit review`: shared settings, the status table and the stop flag.

    Passes run in threads; every write to the ledger and the status table holds
    the lock, and a usage limit sets `stop` so no further pass starts.
    """

    def __init__(
        self,
        ws: Workspace,
        s: KitSettings,
        cfg: ModelsConfig,
        base: file_record.Provenance,
        runner: PassRunner,
        pause: Pause,
    ) -> None:
        self.ws = ws
        self.s = s
        self.cfg = cfg
        self.base = base
        self.runner = runner
        self.pause = pause
        self.system = system_prompt(s.kit_home)
        self.status = ledger.read_status(ws)
        self.lock = threading.Lock()
        self.stop = threading.Event()

    def record(self, row: ledger.PassRow) -> None:
        with self.lock:
            ledger.append(self.ws, row)

    def set_status(
        self, unit: Unit, status: ledger.UnitStatus, label: str, tokens: int
    ) -> None:
        with self.lock:
            self.status[unit.id] = ledger.StatusRow(
                unit.id, status, label, tokens, utc_minute()
            )
            ledger.write_status(self.ws, self.status)

    def provenance(
        self, chosen: Pass, started: str, attempt: int
    ) -> file_record.Provenance:
        family = self.cfg.providers[chosen.provider].family
        return self.base.model_copy(
            update={
                "label": chosen.label,
                "provider": chosen.provider,
                "model_family": family,
                "model": chosen.model,
                "started_utc": started,
                "finished_utc": utc_minute(),
                "sessions": attempt,
            }
        )


def _row(
    unit: Unit, chosen: Pass, attempt: int, at: str, reply: Reply
) -> ledger.PassRow:
    """Return a ledger row for one attempt; the caller sets its outcome."""
    return ledger.PassRow(
        stage=STAGE,
        unit=unit.id,
        label=chosen.label,
        model=chosen.model,
        attempt=attempt,
        outcome="ok",
        started_utc=at,
        turns=reply.turns,
        input_tokens=reply.usage.input,
        output_tokens=reply.usage.output,
        cache_read_tokens=reply.usage.cache_read,
        cache_write_tokens=reply.usage.cache_write,
        cost_usd=reply.cost_usd,
        seconds=round(reply.seconds, 1),
        session_id=reply.session,
    )


def _check(
    ws: Workspace, unit: Unit, reply: Reply, meta: BriefMeta
) -> tuple[file_record.PassOutput | None, list[str]]:
    """Return the output if every check passes, else None and the problems."""
    try:
        out = file_record.parse(reply.text)
    except file_record.InvalidOutputError as exc:
        return None, exc.problems
    problems = file_record.problems(ws, unit, out, Searcher(ws), meta.check_ids)
    return (None, problems) if problems else (out, [])


def _review_one(ctx: _Run, unit: Unit, chosen: Pass, meta: BriefMeta) -> PassStatus:
    """Run one unit's pass with one repair round, and return its status.

    Raises:
        RateLimitedError: If the provider refuses the pass for a usage limit.
    """
    if ctx.stop.is_set():
        return "pending"
    ws = ctx.ws
    brief_md = brief.brief_paths(unit.id)[0]
    brief_text = ws.read_text(brief_md, limit=50_000_000)
    prompt, tokens, last, failed = brief_text, 0, "", ["not run"]
    ctx.set_status(unit, "running", chosen.label, 0)
    started = utc_minute()
    for attempt in range(1, ATTEMPTS + 1):
        at = utc_minute()
        reply = ctx.runner(ctx.s.claude, chosen.model, ctx.system, prompt)
        tokens += reply.usage.total
        row = _row(unit, chosen, attempt, at, reply)
        if reply.rate_limited:
            ctx.record(
                row.model_copy(
                    update={"outcome": "rate limited", "problems": [reply.error]}
                )
            )
            ctx.stop.set()
            ctx.set_status(unit, "interrupted", chosen.label, tokens)
            raise RateLimitedError(f"{unit.id}: {reply.error}")
        if not reply.ok:
            # A failed run is run again with the same brief (D4).
            ctx.record(
                row.model_copy(update={"outcome": "error", "problems": [reply.error]})
            )
            prompt, failed = brief_text, [f"the pass failed: {reply.error}"]
            if attempt < ATTEMPTS:
                ctx.pause(RETRY_SECONDS * attempt * _JITTER.uniform(0.5, 1.5))
            continue
        last = reply.text
        out, failed = _check(ws, unit, reply, meta)
        outcome: ledger.Outcome = "ok" if out is not None else "checks failed"
        ctx.record(row.model_copy(update={"outcome": outcome, "problems": failed[:20]}))
        if out is not None:
            prov = ctx.provenance(chosen, started, attempt)
            record = file_record.build(unit, out, prov, meta)
            file_record.write(ws, unit, record, str(brief_md))
            ctx.set_status(unit, "done", chosen.label, tokens)
            return "done"
        prompt = repair_prompt(brief_text, reply.text, failed)
    ws.write_text(WORK / unit.id / "rejected.txt", last + "\n")
    ws.write_text(WORK / unit.id / "problems.txt", "".join(f"{p}\n" for p in failed))
    ctx.set_status(unit, "gate-failed", chosen.label, tokens)
    return "gate-failed"


def _provenance(loc: Located, s: KitSettings) -> file_record.Provenance:
    """Return what every record in this run shares; the pass fills in the rest."""
    root = loc.ws.root
    try:
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    except CommandError:
        branch = "unknown"
    try:
        words = run([s.claude, "--version"], timeout=30).text.split()
    except CommandError:
        words = []
    harness = (
        f"claude-code {words[0]}" if words else "claude-code (version not reported)"
    )
    return file_record.Provenance(
        label="",
        provider="",
        model_family="",
        model="",
        harness=harness,
        repository=loc.state.get("project") or root.name,
        commit=snapshot_commit(loc),
        branch=branch,
        started_utc="",
        finished_utc="",
    )


def _briefs(
    ws: Workspace, units: list[Unit], version: str, given: str
) -> dict[str, BriefMeta]:
    """Return each unit's brief.json, refusing a brief that's missing or stale.

    Raises:
        AuditKitError: If a brief is missing, from another kit version, or for
            different code.
    """
    metas: dict[str, BriefMeta] = {}
    for u in units:
        meta = brief.read_meta(ws, u.id)
        _, text = brief.unit_text(ws, u)
        current = (
            meta is not None
            and meta.kit_version == version
            and meta.unit_sha256 == brief.sha256(text)
        )
        if meta is None or not current:
            raise AuditKitError(
                f"{u.id}: brief missing or out of date; run kit units {given}"
            )
        metas[u.id] = meta
    return metas


@dataclass
class _Plan:
    queue: list[tuple[Unit, Pass]]
    kept: int = 0
    reused: int = 0


def _plan(
    ctx: _Run,
    todo: list[Unit],
    metas: dict[str, BriefMeta],
    passes: list[Pass],
    old: Workspace | None,
) -> _Plan:
    """Decide each unit: keep its record, reuse an earlier one, or review it."""
    plan = _Plan(queue=[])
    for u in todo:
        try:
            record = file_record.read(ctx.ws, u)
        except file_record.InvalidRecordError as exc:
            warn(f"{u.id}: reviewing again ({exc})")
            record = None
        if record is not None and record.made_from(u, metas[u.id]):
            plan.kept += 1
            continue
        if old is not None:
            result = reuse(ctx.ws, old, u, metas[u.id], ctx.base)
            if result.status == "reused":
                ctx.set_status(u, "reused", "-", 0)
                plan.reused += 1
                continue
            if result.status == "rejected":
                warn(f"{u.id}: not reused ({result.problems[0]})")
        chosen = pick_pass(passes, u.lines)
        if chosen is None:
            raise AuditKitError(f"{u.id}: no file-reviewer pass takes {u.lines} lines")
        plan.queue.append((u, chosen))
    return plan


def _execute(
    ctx: _Run, plan: _Plan, metas: dict[str, BriefMeta]
) -> tuple[dict[str, int], str]:
    """Run the queued passes; return counts by status and any usage-limit message."""
    counts = {"done": 0, "gate-failed": 0, "interrupted": 0, "pending": 0}
    stopped = ""
    workers = max(1, ctx.cfg.limits.max_parallel_passes)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            (u, pool.submit(_review_one, ctx, u, p, metas[u.id])) for u, p in plan.queue
        ]
        for u, future in futures:
            status: PassStatus | Literal["interrupted"]
            try:
                status = future.result()
            except RateLimitedError as exc:
                stopped, status = str(exc), "interrupted"
            counts[status] += 1
            if status == "pending":
                ctx.set_status(u, "pending", "-", 0)
            report = ok if status == "done" else skip if status == "pending" else warn
            report(f"{u.id} {status}")
    return counts, stopped


def review(
    s: KitSettings,
    given: str,
    *,
    only: list[str] | None = None,
    reuse_from: str | None = None,
    dry_run: bool = False,
    runner: PassRunner = call_claude,
    pause: Pause = time.sleep,
) -> int:
    """Run the file review's passes (`kit review`).

    Args:
        s: Kit settings.
        given: The workspace path or name.
        only: Unit ids to review instead of the configured selection.
        reuse_from: An earlier audit's workspace to take unchanged records from.
        dry_run: List what would run, and run nothing.
        runner: Runs one pass; a fake in tests.
        pause: Waits before a failed pass runs again; a no-op in tests.

    Returns:
        How many units are left: failed twice, interrupted, or not started.

    Raises:
        AuditKitError: If the configuration, units or briefs aren't ready.
    """
    loc = locate(s, given)
    ws = loc.ws
    cfg = load_models(ws)
    passes = cfg.agents.passes_of("file-reviewer")
    if not passes:
        raise AuditKitError("models.yaml has no file-reviewer passes")
    other = sorted({p.harness for p in passes if p.harness != "claude-code"})
    if other:
        raise AuditKitError(
            f"kit review runs claude-code passes only; run {other} by hand"
        )
    units = parse_units(ws.read_text(UNITS)) if ws.is_file(UNITS) else []
    if not units:
        raise AuditKitError(f"no units; run kit units {given}")
    todo = selected(cfg, units, only)
    if cfg.file_review.mode == "pilot" and not only:
        ws.write_text(PILOT, "".join(f"{u.id}\n" for u in todo))
    metas = _briefs(ws, todo, s.version, given)
    ctx = _Run(ws, s, cfg, _provenance(loc, s), runner, pause)
    old = locate(s, reuse_from).ws if reuse_from and not dry_run else None
    plan = _plan(ctx, todo, metas, passes, old)
    if dry_run:
        for u, p in plan.queue:
            say(f"{u.id}\t{u.lines} lines\t{p.label}\t{p.model}\t{u.record}")
        say(f"{len(plan.queue)} to review, {plan.kept} kept (unchanged)")
        return 0
    counts, stopped = _execute(ctx, plan, metas)
    summary = {"kept": plan.kept, "reused": plan.reused, **counts}
    say(", ".join(f"{k}: {v}" for k, v in summary.items()))
    if stopped:
        warn(
            f"stopped on a usage limit or login problem: {stopped}. Finished units "
            f"are kept. Log in with another account or wait for the reset, then run "
            f"kit review {given}: it carries on from the unit that stopped."
        )
    if counts["gate-failed"]:
        warn(
            f"{counts['gate-failed']} unit(s) failed the checks twice; "
            f"see {WORK}/<unit>/problems.txt"
        )
    return counts["gate-failed"] + counts["interrupted"] + counts["pending"]
