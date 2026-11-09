"""ADR 0007 D5: a tool that didn't look is never a pass."""

from __future__ import annotations

import json

import pytest

from audit_kit import gates, scan_rows
from audit_kit.inventory import build
from audit_kit.units import Unit
from audit_kit.workspace import Workspace


def statuses(ws: Workspace, unit: Unit) -> dict[str, str]:
    index = scan_rows.build_index(ws, {unit.path})
    return {g.gate: g.status for g in gates.unit_gates(index, unit)}


@pytest.mark.parametrize(
    ("gate", "status"),
    [
        ("eslint", "fail"),
        ("complexity", "fail"),
        ("tsc", "fail"),
        ("semgrep", "unavailable"),
        ("knip", "unavailable"),
        ("duplication", "pass"),
    ],
)
def test_a_script_unit_gets_each_tools_verdict(
    ws: Workspace, route: Unit, gate: str, status: str
) -> None:
    assert statuses(ws, route)[gate] == status


def test_a_file_the_tool_did_not_examine_is_unavailable(
    ws: Workspace, units: list[Unit]
) -> None:
    ws.write_text(".audit/scans/typecheck-files.txt", "")
    route = next(u for u in units if u.path == "lib/export.js")
    assert statuses(ws, route)["tsc"] == "unavailable"


def test_a_missing_examined_list_says_so(ws: Workspace, units: list[Unit]) -> None:
    (ws.root / ".audit/scans/typecheck-files.txt").unlink()
    route = next(u for u in units if u.path == "lib/export.js")
    index = scan_rows.build_index(ws, {route.path})
    tsc = next(g for g in gates.unit_gates(index, route) if g.gate == "tsc")
    assert tsc.status == "unavailable"
    assert "no readable list" in tsc.evidence and "not written" in tsc.evidence


def test_inline_scripts_are_unavailable_to_the_javascript_tools(
    ws: Workspace, units: list[Unit]
) -> None:
    script = next(u for u in units if u.kind == "inline script")
    got = statuses(ws, script)
    assert (got["eslint"], got["tsc"], got["semgrep"]) == ("unavailable",) * 3


def test_markup_is_not_applicable_to_the_javascript_tools(
    ws: Workspace, units: list[Unit]
) -> None:
    markup = next(u for u in units if u.kind == "markup")
    got = statuses(ws, markup)
    assert {got[g] for g in ("eslint", "tsc", "semgrep", "knip", "complexity")} == {
        "not_applicable"
    }


def write_target_ci(ws: Workspace) -> set[str]:
    root = ws.root
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/ci.yml").write_text(
        "jobs:\n  t:\n    steps:\n      - run: npm run lint\n"
    )
    (root / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "types": "tsc -p ."}})
    )
    (root / "eslint.config.js").write_text(
        "export default [{ rules: { complexity: ['warn', 8] } }];\n"
    )
    return {e.path for e in build(ws).entries if e.kind == "file"}


def test_a_gate_run_through_a_package_script_in_ci_runs_in_ci(ws: Workspace) -> None:
    data = gates.repository(ws, write_target_ci(ws))
    eslint = next(g for g in data.gates if g.gate == "eslint")
    assert (eslint.target, eslint.where) == (
        "runs in CI",
        [".github/workflows/ci.yml:4"],
    )


def test_a_script_ci_never_runs_is_a_package_script_only(ws: Workspace) -> None:
    data = gates.repository(ws, write_target_ci(ws))
    assert (
        next(g for g in data.gates if g.gate == "tsc").target == "package script only"
    )


def test_complexity_runs_where_eslint_runs_with_the_rule_on(ws: Workspace) -> None:
    data = gates.repository(ws, write_target_ci(ws))
    assert next(g for g in data.gates if g.gate == "complexity").target == "runs in CI"


def test_a_gate_with_no_mention_is_not_found(ws: Workspace) -> None:
    data = gates.repository(ws, write_target_ci(ws))
    assert next(g for g in data.gates if g.gate == "semgrep").target == "not found"


def test_the_repository_table_round_trips_through_its_file(ws: Workspace) -> None:
    written = gates.write_repository(ws, write_target_ci(ws))
    assert gates.read_repository(ws) == written
