"""ADR 0007 D3: a pass's JSON is checked before anything is written."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from audit_kit import brief, file_record
from audit_kit.units import Unit
from audit_kit.verification import RECORD_SECTIONS, Searcher, excerpt_problem
from audit_kit.workspace import Workspace

Output = Callable[..., dict[str, Any]]


def test_the_checked_in_schema_is_the_generated_one(kit_home: Path) -> None:
    assert (kit_home / file_record.SCHEMA_PATH).read_text() == file_record.schema()


def test_a_reply_in_a_code_fence_parses(route: Unit, make_output: Output) -> None:
    text = "Here:\n```json\n" + json.dumps(make_output(route)) + "\n```\n"
    assert file_record.parse(text).unit == route.id


def test_a_reply_missing_a_section_lists_it(route: Unit) -> None:
    with pytest.raises(file_record.InvalidOutputError) as raised:
        file_record.parse('{"unit": "u001"}')
    assert any("facts" in p for p in raised.value.problems)


def check(ws: Workspace, route: Unit, make_output: Output, **changes: Any) -> list[str]:
    out = file_record.PassOutput.model_validate(make_output(route, **changes))
    return [
        p.split(":")[0] for p in file_record.problems(ws, route, out, Searcher(ws), [])
    ]


def test_a_valid_output_has_no_problems(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    assert check(ws, route, make_output) == []


@pytest.mark.parametrize(
    ("changes", "check_id"),
    [
        ({"excerpt": "exec(folder)"}, "OUT-F7"),
        ({"location": "lib/other.js:1"}, "OUT-U2"),
        ({"location": "lib/export.js:40"}, "OUT-U2"),
        ({"severity": "high", "edges": []}, "OUT-F9"),
        ({"severity": "high", "trigger": "GET /export?folder=;rm"}, "OUT-U4"),
        ({"key": "NODE-X:lib/other.js"}, "OUT-F2"),
        ({"key": "not a key"}, "OUT-F2"),
        ({"edges": [3]}, "OUT-F1"),
        ({"searched": ["`exec` in `lib/export.js`"]}, "OUT-F8"),
        ({"verification": "verified"}, "OUT-U4"),
        (
            {"severity": "high", "trigger": "GET /export?folder=x", "edges": []},
            "OUT-U4",
        ),
    ],
)
def test_each_record_check_catches_its_failure(
    ws: Workspace,
    route: Unit,
    make_output: Output,
    changes: dict[str, Any],
    check_id: str,
) -> None:
    assert check_id in check(ws, route, make_output, **changes)


def test_two_findings_with_one_key_fail_f3(
    ws: Workspace, route: Unit, make_output: Output, make_finding: Output
) -> None:
    data = make_output(route)
    data["findings"].append(make_finding(route, title="again"))
    out = file_record.PassOutput.model_validate(data)
    problems = file_record.problems(ws, route, out, Searcher(ws), [])
    assert any(p.startswith("OUT-F3") for p in problems)


@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs", "Cc", "Zl", "Zp")),
        min_size=1,
        max_size=60,
    ).filter(
        lambda s: s.strip() and "****" not in s and "..." not in s and "…" not in s
    )
)
def test_any_line_quoted_as_the_kit_quotes_it_matches_itself(line: str) -> None:
    lines = {"a.js": [line]}
    problem = excerpt_problem(
        Workspace(Path(".")), "a.js:1", file_record.quoted(line), lines.get
    )
    assert problem is None


@given(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs", "Cc", "Zl", "Zp")),
        min_size=1,
        max_size=60,
    ).filter(
        lambda s: (
            s.strip()
            and "****" not in s
            and "..." not in s
            and "…" not in s
            and "`" not in s
        )
    )
)
def test_an_excerpt_in_a_record_table_cell_matches_its_line(line: str) -> None:
    lines = {"a.py": [line]}
    cell = file_record._cell(file_record.quoted(line))
    problem = excerpt_problem(Workspace(Path(".")), "a.py:1", cell, lines.get)
    assert problem is None


def test_a_python_union_excerpt_escaped_in_a_table_matches() -> None:
    lines = {"a.py": ["    review_id: UUID | None = None"]}
    problem = excerpt_problem(
        Workspace(Path(".")), "a.py:1", "`review_id: UUID \\| None = None`", lines.get
    )
    assert problem is None


def write_record(ws: Workspace, route: Unit, make_output: Output) -> str:
    meta = brief.read_meta(ws, route.id)
    assert meta is not None
    out = file_record.PassOutput.model_validate(make_output(route, evidence=""))
    prov = file_record.Provenance(
        label="a",
        provider="anthropic",
        model_family="claude",
        model="m",
        harness="h",
        repository="demo",
        commit="abc",
        branch="audit/x",
        started_utc="t0",
        finished_utc="t1",
    )
    record = file_record.build(route, out, prov, meta)
    file_record.write(ws, route, record, "brief.md")
    return ws.read_text(route.record)


def test_the_rendered_record_has_every_required_section(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    md = write_record(ws, route, make_output)
    assert all(f"\n## {section}" in md for section in RECORD_SECTIONS)


def test_the_kit_numbers_findings_and_links_their_edges(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    md = write_record(ws, route, make_output)
    assert "### FILE-u001-001 Query string reaches a shell command" in md
    assert "- Related: EDGE-u001-001" in md
    assert "- Findings that depend on it: FILE-u001-001" in md


def test_missing_evidence_is_built_from_location_and_excerpt(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    md = write_record(ws, route, make_output)
    assert "- Evidence: exec(`zip -r out.zip ${folder}`); (lib/export.js:6)" in md


def test_a_stored_record_reads_back_unchanged(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    write_record(ws, route, make_output)
    record = file_record.read(ws, route)
    assert record is not None
    assert record.output == file_record.PassOutput.model_validate(
        make_output(route, evidence="")
    )


def test_a_stored_record_that_is_not_one_is_refused(ws: Workspace, route: Unit) -> None:
    ws.write_text(file_record.record_paths(route)[1], '{"output": {}}')
    with pytest.raises(file_record.InvalidRecordError):
        file_record.read(ws, route)


def test_a_verified_finding_needs_no_open_edge(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    assert check(ws, route, make_output, verification="verified", edges=[]) == []


def test_the_summary_counts_findings_edges_and_gates(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    write_record(ws, route, make_output)
    record = file_record.read(ws, route)
    assert record is not None
    s = record.summary
    assert (s.medium, s.high, s.verified, s.unverified, s.open_edges) == (1, 0, 0, 1, 1)
    assert (s.facts, s.flows, s.gates_failed, s.gates_unavailable) == (1, 1, 3, 2)


def test_the_summary_leads_the_record(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    md = write_record(ws, route, make_output)
    assert md.index("## Summary") < md.index("## Facts")
    assert "| 0 critical, 0 high, 1 medium, 0 low, 0 info | 0 | 1 | 1 |" in md


def test_each_finding_says_whether_it_is_verified(
    ws: Workspace, briefs: list[Unit], route: Unit, make_output: Output
) -> None:
    assert "- Verification: unverified" in write_record(ws, route, make_output)


LISTED = ["NODE-DANGEROUS-SINK", "JS-VAR"]


def coverage(
    ws: Workspace, route: Unit, data: dict[str, Any], listed: list[str]
) -> list[str]:
    out = file_record.PassOutput.model_validate(data)
    found = file_record.problems(ws, route, out, Searcher(ws), listed)
    return [p for p in found if p.startswith("OUT-U6")]


def test_answering_every_listed_check_passes_u6(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    assert coverage(ws, route, make_output(route, LISTED), LISTED) == []


def test_a_check_left_unanswered_fails_u6(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    problems = coverage(
        ws, route, make_output(route, LISTED), [*LISTED, "JS-OR-DEFAULT"]
    )
    assert problems == ["OUT-U6: checks not answered: JS-OR-DEFAULT"]


def test_a_check_marked_found_without_a_finding_fails_u6(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    data = make_output(route, LISTED)
    data["checks"][1]["result"] = "found"
    assert coverage(ws, route, data, LISTED) == [
        "OUT-U6: JS-VAR is found, but no finding has that Key"
    ]


def test_a_finding_whose_check_says_not_found_fails_u6(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    data = make_output(route, LISTED)
    data["checks"][0]["result"] = "not found"
    assert coverage(ws, route, data, LISTED) == [
        "OUT-U6: NODE-DANGEROUS-SINK has a finding, so its result is found"
    ]


def test_a_check_not_in_the_brief_fails_u6(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    problems = coverage(ws, route, make_output(route, LISTED), ["NODE-DANGEROUS-SINK"])
    assert problems == ["OUT-U6: checks not in this brief's list: JS-VAR"]


JOB = (
    "def load(path):\n"  # 1
    "    try:\n"  # 2
    "        return read(path)\n"  # 3
    "    except OSError:\n"  # 4
    "        return None\n"  # 5
)
HANDLER_CHECKS = ["SLOP-SWALLOW", "SLOP-LOSSY-HANDLER"]


def handler_problems(
    ws: Workspace,
    code: str,
    answers: dict[str, tuple[str, str]],
    prefix: str = "OUT-U7",
) -> list[str]:
    """Check an output with no findings for a one-file unit holding `code`."""
    ws.write_text("lib/job.py", code)
    unit = Unit("u009", "lib/job.py", "", 1, len(code.splitlines()), "file")
    data = {
        "unit": unit.id,
        "checks": [
            {"check": check, "result": result, "note": note}
            for check, (result, note) in answers.items()
        ],
        "facts": [],
        "comments": [],
        "flows": [],
        "functions": [],
        "findings": [],
        "edges": [],
        "limitations": [],
    }
    out = file_record.PassOutput.model_validate(data)
    found = file_record.problems(ws, unit, out, Searcher(ws), list(answers))
    return [p for p in found if p.startswith(prefix)]


def test_a_handler_check_not_found_without_a_note_fails_u7(ws: Workspace) -> None:
    answers = dict.fromkeys(HANDLER_CHECKS, ("not found", ""))
    problems = handler_problems(ws, JOB, answers)
    assert [p.split(" is ")[0] for p in problems] == [
        "OUT-U7: SLOP-SWALLOW",
        "OUT-U7: SLOP-LOSSY-HANDLER",
    ]


def test_a_note_that_names_no_line_in_the_unit_fails_u7(ws: Workspace) -> None:
    answers = {"SLOP-SWALLOW": ("not found", "the handler at line 40 is deliberate")}
    assert len(handler_problems(ws, JOB, answers)) == 1


def test_a_note_that_names_the_handler_line_passes_u7(ws: Workspace) -> None:
    note = "line 4 returns None, which the caller checks"
    answers = dict.fromkeys(HANDLER_CHECKS, ("not found", note))
    assert handler_problems(ws, JOB, answers, prefix="OUT-U") == []


def test_a_unit_with_no_handler_needs_no_note(ws: Workspace) -> None:
    answers = dict.fromkeys(HANDLER_CHECKS, ("not found", ""))
    assert (
        handler_problems(ws, "def load(path):\n    return read(path)\n", answers) == []
    )


def test_only_the_handler_checks_need_the_note(ws: Workspace) -> None:
    answers = {
        "SLOP-DUP": ("not found", ""),
        "SLOP-SWALLOW": ("not applicable", "no error path"),
    }
    assert handler_problems(ws, JOB, answers) == []


@pytest.mark.parametrize(
    "handler",
    [
        "with suppress(OSError):\n    path.unlink()\n",
        "try {\n  run();\n} catch (e) {\n}\n",
        "try {\n  run();\n} catch {\n}\n",
        "run().catch(() => {});\n",
    ],
)
def test_each_kind_of_handler_is_seen(ws: Workspace, handler: str) -> None:
    answers = {"SLOP-SWALLOW": ("not found", "")}
    assert len(handler_problems(ws, handler, answers)) == 1


def test_the_word_except_in_a_comment_is_not_a_handler(ws: Workspace) -> None:
    code = "# every path except the root\nvalue = 1\n"
    assert handler_problems(ws, code, {"SLOP-SWALLOW": ("not found", "")}) == []


def guided(
    ws: Workspace, route: Unit, make_output: Output, **changes: Any
) -> list[str]:
    """Return the OUT-U8 problems for the route unit's finding, as a SLOP finding."""
    data = make_output(route, key=f"SLOP-SWALLOW:{route.path}", **changes)
    out = file_record.PassOutput.model_validate(data)
    found = file_record.problems(ws, route, out, Searcher(ws), [])
    return [p for p in found if p.startswith("OUT-U8")]


@pytest.mark.parametrize("severity", ["medium", "high", "critical"])
def test_a_guided_finding_rated_medium_or_higher_needs_evidence(
    ws: Workspace, route: Unit, make_output: Output, severity: str
) -> None:
    assert guided(ws, route, make_output, severity=severity) == [
        f"OUT-U8: findings[1]: {severity} under the severity guide: name the "
        "question answered yes and the line number that shows it in evidence"
    ]


def test_evidence_that_names_no_line_in_the_unit_fails_u8(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    evidence = "Ruff BLE001 fires and the caller is told it succeeded, see line 40"
    assert len(guided(ws, route, make_output, evidence=evidence)) == 1


def test_evidence_that_names_the_line_passes_u8(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    evidence = "Medium: line 7 sends ok after the failed call"
    assert guided(ws, route, make_output, evidence=evidence) == []


@pytest.mark.parametrize("severity", ["low", "info"])
def test_a_low_guided_finding_needs_no_evidence(
    ws: Workspace, route: Unit, make_output: Output, severity: str
) -> None:
    assert guided(ws, route, make_output, severity=severity) == []


def test_a_finding_outside_the_guided_catalogue_needs_no_evidence(
    ws: Workspace, route: Unit, make_output: Output
) -> None:
    out = file_record.PassOutput.model_validate(make_output(route))
    found = file_record.problems(ws, route, out, Searcher(ws), [])
    assert [p for p in found if p.startswith("OUT-U8")] == []


def test_the_brief_lists_every_check_id_in_its_rules(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    meta = brief.read_meta(ws, route.id)
    assert meta is not None
    assert {"JS-FLOATING", "NODE-DANGEROUS-SINK", "SLOP-SWALLOW"} <= set(meta.check_ids)
    assert "CHECK-ID" not in meta.check_ids
