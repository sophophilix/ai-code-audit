"""`kit register`: which specialist finding reports each record and trace finding."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from audit_kit import register
from audit_kit.errors import AuditKitError
from audit_kit.findings import parse_findings
from audit_kit.settings import KitSettings
from audit_kit.units import Unit
from audit_kit.workspace import Workspace


def block(fid: str, key: str, severity: str, line: int = 4, more: str = "") -> str:
    return (
        f"### {fid} Title of {fid}\n- Key: {key}\n- Severity: {severity}\n"
        f"- Location: lib/export.js:{line}\n- Verification: verified\n{more}"
    )


RECORD = (
    "## Findings\n"
    + block("FILE-u001-001", "NODE-EXEC:lib/export.js", "medium", 6)
    + block("FILE-u001-002", "SLOP-COMMENT:lib/export.js", "low", 3)
    + block("FILE-u001-003", "X-order:lib/export.js", "low", 4)
    + "## Open edges\n"
)
TRACE = "## Findings\n" + block("TRACE-t01-001", "X-zip:lib/export.js", "High", 6)
SECURITY = (
    "Map: FILE-u001-002 was read.\n"
    "## Findings\n"
    + block("SEC-001", "NODE-EXEC:lib/export.js", "high", 6)
    + block(
        "SEC-002", "X-archive:lib/export.js", "high", 6, "- Related: TRACE-t01-001\n"
    )
    + block("SEC-003", "X-other:lib/export.js", "low", 4)
)


@pytest.fixture
def audited(ws: Workspace) -> Workspace:
    """Provide a workspace with one record, one trace and one specialist output."""
    ws.write_text(".audit/files/lib/export.js.md", RECORD)
    ws.write_text(".audit/traces/get-export.md", TRACE)
    ws.write_text(".audit/04-security.md", SECURITY)
    return ws


def by_id(ws: Workspace) -> dict[str, tuple[str, ...]]:
    return {e.id: e.reported_as for e in register.build(ws)}


def test_a_specialist_finding_with_the_same_key_reports_it(audited: Workspace) -> None:
    assert by_id(audited)["FILE-u001-001"] == ("SEC-001",)


def test_a_specialist_finding_that_names_the_id_reports_it(audited: Workspace) -> None:
    assert by_id(audited)["TRACE-t01-001"] == ("SEC-002",)


def test_an_id_named_outside_a_finding_block_reports_nothing(
    audited: Workspace,
) -> None:
    assert by_id(audited)["FILE-u001-002"] == ()


def test_a_finding_on_the_same_lines_under_another_key_reports_nothing(
    audited: Workspace,
) -> None:
    # SEC-003 cites the line FILE-u001-003 cites. It may be another fault.
    assert by_id(audited)["FILE-u001-003"] == ()


def test_two_specialists_on_one_finding_are_both_listed(audited: Workspace) -> None:
    audited.write_text(
        ".audit/03-engineering.md",
        block("ENG-001", "X-shell:lib/export.js", "low", 6, "Same as FILE-u001-001.\n")
        + block("ENG-002", "NODE-EXEC:lib/export.js", "low", 6, "- Related: FILE-u001-001\n"),
    )  # fmt: skip
    assert by_id(audited)["FILE-u001-001"] == ("ENG-001", "ENG-002", "SEC-001")


def test_a_report_from_a_later_stage_is_not_a_source(audited: Workspace) -> None:
    audited.write_text(
        ".audit/06-verification.md", block("SEC-009", "X-order:lib/export.js", "low")
    )
    assert by_id(audited)["FILE-u001-003"] == ()


def test_entries_run_from_most_severe_then_by_place(audited: Workspace) -> None:
    assert [e.id for e in register.build(audited)] == [
        "TRACE-t01-001",
        "FILE-u001-001",
        "FILE-u001-002",
        "FILE-u001-003",
    ]


def test_a_later_line_sorts_after_an_earlier_one_whatever_its_digits() -> None:
    stored = parse_findings(
        block("FILE-u001-001", "X-a:f.js", "low", 136)
        + block("FILE-u001-002", "X-b:f.js", "low", 14)
        + "### FILE-u001-003 No place\n- Key: X-c:f.js\n- Severity: low\n"
    )
    assert [e.id for e in register.entries(stored, [])] == [
        "FILE-u001-003",
        "FILE-u001-002",
        "FILE-u001-001",
    ]


def test_the_register_counts_and_lists_what_no_specialist_reports(
    audited: Workspace,
) -> None:
    text = register.render(register.build(audited))
    assert "wrote 4 findings" in text
    assert "2 are in no specialist output" in text
    assert "| high | 1 | 1 | 0 |" in text
    assert "| low | 2 | 0 | 2 |" in text
    assert "| Total | 4 | 2 | 2 |" in text
    left, reported = text.split("## Reported by a specialist")
    assert (
        "| FILE-u001-002 | low | SLOP-COMMENT | Title of FILE-u001-002 "
        "| lib/export.js:3 | verified |"
    ) in left
    assert "FILE-u001-001" not in left.split("## Not reported by a specialist")[1]
    assert "| TRACE-t01-001 | high | SEC-002 | X-zip | lib/export.js:6 |" in reported


def test_unreported_findings_below_medium_are_counted_by_check() -> None:
    stored = parse_findings(
        block("FILE-u001-001", "SLOP-DUP:a.js", "low")
        + block("FILE-u002-001", "SLOP-DUP:b.js", "info").replace(
            "lib/export.js", "b.js"
        )
        + block("FILE-u003-001", "SLOP-DUP:a.js", "odd")
        + block("FILE-u001-002", "PY-ASSERT-CHECK:a.js", "low")
        + block("FILE-u001-003", "X-one:a.js", "low")
        + block("FILE-u001-004", "X-two:a.js", "low")
        + block("FILE-u001-005", "X-three:a.js", "low")
        + block("FILE-u001-006", "SLOP-GOD:a.js", "medium")
        + block("FILE-u001-007", "NODE-EXEC:lib/export.js", "low")
    )
    text = register.render(register.entries(stored, parse_findings(SECURITY)))
    section = text.split("## Low and info findings not reported, by check")[1]
    rows = [r for r in section.split("## Reported")[0].splitlines() if r[:1] == "|"]
    assert rows[2:] == [
        "| SLOP-DUP | 1 | 1 | 1 | 2 |",
        "| PY-ASSERT-CHECK | 1 | 0 | 0 | 1 |",
        "| No catalogue check (`X-`) | 3 | 0 | 0 | 1 |",
    ]


def test_the_same_files_give_the_same_register(audited: Workspace) -> None:
    assert register.render(register.build(audited)) == register.render(
        register.build(audited)
    )


def test_a_title_cannot_break_the_table() -> None:
    stored = parse_findings(
        "### FILE-u001-001 a | b\n- Key: X-a:f.js\n- Severity: odd\n- Location: f.js:1\n"
    )
    text = register.render(register.entries(stored, []))
    assert "| FILE-u001-001 | odd | X-a | a \\| b | f.js:1 |  |" in text
    assert "| odd | 1 | 0 | 1 |" in text


def test_a_register_with_nothing_left_says_none(audited: Workspace) -> None:
    stored = parse_findings(TRACE)
    text = register.render(register.entries(stored, parse_findings(SECURITY)))
    assert "## Not reported by a specialist\n\nNone.\n" in text
    assert "by check\n\nThe findings" in text
    assert "recorded here only.\n\nNone.\n" in text
    assert register.render(register.entries(stored, [])).endswith(
        "## Reported by a specialist\n\nNone.\n"
    )


def test_the_command_writes_the_register(
    audited: Workspace,
    settings: KitSettings,
    ready: Callable[..., list[Unit]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    ready()
    register.register(settings, str(audited.root))
    assert audited.read_text(register.OUTPUT) == register.render(
        register.build(audited)
    )
    assert "4 findings, 2 not reported by a specialist" in capsys.readouterr().out


def test_the_command_refuses_a_workspace_with_no_findings(
    ws: Workspace, settings: KitSettings, ready: Callable[..., list[Unit]]
) -> None:
    ready()
    with pytest.raises(AuditKitError, match="no file-record or trace findings yet"):
        register.register(settings, str(ws.root))
    assert not ws.is_file(register.OUTPUT)
