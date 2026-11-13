"""The planted fixtures in tests/fixtures, each checked against its expected.json."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from audit_kit.code_facts import (
    LINT,
    TSC_FILES,
    blind_spots,
    coverage,
    suppressions,
    sweep,
)
from audit_kit.inventory import build
from audit_kit.verification import Status, check
from audit_kit.workspace import Workspace

FIXTURES = Path(__file__).parents[1] / "fixtures"


def load(name: str, tmp_path: Path) -> tuple[Workspace, dict[str, Any]]:
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    expected = json.loads((root / "expected.json").read_text())
    (root / "expected.json").unlink()
    return Workspace(root), expected


def matches(entry: dict[str, Any], want: dict[str, Any]) -> bool:
    return all(entry.get(k) == v for k, v in want.items())


def test_suppressed(tmp_path: Path) -> None:
    ws, expected = load("suppressed", tmp_path)
    entries = suppressions(ws, build(ws), ())["entries"]
    for want in expected["mustFind"]:
        assert any(matches(e, want) for e in entries), want
    for unwanted in expected["mustNotFind"]:
        assert not any(matches(e, unwanted) for e in entries), unwanted
    assert len(entries) == len(expected["mustFind"])


def test_dynamic_require(tmp_path: Path) -> None:
    ws, expected = load("dynamic-require", tmp_path)
    inv = build(ws)
    entries = blind_spots(ws, inv, ())["entries"]
    for want in expected["mustFind"]:
        assert any(matches(e, want) for e in entries), want
    for unwanted in expected["mustNotFind"]:
        assert not any(matches(e, unwanted) for e in entries), unwanted
    gaps = coverage(ws, inv, ())["gaps"]
    assert {"file": expected["inlineScriptGap"], "tool": "eslint, tsc",
            "reason": "inline <script> not checked by any tool"} in gaps  # fmt: skip


@pytest.mark.parametrize("name", ["excerpts", "absent"])
def test_verification_fixtures(name: str, tmp_path: Path) -> None:
    ws, expected = load(name, tmp_path)
    lines = [
        r.detail
        for r in check(ws).results
        if r.check == expected["check"] and r.status is Status.FAIL
    ]
    detail = " ".join(lines)
    for fid in expected["mustFail"]:
        assert re.search(rf"\b{fid}\b", detail), (fid, detail)
    for fid in expected["mustPass"]:
        assert not re.search(rf"\b{fid}\b", detail), (fid, detail)
    for fid, where in expected.get("foundAt", {}).items():
        assert f"{fid} " in detail and where in detail


def test_coverage_names_files_a_tool_skipped(tmp_path: Path) -> None:
    ws, _ = load("dynamic-require", tmp_path)
    ws.write_text(LINT, json.dumps([{"filePath": str(ws.root / "server.js")}]))
    ws.write_text(
        TSC_FILES,
        f"/opt/tsc/lib.d.ts\n{ws.root / 'server.js'}\n{ws.root / 'lib/ok.js'}\n",
    )
    out = coverage(ws, build(ws), ())
    gaps = {(g["file"], g["tool"]): g["reason"] for g in out["gaps"]}
    assert gaps[("lib/ok.js", "eslint")] == "the tool didn't report it"
    assert ("lib/ok.js", "tsc") not in gaps
    assert out["tools"]["eslint"] == {"status": "ran", "expected": 2, "examined": 1}
    assert out["tools"]["semgrep"]["status"] == "not reported"


def test_coverage_without_scans_is_a_gap_for_every_file(tmp_path: Path) -> None:
    ws, _ = load("dynamic-require", tmp_path)
    out = coverage(ws, build(ws), ())
    assert out["tools"]["tsc"]["status"] == "no usable output"
    assert sum(g["tool"] == "tsc" for g in out["gaps"]) == 2


def test_coverage_survives_a_moved_workspace(tmp_path: Path) -> None:
    ws, _ = load("dynamic-require", tmp_path)
    (ws.root / "ok.js").write_text("module.exports = 2;\n")
    old = "/Users/someone/audits/old-copy"
    ws.write_text(LINT, json.dumps([{"filePath": f"{old}/lib/ok.js"}]))
    gaps = {(g["file"], g["tool"]) for g in coverage(ws, build(ws), ())["gaps"]}
    assert ("lib/ok.js", "eslint") not in gaps
    assert ("ok.js", "eslint") in gaps and ("server.js", "eslint") in gaps


def test_vendor_eval(tmp_path: Path) -> None:
    ws, expected = load("vendor-eval", tmp_path)
    inv = build(ws)
    assert {e.path: e.cls for e in inv.entries}["public/vendor/jquery.js"] == "vendored"
    out = sweep(ws, inv)
    for want in expected["mustFind"]:
        assert any(matches(e, want) for e in out["entries"]), want
    for unwanted in expected["mustNotFind"]:
        assert not any(matches(e, unwanted) for e in out["entries"]), unwanted
    assert out["counts"]["vendored"]["network"] == 1


PY_SOURCE = (
    "import pickle, subprocess\n"  # 1
    "x = eval(data)  # noqa: S307 trusted admin input\n"  # 2
    "y: int = z  # type: ignore[assignment]\n"  # 3
    "subprocess.run(cmd, shell=True)  # nosec B602\n"  # 4
    "obj = pickle.loads(blob)\n"  # 5
    "mod = importlib.import_module(name)\n"  # 6
    "# eval(commented) is not a blind spot\n"  # 7
)


def python_target(tmp_path: Path) -> Workspace:
    (tmp_path / "app.py").write_text(PY_SOURCE)
    return Workspace(tmp_path)


def test_python_suppressions_name_their_rules_and_reasons(tmp_path: Path) -> None:
    ws = python_target(tmp_path)
    found = {
        (e["line"], e["directive"]): (e["rules"], e["has_reason"])
        for e in suppressions(ws, build(ws), ())["entries"]
    }
    assert found == {
        (2, "noqa"): (["S307"], True),
        (3, "type: ignore"): (["assignment"], False),
        (4, "nosec"): (["B602"], False),
    }


def test_python_code_from_strings_and_dynamic_imports_are_blind_spots(
    tmp_path: Path,
) -> None:
    ws = python_target(tmp_path)
    kinds = [(e["line"], e["kind"]) for e in blind_spots(ws, build(ws), ())["entries"]]
    assert kinds == [(2, "eval"), (6, "dynamic import")]


def test_the_sweep_finds_python_subprocess_and_deserialisation(tmp_path: Path) -> None:
    ws = python_target(tmp_path)
    report = sweep(ws, build(ws))
    text = json.dumps(report)
    assert "subprocess" in text and "deserialisation" in text


def test_coverage_names_python_files_ruff_skipped(tmp_path: Path) -> None:
    ws = python_target(tmp_path)
    (tmp_path / "other.py").write_text("x = 1\n")
    (tmp_path / ".audit/scans").mkdir(parents=True)
    (tmp_path / ".audit/scans/lint-python-files.txt").write_text(f"{tmp_path}/app.py\n")
    out = coverage(ws, build(ws), ())
    assert out["tools"]["ruff"] == {"status": "ran", "expected": 2, "examined": 1}
    assert {
        "file": "other.py",
        "tool": "ruff",
        "reason": "the tool didn't report it",
    } in out["gaps"]


def test_a_reason_in_the_comment_above_counts(tmp_path: Path) -> None:
    (tmp_path / "db.py").write_text(
        "# Column names come from a fixed list.\n"
        'cur.execute(f"SELECT {c} FROM t")  # nosec B608\n'
        'cur.execute(f"SELECT {d} FROM t")  # nosec B608\n'
    )
    ws = Workspace(tmp_path)
    found = [e["has_reason"] for e in suppressions(ws, build(ws), ())["entries"]]
    assert found == [True, False]
