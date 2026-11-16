from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from audit_kit import register, search, verification
from audit_kit.runner import CommandError, Result
from audit_kit.search import first_match, main
from audit_kit.verification import Status, check, rejected_ids
from audit_kit.workspace import Workspace

HEADER = "---\nkit_version: 0.7.1\nagent: security\nmodel: m\ncommit: abc\nstatus: complete\n---\n"


def finding(
    fid: str,
    key: str,
    severity: str = "high",
    location: str = "app.js:2",
    excerpt: str = "`b`",
) -> str:
    return (
        f"### {fid} Title\n- Key: {key}\n- Category: security\n- Severity: {severity}\n"
        f"- Confidence: high\n- Location: {location}\n- Evidence: seen\n"
        f"- Excerpt: {excerpt}\n- Trigger: GET /?x=1 reaches it\n"
    )


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    (root / ".audit/work/04-security").mkdir(parents=True)
    (root / ".audit/diagrams").mkdir()
    (root / "app.js").write_text("a\nb\nc\n")
    audit = root / ".audit"
    (audit / "04-security.md").write_text(
        HEADER
        + finding("SEC-001", "EXP-TRUST-PROXY:app.js")
        + finding("SEC-002", "X-foo:app.js", "medium", "app.js:1-3", "`a b ... c`")
    )
    (audit / "06-verification.md").write_text("| SEC-001 | high | Confirmed |\n")
    (audit / "07-final-report.md").write_text(
        "SEC-001 is serious.\n## Not examined\nNone.\n![Request flow from residents through the WAF to the app](d.png)\n"
    )
    (audit / "08-backlog.csv").write_text(
        'Work Item Type,Title,Description,Acceptance Criteria,Priority,Tags\n"Bug","SEC-001 x","d","proxy hop count set","2","audit"\n'
    )
    (audit / "work/04-security/LOCK").write_text("state: released\n")
    (audit / "diagrams/as-is.ir.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "app",
                        "style": "image;image=img/lib/azure2/app_services/App_Services.svg;",
                        "provenance": {"path": "app.js", "line": 1},
                    },
                ]
            }
        )
    )
    return Workspace(root)


def failed(ws: Workspace) -> list[str]:
    return [r.line() for r in check(ws).results if r.status is Status.FAIL]


def write(ws: Workspace, name: str, text: str) -> None:
    path = ws.root / ".audit" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_good_workspace_passes(ws: Workspace) -> None:
    assert failed(ws) == []


def test_missing_field_and_missing_line_fail(ws: Workspace) -> None:
    write(
        ws,
        "04-security.md",
        HEADER
        + finding("SEC-001", "EXP-X:app.js", location="app.js:99").replace(
            "- Evidence: seen\n", ""
        ),
    )
    lines = "\n".join(failed(ws))
    assert "OUT-F1" in lines
    assert "OUT-F4" in lines


def test_a_location_outside_the_workspace_fails(ws: Workspace, tmp_path: Path) -> None:
    # Regression for review finding F8: ../ paths are refused, not opened.
    (tmp_path / "outside.js").write_text("x\n" * 50)
    write(
        ws,
        "04-security.md",
        HEADER + finding("SEC-001", "EXP-X:app.js", location="../outside.js:2"),
    )
    assert any("OUT-F4" in line for line in failed(ws))


def test_duplicate_and_malformed_keys_fail(ws: Workspace) -> None:
    write(
        ws,
        "04-security.md",
        HEADER
        + finding("SEC-001", "EXP-A:app.js")
        + finding("SEC-002", "EXP-A:app.js")
        + finding("SEC-003", "upload limit"),
    )
    lines = "\n".join(failed(ws))
    assert "OUT-F3" in lines
    assert "OUT-F2" in lines


def test_in_progress_output_and_active_lock_fail(ws: Workspace) -> None:
    write(
        ws,
        "04-security.md",
        (HEADER + finding("SEC-001", "EXP-A:app.js")).replace(
            "status: complete", "status: in-progress"
        ),
    )
    (ws.root / ".audit/work/04-security/LOCK").write_text("state: active\n")
    lines = "\n".join(failed(ws))
    assert "04-security.md: status in-progress" in lines
    assert "still active" in lines


def test_report_with_unknown_id_missing_high_and_vague_alt_fails(ws: Workspace) -> None:
    write(ws, "07-final-report.md", "See SEC-009.\n![diagram](d.png)\n")
    lines = "\n".join(failed(ws))
    assert "unknown ['SEC-009']" in lines
    assert "OUT-R2" in lines
    assert "OUT-R6" in lines


def test_a_rejected_high_may_be_absent_from_the_report(ws: Workspace) -> None:
    write(
        ws, "06-verification.md", "| SEC-001 | high | Rejected | mitigated by proxy |\n"
    )
    write(ws, "07-final-report.md", "Nothing serious.\n")
    assert not any("OUT-R2" in line for line in failed(ws))


def test_a_note_mentioning_rejected_does_not_excuse_a_confirmed_high(
    ws: Workspace,
) -> None:
    # Regression for review finding F5.
    write(
        ws,
        "06-verification.md",
        "| SEC-001 | high | Confirmed | the mitigation theory was rejected |\n",
    )
    write(ws, "07-final-report.md", "Nothing serious.\n")
    assert any("OUT-R2" in line for line in failed(ws))


def test_verdict_lines_are_recognised() -> None:
    assert rejected_ids(
        "### SEC-004 Upload limit\n- Verdict: Rejected (unreachable)\n"
    ) == {"SEC-004"}
    assert rejected_ids("### SEC-005 X\n- Verdict: Confirmed\n") == set()
    assert rejected_ids("SEC-004 Verdict: Rejected (unreachable)") == {"SEC-004"}


def test_unverified_high_fails(ws: Workspace) -> None:
    write(ws, "06-verification.md", "nothing\n")
    assert any("OUT-V1" in line for line in failed(ws))


def test_backlog_header_and_rows_are_checked(ws: Workspace) -> None:
    write(
        ws,
        "08-backlog.csv",
        'Work Item Type,Title,Description,Acceptance Criteria,Priority,Tags\n"Bug","t","d","","7","x"\n',
    )
    assert any("OUT-B1" in line for line in failed(ws))
    write(ws, "08-backlog.csv", "Title,Type\n")
    assert any("OUT-B1  header" in line for line in failed(ws))


def test_legacy_icons_and_missing_provenance_fail(ws: Workspace) -> None:
    write(
        ws,
        "diagrams/as-is.ir.json",
        json.dumps({"nodes": [{"id": "x", "style": "shape=mxgraph.azure.sql;"}]}),
    )
    lines = "\n".join(failed(ws))
    assert "OUT-D4" in lines
    assert "OUT-D3" in lines


def test_pass_labelled_ids_are_understood(ws: Workspace) -> None:
    write(ws, "04-security.a.md", HEADER + finding("SEC-a-001", "EXP-B:app.js", "low"))
    assert failed(ws) == []


def test_a_high_without_a_trigger_fails(ws: Workspace) -> None:
    write(
        ws,
        "04-security.md",
        HEADER
        + finding("SEC-001", "EXP-A:app.js").replace(
            "- Trigger: GET /?x=1 reaches it\n", ""
        ),
    )
    assert any("OUT-F9" in line and "SEC-001" in line for line in failed(ws))


def test_a_report_without_a_not_examined_section_fails(ws: Workspace) -> None:
    write(ws, "07-final-report.md", "SEC-001 is serious.\n")
    assert any("OUT-R11" in line for line in failed(ws))


def test_discovery_table_excerpts_are_checked(ws: Workspace) -> None:
    write(
        ws,
        "01-discovery.md",
        HEADER.replace("security", "discovery")
        + "## Routes\n| Method | Handler | Excerpt |\n|---|---|---|\n"
        + "| GET | `app.js:2` | `b` |\n| POST | `app.js:3` | `a` |\n"
        + "| PUT | config only | |\n",
    )
    lines = [line for line in failed(ws) if "OUT-F10" in line]
    assert len(lines) == 1
    assert "2 table excerpts" in lines[0] and "'a'" in lines[0]


def test_a_recommended_package_that_does_not_exist_fails(ws: Workspace) -> None:
    write(
        ws,
        "03-engineering.md",
        HEADER.replace("security", "engineer")
        + finding("ENG-001", "X-clone:app.js", "low")
        + "- Packages: made-up-pkg\n",
    )
    assert any("OUT-R12" in line and "run kit lookup" in line for line in failed(ws))
    write(
        ws,
        "scans/upstream-status.json",
        '{"policy": "allow", "results": [{"subject": "made-up-pkg", '
        '"check": "recommended package", "result": "not found"}]}',
    )
    assert any(
        "remove or replace ['made-up-pkg (not found)']" in line for line in failed(ws)
    )


def test_a_search_that_times_out_fails_the_claim(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_slow(*_: object, **__: object) -> Result:
        raise CommandError("python3 timed out after 30s")

    monkeypatch.setattr(verification, "run", too_slow)
    write(
        ws,
        "03-engineering.md",
        HEADER.replace("security", "engineer")
        + finding("ENG-001", "X-slow:app.js", "low")
        + "- Searched: `rateLimit` in `app.js`\n",
    )
    assert any("OUT-F8" in line and "took over 30 s" in line for line in failed(ws))


@pytest.mark.integration
def test_a_search_that_backtracks_badly_fails_instead_of_hanging(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding F5: (a|aa)+ passes the nested-quantifier filter. Real
    # process and real time; the fake-run test above is the deterministic one.
    monkeypatch.setattr(verification, "SEARCH_SECONDS", 1.0)
    (ws.root / "slow.txt").write_text("a" * 40 + "!\n")
    write(
        ws,
        "03-engineering.md",
        HEADER.replace("security", "engineer")
        + finding("ENG-001", "X-slow:app.js", "low")
        + "- Searched: `(a|aa)+b` in `slow.txt`\n",
    )
    assert any("OUT-F8" in line and "took over 1 s" in line for line in failed(ws))


def test_the_search_process_reports_the_first_match(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib/a.js").write_text("x\nrateLimit()\n")
    ws = Workspace(tmp_path)
    assert first_match(ws, re.compile("rateLimit"), ["lib"]) == "lib/a.js:2"
    assert first_match(ws, re.compile("nope"), ["."]) == ""
    assert main([str(tmp_path), "(", "lib"]) == 2


def test_a_search_process_that_fails_fails_the_claim(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A crash must never read as "nothing found".
    monkeypatch.setattr(
        verification, "run", lambda *a, **k: Result(1, b"", b"ImportError: boom")
    )
    write(
        ws,
        "03-engineering.md",
        HEADER.replace("security", "engineer")
        + finding("ENG-001", "X-none:app.js", "low")
        + "- Searched: `rateLimit` in `app.js`\n",
    )
    assert any("search failed (exit 1): ImportError: boom" in x for x in failed(ws))


def test_the_search_process_signals_the_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "big.txt").write_text("x" * 50)
    monkeypatch.setattr(search, "TOTAL_LIMIT", 10)
    assert main([str(tmp_path), "y", "."]) == search.LIMIT_REACHED


def test_a_search_walks_only_the_paths_it_names(tmp_path: Path) -> None:
    from audit_kit.search import files_under

    for rel in ("lib/a.js", "lib/deep/b.js", "other/c.js", ".audit/x.md", "top.js"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n")
    ws = Workspace(tmp_path)
    assert files_under(ws, ["lib", "top.js"]) == ["lib/a.js", "lib/deep/b.js", "top.js"]
    assert ".audit/x.md" not in files_under(ws, ["."])
    assert files_under(ws, [".audit"]) == []


def test_a_report_for_a_ui_needs_a_still_to_check_by_hand_section(
    ws: Workspace,
) -> None:
    assert not any("OUT-R13" in line for line in failed(ws))  # no UI: not required
    write(
        ws,
        "detected.md",
        "## Profiles to load\n\nnode-express, web-accessibility, ai-governance\n",
    )
    assert any("OUT-R13" in line and "missing" in line for line in failed(ws))
    write(
        ws,
        "07-final-report.md",
        "SEC-001 is serious.\n## Not examined\nNone.\n## Still to check by hand\n- NVDA pass\n"
        "![Request flow from residents through the WAF to the app](d.png)\n",
    )
    assert not any("OUT-R13" in line for line in failed(ws))


def test_a_report_may_cite_a_trace_finding(ws: Workspace) -> None:
    write(
        ws,
        "traces/login.md",
        HEADER.replace("security", "tracer")
        + "## Findings\n"
        + finding("TRACE-t01-001", "X-cross-file:app.js", "low"),
    )
    write(
        ws,
        "07-final-report.md",
        "SEC-001 and TRACE-t01-001 are one cause.\n## Not examined\nNone.\n",
    )
    assert not [line for line in failed(ws) if " OUT-R1 " in line]


def lines(ws: Workspace, check_id: str) -> list[str]:
    return [r.line() for r in check(ws).results if r.check == check_id]


def trace(ws: Workspace, *blocks: str) -> None:
    write(
        ws,
        "traces/login.md",
        HEADER.replace("security", "tracer") + "## Findings\n" + "".join(blocks),
    )


def write_register(ws: Workspace) -> None:
    ws.write_text(register.OUTPUT, register.render(register.build(ws)))


def test_the_register_checks_wait_for_findings_and_for_the_register(
    ws: Workspace,
) -> None:
    assert lines(ws, "OUT-R16") == ["SKIP  OUT-R16 no file-record or trace findings"]
    trace(ws, finding("TRACE-t01-001", "X-cross-file:app.js", "medium"))
    (ws.root / ".audit/07-final-report.md").unlink()
    assert lines(ws, "OUT-R16") == [
        "SKIP  OUT-R16 no findings-register.md yet (kit register, after Stage 2)"
    ]
    assert lines(ws, "OUT-R17") == []


def test_a_report_with_no_register_fails(ws: Workspace) -> None:
    trace(ws, finding("TRACE-t01-001", "X-cross-file:app.js", "medium"))
    assert lines(ws, "OUT-R16") == [
        "FAIL  OUT-R16 no findings-register.md; run kit register"
    ]


def test_a_register_older_than_a_specialist_output_fails(ws: Workspace) -> None:
    trace(ws, finding("TRACE-t01-001", "X-foo:app.js", "low"))
    (ws.root / ".audit/07-final-report.md").unlink()
    write_register(ws)
    assert lines(ws, "OUT-R16") == [
        "PASS  OUT-R16 findings-register.md: 1 findings, 0 not reported by a specialist"
    ]
    write(ws, "04-security.md", HEADER + finding("SEC-001", "EXP-TRUST-PROXY:app.js"))
    assert lines(ws, "OUT-R16") == [
        "FAIL  OUT-R16 findings-register.md: 1 findings, 1 not reported by a "
        "specialist; out of date, run kit register again"
    ]


def test_the_report_has_to_name_the_register(ws: Workspace) -> None:
    trace(ws, finding("TRACE-t01-001", "X-foo:app.js", "low"))
    write_register(ws)
    assert "FAIL  OUT-R16 report does not name findings-register.md" in lines(
        ws, "OUT-R16"
    )
    write(ws, "07-final-report.md", "## Not examined\nSee findings-register.md.\n")
    assert [line[:4] for line in lines(ws, "OUT-R16")] == ["PASS", "PASS"]


def test_a_medium_no_specialist_reports_has_to_be_named(ws: Workspace) -> None:
    trace(
        ws,
        finding("TRACE-t01-001", "X-cross-file:app.js", "medium"),
        finding("TRACE-t01-002", "X-other:app.js", "high"),
        finding("TRACE-t01-003", "X-small:app.js", "low"),
        finding("TRACE-t01-004", "X-foo:app.js", "medium"),  # SEC-002 has this Key
    )
    write_register(ws)
    assert lines(ws, "OUT-R17") == [
        "FAIL  OUT-R17 medium and above not reported by a specialist: 0/2 named in "
        "the report or backlog; missing ['TRACE-t01-002', 'TRACE-t01-001']"
    ]
    write(ws, "07-final-report.md", "## Not examined\nTRACE-t01-002 holds.\n")
    backlog = ws.root / ".audit/08-backlog.csv"
    backlog.write_text(
        backlog.read_text() + '"Task","TRACE-t01-001 x","d","a","3","t"\n'
    )
    assert lines(ws, "OUT-R17") == [
        "PASS  OUT-R17 medium and above not reported by a specialist: 2/2 named in "
        "the report or backlog"
    ]
