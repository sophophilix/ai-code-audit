"""Which specialist finding reports each file-record and trace finding.

The specialists read the file records and traces as a map and write their own
findings. A record finding that no specialist repeats used to reach nobody: it
stayed in the store, and the report said nothing of it. `kit register` lists
every one beside the specialist finding that reports it, so the lead reviewer
works from a list and `kit verify` (OUT-R16, OUT-R17) checks nothing was dropped.

A specialist finding reports a record or trace finding when it has the same Key
or names the ID. Nothing looser counts: two findings on the same lines can be
two different faults, and a finding wrongly called reported is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from audit_kit.console import ok
from audit_kit.errors import AuditKitError
from audit_kit.findings import LOCATION, Finding, parse_findings
from audit_kit.settings import KitSettings
from audit_kit.workspace import Workspace
from audit_kit.workspaces import locate

OUTPUT = PurePosixPath(".audit/findings-register.md")
RECORDS = PurePosixPath(".audit/files")
TRACES = PurePosixPath(".audit/traces")
# Discovery and the four specialists. A report from 06 on is not a source.
STAGE_FILES = "0[1-5]-*.md"
STAGE_BYTES = 50_000_000
SEVERITIES = ("critical", "high", "medium", "low", "info")
# The final report accounts for each of these by ID (OUT-R17).
ACCOUNTED = frozenset({"critical", "high", "medium"})
# The row for findings whose check is not in a catalogue.
NO_CHECK = "No catalogue check (`X-`)"
STORE_ID = re.compile(r"\b(?:FILE|TRACE)-[a-z0-9]+-\d{3}\b")


@dataclass(frozen=True)
class Entry:
    """One file-record or trace finding, and the specialist findings for it."""

    id: str
    severity: str
    check: str
    title: str
    location: str
    verification: str
    reported_as: tuple[str, ...]


def _parsed(ws: Workspace, paths: list[Path]) -> list[Finding]:
    return [
        finding
        for path in paths
        for finding in parse_findings(
            ws.read_text(path.relative_to(ws.root).as_posix(), STAGE_BYTES)
        )
    ]


def stage_findings(ws: Workspace) -> list[Finding]:
    """Return every finding block in the discovery and specialist outputs.

    Raises:
        WorkspaceError: If an output can't be read.
    """
    return _parsed(ws, sorted((ws.root / ".audit").glob(STAGE_FILES)))


def stored_findings(ws: Workspace) -> list[Finding]:
    """Return every finding block in the file records and the traces.

    Raises:
        WorkspaceError: If a record or a trace can't be read.
    """
    records, traces = ws.root / RECORDS, ws.root / TRACES
    return _parsed(
        ws,
        (sorted(records.rglob("*.md")) if records.is_dir() else [])
        + (sorted(traces.glob("*.md")) if traces.is_dir() else []),
    )


def _rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def _place(location: str) -> tuple[str, int]:
    """Return a location's file and first line, so line 14 sorts before 136."""
    m = LOCATION.match(location)
    return (m.group(1), int(m.group(2) or 0)) if m else (location, 0)


def entries(stored: list[Finding], stage: list[Finding]) -> list[Entry]:
    """Pair each record or trace finding with the specialist findings for it.

    Args:
        stored: The file-record and trace findings.
        stage: The discovery and specialist findings.

    Returns:
        The entries, most severe first, then by location and ID.
    """
    # A finding's place in the outputs, so its reporters are listed in that order.
    order = {finding.id: n for n, finding in enumerate(stage)}
    reported: dict[str, list[str]] = {}
    by_key: dict[str, list[str]] = {}
    for finding in stage:
        if finding.get("Key"):
            by_key.setdefault(finding.get("Key"), []).append(finding.id)
        for named in STORE_ID.findall(finding.text):
            reported.setdefault(named, []).append(finding.id)
    out = [
        Entry(
            id=f.id,
            severity=f.get("Severity").lower(),
            check=f.get("Key").split(":", 1)[0],
            title=f.get("Title"),
            location=f.get("Location"),
            verification=f.get("Verification").lower(),
            reported_as=tuple(
                sorted(
                    {*by_key.get(f.get("Key"), []), *reported.get(f.id, [])},
                    key=order.__getitem__,
                )
            ),
        )
        for f in stored
    ]
    return sorted(out, key=lambda e: (_rank(e.severity), *_place(e.location), e.id))


def build(ws: Workspace) -> list[Entry]:
    """Return the register's entries from the files on disk.

    Raises:
        WorkspaceError: If a record, a trace or a specialist output can't be read.
    """
    return entries(stored_findings(ws), stage_findings(ws))


def unreported(found: list[Entry]) -> list[Entry]:
    """Return the entries no specialist finding reports."""
    return [e for e in found if not e.reported_as]


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _counts(found: list[Entry]) -> list[str]:
    out = [
        "| Severity | Findings | Reported by a specialist | Not reported |",
        "|---|---|---|---|",
    ]
    known = [s for s in SEVERITIES if any(e.severity == s for e in found)]
    other = sorted({e.severity for e in found} - set(SEVERITIES))
    for severity in [*known, *other]:
        group = [e for e in found if e.severity == severity]
        left = len(unreported(group))
        out.append(
            f"| {severity or 'not stated'} | {len(group)} | {len(group) - left} "
            f"| {left} |"
        )
    left = len(unreported(found))
    out.append(f"| Total | {len(found)} | {len(found) - left} | {left} |")
    return out


def _by_check(left: list[Entry]) -> list[str]:
    """Count the unreported findings below Medium by check, most common first.

    A check the reviewer made up (`X-...`) names one finding, so those share a row.
    """
    minor = [e for e in left if e.severity not in ACCOUNTED]
    if not minor:
        return ["None."]
    groups: dict[str, list[Entry]] = {}
    for e in minor:
        groups.setdefault(NO_CHECK if e.check.startswith("X-") else e.check, []).append(
            e
        )
    out = ["| Check | Low | Info | Other | Files |", "|---|---|---|---|---|"]
    for check, group in sorted(
        groups.items(), key=lambda item: (item[0] == NO_CHECK, -len(item[1]), item[0])
    ):
        low = sum(e.severity == "low" for e in group)
        info = sum(e.severity == "info" for e in group)
        files = len({_place(e.location)[0] for e in group})
        out.append(
            f"| {_cell(check)} | {low} | {info} | {len(group) - low - info} | {files} |"
        )
    return out


def render(found: list[Entry]) -> str:
    """Render the register. The same files always give the same text."""
    left = unreported(found)
    reported = [e for e in found if e.reported_as]
    out = [
        "# Register of file-record and trace findings",
        "",
        "`kit register` writes this file. Don't edit it. Run `kit register` again "
        "after a discovery or specialist output (`01` to `05`) changes: "
        "`kit verify` (OUT-R16) fails when the register is out of date.",
        "",
        f"The file reviewers and tracers wrote {len(found)} findings. A specialist "
        "finding reports one of them when it has the same Key or names the ID. "
        f"{len(left)} are in no specialist output. The final report accounts for "
        "each of those rated Medium or higher (OUT-R17). The rest are recorded "
        "here and nowhere else: no verifier and no person has checked them.",
        "",
        "## Counts",
        "",
        *_counts(found),
        "",
        "## Not reported by a specialist",
        "",
    ]
    if left:
        out += [
            "| ID | Severity | Check | Title | Location | Verification |",
            "|---|---|---|---|---|---|",
            *(
                f"| {e.id} | {e.severity} | {_cell(e.check)} | {_cell(e.title)} "
                f"| {_cell(e.location)} | {e.verification} |"
                for e in left
            ),
        ]
    else:
        out.append("None.")
    out += [
        "",
        "## Low and info findings not reported, by check",
        "",
        "The findings in the table above that are rated below Medium, counted by "
        "check. The final report repeats this table, so a reader sees what kinds "
        "of fault are recorded here only.",
        "",
        *_by_check(left),
        "",
        "## Reported by a specialist",
        "",
    ]
    if reported:
        out += [
            "| ID | Severity | Reported as | Check | Location |",
            "|---|---|---|---|---|",
            *(
                f"| {e.id} | {e.severity} | {', '.join(e.reported_as)} "
                f"| {_cell(e.check)} | {_cell(e.location)} |"
                for e in reported
            ),
        ]
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


def register(s: KitSettings, given: str) -> None:
    """Write .audit/findings-register.md (`kit register`).

    Raises:
        AuditKitError: If there is no file-record or trace finding yet.
    """
    ws = locate(s, given).ws
    found = build(ws)
    if not found:
        raise AuditKitError(
            "no file-record or trace findings yet (kit review writes the records)"
        )
    ws.write_text(OUTPUT, render(found))
    ok(
        f"register: {len(found)} findings, {len(unreported(found))} not reported "
        f"by a specialist ({OUTPUT})"
    )
