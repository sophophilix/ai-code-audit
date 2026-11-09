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
