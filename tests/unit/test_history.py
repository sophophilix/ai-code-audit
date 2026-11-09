"""Hotspots and coupling from git history, ending at the audited commit."""

from __future__ import annotations

import json
from pathlib import Path

from audit_kit.history import RECORD, analyse, complexity, parse_log, report
from audit_kit.workspace import Workspace


def commit(author: str, *files: tuple[str, int]) -> str:
    return f"{RECORD}{author}\n\n" + "".join(f"{n}\t0\t{p}\n" for p, n in files)


LOG = (
    "".join(commit("A@x", ("server.js", 10), ("lib/db.js", 3)) for _ in range(5))
    + commit("b@x", ("server.js", 2), ("README.md", 1))
    + commit("c@x", ("lib/db.js", 1))
    + f"{RECORD}a@x\n\n-\t-\tlogo.png\n"
)
OWN = {"server.js", "lib/db.js", "lib/quiet.js"}


def test_parse_log_reads_authors_and_line_counts() -> None:
    commits = parse_log(LOG)
    assert len(commits) == 8
    assert commits[0] == ("a@x", [("server.js", 10), ("lib/db.js", 3)])
    assert commits[-1] == ("a@x", [("logo.png", 0)])


def test_hotspots_rank_change_times_complexity_and_count_authors() -> None:
    out = analyse(parse_log(LOG), OWN, {"lib/db.js": 20, "server.js": 4})
    first, second = out["hotspots"]
    assert first["file"] == "lib/db.js" and first["score"] == 1.0
    assert (second["file"], second["commits"], second["authors"]) == ("server.js", 6, 2)
    assert second["lines_changed"] == 52
    assert "README.md" not in {f["file"] for f in out["hotspots"]}


def test_files_that_change_together_are_coupled() -> None:
    out = analyse(parse_log(LOG), OWN, {})
    assert out["coupled"] == [
        {"files": ["lib/db.js", "server.js"], "commits_together": 5}
    ]


def test_bulk_commits_are_not_coupling() -> None:
    files = [(f"f{i}.js", 1) for i in range(60)]
    log = "".join(commit("a@x", *files) for _ in range(6))
    out = analyse(parse_log(log), {p for p, _ in files}, {})
    assert out["coupled"] == []


def test_no_history_is_a_gap_not_an_estimate(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert "gap" in report(None, OWN, ws, "abc")
    assert (
        "too little history"
        in report(commit("a@x", ("a.js", 1)), OWN, ws, "abc")["gap"]
    )


def test_complexity_survives_a_moved_workspace(tmp_path: Path) -> None:
    # Review finding F7: lint.json written on another machine or before a copy.
    ws = Workspace(tmp_path)
    lint = [
        {
            "filePath": "/Users/someone/old-copy/lib/db.js",
            "messages": [{"ruleId": "complexity", "message": "has a complexity of 9."}],
        }
    ]
    ws.write_text(".audit/scans/lint.json", json.dumps(lint))
    assert complexity(ws, OWN) == {"lib/db.js": 9}


def test_complexity_comes_from_lint(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    lint = [
        {
            "filePath": str(tmp_path / "lib/db.js"),
            "messages": [
                {
                    "ruleId": "complexity",
                    "message": "Function 'q' has a complexity of 14.",
                },
                {
                    "ruleId": "complexity",
                    "message": "Function 'r' has a complexity of 11.",
                },
            ],
        }
    ]
    ws.write_text(".audit/scans/lint.json", json.dumps(lint))
    out = report(LOG, OWN, ws, "abc")
    assert out["hotspots"][0] == {
        "file": "lib/db.js",
        "commits": 6,
        "lines_changed": 16,
        "authors": 2,
        "max_complexity": 14,
        "score": 1.0,
    }


def test_a_failed_git_log_is_a_recorded_gap(tmp_path: Path) -> None:
    out = report(None, OWN, Workspace(tmp_path), "abc", "git log failed (bad object)")
    assert out["gap"].startswith("git log failed (bad object)")
