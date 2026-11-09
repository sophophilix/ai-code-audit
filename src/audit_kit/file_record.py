"""A unit pass's JSON output: its schema, its checks, and the record built from it.

ADR 0007 D3. The pass returns one JSON object. The kit validates it against
`config/file-record.schema.json`, runs the record checks (OUT-F1 to F4, F7 to
F9, U2, U4), and only then writes `.audit/files/<path>[#<part>].json` and
renders the Markdown record beside it. IDs, the provenance header, the gate
table and missing Evidence lines are the kit's, so a pass can't get them wrong.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from audit_kit.brief import BriefMeta
from audit_kit.errors import AuditKitError, WorkspaceError
from audit_kit.gates import Gate, render_table
from audit_kit.units import Unit
from audit_kit.verification import (
    KEY_OK,
    LOCATION,
    Searcher,
    excerpt_problem,
    location_exists,
)
from audit_kit.workspace import Workspace

SCHEMA_PATH = "config/file-record.schema.json"
CITED_CHARS = 400
SHOWN = 12
RECORD_VERSION = 1
Severity = Literal["critical", "high", "medium", "low", "info"]
SEVERITIES: tuple[Severity, ...] = ("critical", "high", "medium", "low", "info")
Verification = Literal["verified", "unverified"]
Level = Literal["high", "medium", "low"]
Category = Literal[
    "security",
    "privacy",
    "compliance",
    "reliability",
    "maintainability",
    "operations",
    "performance",
    "cost",
    "accessibility",
    "architecture",
    "testing",
    "governance",
]
FactKind = Literal[
    "export", "import", "route", "environment", "state", "timer", "outbound", "other"
]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Fact(_Out):
    """An export, import, route, environment read, state, timer or outbound call."""

    kind: FactKind
    name: str = Field(min_length=1)
    location: str = Field(min_length=1, description="file:line in this unit")
    excerpt: str = Field(min_length=1, description="copied verbatim from the line")


class Comment(_Out):
    """A comment that claims what the code does, checked against the code."""

    claim: str = Field(min_length=1)
    location: str = Field(min_length=1, description="file:line of the comment")
    excerpt: str = Field(min_length=1, description="the comment, copied verbatim")
    code_lines: str = Field(description="the lines the claim is about, e.g. 40-52")
    verdict: Literal["agrees", "disagrees", "not shown here"]


class Flow(_Out):
    """A path from untrusted input to a sink, within this unit."""

    source: str = Field(min_length=1, description="file:line where the input enters")
    source_excerpt: str = Field(min_length=1)
    sink: str = Field(min_length=1, description="file:line of the sink")
    sink_excerpt: str = Field(min_length=1)
    validation: str = Field(
        description="file:line of validation or encoding, or 'none in this file'"
    )
    cwe: str = Field(pattern=r"^CWE-\d+$")


class Function(_Out):
    """One function, with its complexity hypothesis (ADR 0002 D5)."""

    name: str = Field(min_length=1)
    lines: str = Field(pattern=r"^\d+-\d+$")
    complexity: int | None = Field(
        description="from the lint rows, or null if not scanned"
    )
    n: str = Field(description="what n is, or 'none'")
    controlled_by: Literal["attacker", "user", "nobody", "not applicable"]
    growth: str = Field(description="growth class, e.g. O(n), O(n^2), constant")
    growth_lines: str = Field(description="the lines that cause the growth, or 'none'")
    runs_on: Literal["request", "start-up", "timer", "event", "other", "unknown"]
    confidence: Level


class Finding(_Out):
    """A finding in the audit-findings format; the kit assigns its ID."""

    key: str = Field(min_length=1, description="<CHECK-ID>:<this unit's file>")
    title: str = Field(min_length=1)
    category: Category
    severity: Severity
    confidence: Level
    verification: Verification = Field(
        description=(
            "verified: this unit's code and scan rows show everything the finding "
            "claims; unverified: it depends on another file, a rendered page or a "
            "scan that didn't run"
        )
    )
    location: str = Field(min_length=1, description="file:line or file:start-end")
    excerpt: str = Field(min_length=1, description="1-3 lines copied verbatim")
    trigger: str = Field(default="", description="required for critical and high")
    evidence: str = Field(
        default="", description="built from location and excerpt if empty"
    )
    description: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    sources: str = Field(
        min_length=1, description="official URLs, or 'none \u2013 reviewer judgement'"
    )
    effort: Literal["S", "M", "L"]
    searched: list[str] = Field(
        default_factory=list,
        description="`<regex>` in `<paths>`, for a claim of absence",
    )
    packages: list[str] = Field(default_factory=list)
    related: str = ""
    edges: list[int] = Field(
        default_factory=list,
        description="numbers (from 1) of the open edges it depends on",
    )


class Edge(_Out):
    """A question only another file can answer."""

    question: str = Field(min_length=1, description="one line, used as the heading")
    unknown: str = Field(min_length=1, description="what this file can't show")
    resolve_in: str = Field(min_length=1, description="where the answer would be")


class Experiment(_Out):
    """A measurement that could prove a static claim false."""

    hypothesis: str = Field(min_length=1)
    vary: str = Field(min_length=1, description="the input to vary, and its sizes")
    measure: str = Field(min_length=1)
    refuted_if: str = Field(min_length=1)


CheckResultValue = Literal["found", "not found", "not applicable"]


class CheckResult(_Out):
    """The pass's answer for one check in its brief (OUT-U6)."""

    check: str = Field(min_length=1, description="a CHECK-ID from the brief's list")
    result: CheckResultValue
    note: str = Field(default="", description="for not applicable: why, in a few words")


class PassOutput(_Out):
    """Everything a unit pass returns. Every list is required; empty means none."""

    unit: str = Field(pattern=r"^u\d{3,}$")
    checks: list[CheckResult] = Field(
        description="one answer for every check ID the brief lists, in any order"
    )
    facts: list[Fact]
    comments: list[Comment]
    flows: list[Flow]
    functions: list[Function]
    findings: list[Finding]
    edges: list[Edge]
    experiments: list[Experiment] = Field(default_factory=list)
    limitations: list[str]
    still_to_check_by_hand: list[str] = Field(default_factory=list)


def schema() -> str:
    """The JSON Schema a pass's output must match (config/file-record.schema.json)."""
    data = PassOutput.model_json_schema()
    data["title"] = "agent-audit-kit file review pass output"
    data["$id"] = f"https://agent-audit-kit/file-record/{RECORD_VERSION}"
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def extract_json(text: str) -> str:
    """Return the JSON object in a reply, without a code fence or prose around it."""
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    body = fenced.group(1) if fenced else text
    start, end = body.find("{"), body.rfind("}")
    return body[start : end + 1] if 0 <= start < end else body.strip()


class InvalidOutputError(AuditKitError):
    """A pass's reply isn't output the kit can write; `problems` says why."""

    def __init__(self, problems: list[str]) -> None:
        """Keep every problem, for the repair prompt."""
        super().__init__("; ".join(problems[:3]))
        self.problems = problems


class InvalidRecordError(AuditKitError):
    """A stored record isn't what `kit review` writes."""


def parse(text: str) -> PassOutput:
    """Validate a reply against the schema.

    Raises:
        InvalidOutputError: With one problem per schema error (at most 20).
    """
    try:
        return PassOutput.model_validate_json(extract_json(text))
    except ValidationError as exc:
        raise InvalidOutputError(
            [
                f"schema: {'.'.join(str(p) for p in e['loc']) or 'object'}: {e['msg']}"
                for e in exc.errors()[:20]
            ]
        ) from exc


def _inside(unit: Unit, location: str) -> bool:
    m = LOCATION.match(location)
    if not m or m.group(1) != unit.path:
        return False
    first = int(m.group(2) or unit.start)
    last = int(m.group(3) or first)
    return unit.start <= first <= last <= unit.end


def _located(out: PassOutput) -> list[tuple[str, str, str]]:
    """Every (where, location, excerpt) in an output, for the location checks."""
    located = [
        (f"facts[{i}]", f.location, f.excerpt) for i, f in enumerate(out.facts, 1)
    ]
    located += [
        (f"comments[{i}]", c.location, c.excerpt) for i, c in enumerate(out.comments, 1)
    ]
    for i, flow in enumerate(out.flows, 1):
        located.append((f"flows[{i}].source", flow.source, flow.source_excerpt))
        located.append((f"flows[{i}].sink", flow.sink, flow.sink_excerpt))
    located += [
        (f"findings[{i}]", f.location, f.excerpt) for i, f in enumerate(out.findings, 1)
    ]
    return located


def _location_problems(
    ws: Workspace, unit: Unit, out: PassOutput, searcher: Searcher
) -> list[str]:
    found: list[str] = []
    span = f"{unit.path}:{unit.start}-{unit.end}"
    for where, location, excerpt in _located(out):
        if not _inside(unit, location):
            found.append(f"OUT-U2: {where}: {location!r} is outside {span}")
        elif not location_exists(ws, location):
            found.append(f"OUT-F4: {where}: {location!r} doesn't exist")
        elif problem := excerpt_problem(ws, location, quoted(excerpt), searcher.lines):
            found.append(
                f"OUT-F7: {where}: excerpt {problem}; {_cited(location, searcher)}"
            )
    return found


def _cited(location: str, searcher: Searcher) -> str:
    """Quote the cited lines, so a repair can copy them instead of guessing."""
    m = LOCATION.match(location)
    lines = searcher.lines(m.group(1)) if m and m.group(2) else None
    if m is None or lines is None or not m.group(2):
        return "the cited lines couldn't be read"
    first = int(m.group(2))
    last = int(m.group(3) or first)
    text = "\n".join(lines[first - 1 : last])
    return f"lines {first}-{last} read exactly: {text[:CITED_CHARS]!r}"


def _check_problems(out: PassOutput, check_ids: Sequence[str]) -> list[str]:
    """OUT-U6: every check in the brief is answered, and answers match findings."""
    found: list[str] = []
    wanted = set(check_ids)
    answers = [c.check for c in out.checks]
    missing = [c for c in check_ids if c not in answers]
    if missing:
        more = f" (and {len(missing) - SHOWN} more)" if len(missing) > SHOWN else ""
        found.append(f"OUT-U6: checks not answered: {', '.join(missing[:SHOWN])}{more}")
    unknown = sorted({c for c in answers if c not in wanted})
    if unknown:
        found.append(f"OUT-U6: checks not in this brief's list: {', '.join(unknown)}")
    repeated = sorted({c for c in answers if answers.count(c) > 1})
    if repeated:
        found.append(f"OUT-U6: checks answered twice: {', '.join(repeated)}")
    keyed = {f.key.split(":", 1)[0] for f in out.findings}
    for c in out.checks:
        if c.result == "found" and c.check not in keyed:
            found.append(f"OUT-U6: {c.check} is found, but no finding has that Key")
        if c.result != "found" and c.check in keyed:
            found.append(f"OUT-U6: {c.check} has a finding, so its result is found")
    return found


def _finding_problems(unit: Unit, out: PassOutput, searcher: Searcher) -> list[str]:
    found: list[str] = []
    keys = [f.key for f in out.findings]
    for i, f in enumerate(out.findings, 1):
        where = f"findings[{i}]"
        if not KEY_OK.match(f.key):
            found.append(f"OUT-F2: {where}: key {f.key!r} isn't CHECK-ID:file")
        elif not f.key.endswith(f":{unit.path}"):
            found.append(f"OUT-F2: {where}: key {f.key!r} must end with :{unit.path}")
        if keys.count(f.key) > 1:
            found.append(f"OUT-F3: {where}: duplicate key {f.key!r}")
        high = f.severity in ("critical", "high")
        if high and not f.trigger.strip():
            found.append(f"OUT-F9: {where}: {f.severity} without a trigger")
        if high and f.edges:
            found.append(
                f"OUT-U4: {where}: {f.severity} depends on an open edge; "
                "Medium at most until a trace resolves it"
            )
        if high and f.verification == "unverified":
            found.append(
                f"OUT-U4: {where}: {f.severity} is unverified; Medium at most until "
                "it can be shown from this unit"
            )
        if f.edges and f.verification == "verified":
            found.append(
                f"OUT-U4: {where}: depends on an open edge, so it can't be verified"
            )
        missing = [e for e in f.edges if not 1 <= e <= len(out.edges)]
        if missing:
            found.append(f"OUT-F1: {where}: edges {missing} don't exist")
        for search in f.searched:
            if problem := searcher.problem(search):
                found.append(f"OUT-F8: {where}: searched {search!r}: {problem}")
    return found


def problems(
    ws: Workspace,
    unit: Unit,
    out: PassOutput,
    searcher: Searcher,
    check_ids: Sequence[str],
) -> list[str]:
    """Return the record checks a pass's output fails; empty when it can be written.

    Each problem starts with its check ID, so the repair prompt can name it.

    Args:
        ws: The workspace.
        unit: The unit the output is for.
        out: The pass's output.
        searcher: Re-runs "not found" searches and reads cited lines.
        check_ids: The check IDs the unit's brief lists (OUT-U6).
    """
    found: list[str] = []
    if out.unit != unit.id:
        found.append(f"OUT-U2: unit is {out.unit!r}, expected {unit.id!r}")
    return [
        *found,
        *_location_problems(ws, unit, out, searcher),
        *_finding_problems(unit, out, searcher),
        *_check_problems(out, check_ids),
    ]


def quoted(excerpt: str) -> str:
    """Return an excerpt in backticks, unless it has its own (a template literal)."""
    return excerpt if "`" in excerpt else f"`{excerpt}`"


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Provenance(_Record):
    """Who and what produced a record; the kit fills it in."""

    label: str
    provider: str
    model_family: str
    model: str
    harness: str
    repository: str
    commit: str
    branch: str
    started_utc: str
    finished_utc: str
    sessions: int = Field(default=1, ge=1)
    reused_from: str = ""


class UnitRef(_Record):
    """The unit a record is for."""

    id: str
    path: str
    part: str
    start: int
    end: int
    kind: str

    @classmethod
    def of(cls, unit: Unit) -> UnitRef:
        """Describe a unit."""
        return cls(
            id=unit.id,
            path=unit.path,
            part=unit.part,
            start=unit.start,
            end=unit.end,
            kind=unit.kind,
        )


class Hashes(_Record):
    """What a record depends on; unchanged hashes mean it can be reused (D7)."""

    unit_sha256: str
    skills_sha256: str
    scans_sha256: str
    kit_version: str

    @classmethod
    def of(cls, meta: BriefMeta) -> Hashes:
        """Take the hashes from a unit's brief."""
        return cls(
            unit_sha256=meta.unit_sha256,
            skills_sha256=meta.skills_sha256,
            scans_sha256=meta.scans_sha256,
            kit_version=meta.kit_version,
        )


class Summary(_Record):
    """A unit's counts, computed by the kit from the checked output and gates."""

    critical: int
    high: int
    medium: int
    low: int
    info: int
    verified: int
    unverified: int
    open_edges: int
    facts: int
    flows: int
    gates_failed: int
    gates_unavailable: int
    checks_found: int
    checks_not_found: int
    checks_not_applicable: int

    @classmethod
    def of(cls, out: PassOutput, gates: list[Gate]) -> Summary:
        """Count a unit's findings, edges, facts, flows and gates."""
        severity = {s: sum(f.severity == s for f in out.findings) for s in SEVERITIES}
        return cls(
            **severity,
            verified=sum(f.verification == "verified" for f in out.findings),
            unverified=sum(f.verification == "unverified" for f in out.findings),
            open_edges=len(out.edges),
            facts=len(out.facts),
            flows=len(out.flows),
            gates_failed=sum(g.status == "fail" for g in gates),
            gates_unavailable=sum(g.status == "unavailable" for g in gates),
            checks_found=sum(c.result == "found" for c in out.checks),
            checks_not_found=sum(c.result == "not found" for c in out.checks),
            checks_not_applicable=sum(c.result == "not applicable" for c in out.checks),
        )


class StoredRecord(_Record):
    """A record as written to `.audit/files/<path>[#<part>].json`."""

    record_version: Literal[1] = 1
    unit: UnitRef
    hashes: Hashes
    provenance: Provenance
    summary: Summary
    scan_rows: dict[str, int]
    gates: list[Gate]
    output: PassOutput

    def made_from(self, unit: Unit, meta: BriefMeta) -> bool:
        """Return True if this record was made from this unit's brief as it is now.

        The unit's text, the kit version, the skill sections and the scan rows
        must all be unchanged (ADR 0007 D7).
        """
        return self.unit == UnitRef.of(unit) and self.hashes == Hashes.of(meta)


def build(
    unit: Unit, out: PassOutput, prov: Provenance, meta: BriefMeta
) -> StoredRecord:
    """Return the record for a pass's checked output."""
    return StoredRecord(
        unit=UnitRef.of(unit),
        hashes=Hashes.of(meta),
        provenance=prov,
        summary=Summary.of(out, meta.gates),
        scan_rows=meta.scan_rows,
        gates=meta.gates,
        output=out,
    )


def finding_id(unit_id: str, n: int) -> str:
    """Return a finding's ID, such as `FILE-u042-001`."""
    return f"FILE-{unit_id}-{n:03d}"


def edge_id(unit_id: str, n: int) -> str:
    """Return an open edge's ID, such as `EDGE-u042-001`."""
    return f"EDGE-{unit_id}-{n:03d}"


def evidence_of(f: Finding) -> str:
    """Return a finding's Evidence, built from Location and Excerpt if it has none."""
    return f.evidence.strip() or f"{quoted(f.excerpt)} ({f.location})"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _code(text: str) -> str:
    return _cell(quoted(text))


def _table(title: str, head: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return [f"## {title}", "none", ""]
    return [
        f"## {title}",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(r) + " |" for r in rows),
        "",
    ]


def _header(record: StoredRecord, brief_rel: str) -> list[str]:
    p, u = record.provenance, record.unit
    reused = [f"reused_from: {p.reused_from}"] if p.reused_from else []
    part = f" #{u.part}" if u.part else ""
    return [
        "---",
        f"kit_version: {record.hashes.kit_version}",
        "agent: file-reviewer",
        f"pass: {p.label}",
        f"provider: {p.provider}",
        f"model_family: {p.model_family}",
        f"model: {p.model}",
        f"harness: {p.harness}",
        f"repository: {p.repository}",
        f"commit: {p.commit}",
        f"branch: {p.branch}",
        f"scope: partial \u2013 {u.path}:{u.start}-{u.end}",
        "status: complete",
        f"sessions: {p.sessions}",
        f"started_utc: {p.started_utc}",
        f"finished_utc: {p.finished_utc}",
        f"inputs: [{brief_rel}]",
        f"unit: {u.id}",
        f"lines: {u.start}-{u.end}",
        *reused,
        "---",
        "",
        f"# File record: {u.path}{part}",
        "",
        "Rendered by the kit from the JSON beside it (ADR 0007 D3). Change the JSON, "
        "not this file.",
        "",
    ]


def _tables(out: PassOutput) -> list[str]:
    facts = [[f.kind, _cell(f.name), f.location, _code(f.excerpt)] for f in out.facts]
    comments = [
        [_cell(c.claim), c.location, _code(c.excerpt), _cell(c.code_lines), c.verdict]
        for c in out.comments
    ]
    flows = [
        [
            f.source,
            _code(f.source_excerpt),
            f.sink,
            _code(f.sink_excerpt),
            _cell(f.validation),
            f.cwe,
        ]
        for f in out.flows
    ]
    functions = [
        [
            _cell(f.name),
            f.lines,
            "not scanned" if f.complexity is None else str(f.complexity),
            _cell(f.n),
            f.controlled_by,
            _cell(f.growth),
            _cell(f.growth_lines),
            f.runs_on,
            f.confidence,
        ]
        for f in out.functions
    ]
    function_head = [
        "Name",
        "Lines",
        "Complexity",
        "n",
        "Controlled by",
        "Growth",
        "Growth lines",
        "Runs on",
        "Confidence",
    ]
    return [
        *_table("Facts", ["Kind", "Name", "Location", "Excerpt"], facts),
        *_table(
            "Comments versus code",
            ["Claim", "Comment", "Excerpt", "Code lines", "Verdict"],
            comments,
        ),
        *_table(
            "Sources and sinks",
            ["Source", "Source excerpt", "Sink", "Sink excerpt", "Validation", "CWE"],
            flows,
        ),
        *_table("Functions", function_head, functions),
    ]


def _finding(unit_id: str, n: int, f: Finding) -> list[str]:
    related = ", ".join(
        x for x in [f.related, *(edge_id(unit_id, e) for e in f.edges)] if x
    )
    fields = [
        ("Key", f.key),
        ("Category", f.category),
        ("Severity", f.severity),
        ("Confidence", f.confidence),
        ("Verification", f.verification),
        ("Location", f.location),
        ("Excerpt", quoted(f.excerpt)),
        ("Trigger", f.trigger),
        ("Evidence", evidence_of(f)),
        ("Description", f.description),
        ("Impact", f.impact),
        ("Recommendation", f.recommendation),
        ("Sources", f.sources),
        ("Effort", f.effort),
        ("Packages", ", ".join(f.packages)),
        ("Related", related),
        ("Checked-by-author", "yes"),
    ]
    return [
        f"### {finding_id(unit_id, n)} {_cell(f.title)}",
        *(f"- {name}: {_cell(value)}" for name, value in fields if value.strip()),
        *(f"- Searched: {s}" for s in f.searched),
        "",
    ]


def _findings_and_edges(unit_id: str, out: PassOutput) -> list[str]:
    body = ["## Findings"]
    for n, f in enumerate(out.findings, 1):
        body += _finding(unit_id, n, f)
    if not out.findings:
        body += ["none", ""]
    body.append("## Open edges")
    for n, edge in enumerate(out.edges, 1):
        depends = [
            finding_id(unit_id, i)
            for i, f in enumerate(out.findings, 1)
            if n in f.edges
        ]
        body += [
            f"### {edge_id(unit_id, n)} {_cell(edge.question)}",
            f"- Unknown here: {_cell(edge.unknown)}",
            f"- Resolve in: {_cell(edge.resolve_in)}",
            f"- Findings that depend on it: {', '.join(depends) or 'none'}",
            "",
        ]
    if not out.edges:
        body += ["none", ""]
    return body


def _checks(out: PassOutput) -> list[str]:
    def ids(result: str) -> str:
        chosen = [c.check for c in out.checks if c.result == result]
        return ", ".join(chosen) or "none"

    not_applicable = [
        f"{c.check} ({_cell(c.note)})" if c.note else c.check
        for c in out.checks
        if c.result == "not applicable"
    ]
    return [
        "## Checks",
        f"- Found: {ids('found')}",
        f"- Not found: {ids('not found')}",
        f"- Not applicable: {', '.join(not_applicable) or 'none'}",
        "",
    ]


def _closing(out: PassOutput) -> list[str]:
    body: list[str] = []
    if out.experiments:
        body.append("## Experiment plans")
        for x in out.experiments:
            body += [
                f"- Hypothesis: {_cell(x.hypothesis)}",
                f"  - Vary: {_cell(x.vary)}",
                f"  - Measure: {_cell(x.measure)}",
                f"  - Refuted if: {_cell(x.refuted_if)}",
            ]
        body.append("")
    body.append("## Limitations")
    body += [f"- {_cell(x)}" for x in out.limitations] or ["none"]
    if out.still_to_check_by_hand:
        body += ["", "### Still to check by hand"]
        body += [f"- {_cell(x)}" for x in out.still_to_check_by_hand]
    return body


def _summary(s: Summary) -> list[str]:
    findings = ", ".join(f"{getattr(s, sev)} {sev}" for sev in SEVERITIES)
    return [
        "## Summary",
        "| Findings | Verified | Unverified | Open edges | Facts | Sources and sinks "
        "| Gates failed | Gates unavailable |",
        "|---|---|---|---|---|---|---|---|",
        f"| {findings} | {s.verified} | {s.unverified} | {s.open_edges} | {s.facts} "
        f"| {s.flows} | {s.gates_failed} | {s.gates_unavailable} |",
        "",
    ]


def render(record: StoredRecord, brief_rel: str) -> str:
    """Render the Markdown record (ADR 0002 D4) from a stored record."""
    body = [
        *_header(record, brief_rel),
        *_summary(record.summary),
        *_tables(record.output),
        "## Gates",
        render_table(record.gates),
        "",
        *_findings_and_edges(record.unit.id, record.output),
        *_checks(record.output),
        *_closing(record.output),
    ]
    return "\n".join(body) + "\n"


def record_paths(unit: Unit) -> tuple[str, str]:
    """Return a record's Markdown and JSON paths."""
    return unit.record, unit.record.removesuffix(".md") + ".json"


def write(ws: Workspace, unit: Unit, record: StoredRecord, brief_rel: str) -> None:
    """Write a record's JSON and the Markdown rendered from it."""
    md, js = record_paths(unit)
    ws.write_text(js, record.model_dump_json(indent=1) + "\n")
    ws.write_text(md, render(record, brief_rel))


def read(ws: Workspace, unit: Unit) -> StoredRecord | None:
    """Return a unit's stored record, or None if it has none.

    Raises:
        InvalidRecordError: If the JSON file isn't a record `kit review` wrote.
    """
    _, js = record_paths(unit)
    return read_path(ws, js) if ws.is_file(js) else None


def read_path(ws: Workspace, rel: str) -> StoredRecord:
    """Read a stored record by its path.

    Raises:
        InvalidRecordError: If the file isn't a record `kit review` wrote.
    """
    try:
        return StoredRecord.model_validate_json(ws.read_text(rel, limit=50_000_000))
    except (WorkspaceError, ValidationError) as exc:
        raise InvalidRecordError(f"{rel}: not a record ({exc})") from exc
