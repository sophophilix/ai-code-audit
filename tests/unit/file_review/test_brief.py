"""ADR 0007 D1: a brief carries every scan row for its unit, and nothing secret."""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from audit_kit import brief, review, scan_rows
from audit_kit.inventory import build
from audit_kit.units import Unit, build_units
from audit_kit.workspace import Workspace


def text_of(ws: Workspace, unit: Unit) -> str:
    return ws.read_text(brief.brief_paths(unit.id)[0])


def test_the_brief_counts_the_rows_in_the_unit(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    meta = brief.read_meta(ws, route.id)
    assert meta is not None
    counted = {k: v for k, v in meta.scan_rows.items() if v}
    assert counted == {"lint": 2, "typecheck": 1, "sweep": 1, "secrets": 1}


def test_rows_outside_the_unit_are_counted_but_not_shown(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    text = text_of(ws, route)
    assert "| typecheck | ran | 1 | 1 |" in text
    assert "outside the unit" not in text


def test_another_files_rows_stay_out(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    assert "Expected '==='" not in text_of(ws, route)


def test_a_secret_appears_as_its_rule_and_line_only(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    text = text_of(ws, route)
    assert "SECRETVALUE" not in text
    assert "- 2: generic-api-key: Generic key (value not shown)" in text


def test_a_scan_that_did_not_run_says_so(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    assert "| knip | not run | 0 | 0 |" in text_of(ws, route)


def test_a_malformed_scan_is_unreadable_not_empty(
    ws: Workspace, units: list[Unit]
) -> None:
    ws.write_text(".audit/scans/lint.json", json.dumps({"not": "eslint"}))
    index = scan_rows.build_index(ws, {u.path for u in units})
    assert index.status["lint"] is scan_rows.ScanStatus.UNREADABLE


def test_code_lines_keep_their_file_line_numbers(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    assert "6    exec(`zip -r out.zip ${folder}`);" in text_of(ws, route)


def test_the_rules_follow_the_unit_kind(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    text = text_of(ws, route)
    assert "### Node.js" in text
    assert "### 8. Browser security" not in text


def test_the_count_table_matches_the_rows_shown(
    ws: Workspace, briefs: list[Unit], route: Unit
) -> None:
    text = text_of(ws, route)
    assert brief.parse_scan_table(text) == brief.count_rendered_rows(text)


def test_a_section_of_a_large_file_gets_its_imports_as_context(
    tmp_path: Path, kit_home: Path
) -> None:
    functions = [f"function f{i}() {{\n" + "  x();\n" * 248 + "}" for i in range(6)]
    root = tmp_path / "big"
    root.mkdir()
    (root / "big.js").write_text(
        'const fs = require("fs");\n' + "\n".join(functions) + "\n"
    )
    ws = Workspace(root)
    found, _ = build_units(ws, build(ws), ())
    later = next(u for u in found if u.start > 1)
    review.prepare(ws, [later], kit_home, "9.9.9")
    text = text_of(ws, later)
    assert "## Context from the same file" in text
    assert '1  const fs = require("fs");' in text


def write_every_scan(scans: Path) -> None:
    sarif = {
        "runs": [
            {
                "results": [
                    {
                        "ruleId": "detect-child-process",
                        "message": {"text": "child process"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "lib/export.js"},
                                    "region": {"startLine": 6},
                                }
                            }
                        ],
                    }
                ]
            }
        ]
    }
    duplicates = {
        "duplicates": [
            {
                "lines": 3,
                "firstFile": {"name": "lib/export.js", "start": 4, "end": 7},
                "secondFile": {"name": "lib/other.js", "start": 1, "end": 1},
            }
        ]
    }
    unused = {
        "unreachable_files": [{"file": "lib/export.js"}],
        "unused_exports": [{"file": "lib/export.js", "name": "router", "line": 9}],
        "undeclared_dependencies": [
            {"name": "express", "file": "lib/export.js", "line": 1}
        ],
    }
    blind = {
        "entries": [{"kind": "dynamic import", "file": "lib/export.js", "line": 5}]
    }
    suppressed = {
        "entries": [
            {
                "file": "lib/export.js",
                "line": 3,
                "directive": "eslint-disable-next-line",
                "rules": ["no-undef"],
            }
        ]
    }
    knip = {
        "files": [],
        "issues": [
            {
                "file": "lib/export.js",
                "exports": [{"name": "router", "line": 9}],
                "types": [],
            }
        ],
    }
    design = {
        "contrast_pairs": [
            {
                "selector": "h1",
                "where": "public/index.html:4",
                "text": "#777",
                "background": "#fff",
                "ratio": 4.48,
            }
        ],
        "unmeasured_pairs": [
            {"selector": "main", "where": "public/index.html:3", "why": "image"}
        ],
    }
    (scans / "dynamic").mkdir()
    for rel, data in {
        "sast.sarif": sarif,
        "duplication.json": duplicates,
        "unused.json": unused,
        "blindspots.json": blind,
        "suppressions.json": suppressed,
        "dynamic/knip.json": knip,
        "design-inventory.json": design,
    }.items():
        (scans / rel).write_text(json.dumps(data))


def test_every_scan_format_reaches_the_brief(
    ws: Workspace, units: list[Unit], kit_home: Path
) -> None:
    write_every_scan(ws.root / ".audit/scans")
    review.prepare(ws, units, kit_home, "9.9.9")
    meta = brief.read_meta(ws, "u001")
    assert meta is not None
    assert {k: v for k, v in meta.scan_rows.items() if v} == {
        "lint": 2,
        "typecheck": 1,
        "sast": 1,
        "sweep": 1,
        "duplication": 1,
        "suppressions": 1,
        "blindspots": 1,
        "unused": 3,
        "knip": 1,
        "secrets": 1,
    }


def test_contrast_pairs_reach_the_markup_brief(
    ws: Workspace, units: list[Unit], kit_home: Path
) -> None:
    write_every_scan(ws.root / ".audit/scans")
    review.prepare(ws, units, kit_home, "9.9.9")
    markup = next(u for u in units if u.kind == "markup")
    assert "ratio 4.48 (fails 4.5:1)" in text_of(ws, markup)


line_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc", "Zl", "Zp")), max_size=80
)


@given(st.lists(st.tuples(st.sampled_from(scan_rows.NAMES), line_text), max_size=20))
def test_any_rows_render_as_many_as_the_table_counts(
    rows: list[tuple[str, str]],
) -> None:
    index = scan_rows.ScanIndex(
        rows={
            name: {"a.js": [scan_rows.Row(1, t) for n, t in rows if n == name]}
            for name in scan_rows.NAMES
        },
        status=dict.fromkeys(scan_rows.NAMES, scan_rows.ScanStatus.RAN),
    )
    unit = Unit("u001", "a.js", "", 1, 1, "file")
    part = (
        "\n## Scan rows\n"
        + "\n".join(brief.scan_part(scan_rows.unit_rows(index, unit), index))
        + "\n## Gates\n"
    )
    assert brief.parse_scan_table(part) == brief.count_rendered_rows(part)


def test_old_unused_reports_and_near_duplicates_reach_their_files(
    ws: Workspace, units: list[Unit], kit_home: Path
) -> None:
    scans = ws.root / ".audit/scans"
    # An unused.json written before 0.18.0: unused dependencies without a line.
    (scans / "unused.json").write_text(
        json.dumps(
            {"unused_dependencies": [{"name": "left-pad", "section": "dependencies"}]}
        )
    )
    (scans / "similar.json").write_text(
        json.dumps(
            {
                "pairs": [
                    {
                        "similarity": 0.95,
                        "first": {"file": "lib/export.js", "name": "a", "line": 4},
                        "second": {"file": "lib/other.js", "name": "b", "line": 1},
                        "differences": [{"first": '" "', "second": "/ \\\\ s + /"}],
                    }
                ]
            }
        )
    )
    index = scan_rows.build_index(ws, {"lib/export.js", "lib/other.js", "package.json"})
    assert index.of("unused", "package.json")[0].text.startswith(
        "`left-pad` is declared in dependencies"
    )
    here = index.of("similar", "lib/export.js")[0]
    there = index.of("similar", "lib/other.js")[0]
    assert (here.line, there.line) == (4, 1)
    assert "matches `b` at lib/other.js:1 (95% of tokens)" in here.text
    assert '`" "` here' in here.text and '`" "` there' in there.text
