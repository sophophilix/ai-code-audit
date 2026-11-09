"""File review units (ADR 0002 D1) and the checks on their records (D4)."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from audit_kit.inventory import build
from audit_kit.units import (
    MARKUP_BOUNDARY,
    MAX_LINES,
    OUTPUT,
    Unit,
    build_units,
    parse,
    render,
    sections,
)
from audit_kit.verification import Status, check
from audit_kit.workspace import Workspace

HEADER = "---\nagent: file-reviewer\nmodel: m\ncommit: c\nstatus: complete\nunit: {unit}\n---\n"
SECTIONS = "".join(
    f"## {h}\nnone\n"
    for h in (
        "Summary",
        "Facts",
        "Comments versus code",
        "Sources and sinks",
        "Functions",
        "Gates",
        "Findings",
        "Open edges",
        "Limitations",
    )
)


def big_file(functions: int, size: int) -> str:
    body = "".join(
        f"function f{i}() {{\n" + "  x();\n" * (size - 2) + "}\n"
        for i in range(functions)
    )
    return "const a = 1;\n" + body


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    (root / "lib").mkdir(parents=True)
    (root / "public/vendor").mkdir(parents=True)
    (root / "server.js").write_text("const app = 1;\napp.listen(1);\n")
    (root / "lib/big.js").write_text(big_file(12, 200))
    (root / "db.sql").write_text("CREATE TABLE t (id INT);\n")
    (root / "public/vendor/lib.js").write_text("vendored();\n")
    (root / "public/index.html").write_text(
        "<html>\n<script src='/a.js'></script>\n<script>\n  run();\n  more();\n</script>\n"
        "<script></script>\n<script>go();</script>\n</html>\n"
    )
    (root / "README.md").write_text("# hi\n")
    return Workspace(root)


def test_a_package_manifest_is_one_unit_and_its_lockfile_none(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "package.json").write_text('{\n  "name": "x"\n}\n')
    (tmp_path / "package-lock.json").write_text("{}\n")
    (tmp_path / "app/package.json").write_text("{}\n")
    (tmp_path / "app/my-package.json").write_text("{}\n")
    ws = Workspace(tmp_path)
    units, _ = build_units(ws, build(ws), ())
    assert [(u.path, u.start, u.end, u.kind) for u in units] == [
        ("app/package.json", 1, 1, "manifest"),
        ("package.json", 1, 3, "manifest"),
    ]


def test_sections_cut_at_top_level_boundaries_and_cover_every_line() -> None:
    lines = big_file(12, 200).splitlines()
    spans = sections(lines)
    assert spans[0][0] == 1 and spans[-1][1] == len(lines)
    assert all(b - a + 1 <= MAX_LINES for a, b in spans)
    assert all(nxt[0] == cur[1] + 1 for cur, nxt in itertools.pairwise(spans))
    assert all(lines[a - 1].startswith("function") for a, _ in spans[1:])


def test_a_file_with_no_boundary_is_cut_at_the_limit() -> None:
    spans = sections(["x();"] * 2500)
    assert spans == [(1, 1000), (1001, 2000), (2001, 2500)]


def test_units_cover_own_code_files_sections_and_inline_scripts(ws: Workspace) -> None:
    units, problems = build_units(ws, build(ws), ())
    assert problems == []
    by = {(u.path, u.part): u for u in units}
    assert {p for p, _ in by} == {
        "server.js",
        "lib/big.js",
        "db.sql",
        "public/index.html",
    }
    assert [u.part for u in units if u.path == "lib/big.js"] == ["1", "2", "3", "4"]
    first, second = (
        by[("public/index.html", "script-1")],
        by[("public/index.html", "script-3")],
    )
    assert (first.start, first.end, first.kind) == (3, 6, "inline script")
    assert (second.start, second.end) == (8, 8)
    assert first.record == ".audit/files/public/index.html#script-1.md"
    assert by[("server.js", "")].record == ".audit/files/server.js.md"
    assert [u.id for u in units] == [f"u{i:03d}" for i in range(1, len(units) + 1)]
    assert parse(render(units)) == units


def write_units(ws: Workspace) -> list[Unit]:
    units, _ = build_units(ws, build(ws), ())
    ws.write_text(OUTPUT, render(units))
    return units


def record(ws: Workspace, unit: Unit, findings: str = "") -> None:
    ws.write_text(unit.record, HEADER.format(unit=unit.id) + SECTIONS + findings)


def failures(ws: Workspace) -> str:
    return "\n".join(r.line() for r in check(ws).results if r.status is Status.FAIL)


def test_records_are_checked_for_sections_scope_and_completeness(ws: Workspace) -> None:
    (ws.root / ".audit").mkdir(exist_ok=True)
    units = write_units(ws)
    server = next(u for u in units if u.path == "server.js")
    record(
        ws,
        server,
        "### FILE-u004-001 Listens on a fixed port\n- Key: X-port:server.js\n"
        "- Category: operations\n- Severity: low\n- Confidence: high\n"
        "- Location: server.js:2\n- Evidence: e\n- Excerpt: `app.listen(1);`\n"
        "### FILE-u004-002 Cites another file\n- Key: X-other:db.sql\n"
        "- Category: security\n- Severity: low\n- Confidence: high\n"
        "- Location: db.sql:1\n- Evidence: e\n- Excerpt: `CREATE TABLE`\n",
    )
    out = failures(ws)
    assert "OUT-U2" in out and "FILE-u004-002" in out and "FILE-u004-001" not in out
    assert "OUT-U3" in out and "1/" in out
    ws.write_text(server.record, HEADER.format(unit=server.id) + "## Facts\n")
    assert "lacks ['Summary', 'Comments versus code'" in failures(ws)


def test_a_pilot_needs_only_its_units(ws: Workspace) -> None:
    (ws.root / ".audit").mkdir(exist_ok=True)
    units = write_units(ws)
    sql = next(u for u in units if u.path == "db.sql")
    record(ws, sql)
    ws.write_text(".audit/work/files/pilot.txt", f"{sql.id}\n")
    assert "OUT-U3" not in failures(ws)


def test_inline_scripts_split_at_their_own_top_level_despite_column_zero_strings() -> (
    None
):
    # Shaped like the pilot app's public/index.html: functions indented four spaces,
    # template-literal HTML at column 0 inside them.
    block = (
        "    function f{i}() {{\n      const h = `\n<div>\n</div>\n`;\n"
        + "      x();\n" * 195
        + "    }}\n"
    )
    lines = "".join(block.format(i=i) for i in range(8)).splitlines()
    spans = sections(lines, first=100)
    assert len(spans) > 1
    assert all(lines[a - 100].strip().startswith("function") for a, _ in spans)


def test_a_symlinked_record_fails_a_check_instead_of_crashing(
    ws: Workspace, tmp_path: Path
) -> None:
    # Review finding F3: records are agent output and may be anything.
    (ws.root / ".audit/files").mkdir(parents=True)
    (tmp_path / "elsewhere.md").write_text("# not a record\n")
    (ws.root / ".audit/files/a.md").symlink_to(tmp_path / "elsewhere.md")
    assert "files/a.md: not read" in failures(ws)


def test_pages_get_markup_units_between_scripts_and_stylesheets_their_own(
    tmp_path: Path,
) -> None:
    root = tmp_path / "site"
    (root / "views").mkdir(parents=True)
    (root / "site.css").write_text(
        ":root {\n  --c: #111;\n}\n.btn {\n  color: var(--c);\n}\n"
    )
    page = (
        "<!doctype html>\n<html lang='en'>\n<head><title>T</title></head>\n"
        "<body>\n<main>\n<h1>Report</h1>\n<form action='/r'>\n</form>\n</main>\n"
        "<script>\n  go();\n</script>\n"
        "<footer>\n<p>Contact</p>\n<p>Privacy</p>\n</footer>\n</body>\n</html>\n"
    )
    (root / "views/report.ejs").write_text(page)
    ws = Workspace(root)
    units, _ = build_units(ws, build(ws), ())
    kinds = {(u.path, u.part): (u.kind, u.start, u.end) for u in units}
    assert kinds[("site.css", "")] == ("stylesheet", 1, 6)
    assert kinds[("views/report.ejs", "script-1")] == ("inline script", 10, 12)
    assert kinds[("views/report.ejs", "markup.1")] == ("markup", 1, 9)
    assert kinds[("views/report.ejs", "markup.2")][0] == "markup"
    assert kinds[("views/report.ejs", "markup.2")][1] == 13
    record = next(u for u in units if u.part == "markup.1").record
    assert record == ".audit/files/views/report.ejs#markup.1.md"


def test_large_markup_splits_at_page_regions_not_inside_them() -> None:
    region = "<section>\n" + "  <p>x</p>\n" * 400 + "</section>\n"
    lines = (region * 4).splitlines()
    spans = sections(lines, 1, MARKUP_BOUNDARY)
    assert len(spans) > 1
    assert all(lines[a - 1].startswith("<section>") for a, _ in spans)


def test_inline_styles_are_their_own_units_and_leave_the_markup(tmp_path: Path) -> None:
    # Found on the pilot app: a 1,024-line <style> in the head swallowed the markup.
    root = tmp_path / "site"
    root.mkdir()
    css = "".join(f".c{i} {{\n  color: red;\n}}\n" for i in range(400))
    page = f"<html>\n<head>\n<style>\n{css}</style>\n</head>\n<body>\n<main>\n<h1>T</h1>\n</main>\n</body>\n</html>\n"
    (root / "index.html").write_text(page)
    ws = Workspace(root)
    units, _ = build_units(ws, build(ws), ())
    styles = [u for u in units if u.kind == "inline style"]
    markup = [u for u in units if u.kind == "markup"]
    assert [u.part for u in styles] == ["style-1.1", "style-1.2"]
    assert all(u.lines <= MAX_LINES for u in styles)
    assert not any(a.start <= s.start <= a.end for a in markup for s in styles)
