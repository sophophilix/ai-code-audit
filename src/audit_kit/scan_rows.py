"""Scan rows by file, read once for every brief (ADR 0007 D1).

Each scan file is tool output, so it's parsed by its format and validated
against a boundary model before any row is built. A file that doesn't match is
`unreadable`, which a brief and a gate report as such: never as a clean scan.
The models ignore fields the kit doesn't use, so gitleaks' matched text and
secret never enter memory, let alone a brief (AGENTS.md rule 6).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from audit_kit import code_facts
from audit_kit.errors import WorkspaceError
from audit_kit.units import Unit
from audit_kit.workspace import Workspace

SCAN_BYTES = 500_000_000
TSC_LINE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),\d+\): (?P<text>.*)$")


@dataclass(frozen=True)
class Source:
    """One scan a brief draws rows from."""

    name: str
    rel: PurePosixPath
    what: str


SOURCES = (
    Source("lint", PurePosixPath(".audit/scans/lint.json"), "ESLint, the kit's config"),
    Source(
        "typecheck",
        PurePosixPath(".audit/scans/typecheck.txt"),
        "tsc --checkJs, the kit's tsconfig",
    ),
    Source("sast", PurePosixPath(".audit/scans/sast.sarif"), "Semgrep"),
    Source(
        "sweep",
        PurePosixPath(".audit/scans/sweep.json"),
        "the kit's sweep for dangerous calls",
    ),
    Source("duplication", PurePosixPath(".audit/scans/duplication.json"), "jscpd"),
    Source(
        "similar",
        PurePosixPath(".audit/scans/similar.json"),
        "the kit's near-duplicate function check",
    ),
    Source(
        "suppressions",
        PurePosixPath(".audit/scans/suppressions.json"),
        "comments that switch checks off",
    ),
    Source(
        "blindspots",
        PurePosixPath(".audit/scans/blindspots.json"),
        "code static analysis can't see into",
    ),
    Source(
        "unused",
        PurePosixPath(".audit/scans/unused.json"),
        "the kit's unused-code analysis",
    ),
    Source(
        "knip", PurePosixPath(".audit/scans/dynamic/knip.json"), "knip, in the sandbox"
    ),
    Source(
        "secrets",
        PurePosixPath(".audit/scans/secrets.json"),
        "gitleaks; values are never shown",
    ),
    Source(
        "design",
        PurePosixPath(".audit/scans/design-inventory.json"),
        "contrast pairs from the design inventory",
    ),
)
NAMES = tuple(s.name for s in SOURCES)


class ScanStatus(StrEnum):
    """Whether a scan's rows can be used."""

    RAN = "ran"
    NOT_RUN = "not run"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Row:
    """One scan row about one file; a row without a line is about the whole file."""

    line: int | None
    text: str


# Boundary models. Line numbers from tools may arrive as strings; converting
# them is safe, so these models are lax. Unknown fields are ignored.
class _Scan(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _EslintMessage(_Scan):
    ruleId: str | None = None  # noqa: N815  ESLint's field name
    message: str = ""
    line: int | None = None


class _EslintResult(_Scan):
    filePath: str  # noqa: N815  ESLint's field name
    messages: list[_EslintMessage] = Field(default_factory=list)


class _SarifRegion(_Scan):
    startLine: int | None = None  # noqa: N815  SARIF's field name


class _SarifArtifact(_Scan):
    uri: str = ""


class _SarifPhysical(_Scan):
    artifactLocation: _SarifArtifact = Field(default_factory=_SarifArtifact)  # noqa: N815
    region: _SarifRegion = Field(default_factory=_SarifRegion)


class _SarifLocation(_Scan):
    physicalLocation: _SarifPhysical = Field(default_factory=_SarifPhysical)  # noqa: N815


class _SarifMessage(_Scan):
    text: str = ""


class _SarifResult(_Scan):
    ruleId: str = ""  # noqa: N815  SARIF's field name
    message: _SarifMessage = Field(default_factory=_SarifMessage)
    locations: list[_SarifLocation] = Field(default_factory=list)


class _SarifRun(_Scan):
    results: list[_SarifResult] = Field(default_factory=list)


class _SarifLog(_Scan):
    runs: list[_SarifRun] = Field(default_factory=list)


class _JscpdSide(_Scan):
    name: str
    start: int | None = None
    end: int | None = None


class _JscpdDuplicate(_Scan):
    lines: int | None = None
    firstFile: _JscpdSide  # noqa: N815  jscpd's field name
    secondFile: _JscpdSide  # noqa: N815  jscpd's field name


class _JscpdReport(_Scan):
    duplicates: list[_JscpdDuplicate] = Field(default_factory=list)


class _KitEntry(_Scan):
    file: str
    line: int | None = None
    kind: str = ""
    text: str = ""
    spec: str = ""
    directive: str = ""
    rules: list[str] = Field(default_factory=list)
    reason: str = ""


class _KitEntries(_Scan):
    entries: list[_KitEntry] = Field(default_factory=list)


class _Unreachable(_Scan):
    file: str
    required_by: list[str] = Field(default_factory=list)
    name_mentioned_in: list[str] = Field(default_factory=list)


class _NamedLine(_Scan):
    file: str
    name: str
    line: int | None = None


class _UnusedDependency(_Scan):
    name: str
    section: str = "dependencies"
    # Reports written before 0.18.0 have neither; the root manifest is the one read.
    file: str = "package.json"
    line: int | None = None


class _UnusedReport(_Scan):
    unreachable_files: list[_Unreachable] = Field(default_factory=list)
    unused_exports: list[_NamedLine] = Field(default_factory=list)
    unused_dependencies: list[_UnusedDependency] = Field(default_factory=list)
    undeclared_dependencies: list[_NamedLine] = Field(default_factory=list)


class _SimilarSide(_Scan):
    file: str
    name: str
    line: int | None = None


class _SimilarDifference(_Scan):
    first: str = ""
    second: str = ""


class _SimilarPair(_Scan):
    similarity: float
    first: _SimilarSide
    second: _SimilarSide
    differences: list[_SimilarDifference] = Field(default_factory=list)


class _SimilarReport(_Scan):
    pairs: list[_SimilarPair] = Field(default_factory=list)


class _KnipItem(_Scan):
    name: str = ""
    line: int | None = None


class _KnipIssue(BaseModel):
    # Knip adds issue types between releases, so they're kept and read as data.
    model_config = ConfigDict(extra="allow", frozen=True)

    file: str


class _KnipReport(_Scan):
    files: list[str] = Field(default_factory=list)
    issues: list[_KnipIssue] = Field(default_factory=list)


class _Leak(_Scan):
    File: str
    StartLine: int | None = None
    RuleID: str = "secret"
    Description: str = ""


class _ContrastPair(_Scan):
    selector: str = ""
    where: str
    text: str = ""
    background: str = ""
    ratio: float | None = None
    passes_text_4_5: bool = False
    other_values: bool = False


class _Unmeasured(_Scan):
    selector: str = ""
    where: str
    why: str = ""


class _DesignReport(_Scan):
    contrast_pairs: list[_ContrastPair] = Field(default_factory=list)
    unmeasured_pairs: list[_Unmeasured] = Field(default_factory=list)


_ESLINT = TypeAdapter(list[_EslintResult])
_LEAKS = TypeAdapter(list[_Leak])
_KNIP_ITEMS = TypeAdapter(list[_KnipItem])

Found = list[tuple[str, Row]]
Match = Callable[[str], str | None]


def _lint(text: str, match: Match) -> Found:
    found: Found = []
    for result in _ESLINT.validate_json(text):
        path = match(result.filePath)
        if path is None:
            continue
        for m in result.messages:
            found.append(
                (path, Row(m.line, f"{m.ruleId or 'parse error'}: {m.message}"))
            )
    return found


def _typecheck(text: str, match: Match) -> Found:
    found: Found = []
    current: str | None = None
    for line in text.splitlines():
        m = TSC_LINE.match(line)
        if m:
            current = match(m.group("file"))
            if current is not None:
                found.append((current, Row(int(m.group("line")), m.group("text"))))
        elif line.startswith(" ") and current is not None and found:
            # A continuation line belongs to the diagnostic above it.
            path, row = found[-1]
            found[-1] = (path, Row(row.line, f"{row.text} {line.strip()}"))
    return found


def _sarif(text: str, match: Match) -> Found:
    found: Found = []
    for run in _SarifLog.model_validate_json(text).runs:
        for result in run.results:
            for loc in result.locations[:1]:
                path = match(loc.physicalLocation.artifactLocation.uri)
                if path is not None:
                    row_text = f"{result.ruleId}: {result.message.text}".strip()
                    found.append(
                        (path, Row(loc.physicalLocation.region.startLine, row_text))
                    )
    return found


def _duplication(text: str, match: Match) -> Found:
    found: Found = []
    for d in _JscpdReport.model_validate_json(text).duplicates:
        for this, other in ((d.firstFile, d.secondFile), (d.secondFile, d.firstFile)):
            path = match(this.name)
            if path is not None:
                row_text = (
                    f"lines {this.start}-{this.end} repeat "
                    f"{other.name}:{other.start}-{other.end} ({d.lines} lines)"
                )
                found.append((path, Row(this.start, row_text)))
    return found


def _sweep(text: str, _match: Match) -> Found:
    entries = _KitEntries.model_validate_json(text).entries
    return [(e.file, Row(e.line, f"{e.kind}: {e.text}")) for e in entries]


def _suppressions(text: str, _match: Match) -> Found:
    entries = _KitEntries.model_validate_json(text).entries
    return [
        (
            e.file,
            Row(
                e.line,
                f"{e.directive} {', '.join(e.rules)}; reason: {e.reason or 'none'}",
            ),
        )
        for e in entries
    ]


def _blindspots(text: str, _match: Match) -> Found:
    entries = _KitEntries.model_validate_json(text).entries
    return [(e.file, Row(e.line, f"{e.kind}: {e.text or e.spec}")) for e in entries]


def _unused(text: str, _match: Match) -> Found:
    report = _UnusedReport.model_validate_json(text)
    found: Found = []
    for u in report.unreachable_files:
        required = ", ".join(u.required_by) or "nothing"
        mentioned = ", ".join(u.name_mentioned_in) or "nowhere"
        row_text = (
            "unreachable from every entry point; "
            f"required by {required}; name mentioned in {mentioned}"
        )
        found.append((u.file, Row(None, row_text)))
    for e in report.unused_exports:
        found.append(
            (e.file, Row(e.line, f"export `{e.name}` is used by no other own file"))
        )
    for d in report.unused_dependencies:
        found.append(
            (
                d.file,
                Row(
                    d.line,
                    f"`{d.name}` is declared in {d.section} but no own file requires "
                    "or imports it, and no script names it",
                ),
            )
        )
    for e in report.undeclared_dependencies:
        found.append(
            (e.file, Row(e.line, f"`{e.name}` is required but not in package.json"))
        )
    return found


def _similar(text: str, _match: Match) -> Found:
    found: Found = []
    for p in _SimilarReport.model_validate_json(text).pairs:
        for here, there, flip in (
            (p.first, p.second, False),
            (p.second, p.first, True),
        ):
            sides = [
                (d.second, d.first) if flip else (d.first, d.second)
                for d in p.differences
            ]
            diffs = "; ".join(
                f"`{mine or '(nothing)'}` here, `{theirs or '(nothing)'}` there"
                for mine, theirs in sides
            )
            found.append(
                (
                    here.file,
                    Row(
                        here.line,
                        f"`{here.name}` matches `{there.name}` at "
                        f"{there.file}:{there.line} ({p.similarity:.0%} of tokens); "
                        f"differs: {diffs or 'nothing but names'}",
                    ),
                )
            )
    return found


def _knip_items(value: object) -> list[_KnipItem]:
    """Flatten one knip issue type: a list, a list of lists, or a dict of lists."""
    if isinstance(value, dict):
        return [item for v in value.values() for item in _knip_items(v)]
    if isinstance(value, list) and value and all(isinstance(v, list) for v in value):
        return [item for v in value for item in _knip_items(v)]
    if isinstance(value, list):
        return _KNIP_ITEMS.validate_python(value)
    return []


def _knip(text: str, match: Match) -> Found:
    """Read knip's JSON reporter, which has listed unused files two ways."""
    report = _KnipReport.model_validate_json(text)
    found: Found = [
        (path, Row(None, "knip: unused file"))
        for name in report.files
        if (path := match(name)) is not None
    ]
    for issue in report.issues:
        path = match(issue.file)
        if path is None:
            continue
        for kind, value in sorted((issue.model_extra or {}).items()):
            if kind == "files" and value is True:
                found.append((path, Row(None, "knip: unused file")))
            elif kind != "owners":
                found += [
                    (path, Row(item.line, f"knip {kind}: {item.name}"))
                    for item in _knip_items(value)
                ]
    return found


def _secrets(text: str, match: Match) -> Found:
    return [
        (
            path,
            Row(leak.StartLine, f"{leak.RuleID}: {leak.Description} (value not shown)"),
        )
        for leak in _LEAKS.validate_json(text)
        if (path := match(leak.File)) is not None
    ]


def _where(where: str) -> tuple[str, int | None]:
    path, _, line = where.rpartition(":")
    return (path, int(line)) if line.isdigit() else (where, None)


def _design(text: str, _match: Match) -> Found:
    report = _DesignReport.model_validate_json(text)
    found: Found = []
    for p in report.contrast_pairs:
        path, line = _where(p.where)
        verdict = "passes" if p.passes_text_4_5 else "fails"
        themed = ", other theme values exist" if p.other_values else ""
        row_text = (
            f"`{p.selector}`: text {p.text} on {p.background}, "
            f"ratio {p.ratio} ({verdict} 4.5:1{themed})"
        )
        found.append((path, Row(line, row_text)))
    for u in report.unmeasured_pairs:
        path, line = _where(u.where)
        found.append(
            (path, Row(line, f"`{u.selector}`: not measurable from source: {u.why}"))
        )
    return found


_READERS: dict[str, Callable[[str, Match], Found]] = {
    "lint": _lint,
    "typecheck": _typecheck,
    "sast": _sarif,
    "sweep": _sweep,
    "duplication": _duplication,
    "similar": _similar,
    "suppressions": _suppressions,
    "blindspots": _blindspots,
    "unused": _unused,
    "knip": _knip,
    "secrets": _secrets,
    "design": _design,
}


@dataclass
class ScanIndex:
    """Every scan's rows by source and file, with whether each scan can be used."""

    rows: dict[str, dict[str, list[Row]]] = field(default_factory=dict)
    status: dict[str, ScanStatus] = field(default_factory=dict)
    problems: dict[str, str] = field(default_factory=dict)
    # Files a tool says it examined, for the tools that say (ESLint, tsc).
    examined: dict[str, frozenset[str]] = field(default_factory=dict)

    def of(self, source: str, path: str) -> list[Row]:
        """Return one source's rows about one file, in line order."""
        return self.rows.get(source, {}).get(path, [])

    def ran(self, source: str) -> bool:
        """Return True if a scan's rows can be used."""
        return self.status.get(source) is ScanStatus.RAN


def _matcher(ws: Workspace, wanted: set[str]) -> Match:
    """Map a path as a tool wrote it to a wanted relative path, or None."""
    cache: dict[str, str | None] = {}

    def match(name: str) -> str | None:
        if name not in cache:
            if name in wanted:
                cache[name] = name
            else:
                cache[name] = code_facts.match_tool_paths(ws.root, [name], wanted).get(
                    name
                )
        return cache[name]

    return match


def _examined(ws: Workspace, match: Match, index: ScanIndex) -> None:
    """Record the files ESLint and tsc say they examined.

    A tool whose list is missing or unreadable gets no entry, and the reason
    goes in `index.problems`, so its gates say why they can't judge a file.
    """
    lists = (("lint", code_facts.LINT), ("typecheck", code_facts.TSC_FILES))
    for source, rel in lists:
        if not ws.is_file(rel):
            index.problems[f"{source} examined list"] = f"{rel} not written"
            continue
        try:
            text = ws.read_text(rel, SCAN_BYTES)
            names = (
                [r.filePath for r in _ESLINT.validate_json(text)]
                if source == "lint"
                else text.splitlines()
            )
        except (WorkspaceError, ValidationError) as exc:
            index.problems[f"{source} examined list"] = f"{rel}: {type(exc).__name__}"
            continue
        index.examined[source] = frozenset(p for n in names if (p := match(n)))


def build_index(ws: Workspace, paths: set[str]) -> ScanIndex:
    """Read every scan file once and index its rows for the given files."""
    match = _matcher(ws, paths)
    index = ScanIndex()
    _examined(ws, match, index)
    for source in SOURCES:
        if not ws.is_file(source.rel) or not ws.size(source.rel):
            index.status[source.name] = ScanStatus.NOT_RUN
            continue
        try:
            found = _READERS[source.name](ws.read_text(source.rel, SCAN_BYTES), match)
        except (WorkspaceError, ValidationError, json.JSONDecodeError) as exc:
            index.status[source.name] = ScanStatus.UNREADABLE
            index.problems[source.name] = type(exc).__name__
            continue
        index.status[source.name] = ScanStatus.RAN
        by_file: dict[str, list[Row]] = {}
        for path, row in found:
            if path in paths:
                by_file.setdefault(path, []).append(row)
        index.rows[source.name] = {
            p: sorted(rows, key=lambda r: (r.line or 0, r.text))
            for p, rows in by_file.items()
        }
    return index


@dataclass(frozen=True)
class UnitRows:
    """One source's rows for a unit, and how many the file has outside it."""

    inside: list[Row]
    elsewhere: int


def unit_rows(index: ScanIndex, unit: Unit) -> dict[str, UnitRows]:
    """Return each source's rows for a unit.

    A row is the unit's when its line is in the unit, or when it has no line
    (it's about the whole file).
    """
    out: dict[str, UnitRows] = {}
    for name in NAMES:
        rows = index.of(name, unit.path)
        inside = [r for r in rows if r.line is None or unit.start <= r.line <= unit.end]
        out[name] = UnitRows(inside, len(rows) - len(inside))
    return out
