"""The findings store: every record, trace, gate and pass in one DuckDB file.

ADR 0007 D6. The JSON records, the traces and the pass ledger are the source of
truth; `kit store` rebuilds `.audit/findings.duckdb` from them from scratch, in
one process, after the passes finish. `kit query` opens it read-only with
external access off, so a query can read the tables and nothing else: no files,
no network, no extensions, no writes (architecture constraint C10).

The store holds one target's findings and code excerpts. It stays in the
engagement, under its data-handling rules (D9): nothing in it goes into the kit.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import duckdb
from pydantic import ValidationError

from audit_kit import file_record, gates, ledger
from audit_kit.console import ok, say
from audit_kit.errors import AuditKitError, WorkspaceError
from audit_kit.findings import parse_findings
from audit_kit.settings import KitSettings
from audit_kit.units import OUTPUT as UNITS
from audit_kit.units import Unit
from audit_kit.units import parse as parse_units
from audit_kit.verification import LOCATION
from audit_kit.workspace import Workspace
from audit_kit.workspaces import locate

STORE = PurePosixPath(".audit/findings.duckdb")
COST_OUT = PurePosixPath(".audit/cost.md")
IGNORE = PurePosixPath(".audit/.gitignore")
IGNORED = ("findings.duckdb", "findings.duckdb.tmp", "findings.duckdb.wal")
EDGE_ID = re.compile(r"\bEDGE-u\d{3,}-\d{3}\b")
RECORD_BYTES = 50_000_000

Value = str | int | float | bool | list[str] | None
Row = dict[str, Value]

# Each table's columns, in order. Rows are dicts keyed by these names, so a row
# with a missing or extra column fails the build instead of shifting values.
# The per-unit summary's counts, as units columns (ADR 0007, file_record.Summary).
SUMMARY = tuple(file_record.Summary.model_fields)
TABLES: dict[str, tuple[tuple[str, str], ...]] = {
    "units": (
        ("unit", "VARCHAR PRIMARY KEY"),
        ("path", "VARCHAR"),
        ("part", "VARCHAR"),
        ("start_line", "INTEGER"),
        ("end_line", "INTEGER"),
        ("lines", "INTEGER"),
        ("kind", "VARCHAR"),
        ("record", "VARCHAR"),
        ("status", "VARCHAR"),
        ("reused", "BOOLEAN"),
        ("reused_from", "VARCHAR"),
        ("pass", "VARCHAR"),
        ("model", "VARCHAR"),
        ("unit_sha256", "VARCHAR"),
        ("skills_sha256", "VARCHAR"),
        ("scans_sha256", "VARCHAR"),
        ("kit_version", "VARCHAR"),
        *((name, "INTEGER") for name in SUMMARY),
    ),
    "findings": (
        ("id", "VARCHAR PRIMARY KEY"),
        ("source", "VARCHAR"),
        ("unit", "VARCHAR"),
        ("trace", "VARCHAR"),
        ("key", "VARCHAR"),
        ("check_id", "VARCHAR"),
        ("title", "VARCHAR"),
        ("category", "VARCHAR"),
        ("severity", "VARCHAR"),
        ("confidence", "VARCHAR"),
        ("verification", "VARCHAR"),
        ("path", "VARCHAR"),
        ("start_line", "INTEGER"),
        ("end_line", "INTEGER"),
        ("location", "VARCHAR"),
        ("excerpt", "VARCHAR"),
        ("trigger", "VARCHAR"),
        ("evidence", "VARCHAR"),
        ("description", "VARCHAR"),
        ("impact", "VARCHAR"),
        ("recommendation", "VARCHAR"),
        ("sources", "VARCHAR"),
        ("effort", "VARCHAR"),
        ("edges", "VARCHAR[]"),
    ),
    "edges": (
        ("id", "VARCHAR PRIMARY KEY"),
        ("unit", "VARCHAR"),
        ("question", "VARCHAR"),
        ("unknown", "VARCHAR"),
        ("resolve_in", "VARCHAR"),
        ("findings", "VARCHAR[]"),
        ("resolved_by", "VARCHAR"),
    ),
    "facts": (
        ("unit", "VARCHAR"),
        ("kind", "VARCHAR"),
        ("name", "VARCHAR"),
        ("path", "VARCHAR"),
        ("line", "INTEGER"),
        ("excerpt", "VARCHAR"),
    ),
    "flows": (
        ("unit", "VARCHAR"),
        ("path", "VARCHAR"),
        ("source_line", "INTEGER"),
        ("sink_line", "INTEGER"),
        ("source_excerpt", "VARCHAR"),
        ("sink_excerpt", "VARCHAR"),
        ("validation", "VARCHAR"),
        ("cwe", "VARCHAR"),
    ),
    "checks": (
        ("unit", "VARCHAR"),
        ("check_id", "VARCHAR"),
        ("result", "VARCHAR"),
        ("note", "VARCHAR"),
    ),
    "gates": (
        ("unit", "VARCHAR"),
        ("path", "VARCHAR"),
        ("gate", "VARCHAR"),
        ("status", "VARCHAR"),
        ("evidence", "VARCHAR"),
    ),
    "repo_gates": (
        ("gate", "VARCHAR PRIMARY KEY"),
        ("target", "VARCHAR"),
        ('"where"', "VARCHAR[]"),
        ("kit_config", "VARCHAR"),
        ("kit_ran", "BOOLEAN"),
    ),
    "passes": (
        ("stage", "VARCHAR"),
        ("unit", "VARCHAR"),
        ("pass", "VARCHAR"),
        ("model", "VARCHAR"),
        ("attempt", "INTEGER"),
        ("outcome", "VARCHAR"),
        ("turns", "INTEGER"),
        ("input_tokens", "BIGINT"),
        ("output_tokens", "BIGINT"),
        ("cache_read_tokens", "BIGINT"),
        ("cache_write_tokens", "BIGINT"),
        ("cost_usd", "DOUBLE"),
        ("seconds", "DOUBLE"),
        ("started_utc", "VARCHAR"),
        ("session_id", "VARCHAR"),
    ),
}


def _columns(table: str) -> list[str]:
    return [name.strip('"') for name, _ in TABLES[table]]


def schema_sql() -> str:
    """Return the CREATE TABLE statements for every table."""
    return "\n".join(
        f"CREATE TABLE {table} ({', '.join(f'{n} {t}' for n, t in columns)});"
        for table, columns in TABLES.items()
    )


@dataclass(frozen=True)
class Span:
    """The file and lines a location names."""

    path: str | None
    first: int | None
    last: int | None


def span(location: str) -> Span:
    """Return the file and lines in a `file[:line[-line]]` location."""
    m = LOCATION.match(location)
    if not m:
        return Span(None, None, None)
    first = int(m.group(2)) if m.group(2) else None
    last = int(m.group(3)) if m.group(3) else first
    return Span(m.group(1), first, last)


@dataclass(frozen=True)
class Trace:
    """One trace's name and Markdown."""

    name: str
    text: str


def _traces(ws: Workspace) -> list[Trace]:
    folder = ws.root / ".audit/traces"
    paths = sorted(folder.glob("*.md")) if folder.is_dir() else []
    return [
        Trace(p.stem, ws.read_text(p.relative_to(ws.root).as_posix(), RECORD_BYTES))
        for p in paths
    ]


def _resolved(traces: list[Trace]) -> dict[str, str]:
    """Return each edge ID a trace answers under its "Edges resolved" section."""
    found: dict[str, str] = {}
    for trace in traces:
        section = re.search(
            r"^## Edges resolved\b(.*?)(?=^## |\Z)", trace.text, re.M | re.S
        )
        for edge in EDGE_ID.findall(section.group(1) if section else ""):
            found.setdefault(edge, trace.name)
    return found


def _unit_row(u: Unit, record: file_record.StoredRecord | None, status: str) -> Row:
    prov = record.provenance if record else None
    hashes = record.hashes if record else None
    return {
        "unit": u.id,
        "path": u.path,
        "part": u.part,
        "start_line": u.start,
        "end_line": u.end,
        "lines": u.lines,
        "kind": u.kind,
        "record": u.record,
        "status": status,
        "reused": bool(prov and prov.reused_from),
        "reused_from": (prov.reused_from or None) if prov else None,
        "pass": prov.label if prov else None,
        "model": prov.model if prov else None,
        "unit_sha256": hashes.unit_sha256 if hashes else None,
        "skills_sha256": hashes.skills_sha256 if hashes else None,
        "scans_sha256": hashes.scans_sha256 if hashes else None,
        "kit_version": hashes.kit_version if hashes else None,
        **{name: getattr(record.summary, name) if record else None for name in SUMMARY},
    }


def _record_rows(
    record: file_record.StoredRecord, resolved: dict[str, str]
) -> dict[str, list[Row]]:
    """Return the findings, edges, facts, flows and gates one record holds."""
    unit, out = record.unit.id, record.output
    rows: dict[str, list[Row]] = {
        t: [] for t in ("findings", "edges", "facts", "flows", "checks", "gates")
    }
    for n, f in enumerate(out.findings, 1):
        where = span(f.location)
        rows["findings"].append(
            {
                "id": file_record.finding_id(unit, n),
                "source": "file",
                "unit": unit,
                "trace": None,
                "key": f.key,
                "check_id": f.key.split(":", 1)[0],
                "title": f.title,
                "category": f.category,
                "severity": f.severity,
                "confidence": f.confidence,
                "verification": f.verification,
                "path": where.path,
                "start_line": where.first,
                "end_line": where.last,
                "location": f.location,
                "excerpt": f.excerpt,
                "trigger": f.trigger or None,
                "evidence": file_record.evidence_of(f),
                "description": f.description,
                "impact": f.impact,
                "recommendation": f.recommendation,
                "sources": f.sources,
                "effort": f.effort,
                "edges": [file_record.edge_id(unit, e) for e in f.edges],
            }
        )
    for n, e in enumerate(out.edges, 1):
        eid = file_record.edge_id(unit, n)
        depends = [
            file_record.finding_id(unit, i)
            for i, f in enumerate(out.findings, 1)
            if n in f.edges
        ]
        rows["edges"].append(
            {
                "id": eid,
                "unit": unit,
                "question": e.question,
                "unknown": e.unknown,
                "resolve_in": e.resolve_in,
                "findings": depends,
                "resolved_by": resolved.get(eid),
            }
        )
    for fact in out.facts:
        where = span(fact.location)
        rows["facts"].append(
            {
                "unit": unit,
                "kind": fact.kind,
                "name": fact.name,
                "path": where.path,
                "line": where.first,
                "excerpt": fact.excerpt,
            }
        )
    for flow in out.flows:
        rows["flows"].append(
            {
                "unit": unit,
                "path": span(flow.source).path,
                "source_line": span(flow.source).first,
                "sink_line": span(flow.sink).first,
                "source_excerpt": flow.source_excerpt,
                "sink_excerpt": flow.sink_excerpt,
                "validation": flow.validation,
                "cwe": flow.cwe,
            }
        )
    for c in out.checks:
        rows["checks"].append(
            {"unit": unit, "check_id": c.check, "result": c.result, "note": c.note}
        )
    for g in record.gates:
        rows["gates"].append(
            {
                "unit": unit,
                "path": record.unit.path,
                "gate": g.gate,
                "status": g.status,
                "evidence": g.evidence,
            }
        )
    return rows


def _trace_rows(trace: Trace) -> list[Row]:
    rows: list[Row] = []
    for f in parse_findings(trace.text):
        where = span(f.get("Location"))
        rows.append(
            {
                "id": f.id,
                "source": "trace",
                "unit": None,
                "trace": trace.name,
                "key": f.get("Key"),
                "check_id": f.get("Key").split(":", 1)[0],
                "title": f.get("Title"),
                "category": f.get("Category"),
                "severity": f.get("Severity").lower(),
                "confidence": f.get("Confidence").lower(),
                "verification": f.get("Verification").lower() or None,
                "path": where.path,
                "start_line": where.first,
                "end_line": where.last,
                "location": f.get("Location"),
                "excerpt": f.get("Excerpt"),
                "trigger": f.get("Trigger") or None,
                "evidence": f.get("Evidence"),
                "description": f.get("Description"),
                "impact": f.get("Impact"),
                "recommendation": f.get("Recommendation"),
                "sources": f.get("Sources"),
                "effort": f.get("Effort"),
                "edges": EDGE_ID.findall(f.get("Related")),
            }
        )
    return rows


def _pass_row(p: ledger.PassRow) -> Row:
    return {
        "stage": p.stage,
        "unit": p.unit,
        "pass": p.label,
        "model": p.model,
        "attempt": p.attempt,
        "outcome": p.outcome,
        "turns": p.turns,
        "input_tokens": p.input_tokens,
        "output_tokens": p.output_tokens,
        "cache_read_tokens": p.cache_read_tokens,
        "cache_write_tokens": p.cache_write_tokens,
        "cost_usd": p.cost_usd,
        "seconds": p.seconds,
        "started_utc": p.started_utc,
        "session_id": p.session_id,
    }


def rows(ws: Workspace) -> dict[str, list[Row]]:
    """Return every table's rows, in a fixed order, from the files on disk.

    Raises:
        AuditKitError: If a record, the ledger or the gate table is malformed, or
            two findings share an ID.
    """
    units = parse_units(ws.read_text(UNITS)) if ws.is_file(UNITS) else []
    status = ledger.read_status(ws)
    traces = _traces(ws)
    resolved = _resolved(traces)
    out: dict[str, list[Row]] = {table: [] for table in TABLES}
    for u in units:
        record = file_record.read(ws, u)
        default = "done" if record else "pending"
        out["units"].append(
            _unit_row(u, record, status[u.id].status if u.id in status else default)
        )
        if record is not None:
            for table, found in _record_rows(record, resolved).items():
                out[table] += found
    for trace in traces:
        out["findings"] += _trace_rows(trace)
    try:
        repo = gates.read_repository(ws)
        passes = ledger.read(ws)
    except ValidationError as exc:
        raise AuditKitError(f"a gate table or ledger line is malformed: {exc}") from exc
    for g in repo.gates if repo else []:
        out["repo_gates"].append(
            {
                "gate": g.gate,
                "target": g.target,
                "where": g.where + g.scripts,
                "kit_config": g.kit_config,
                "kit_ran": g.kit_ran,
            }
        )
    out["passes"] = [_pass_row(p) for p in passes]
    ids = [str(f["id"]) for f in out["findings"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise AuditKitError(
            f"duplicate finding IDs across records and traces: {duplicates[:5]}"
        )
    return out


def _insert(con: duckdb.DuckDBPyConnection, table: str, values: Sequence[Row]) -> None:
    columns = _columns(table)
    quoted = ", ".join(f'"{c}"' for c in columns)
    marks = ", ".join("?" * len(columns))
    sql = f"INSERT INTO {table} ({quoted}) VALUES ({marks})"  # noqa: S608  # nosec B608  table and column names are the kit's own
    con.executemany(sql, [[row[c] for c in columns] for row in values])


def build(ws: Workspace) -> dict[str, int]:
    """Rebuild the store from scratch, and return the row count per table."""
    data = rows(ws)
    # Built beside the store and moved over it, so a failed build leaves the
    # last good store. DuckDB writes the file itself, at a path the workspace
    # has confined (C2).
    temp = STORE.with_name(STORE.name + ".tmp")
    ws.remove(temp)
    with duckdb.connect(str(ws.path(temp))) as con:
        con.execute(schema_sql())
        for table, values in data.items():
            if values:
                _insert(con, table, values)
        con.execute("CHECKPOINT")
    ws.move(temp, STORE)
    return {table: len(values) for table, values in data.items()}


def _ignore_store(ws: Workspace) -> None:
    """Keep the store out of checkpoints: it's rebuilt from files they commit."""
    have = ws.read_text(IGNORE).splitlines() if ws.is_file(IGNORE) else []
    missing = [name for name in IGNORED if name not in have]
    if missing:
        ws.write_text(IGNORE, "".join(f"{x}\n" for x in [*have, *missing]))


def store(s: KitSettings, given: str) -> None:
    """Rebuild .audit/findings.duckdb (`kit store`)."""
    ws = locate(s, given).ws
    _ignore_store(ws)
    counts = build(ws)
    ok(f"store: {', '.join(f'{k} {v}' for k, v in counts.items())} ({STORE})")


def connect_read_only(ws: Workspace) -> duckdb.DuckDBPyConnection:
    """Open the store so a query can read its tables and do nothing else.

    Raises:
        AuditKitError: If the store hasn't been built.
    """
    if not ws.is_file(STORE):
        raise AuditKitError(f"no {STORE}; run kit store first")
    return duckdb.connect(
        str(ws.path(STORE)),
        read_only=True,
        config={
            "enable_external_access": False,
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
            "lock_configuration": True,
        },
    )


@dataclass(frozen=True)
class Result:
    """A query's column names and rows."""

    columns: list[str]
    rows: list[tuple[object, ...]]


def query(ws: Workspace, sql: str) -> Result:
    """Run one read-only query.

    Raises:
        AuditKitError: If the store is missing, or DuckDB refuses or fails the query.
    """
    with connect_read_only(ws) as con:
        try:
            cursor = con.execute(sql)
        except duckdb.Error as exc:
            raise AuditKitError(f"query refused or failed: {exc}") from exc
        if cursor.description is None:
            return Result([], [])
        return Result([d[0] for d in cursor.description], cursor.fetchall())


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return " ".join(str(value).split()).replace("|", "\\|")


def render(result: Result, fmt: str) -> str:
    """Render a query result as a Markdown table, CSV or JSON."""
    if fmt == "json":
        records = [dict(zip(result.columns, r, strict=True)) for r in result.rows]
        return json.dumps(records, indent=1, default=str) + "\n"
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(result.columns)
        writer.writerows([[_cell(c) for c in r] for r in result.rows])
        return buffer.getvalue()
    lines = [
        "| " + " | ".join(result.columns) + " |",
        "|" + "---|" * len(result.columns),
    ]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in result.rows]
    return "\n".join(lines) + f"\n\n{len(result.rows)} row(s)\n"


def run_query(s: KitSettings, given: str, sql: str, fmt: str) -> None:
    """Print a read-only query's result (`kit query`)."""
    say(render(query(locate(s, given).ws, sql), fmt).rstrip("\n"))


@dataclass
class _Totals:
    worked_on: set[str] = field(default_factory=set)
    passes: int = 0
    turns: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float = 0.0
    unpriced: int = 0
    seconds: float = 0.0

    @property
    def units(self) -> int:
        """Return how many units a model did work on, across every rerun."""
        return len(self.worked_on)

    def add(self, p: ledger.PassRow) -> None:
        # A pass refused for a usage limit used nothing; it isn't a unit's cost.
        spent = p.input_tokens + p.output_tokens + p.cache_read_tokens
        if spent + p.cache_write_tokens:
            self.worked_on.add(p.unit)
        self.passes += 1
        self.turns += p.turns
        self.input += p.input_tokens
        self.output += p.output_tokens
        self.cache_read += p.cache_read_tokens
        self.cache_write += p.cache_write_tokens
        self.cost += p.cost_usd or 0.0
        self.unpriced += p.cost_usd is None
        self.seconds += p.seconds


def cost_table(passes: list[ledger.PassRow]) -> str:
    """Render totals by stage and model, labelled as API-equivalent cost (D8)."""
    groups: dict[tuple[str, str], _Totals] = {}
    for p in passes:
        groups.setdefault((p.stage, p.model), _Totals()).add(p)
    out = [
        "| Stage | Model | Units | Passes | Turns | Input | Output | Cache read "
        "| Cache write | API-equivalent cost (USD) | Seconds |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    total = _Totals()
    for (stage, model), g in sorted(groups.items()):
        note = f" ({g.unpriced} unpriced)" if g.unpriced else ""
        out.append(
            f"| {stage} | {model} | {g.units} | {g.passes} | {g.turns} | "
            f"{g.input:,} | {g.output:,} | {g.cache_read:,} | {g.cache_write:,} | "
            f"{g.cost:.2f}{note} | {g.seconds:.0f} |"
        )
        total.cost += g.cost
        total.worked_on |= g.worked_on
    per = total.cost / total.units if total.units else 0.0
    out += [
        "",
        f"Total: {total.cost:.2f} USD for {total.units} units ({per:.3f} per unit). "
        "The cost is what `claude -p` reports at API prices; a plan is billed "
        "differently.",
    ]
    return "\n".join(out) + "\n"


def cost(s: KitSettings, given: str) -> None:
    """Print the pass ledger's totals and write .audit/cost.md (`kit cost`).

    Raises:
        AuditKitError: If no pass has been recorded, or the ledger is malformed.
    """
    ws = locate(s, given).ws
    try:
        passes = ledger.read(ws)
    except (WorkspaceError, ValidationError) as exc:
        raise AuditKitError(f"{ledger.PASSES}: {exc}") from exc
    if not passes:
        raise AuditKitError(
            f"no passes in {ledger.PASSES} yet (kit review writes them)"
        )
    table = cost_table(passes)
    ws.write_text(COST_OUT, "# Cost and time per stage and model\n\n" + table)
    say(table.rstrip("\n"))
    ok(f"written to {COST_OUT}")
