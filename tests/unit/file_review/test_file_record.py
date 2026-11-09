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


def test_the_brief_lists_every_check_id_in_its_rules(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    meta = brief.read_meta(ws, route.id)
    assert meta is not None
    assert {"JS-FLOATING", "NODE-DANGEROUS-SINK", "SLOP-SWALLOW"} <= set(meta.check_ids)
    assert "CHECK-ID" not in meta.check_ids
