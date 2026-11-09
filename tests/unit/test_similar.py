"""Near-duplicate named functions (similar.py), on small files written to disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audit_kit.inventory import build
from audit_kit.similar import MIN_TOKENS, functions, report
from audit_kit.workspace import Workspace

LABEL = (
    "function toLabel(s) {\n"
    '  return String(s || "").trim().toLowerCase().split(" ")'
    '.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");\n'
    "}\n"
)
NAME = (
    "// The original helper.\n"
    "const toDisplayName = (s) => {\n"
    '  return String(s || "").trim().toLowerCase().split(/\\s+/)'
    '.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");\n'
    "};\n"
)
OTHER = (
    "class Store {\n"
    "  async save(item) {\n"
    "    const rows = await this.db.query('INSERT INTO t VALUES (?)', [item.id]);\n"
    "    if (!rows) throw new Error('not saved');\n"
    "    return rows.length;\n"
    "  }\n"
    "}\n"
)


def write(root: Path, files: dict[str, str]) -> Workspace:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return Workspace(root)


@pytest.fixture
def found(tmp_path: Path) -> dict[str, Any]:
    ws = write(
        tmp_path,
        {
            "lib/formatLabel.js": LABEL,
            "lib/formatName.js": NAME,
            "lib/store.js": OTHER,
            "vendor/copy.js": LABEL,
        },
    )
    return report(ws, build(ws), ("vendor",))


def test_a_copied_helper_with_a_small_change_is_paired_with_the_change(
    found: dict[str, Any],
) -> None:
    assert found["counts"]["pairs"] == 1
    pair = found["pairs"][0]
    assert {pair["first"]["file"], pair["second"]["file"]} == {
        "lib/formatLabel.js",
        "lib/formatName.js",
    }
    assert pair["similarity"] >= 0.85
    changed = {(d["first"], d["second"]) for d in pair["differences"]}
    assert ('" "', "/ \\ s + /") in changed


def test_excluded_folders_are_not_compared(found: dict[str, Any]) -> None:
    assert found["counts"]["files"] == 3


def test_declarations_arrows_and_methods_are_found_with_their_lines() -> None:
    assert [(f.name, f.line) for f in functions("a.js", LABEL)] == [("toLabel", 1)]
    assert [(f.name, f.line) for f in functions("b.js", NAME)] == [("toDisplayName", 2)]
    assert [(f.name, f.line) for f in functions("c.js", OTHER)] == [("save", 2)]


def test_a_function_too_small_to_compare_is_left_out() -> None:
    tiny = "const on = (v) => v === 'true';\n"
    assert len(tiny.split()) < MIN_TOKENS
    assert functions("t.js", tiny) == []


def test_a_function_is_never_paired_with_one_nested_inside_it(tmp_path: Path) -> None:
    body = "    return list.map((x) => x * 2).filter((x) => x > limit).length;\n"
    outer = (
        "function outer(list, limit) {\n"
        f"  function inner(list, limit) {{\n{body}  }}\n"
        f"  {body.strip()}\n"
        "}\n"
    )
    ws = write(tmp_path, {"a.js": outer})
    assert report(ws, build(ws), ())["pairs"] == []
