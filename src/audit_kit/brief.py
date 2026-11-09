"""One brief per file review unit: everything its pass may read (ADR 0007 D1).

A brief holds the unit's lines, numbered; this file's rows from every scan; the
unit's gate table; the skill sections for its kind; and the output schema. The
pass reads the brief and nothing else, so the brief must leave nothing out:
every row it selects is counted, and `kit verify` (OUT-U5) recounts them.
`brief.json` beside it holds what the kit needs later: the hashes a record is
reused by (D7), the row counts, and the gates.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from audit_kit import skill_sections
from audit_kit.detection import loaded_profiles
from audit_kit.gates import Gate, render_table
from audit_kit.scan_rows import NAMES, SOURCES, ScanIndex, UnitRows, unit_rows
from audit_kit.units import Unit
from audit_kit.workspace import Workspace

WORK = PurePosixPath(".audit/work/files")
UNIT_BYTES = 16_000_000
ROW_CHARS = 400
# Lines above a section of a large file that it may need to resolve names.
IMPORT_LINE = re.compile(
    r"^\s*(?:import\b|export\s+[^=]*\bfrom\b|(?:const|let|var)\s+[^=]+=\s*require\()"
)
SCAN_HEADING = re.compile(r"^### (?P<source>\w+) \(")
# A catalogue row starts with its CHECK-ID: `| JS-FLOATING | ...`, `| WCAG-1.4.3 |`.
CHECK_ROW = re.compile(r"^\| (?P<id>[A-Z][A-Z0-9]*(?:-[A-Z0-9.]+)+) \|", re.M)


class BriefMeta(BaseModel):
    """What the kit keeps about a brief (brief.json)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: str
    path: str
    part: str
    start: int
    end: int
    kind: str
    brief_kind: str
    unit_sha256: str
    skills_sha256: str
    scans_sha256: str
    kit_version: str
    sections: list[str]
    check_ids: list[str]
    scan_rows: dict[str, int]
    scan_status: dict[str, str]
    gates: list[Gate]


@dataclass(frozen=True)
class Brief:
    """A rendered brief and what the kit keeps about it."""

    text: str
    meta: BriefMeta


def sha256(text: str) -> str:
    """Return the hex SHA-256 of text encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unit_text(ws: Workspace, unit: Unit) -> tuple[list[str], str]:
    """Return the unit's file's lines, and the unit's own text."""
    lines = ws.read_text(unit.path, limit=UNIT_BYTES).split("\n")
    return lines, "\n".join(lines[unit.start - 1 : unit.end])


def _fence(text: str) -> str:
    """A code fence longer than any run of backticks in the text."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _numbered(numbered: list[tuple[int, str]]) -> str:
    width = len(str(numbered[-1][0])) if numbered else 1
    return "\n".join(f"{n:>{width}}  {line}" for n, line in numbered)


def _one_line(text: str) -> str:
    return " ".join(text.split())[:ROW_CHARS]


def context_lines(lines: list[str], unit: Unit) -> list[tuple[int, str]]:
    """Return the import lines above a section that doesn't start its file."""
    if unit.kind != "file" or unit.start == 1:
        return []
    return [
        (n, x) for n, x in enumerate(lines[: unit.start - 1], 1) if IMPORT_LINE.match(x)
    ]


def check_ids(rules_text: str) -> list[str]:
    """Return the check IDs in a brief's rules, in the order they first appear."""
    found = (m.group("id") for m in CHECK_ROW.finditer(rules_text))
    # A catalogue's header row starts with the column name, which isn't a check.
    return list(dict.fromkeys(i for i in found if i != "CHECK-ID"))


def scan_table(rows: dict[str, UnitRows], index: ScanIndex) -> str:
    """Render the counts table that `kit verify` compares with the rows below it."""
    out = [
        "| Scan | Status | Rows here | Rows elsewhere in the file |",
        "|---|---|---|---|",
    ]
    for name in NAMES:
        status = index.status.get(name, "not run")
        out.append(
            f"| {name} | {status} | {len(rows[name].inside)} | {rows[name].elsewhere} |"
        )
    return "\n".join(out)


def parse_scan_table(text: str) -> dict[str, int]:
    """Read back the "Rows here" column of a brief's scan table."""
    found: dict[str, int] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0] in NAMES and cells[2].isdigit():
            found[cells[0]] = int(cells[2])
    return found


def count_rendered_rows(text: str) -> dict[str, int]:
    """Count the rows shown under each scan's heading in a brief, zero if none."""
    part = text.split("\n## Scan rows\n", 1)[-1].split("\n## Gates\n", 1)[0]
    counts = dict.fromkeys(NAMES, 0)
    current = ""
    for line in part.splitlines():
        heading = SCAN_HEADING.match(line)
        if heading:
            current = heading.group("source")
        elif current in counts and line.startswith("- "):
            counts[current] += 1
    return counts


def _header(unit: Unit, kind: str) -> list[str]:
    part = f" #{unit.part}" if unit.part else ""
    return [
        f"# Brief for {unit.id}: {unit.path}{part}, lines {unit.start}-{unit.end} ({kind})",
        "",
        "Everything you may use is in this brief. Each line of code below starts "
        "with its line number in the file; the number is not part of the code, so "
        "never copy it into an excerpt.",
        "",
        "## Unit",
        "",
        f"- Unit: {unit.id}",
        f"- File: {unit.path}",
        f"- Part: {unit.part or 'whole file'}",
        f"- Lines: {unit.start}-{unit.end}",
        f"- Kind: {unit.kind} (rules for: {kind})",
        "",
    ]


def _context(lines: list[str], unit: Unit) -> list[str]:
    context = context_lines(lines, unit)
    if not context:
        return []
    body = _numbered(context)
    fence = _fence(body)
    return [
        "## Context from the same file",
        "",
        "Import lines above this section, to resolve names. They aren't part of the "
        "unit: don't cite them.",
        "",
        f"{fence}text\n{body}\n{fence}",
        "",
    ]


def scan_part(rows: dict[str, UnitRows], index: ScanIndex) -> list[str]:
    """Render the brief's scan section: the count table, then each scan's rows."""
    out = [
        "## Scan rows",
        "",
        "Rows for this file from every scan, limited to the unit's lines (rows about "
        "the whole file have no line). A scan that didn't run is a limitation, never "
        "a pass.",
        "",
        scan_table(rows, index),
        "",
    ]
    for source in SOURCES:
        inside = rows[source.name].inside
        if not inside:
            continue
        out += [f"### {source.name} ({source.rel}: {source.what})", ""]
        out += [
            f"- {r.line if r.line is not None else 'file'}: {_one_line(r.text)}"
            for r in inside
        ]
        out.append("")
    return out


def build_brief(
    ws: Workspace,
    unit: Unit,
    index: ScanIndex,
    rules: list[skill_sections.Section],
    gates: list[Gate],
    schema: str,
    kit_version: str,
) -> Brief:
    """Render one unit's brief.

    Args:
        ws: The workspace.
        unit: The unit.
        index: Every scan's rows.
        rules: The skill sections for the unit's kind.
        gates: The unit's gates.
        schema: The output schema, as JSON.
        kit_version: The kit version the brief is built by.
    """
    lines, own = unit_text(ws, unit)
    rows = unit_rows(index, unit)
    kind = skill_sections.kind_of(unit)
    rules_text = skill_sections.render(rules)
    scans = scan_part(rows, index)
    ids = check_ids(rules_text)
    code = _numbered(list(enumerate(lines[unit.start - 1 : unit.end], unit.start)))
    fence = _fence(code)
    out = [
        *_header(unit, kind),
        *_context(lines, unit),
        "## Code",
        "",
        f"{fence}text\n{code}\n{fence}",
        "",
        *scans,
        "## Gates",
        "",
        render_table(gates),
        "",
        "## Rules",
        "",
        rules_text,
        "",
        "## Checks to answer",
        "",
        "Answer every one of these in `checks`: `found` (with a finding whose Key "
        "uses it), `not found` (you looked and it isn't here), or `not applicable` "
        "(it can't apply to this unit; say why in `note`).",
        "",
        ", ".join(ids) or "none",
        "",
        "## Output",
        "",
        "Return one JSON object that matches this schema, and nothing else: no prose "
        "before or after it.",
        "",
        f"```json\n{schema.strip()}\n```",
        "",
    ]
    meta = BriefMeta(
        unit=unit.id,
        path=unit.path,
        part=unit.part,
        start=unit.start,
        end=unit.end,
        kind=unit.kind,
        brief_kind=kind,
        unit_sha256=sha256(own),
        skills_sha256=sha256(rules_text),
        scans_sha256=sha256("\n".join(scans)),
        kit_version=kit_version,
        sections=[f"{s.source}: {s.heading.lstrip('# ')}" for s in rules],
        check_ids=ids,
        scan_rows={name: len(rows[name].inside) for name in NAMES},
        scan_status={name: str(index.status.get(name, "not run")) for name in NAMES},
        gates=gates,
    )
    return Brief("\n".join(out), meta)


def brief_paths(unit_id: str) -> tuple[PurePosixPath, PurePosixPath]:
    """Return where a unit's brief and its brief.json are written."""
    return WORK / unit_id / "brief.md", WORK / unit_id / "brief.json"


def write(ws: Workspace, brief: Brief) -> None:
    """Write a brief and its brief.json."""
    md, js = brief_paths(brief.meta.unit)
    ws.write_text(md, brief.text)
    ws.write_text(js, brief.meta.model_dump_json(indent=1) + "\n")


def read_meta(ws: Workspace, unit_id: str) -> BriefMeta | None:
    """Return a unit's brief.json, or None if `kit units` hasn't written one.

    Raises:
        pydantic.ValidationError: If brief.json isn't what `kit units` writes.
    """
    _, rel = brief_paths(unit_id)
    if not ws.is_file(rel):
        return None
    return BriefMeta.model_validate_json(ws.read_text(rel))


def profiles_of(ws: Workspace) -> tuple[str, ...]:
    """Return the profiles `detected.md` says to load; none if it isn't there."""
    rel = ".audit/detected.md"
    return loaded_profiles(ws.read_text(rel)) if ws.is_file(rel) else ()
