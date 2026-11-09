"""The data check and the deterministic scanners (run by a person, never by agents)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from audit_kit import code_facts, design_inventory, gates, history, review, units
from audit_kit.console import ok, say, skip, warn
from audit_kit.inventory import (
    DATA_PATTERNS,
    INVENTORY_PATH,
    KIT_ROOT,
    Inventory,
    build,
)
from audit_kit.lookups import OUTPUT as LOOKUPS
from audit_kit.lookups import look_up, render
from audit_kit.policy import load_policy
from audit_kit.projects import list_lines
from audit_kit.runner import LONG, CommandError, git, have, run
from audit_kit.settings import KitSettings
from audit_kit.unused import JS
from audit_kit.unused import OUTPUT as UNUSED
from audit_kit.unused import write_report as write_unused
from audit_kit.workspace import Workspace
from audit_kit.workspaces import checkpoint, locate, utc_minute

# Kit-owned top-level folders; the kit's `.claude` adapter is never a scan target.
KIT_FOLDERS = (*sorted(KIT_ROOT), ".claude")
SCANS = PurePosixPath(".audit/scans")
CROSSCHECK = SCANS / "inventory-crosscheck.txt"
# Syft records digests only for package-owned files unless told otherwise.
SYFT_CONFIG = """check-for-app-update: false
file:
  metadata:
    selection: all
    digests: [sha256]
exclude: ["./.git/**", "./.audit/**", "./.audit-kit/**", "./.claude/**"]
"""
LOOKUPS_DENIED = (
    "upstream status (deprecated, archived, end of life): not looked up, "
    "denied by .audit/policy.yaml network.metadata_lookups"
)
MISSING = SCANS / "MISSING.txt"
TSCONFIG = SCANS / "tsconfig.audit.json"


def tsconfig(root: Path, excludes: list[str], tsc: Path) -> str:
    """Return the kit's type-check config; paths are relative to .audit/scans.

    The target's own tsconfig or jsconfig is never used. Types for Node.js come from
    the @types/node installed beside tsc, because the target's dependencies are
    never installed.
    """
    up = "../../"
    exclude = [f"{up}{e}/**" if (root / e).is_dir() else f"{up}{e}" for e in excludes]
    config = {
        "compilerOptions": {
            "allowJs": True,
            "checkJs": True,
            "noEmit": True,
            "skipLibCheck": True,
            "strict": False,
            "target": "es2022",
            "module": "nodenext",
            "lib": ["es2022", "dom"],
            "types": ["node"],
            "typeRoots": [str(tsc.parents[1] / "@types")],
            "maxNodeModuleJsDepth": 0,
        },
        "include": [f"{up}**/*{ext}" for ext in JS],
        "exclude": [*exclude, f"{up}**/node_modules/**", f"{up}**/*.min.js"],
    }
    return json.dumps(config, indent=1) + "\n"


def check_data(s: KitSettings, given: str) -> bool:
    """List data and credential files in the tree and in git history.

    Returns:
        True when nothing was found.
    """
    loc = locate(s, given)
    ws, root = loc.ws, loc.ws.root
    tree = [e.path for e in build(ws).of("data-candidate")]
    added = git(
        "log",
        "--all",
        "--diff-filter=A",
        "--name-only",
        "--format=",
        cwd=root,
        timeout=LONG,
    )
    history = sorted(
        {
            p
            for p in added.splitlines()
            if p and not p.startswith(".audit") and DATA_PATTERNS.search(p)
        }
    )
    out = SCANS / "data-check.txt"
    body = [
        f"# data check {utc_minute()}",
        "## working tree",
        *tree,
        "## git history (files ever added)",
        *history,
    ]
    ws.write_text(out, "\n".join(body) + "\n")
    hits = len(tree) + len(history)
    if hits:
        warn(
            f"data check: {hits} file(s) need review (see {out}). Remove them or record an approved exception before any agent runs."
        )
        return False
    ok(f"data check: nothing found ({out})")
    return True


class _Scanner:
    """Runs one scanner into .audit/scans, recording missing tools and failures."""

    def __init__(self, ws: Workspace, *, force: bool) -> None:
        self.ws = ws
        self.force = force
        self.missing: list[str] = []

    def __call__(
        self, name: str, tool: str | Path, output: str, command: Callable[[Path], None]
    ) -> None:
        rel = SCANS / output
        target = self.ws.path(rel)
        if target.is_file() and target.stat().st_size and not self.force:
            skip(f"{name} (exists; --force to re-run)")
            return
        if not have(tool):
            skip(f"{name}: {tool} not installed")
            self.missing.append(f"{name}: {tool} not installed")
            return
        try:
            command(target)
        except CommandError as exc:
            self.missing.append(f"{name}: failed ({exc})")
            warn(f"{name} failed: {exc}")
            return
        if target.is_file() and target.stat().st_size:
            ok(name)
        else:
            warn(f"{name} produced no output")
            self.missing.append(f"{name}: produced no output")


def scan(s: KitSettings, given: str, *, force: bool = False) -> None:
    """Run every installed scanner; existing outputs are kept unless force is set."""
    loc = locate(s, given)
    ws, root = loc.ws, loc.ws.root
    ws.mkdir(SCANS)
    excludes = [
        *KIT_FOLDERS,
        *list_lines(ws.path(".audit/detected-excludes.txt")),
        *list_lines(loc.project / "scan-exclude.txt"),
    ]
    folders = sorted({Path(e).name for e in excludes if (root / e).is_dir()})
    files = sorted({Path(e).name for e in excludes if (root / e).is_file()})
    not_match = "|".join([r"\.min\.js$", *(f"^{re.escape(f)}$" for f in files)])
    scanner = _Scanner(ws, force=force)

    def write(target: Path, data: bytes) -> None:
        ws.write_text(
            target.relative_to(root).as_posix(), data.decode("utf-8", errors="replace")
        )

    def cloc(target: Path) -> None:
        result = run(
            [
                "cloc",
                "--quiet",
                f"--exclude-dir={','.join(folders)}",
                f"--not-match-f={not_match}",
                "--json",
                ".",
            ],
            cwd=root,
            timeout=LONG,
        )
        write(target, result.stdout)

    def gitleaks(target: Path) -> None:
        mode = "dir" if loc.state.get("mode") == "eval" else "git"
        run(
            [
                "gitleaks",
                mode,
                "--redact",
                "--exit-code",
                "0",
                "-f",
                "json",
                "-r",
                target,
                ".",
            ],
            cwd=root,
            timeout=LONG,
        )

    def osv(target: Path) -> None:
        result = run(
            [
                "osv-scanner",
                "scan",
                "source",
                "--format",
                "json",
                "-L",
                "package-lock.json",
            ],
            cwd=root,
            timeout=LONG,
            check=False,
        )
        write(target, result.stdout)

    def semgrep(target: Path) -> None:
        args: list[str | Path] = ["semgrep", "scan", "--quiet", "--metrics", "off"]
        for config in ("p/javascript", "p/expressjs", "p/owasp-top-ten"):
            args += ["--config", config]
        for e in excludes:
            args += ["--exclude", e]
        run([*args, "--sarif", "-o", target, "."], cwd=root, timeout=LONG, check=False)

    def jscpd(target: Path) -> None:
        ignore = ",".join(
            f"**/{e}/**" if (root / e).is_dir() else f"**/{e}" for e in excludes
        )
        report_dir = root / SCANS / "jscpd"
        run(
            [
                s.jscpd,
                "--silent",
                "--reporters",
                "json",
                "--output",
                report_dir,
                "--ignore",
                ignore,
                ".",
            ],
            cwd=root,
            timeout=LONG,
            check=False,
        )
        report = report_dir / "jscpd-report.json"
        if report.is_file():
            write(target, report.read_bytes())

    def shapes(target: Path) -> None:
        result = run(
            [
                "python3",
                s.drawio_dir / "scripts/shapesearch.py",
                "azure",
                "--limit",
                "5000",
                "--json",
            ],
            timeout=LONG,
        )
        write(target, result.stdout)

    scanner("cloc", "cloc", "cloc.json", cloc)
    scanner("secrets", "gitleaks", "secrets.json", gitleaks)
    if ws.is_file("package-lock.json"):
        scanner("deps-audit", "osv-scanner", "deps-audit.json", osv)
    else:
        skip("deps-audit: no package-lock.json (nothing to audit)")
        scanner.missing.append("deps-audit: no package-lock.json (nothing to audit)")

    def eslint(target: Path) -> None:
        # The kit's config only; --no-inline-config stops the target's
        # eslint-disable comments from hiding anything.
        args: list[str | Path] = [
            s.eslint, "--config", s.kit_home / "config/eslint.config.mjs",
            "--no-inline-config", "--no-error-on-unmatched-pattern",
            "--format", "json", "-o", target,
        ]  # fmt: skip
        for e in excludes:
            args += ["--ignore-pattern", f"{e}/**" if (root / e).is_dir() else e]
        run([*args, "."], cwd=root, timeout=LONG, check=False)

    def typecheck(target: Path) -> None:
        ws.write_text(TSCONFIG, tsconfig(root, excludes, s.tsc))
        result = run(
            [s.tsc, "-p", root / TSCONFIG, "--pretty", "false"],
            cwd=root,
            timeout=LONG,
            check=False,
        )
        write(target, result.stdout or b"tsc: no type errors\n")
        # The files tsc read, so coverage.json can name any it skipped.
        listed = run(
            [s.tsc, "-p", root / TSCONFIG, "--listFilesOnly"],
            cwd=root,
            timeout=LONG,
            check=False,
        )
        write(root / code_facts.TSC_FILES, listed.stdout)

    scanner("sast", "semgrep", "sast.sarif", semgrep)
    scanner("duplication", s.jscpd, "duplication.json", jscpd)
    scanner("lint", s.eslint, "lint.json", eslint)
    scanner("typecheck", s.tsc, "typecheck.txt", typecheck)
    # The unused-code analysis is the kit's own Python, so there is no tool to find.
    if ws.is_file(UNUSED) and ws.size(UNUSED) and not force:
        skip("unused (exists; --force to re-run)")
    else:
        write_unused(ws, build(ws), tuple(excludes))
        ok("unused")
    # Suppressions, blind spots and coverage are recomputed every time: they are
    # cheap, and coverage depends on whichever scans just ran (ADR 0004).
    inv = build(ws)
    for name, count in code_facts.write_all(ws, inv, tuple(excludes)).items():
        (warn if count else ok)(f"{name}: {count}")
    design = design_inventory.write(ws, inv, tuple(excludes))
    ok(
        f"design inventory: {design['colours']} colours, {design['tokens']} tokens, "
        f"{design['font_families']} font families ({design_inventory.MD_OUT})"
    )
    repo = gates.write_repository(ws, {e.path for e in inv.entries if e.kind == "file"})
    ran = [g.gate for g in repo.gates if g.target == "runs in CI"]
    ok(
        f"repository gates: target runs {', '.join(ran) or 'none'} in CI ({gates.MD_OUT})"
    )
    # Briefs carry the design inventory's rows, so they come after it.
    write_units(s, ws, inv, tuple(excludes))
    commit = loc.state.get("source_commit") or ""
    log, failure = None, ""
    if loc.state.get("mode") == "real" and commit:
        try:
            log = git(
                "log", "--numstat", "--no-renames", f"--format={history.RECORD}%ae",
                commit, "--", cwd=root, timeout=LONG,
            )  # fmt: skip
        except CommandError as exc:
            # A shallow clone or a rewritten history: record it, finish the scan.
            failure = f"git log failed ({exc})"
    own = {e.path for e in inv.of("own") if e.kind == "file"}
    hot = history.report(log, own, ws, commit, failure)
    ws.write_text(history.OUTPUT, json.dumps(hot, indent=1) + "\n")
    if "gap" in hot:
        skip(f"hotspots: {hot['gap']}")
        scanner.missing.append(f"hotspots: {hot['gap']}")
    else:
        ok(f"hotspots: {hot['commits']} commits, {len(hot['coupled'])} coupled pairs")

    def scancode(target: Path) -> None:
        args: list[str | Path] = [
            "scancode", "--info", "--classify", "--generated", "--strip-root",
            "--quiet", "--processes", "2",
        ]  # fmt: skip
        for folder in KIT_FOLDERS:
            args += ["--ignore", folder]
        run([*args, "--json-pp", target, "."], cwd=root, timeout=LONG)

    def syft(target: Path) -> None:
        config = SCANS / "syft-config.yaml"
        ws.write_text(config, SYFT_CONFIG)
        run(
            [
                "syft",
                "scan",
                "dir:.",
                "-q",
                "-c",
                root / config,
                "-o",
                f"syft-json={target}",
            ],
            cwd=root,
            timeout=LONG,
        )

    scanner("inventory-scancode", "scancode", "scancode.json", scancode)
    scanner("inventory-syft", "syft", "syft.json", syft)
    differences = cross_check_tools(ws)
    if differences:
        warn(
            f"{len(differences)} inventory difference(s) with ScanCode or Syft; see {CROSSCHECK}"
        )
    if s.drawio_dir.is_dir():
        scanner("drawio-shapes", "python3", "drawio-azure-shapes.json", shapes)
    else:
        skip("drawio shapes: drawio-skill not installed")
        scanner.missing.append("drawio-shapes: drawio-skill not installed")
    scanner.missing.append(
        "lint, typecheck, unused: HTML inline scripts are not checked (.js files only)"
    )
    if load_policy(ws).network.metadata_lookups != "allow":
        scanner.missing.append(LOOKUPS_DENIED)
    ws.write_text(MISSING, "\n".join(scanner.missing) + "\n")
    say(
        "Missing scans are listed in .audit/scans/MISSING.txt (agents report them as limitations)."
    )
    if checkpoint(root, "scans"):
        ok("checkpoint: scans")


def write_units(
    s: KitSettings, ws: Workspace, inv: Inventory, excluded: tuple[str, ...]
) -> None:
    """Write the file review's units (ADR 0002 D1) and their briefs (ADR 0007 D1)."""
    found, problems = units.build_units(ws, inv, excluded)
    ws.write_text(units.OUTPUT, units.render(found))
    sizes = review.prepare(ws, found, s.kit_home, s.version)
    if found:
        ok(
            f"briefs: {sizes.briefs}, {sizes.bytes // sizes.briefs:,} bytes on "
            f"average ({review.WORK}/<unit>/brief.md)"
        )
    for problem in problems:
        warn(problem)
    bands = {"<=100": 0, "101-300": 0, "301-1000": 0}
    for u in found:
        bands[
            "<=100" if u.lines <= 100 else "101-300" if u.lines <= 300 else "301-1000"
        ] += 1
    detail = ", ".join(f"{k} lines: {v}" for k, v in bands.items())
    ok(f"units: {len(found)} for the file review ({detail}); {units.OUTPUT}")


def refresh_units(s: KitSettings, given: str) -> None:
    """`kit units`: list the units and write their briefs, without re-running the scanners."""
    loc = locate(s, given)
    ws = loc.ws
    excludes = [
        *KIT_FOLDERS,
        *list_lines(ws.path(".audit/detected-excludes.txt")),
        *list_lines(loc.project / "scan-exclude.txt"),
    ]
    write_units(s, ws, build(ws), tuple(excludes))


def lookup(s: KitSettings, given: str) -> None:
    """Look up upstream status (deprecated, archived, end of life) if the policy allows."""
    loc = locate(s, given)
    ws = loc.ws
    ws.mkdir(SCANS)
    if load_policy(ws).network.metadata_lookups != "allow":
        ws.write_text(LOOKUPS, render([], allowed=False))
        skip("lookups: denied by .audit/policy.yaml (network.metadata_lookups: deny)")
        return
    statuses = look_up(ws)
    ws.write_text(LOOKUPS, render(statuses, allowed=True))
    counts = {
        r: sum(st.result == r for st in statuses)
        for r in ("archived", "deprecated", "unknown")
    }
    ok(
        f"lookups: {len(statuses)} results; {counts['archived']} archived, "
        f"{counts['deprecated']} deprecated, {counts['unknown']} unknown ({LOOKUPS})"
    )
    if checkpoint(ws.root, "lookups"):
        ok("checkpoint: lookups")


def _tool_files(ws: Workspace, rel: PurePosixPath, tool: str) -> dict[str, str] | None:
    """Return {path: sha256 or ""} from a ScanCode or Syft JSON file, or None."""
    if not ws.is_file(rel):
        return None
    try:
        raw = json.loads(ws.read_text(rel, limit=500_000_000))
    except json.JSONDecodeError:
        return None
    files = raw.get("files") if isinstance(raw, dict) else None
    found: dict[str, str] = {}
    for item in files if isinstance(files, list) else []:
        if not isinstance(item, dict):
            continue
        if tool == "scancode":
            if item.get("type") == "file" and isinstance(item.get("path"), str):
                found[item["path"]] = str(item.get("sha256") or "")
        else:
            location = item.get("location")
            path = location.get("path") if isinstance(location, dict) else None
            if isinstance(path, str):
                digests = item.get("digests") or []
                sha = next(
                    (str(d.get("value")) for d in digests
                     if isinstance(d, dict) and d.get("algorithm") == "sha256"),
                    "",
                )  # fmt: skip
                found[path.lstrip("/")] = sha
    return found


def cross_check_tools(ws: Workspace) -> list[str]:
    """Compare the inventory with ScanCode's and Syft's file lists, where present.

    Writes .audit/scans/inventory-crosscheck.txt when either tool ran.

    Returns:
        One line per path a tool saw that the inventory didn't, or the reverse,
        or whose sha256 differs.
    """
    if not ws.is_file(INVENTORY_PATH):
        return []
    entries = json.loads(ws.read_text(INVENTORY_PATH, limit=500_000_000)).get(
        "entries", []
    )
    ours = {e["path"]: e["sha256"] for e in entries if e.get("kind") == "file"}
    lines: list[str] = []
    ran = False
    for tool, rel in (
        ("scancode", SCANS / "scancode.json"),
        ("syft", SCANS / "syft.json"),
    ):
        theirs = _tool_files(ws, rel, tool)
        if theirs is None:
            continue
        ran = True
        theirs = {p: h for p, h in theirs.items() if p.split("/")[0] not in KIT_FOLDERS}
        lines += [
            f"{tool} saw, inventory lacks: {p}"
            for p in sorted(theirs.keys() - ours.keys())
        ]
        lines += [
            f"inventory has, {tool} didn't see: {p}"
            for p in sorted(ours.keys() - theirs.keys())
        ]
        lines += [
            f"sha256 differs ({tool}): {p}"
            for p in sorted(ours.keys() & theirs.keys())
            if theirs[p] and theirs[p] != ours[p]
        ]
    if ran:
        ws.write_text(
            CROSSCHECK, "".join(f"{line}\n" for line in lines) or "no differences\n"
        )
    return lines
