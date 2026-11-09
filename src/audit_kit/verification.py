"""Automated output checks for an audit workspace (see evals/output-checks.md).

Covers the checks a script can decide; the rest stay with the tech lead.
Agent outputs are AI-written and treated as untrusted: file locations they cite
are resolved through the confined workspace (architecture constraint C2).
"""

from __future__ import annotations

import csv
import io
import json
import posixpath
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, ValidationError

from audit_kit import brief, search
from audit_kit.detection import loaded_profiles
from audit_kit.errors import OutsideWorkspaceError, WorkspaceError
from audit_kit.findings import HEADING, ID_RE, Finding, parse_findings
from audit_kit.lookups import OUTPUT as LOOKUPS
from audit_kit.lookups import recommended_packages
from audit_kit.runner import CommandError, run
from audit_kit.units import OUTPUT as UNITS
from audit_kit.units import Unit
from audit_kit.units import parse as parse_units
from audit_kit.workspace import Workspace

LOCATION = re.compile(r"^([^\s:]+?)(?::(\d+)(?:-(\d+))?)?(?:\s|$)")
KEY_OK = re.compile(r"^(?:X-[a-z0-9-]+|[A-Z][A-Z0-9.]*(?:-[A-Z0-9.]+)*):\S")
VERDICT_LINE = re.compile(r"\bverdict:\s*rejected\b", re.I)
REQUIRED = ("Key", "Category", "Severity", "Confidence", "Location", "Evidence")
CSV_HEADER = [
    "Work Item Type",
    "Title",
    "Description",
    "Acceptance Criteria",
    "Priority",
    "Tags",
]
VAGUE_ALT = frozenset({"", "diagram", "image", "picture", "figure", "screenshot"})
# A masked secret or an ellipsis splits an excerpt into pieces matched in order.
EXCERPT_GAP = re.compile(r"\*{3,}|\.\.\.|\u2026")
CELL_LOCATION = re.compile(r"([\w@.\-/]+\.[\w]+):(\d+)(?:-(\d+))?")
SEARCHED = re.compile(r"^`(?P<pattern>[^`]+)`\s+in\s+(?P<paths>.+)$")
SEARCHED_LINE = re.compile(r"^\s*- Searched: ?(.*)$")
# Agent-written patterns run over target files. Nested quantifiers are refused
# up front; anything else that backtracks badly hits SEARCH_SECONDS.
NESTED_QUANTIFIER = re.compile(r"\([^()]*[+*][^()]*\)[+*{]")
# Each search runs in its own process (audit_kit.search) with this time limit.
SEARCH_SECONDS = 30.0
RECORD_SECTIONS = (
    "Summary",
    "Facts",
    "Comments versus code",
    "Sources and sinks",
    "Functions",
    "Gates",
    "Findings",
    "Open edges",
    "Checks",
    "Limitations",
)
PILOT = ".audit/work/files/pilot.txt"


class Status(StrEnum):
    """Outcome of one check."""

    # A status label, not a credential (Ruff S105 and Bandit B105 false positive).
    PASS = "PASS"  # noqa: S105  # nosec B105
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Result:
    """One check outcome."""

    status: Status
    check: str
    detail: str

    def line(self) -> str:
        """Render as one aligned output line."""
        return f"{self.status.value:4}  {self.check:7} {self.detail}".rstrip()


@dataclass
class Report:
    """Collected results."""

    results: list[Result] = field(default_factory=list)

    def add(self, check: str, ok: bool, detail: str) -> None:
        """Record a pass or fail."""
        self.results.append(Result(Status.PASS if ok else Status.FAIL, check, detail))

    def skip(self, check: str, detail: str) -> None:
        """Record a check that couldn't run yet."""
        self.results.append(Result(Status.SKIP, check, detail))

    @property
    def failed(self) -> int:
        """Return the number of failed checks."""
        return sum(r.status is Status.FAIL for r in self.results)


def parse_header(text: str) -> dict[str, str]:
    """Parse the provenance header between the leading `---` lines."""
    match = re.match(r"^---\n(.*?)\n---", text, re.S)
    values: dict[str, str] = {}
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key.strip()] = value.split("#", 1)[0].strip()
    return values


def location_exists(ws: Workspace, location: str) -> bool:
    """Return True if a `file[:line[-line]]` location exists inside the workspace."""
    match = LOCATION.match(location)
    if not match:
        return False
    rel = PurePosixPath(match.group(1))
    if not ws.is_file(rel):
        return False
    if not match.group(2):
        return True
    last = int(match.group(3) or match.group(2))
    try:
        lines = ws.read_text(rel, limit=50_000_000).count("\n") + 1
    except WorkspaceError:
        return False
    return last <= lines


def _squash(text: str) -> str:
    return " ".join(text.split())


def excerpt_problem(
    ws: Workspace,
    location: str,
    excerpt: str,
    lines_of: Callable[[str], list[str] | None] | None = None,
) -> str | None:
    """Return why an excerpt doesn't match its cited lines, or None if it does.

    Whitespace is collapsed on both sides, and a masked secret (`****`) or an
    ellipsis splits the excerpt into pieces that must appear in order. A location
    without a line number needs no excerpt (ADR 0004 D1).

    Args:
        ws: The workspace the location is resolved in.
        location: The finding's `file[:line[-line]]`.
        excerpt: The quoted text, usually in backticks.
        lines_of: Returns a file's lines, or None if unreadable; pass a cached
            reader when checking many excerpts.
    """
    match = LOCATION.match(location)
    if not match or not match.group(2):
        return None
    quoted = re.findall(r"`([^`]+)`", excerpt) or [excerpt]
    pieces = [_squash(p) for q in quoted for p in EXCERPT_GAP.split(q) if _squash(p)]
    if not pieces:
        return "no excerpt"
    first = int(match.group(2))
    last = int(match.group(3) or first)
    lines = (lines_of or _Lines(ws))(match.group(1))
    if lines is None:
        return "cited file not readable"
    cited = _squash("\n".join(lines[first - 1 : last]))
    at = 0
    for piece in pieces:
        found = cited.find(piece, at)
        if found < 0:
            return f"not at {match.group(0).strip()}: {piece[:60]!r}"
        at = found + len(piece)
    return None


class _Lines:
    """A file's lines, read once per check run however many findings cite it."""

    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._cache: dict[str, list[str] | None] = {}

    def __call__(self, rel: str) -> list[str] | None:
        if rel not in self._cache:
            try:
                text = self.ws.read_text(rel, limit=50_000_000)
                self._cache[rel] = text.splitlines()
            except WorkspaceError:
                self._cache[rel] = None
        return self._cache[rel]


class Searcher:
    """Re-runs the searches behind "not found" claims (ADR 0004 D6)."""

    def __init__(self, ws: Workspace) -> None:
        """Search within one workspace, reading each file once."""
        self.ws = ws
        self.lines = _Lines(ws)

    def problem(self, value: str) -> str | None:
        """Return why a `- Searched:` value fails, or None if nothing matches."""
        m = SEARCHED.match(value.strip())
        if not m:
            return "not in the form `pattern` in `paths`"
        pattern = m.group("pattern")
        if len(pattern) > 300 or NESTED_QUANTIFIER.search(pattern):
            return "pattern refused (over 300 characters or a nested quantifier)"
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"invalid pattern ({exc})"
        spans = re.findall(r"`([^`]+)`", m.group("paths")) or [m.group("paths")]
        paths = [
            posixpath.normpath(p)
            for span in spans
            for p in re.split(r"[\s,]+", span)
            if p.strip()
        ]
        for path in paths:
            try:
                self.ws.path(path)
            except OutsideWorkspaceError:
                return f"path outside the workspace: {path}"
            if not self.ws.exists(path):
                return f"path not found: {path}"
        try:
            result = run(
                [sys.executable, "-I", "-m", "audit_kit.search",
                 self.ws.root, pattern, *paths],
                timeout=SEARCH_SECONDS,
                check=False,
            )  # fmt: skip
        except CommandError:
            return f"search took over {SEARCH_SECONDS:.0f} s; use a simpler pattern"
        if result.code == search.LIMIT_REACHED:
            return "search stopped after 200 million characters; name fewer paths"
        if result.code != search.FOUND_OR_NONE:
            # A crash must fail the claim; empty output from a failed process
            # would otherwise read as "nothing found".
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            return f"search failed (exit {result.code}): {detail[-200:]}"
        return f"matches at {result.text}" if result.text else None


def _check_searches(name: str, text: str, searcher: Searcher, report: Report) -> None:
    owner, bad, count = f"{name}", [], 0
    for number, line in enumerate(text.splitlines(), 1):
        heading = HEADING.match(line)
        if heading:
            owner = heading.group(1)
        searched = SEARCHED_LINE.match(line)
        if searched:
            count += 1
            problem = searcher.problem(searched.group(1))
            if problem:
                bad.append(f"{owner} (line {number}): {problem}")
    if count:
        report.add(
            "OUT-F8",
            not bad,
            f"{name}: {count} searches re-run"
            + (f"; failed: {'; '.join(bad[:3])}" if bad else ", none matched"),
        )


def _cells(row: str) -> list[str]:
    parts = re.split(r"(?<!\\)\|", row.strip().strip("|"))
    return [p.replace("\\|", "|").strip() for p in parts]


def _check_discovery_tables(
    ws: Workspace, text: str, report: Report, searcher: Searcher
) -> None:
    """Check the Excerpt column of discovery's tables against the cited lines."""
    lines = text.splitlines()
    column: int | None = None
    checked, bad = 0, []
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            column = None
            continue
        following = lines[i + 1] if i + 1 < len(lines) else ""
        if re.match(r"^\s*\|[\s:|-]+\|?\s*$", following):
            heads = [c.lower() for c in _cells(line)]
            column = heads.index("excerpt") if "excerpt" in heads else None
            continue
        if column is None or re.match(r"^\s*\|[\s:|-]+\|?\s*$", line):
            continue
        cells = _cells(line)
        excerpt = cells[column] if column < len(cells) else ""
        location = next(
            (
                m.group(0)
                for c in cells[:column] + cells[column + 1 :]
                for m in CELL_LOCATION.finditer(c)
                if ws.is_file(m.group(1))
            ),
            None,
        )
        if location is None:
            continue
        checked += 1
        problem = excerpt_problem(ws, location, excerpt, searcher.lines)
        if problem:
            bad.append(f"line {i + 1}: {problem}")
    if checked:
        report.add(
            "OUT-F10",
            not bad,
            f"01-discovery.md: {checked} table excerpts"
            + (f"; failed: {'; '.join(bad[:3])}" if bad else " match"),
        )


def rejected_ids(verification: str) -> set[str]:
    """Return IDs whose verdict is exactly Rejected.

    A table row counts when one of its cells is exactly `Rejected`; a block counts
    when it has a `Verdict: Rejected` line. A note that merely mentions the word
    doesn't count.
    """
    rejected: set[str] = set()
    block: list[str] = []
    for line in verification.splitlines():
        if line.startswith("#"):
            block = re.findall(ID_RE, line)
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if "rejected" in cells:
            rejected.update(re.findall(ID_RE, line))
        elif VERDICT_LINE.search(line):
            rejected.update(re.findall(ID_RE, line) or block)
    return rejected


def _check_findings_file(
    ws: Workspace, name: str, text: str, report: Report, searcher: Searcher
) -> list[Finding]:
    header = parse_header(text)
    missing = [k for k in ("agent", "model", "commit", "status") if not header.get(k)]
    report.add(
        "OUT-F5",
        not missing,
        f"{name}: provenance" + (f" missing {missing}" if missing else ""),
    )
    report.add(
        "OUT-P5",
        header.get("status") == "complete",
        f"{name}: status {header.get('status') or 'missing'}",
    )
    found = parse_findings(text)
    incomplete = [
        f"{f.id} ({', '.join(k for k in REQUIRED if not f.get(k))})"
        for f in found
        if any(not f.get(k) for k in REQUIRED)
    ]
    report.add(
        "OUT-F1",
        not incomplete,
        f"{name}: {len(found)} findings"
        + (f"; incomplete: {'; '.join(incomplete[:5])}" if incomplete else ""),
    )
    bad_keys = [f.id for f in found if f.get("Key") and not KEY_OK.match(f.get("Key"))]
    report.add(
        "OUT-F2",
        not bad_keys,
        f"{name}: key format" + (f" wrong in {bad_keys[:5]}" if bad_keys else ""),
    )
    keys = [f.get("Key") for f in found if f.get("Key")]
    dup_keys = sorted({k for k in keys if keys.count(k) > 1})
    report.add(
        "OUT-F3",
        not dup_keys,
        f"{name}: duplicate keys" + (f" {dup_keys[:5]}" if dup_keys else " none"),
    )
    bad_loc = [
        f.id
        for f in found
        if f.get("Location") and not location_exists(ws, f.get("Location"))
    ]
    report.add(
        "OUT-F4",
        not bad_loc,
        f"{name}: locations" + (f" not found: {bad_loc[:5]}" if bad_loc else " exist"),
    )
    wrong = [
        f"{f.id}: {problem}"
        for f in found
        if f.get("Location")
        and (
            problem := excerpt_problem(
                ws, f.get("Location"), f.get("Excerpt"), searcher.lines
            )
        )
    ]
    report.add(
        "OUT-F7",
        not wrong,
        f"{name}: excerpts"
        + (f" wrong: {'; '.join(wrong[:3])}" if wrong else " match"),
    )
    untriggered = [
        f.id
        for f in found
        if f.get("Severity").lower() in ("critical", "high") and not f.get("Trigger")
    ]
    report.add(
        "OUT-F9",
        not untriggered,
        f"{name}: critical/high triggers"
        + (f" missing on {untriggered[:5]}" if untriggered else " present"),
    )
    _check_searches(name, text, searcher, report)
    ids = [f.id for f in found]
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    if dup_ids:
        report.add("OUT-P7", False, f"{name}: duplicate IDs {dup_ids[:5]}")
    return found


def check(ws: Workspace) -> Report:
    """Run every automated output check on a workspace's `.audit/` folder."""
    report = Report()
    audit = ws.root / ".audit"
    if not audit.is_dir():
        report.add("setup", False, f"{audit} not found")
        return report

    findings: dict[str, Finding] = {}
    names = sorted(p.name for p in audit.glob("0[1-5]-*.md"))
    if not names:
        report.skip("OUT-F*", "no findings files (01-05) yet")
    searcher = Searcher(ws)
    for name in names:
        text = ws.read_text(f".audit/{name}", limit=50_000_000)
        for f in _check_findings_file(ws, name, text, report, searcher):
            findings[f.id] = f
        if name == "01-discovery.md":
            _check_discovery_tables(ws, text, report, searcher)

    active = sorted(
        p.relative_to(audit).as_posix()
        for p in audit.glob("work/*/LOCK")
        if "state: active"
        in ws.read_text(PurePosixPath(".audit") / p.relative_to(audit))
    )
    report.add(
        "OUT-P5",
        not active,
        "locks: " + (f"still active {active}" if active else "none active"),
    )

    high = sorted(
        i
        for i, f in findings.items()
        if f.get("Severity").lower() in ("critical", "high")
    )
    rejected: set[str] = set()
    if ws.is_file(".audit/06-verification.md"):
        vtext = ws.read_text(".audit/06-verification.md", limit=50_000_000)
        missing = [i for i in high if not re.search(rf"\b{re.escape(i)}\b", vtext)]
        report.add(
            "OUT-V1",
            not missing,
            f"critical/high with a verdict: {len(high) - len(missing)}/{len(high)}"
            + (f"; missing {missing[:5]}" if missing else ""),
        )
        rejected = rejected_ids(vtext)
    else:
        report.skip("OUT-V1", "no 06-verification.md yet")

    for name in ("07-final-report.md", "09-briefing.slides.md"):
        rel = f".audit/{name}"
        if not ws.is_file(rel):
            report.skip("OUT-R1", f"no {name} yet")
            continue
        text = ws.read_text(rel, limit=50_000_000)
        mentioned = set(re.findall(ID_RE, text))
        unknown = sorted(mentioned - set(findings))
        report.add(
            "OUT-R1",
            not unknown,
            f"{name}: {len(mentioned)} IDs mentioned"
            + (f"; unknown {unknown[:5]}" if unknown else ""),
        )
        if name.startswith("07"):
            section = re.search(r"^#+ .*\bnot examined\b", text, re.I | re.M)
            report.add(
                "OUT-R11",
                bool(section),
                "report: 'Not examined' section"
                + (" present" if section else " missing (ADR 0004 D3)"),
            )
            if _has_user_interface(ws):
                by_hand = re.search(
                    r"^#+ .*\bstill to check by hand\b", text, re.I | re.M
                )
                report.add(
                    "OUT-R13",
                    bool(by_hand),
                    "report: 'Still to check by hand' section"
                    + (" present" if by_hand else " missing (the target has a UI)"),
                )
            absent = [i for i in high if i not in rejected and i not in mentioned]
            report.add(
                "OUT-R2",
                not absent,
                "critical/high in report"
                + (f"; missing {absent[:5]}" if absent else ": all present"),
            )
        alts = re.findall(r"!\[([^\]]*)\]\(", text)
        vague = [a for a in alts if a.strip().lower() in VAGUE_ALT]
        report.add(
            "OUT-R6",
            not vague,
            f"{name}: {len(alts)} images"
            + (f"; {len(vague)} without meaningful alt text" if vague else ""),
        )

    for f in _check_file_review(ws, report, searcher):
        findings[f.id] = f
    _check_recommended(ws, report)
    _check_backlog(ws, report)
    _check_diagrams(ws, report)
    return report


def _summarise(report: Report, where: str, sub: Report, files: int) -> None:
    """Fold per-file results into one line per check, so 100 records stay readable."""
    by_check: dict[str, list[Result]] = {}
    for r in sub.results:
        by_check.setdefault(r.check, []).append(r)
    for check_id, results in sorted(by_check.items()):
        bad = [r.detail for r in results if r.status is Status.FAIL]
        report.add(
            check_id,
            not bad,
            f"{where}: {files} files"
            + (
                f"; failed in {len(bad)}: {'; '.join(bad[:3])}" if bad else ", all pass"
            ),
        )


def _check_file_review(
    ws: Workspace, report: Report, searcher: Searcher
) -> list[Finding]:
    """Check file records (ADR 0002 D4) and traces (D6) like any findings file.

    A record may cite only its own unit's file and lines (D1), has fixed sections,
    and every unit (or every pilot unit) needs one.
    """
    found: list[Finding] = []
    records = (
        sorted((ws.root / ".audit/files").rglob("*.md"))
        if ws.exists(".audit/files")
        else []
    )
    traces = (
        sorted((ws.root / ".audit/traces").glob("*.md"))
        if ws.exists(".audit/traces")
        else []
    )
    if not records and not traces:
        return found
    units = (
        {u.record: u for u in parse_units(ws.read_text(UNITS))}
        if ws.is_file(UNITS)
        else {}
    )
    sub, shape = Report(), Report()
    for path in records:
        rel = path.relative_to(ws.root).as_posix()
        name = rel.removeprefix(".audit/")
        try:
            text = ws.read_text(rel, limit=50_000_000)
        except WorkspaceError as exc:
            # Records are agent output: a symlink or unreadable file fails a
            # check instead of stopping kit verify.
            shape.add("OUT-U1", False, f"{name}: not read ({exc})")
            continue
        blocks = _check_findings_file(ws, name, text, sub, searcher)
        found += blocks
        missing = [
            h
            for h in RECORD_SECTIONS
            if not re.search(rf"^## {re.escape(h)}\b", text, re.M)
        ]
        shape.add(
            "OUT-U1", not missing, f"{name}" + (f" lacks {missing}" if missing else "")
        )
        unit = units.get(rel)
        if unit is None:
            shape.add("OUT-U2", False, f"{name}: not a unit in units.tsv")
            continue
        outside = []
        for f in blocks:
            m = LOCATION.match(f.get("Location"))
            if not m:
                continue
            first = int(m.group(2) or unit.start)
            last = int(m.group(3) or first)
            if m.group(1) != unit.path or first < unit.start or last > unit.end:
                outside.append(f.id)
        shape.add(
            "OUT-U2",
            not outside,
            f"{name}" + (f" cites outside its unit: {outside[:5]}" if outside else ""),
        )
        shape.add("OUT-U4", *_edge_rules(name, unit, blocks))
        # Records from before 0.17.0 have no JSON and no brief to compare.
        record_json = rel.removesuffix(".md") + ".json"
        if ws.is_file(record_json):
            wrong = _brief_count_problems(ws, unit, record_json)
            shape.add(
                "OUT-U5",
                not wrong,
                f"{name}" + (f": {'; '.join(wrong[:3])}" if wrong else ""),
            )
    _summarise(report, "files/", shape, len(records))
    _summarise(report, "files/", sub, len(records))
    if units:
        wanted = set(units)
        if ws.is_file(PILOT):
            pilot = set(ws.read_text(PILOT).split())
            wanted = {r for r, u in units.items() if u.id in pilot}
        have = {p.relative_to(ws.root).as_posix() for p in records}
        missing_units = sorted(units[r].id for r in wanted - have)
        report.add(
            "OUT-U3",
            not missing_units,
            f"file records: {len(wanted & have)}/{len(wanted)} units"
            + (" (pilot)" if ws.is_file(PILOT) else "")
            + (f"; missing {missing_units[:5]}" if missing_units else ""),
        )
    if traces:
        tsub = Report()
        for path in traces:
            rel = path.relative_to(ws.root).as_posix()
            name = rel.removeprefix(".audit/")
            try:
                text = ws.read_text(rel, limit=50_000_000)
            except WorkspaceError as exc:
                tsub.add("OUT-F1", False, f"{name}: not read ({exc})")
                continue
            found += _check_findings_file(ws, name, text, tsub, searcher)
        _summarise(report, "traces/", tsub, len(traces))
    return found


def _edge_rules(name: str, unit: Unit, blocks: list[Finding]) -> tuple[bool, str]:
    """Check OUT-U4 on a record's findings, and return (passed, detail).

    Critical or High needs no open edge and must be verified, and a finding
    with an open edge is unverified (ADR 0002 D3, ADR 0007).
    """
    wrong: list[str] = []
    for f in blocks:
        high = f.get("Severity").lower() in ("critical", "high")
        edged = f"EDGE-{unit.id}-" in f.get("Related")
        verification = f.get("Verification").lower()
        if high and edged:
            wrong.append(f"{f.id} rates High on an open edge")
        if high and verification == "unverified":
            wrong.append(f"{f.id} rates High but is unverified")
        if edged and verification == "verified":
            wrong.append(f"{f.id} is verified but depends on an open edge")
    detail = f"{name}: {'; '.join(wrong[:3])}" if wrong else name
    return not wrong, detail


class _RecordCounts(BaseModel):
    """The one field of a JSON record that OUT-U5 reads."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    scan_rows: dict[str, int]


def _brief_count_problems(ws: Workspace, unit: Unit, record_json: str) -> list[str]:
    """OUT-U5: the brief shows every scan row it counts, and the record agrees."""
    brief_md, _ = brief.brief_paths(unit.id)
    if not ws.is_file(brief_md):
        return [f"no brief at {brief_md}"]
    text = ws.read_text(brief_md, limit=50_000_000)
    table = brief.parse_scan_table(text)
    shown = brief.count_rendered_rows(text)
    wrong = [
        f"{s}: table {n}, shown {shown[s]}" for s, n in table.items() if shown[s] != n
    ]
    try:
        kept = _RecordCounts.model_validate_json(
            ws.read_text(record_json, limit=50_000_000)
        ).scan_rows
    except ValidationError:
        return [*wrong, f"{record_json} has no scan_rows"]
    return wrong + [
        f"{s}: brief {n}, record {kept.get(s)}"
        for s, n in table.items()
        if kept.get(s) != n
    ]


def _check_recommended(ws: Workspace, report: Report) -> None:
    """OUT-R12: every package a finding recommends was looked up and exists."""
    wanted = recommended_packages(ws)
    if not wanted:
        return
    if not ws.is_file(LOOKUPS):
        report.add(
            "OUT-R12", False, f"{len(wanted)} recommended packages; run kit lookup"
        )
        return
    data = json.loads(ws.read_text(LOOKUPS, limit=50_000_000))
    if data.get("policy") != "allow":
        report.skip(
            "OUT-R12",
            f"{len(wanted)} recommended packages not checked (lookups denied); "
            "the report must mark them 'not checked'",
        )
        return
    seen = {
        r.get("subject"): r.get("result")
        for r in data.get("results", [])
        if r.get("check") == "recommended package"
        and r.get("result") != "prefer built-in"
    }
    unchecked = [p for p in wanted if p not in seen]
    bad = [
        f"{p} ({seen[p]})" for p in wanted if seen.get(p) in ("not found", "deprecated")
    ]
    report.add(
        "OUT-R12",
        not unchecked and not bad,
        f"{len(wanted)} recommended packages"
        + (f"; not looked up {unchecked[:5]}" if unchecked else "")
        + (f"; remove or replace {bad[:5]}" if bad else ""),
    )


def _has_user_interface(ws: Workspace) -> bool:
    """True when web-accessibility is in detected.md's "Profiles to load".

    That line, not the detection table, includes the intake's overrides.
    """
    rel = ".audit/detected.md"
    return ws.is_file(rel) and "web-accessibility" in loaded_profiles(ws.read_text(rel))


def _check_backlog(ws: Workspace, report: Report) -> None:
    rel = ".audit/08-backlog.csv"
    if not ws.is_file(rel):
        report.skip("OUT-B1", "no 08-backlog.csv yet")
        return
    rows = list(
        csv.reader(io.StringIO(ws.read_text(rel, limit=50_000_000), newline=""))
    )
    if not rows or rows[0] != CSV_HEADER:
        report.add("OUT-B1", False, f"header is {rows[0] if rows else 'empty'}")
        return
    bad = [
        i + 2
        for i, row in enumerate(rows[1:])
        if len(row) != len(CSV_HEADER) or row[4] not in ("1", "2", "3", "4")
    ]
    report.add(
        "OUT-B1",
        not bad,
        f"{len(rows) - 1} rows" + (f"; bad rows {bad[:5]}" if bad else ""),
    )
    no_ac = [
        i + 2
        for i, row in enumerate(rows[1:])
        if len(row) == len(CSV_HEADER) and not row[3].strip()
    ]
    report.add(
        "OUT-B3",
        not no_ac,
        "acceptance criteria"
        + (f" missing on rows {no_ac[:5]}" if no_ac else " present"),
    )


def _check_diagrams(ws: Workspace, report: Report) -> None:
    irs = sorted((ws.root / ".audit" / "diagrams").glob("*.ir.json"))
    if not irs:
        report.skip("OUT-D*", "no diagram IR yet")
    for path in irs:
        rel = f".audit/diagrams/{path.name}"
        try:
            data = json.loads(ws.read_text(rel, limit=50_000_000))
        except json.JSONDecodeError as exc:
            report.add("OUT-D", False, f"{path.name}: invalid JSON ({exc.msg})")
            continue
        nodes = data.get("nodes", []) if isinstance(data, dict) else []
        nodes = [n for n in nodes if isinstance(n, dict)]
        legacy = [
            n.get("id") for n in nodes if "mxgraph.azure." in str(n.get("style") or "")
        ]
        report.add(
            "OUT-D4",
            not legacy,
            f"{path.name}: icons"
            + (f" legacy mxgraph.azure on {legacy[:5]}" if legacy else " ok"),
        )
        without = [n.get("id") for n in nodes if not n.get("provenance")]
        report.add(
            "OUT-D3",
            not without,
            f"{path.name}: provenance on {len(nodes) - len(without)}/{len(nodes)} nodes",
        )
