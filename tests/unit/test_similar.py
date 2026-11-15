"""Near-duplicate named functions (similar.py), on small files written to disk."""

from __future__ import annotations

import tokenize
from pathlib import Path
from typing import Any

import pytest

from audit_kit import scan_rows, similar_python
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


DIGEST = (
    "import hashlib\n"
    "\n"
    "\n"
    "@cached\n"
    "def digest(path: Path) -> str:\n"
    '    """Return the SHA-256 of a file."""\n'
    "    hasher = hashlib.sha256()\n"
    '    with path.open("rb") as handle:\n'
    "        # Read in blocks.\n"
    '        for block in iter(lambda: handle.read(65536), b""):\n'
    "            hasher.update(block)\n"
    "    return hasher.hexdigest()\n"
)
# The same helper copied: another name, no docstring, and SHA-1.
COPIED = (
    "class Undo:\n"
    "    async def _checksum(self, path: Path) -> str:\n"
    "        hasher = hashlib.sha1()\n"
    '        with path.open("rb") as handle:\n'
    '            for block in iter(lambda: handle.read(65536), b""):\n'
    "                hasher.update(block)\n"
    "        return hasher.hexdigest()\n"
)


@pytest.fixture
def python(tmp_path: Path) -> dict[str, Any]:
    ws = write(
        tmp_path,
        {
            "src/app/files.py": DIGEST,
            "src/app/undo.py": COPIED.replace("self, ", ""),
            "src/app/broken.py": "def (:\n",
            "tests/test_files.py": DIGEST,
            "tests/test_undo.py": DIGEST,
            "tests/conftest.py": "def tiny():\n    return 1\n",
            "lib/formatLabel.js": LABEL,
            "lib/formatName.js": NAME,
        },
    )
    return report(ws, build(ws), ())


def sides(pair: dict[str, Any]) -> set[tuple[str, str, int]]:
    return {(pair[s]["file"], pair[s]["name"], pair[s]["line"]) for s in SIDES}


SIDES = ("first", "second")


def test_a_copied_python_helper_is_paired_with_what_changed(
    python: dict[str, Any],
) -> None:
    pair = next(
        p
        for p in python["pairs"]
        if sides(p)
        == {("src/app/files.py", "digest", 5), ("src/app/undo.py", "_checksum", 2)}
    )
    assert pair["similarity"] >= 0.85
    assert {"first": "sha256", "second": "sha1"} in pair["differences"]


def test_python_and_javascript_are_compared_each_with_its_own(
    python: dict[str, Any],
) -> None:
    languages = [
        {pair[s]["file"].rsplit(".", 1)[1] for s in SIDES} for pair in python["pairs"]
    ]
    assert {"js"} in languages
    assert {"py"} in languages
    assert {"js", "py"} not in languages


def test_two_test_files_are_never_paired_but_a_test_and_code_are(
    python: dict[str, Any],
) -> None:
    files = [{pair[s]["file"] for s in SIDES} for pair in python["pairs"]]
    assert {"tests/test_files.py", "tests/test_undo.py"} not in files
    assert {"src/app/files.py", "tests/test_files.py"} in files


def test_a_python_file_that_does_not_parse_is_a_stated_problem(
    python: dict[str, Any],
) -> None:
    assert python["problems"] == ["src/app/broken.py: not parsed (line 1)"]
    assert python["counts"]["python_functions"] == 4


def test_python_tokens_leave_out_names_docstrings_comments_and_decorators() -> None:
    (found,) = similar_python.functions(DIGEST)
    assert (found.name, found.first, found.last) == ("digest", 5, 12)
    assert found.tokens[:6] == ("(", "path", ":", "Path", ")", "->")
    joined = " ".join(found.tokens)
    assert "Return the SHA-256" not in joined
    assert "Read in blocks" not in joined
    assert "cached" not in joined
    assert "digest" not in found.tokens


def test_nested_and_async_python_functions_are_each_found() -> None:
    code = "def outer():\n    async def inner():\n        return 1\n    return inner\n"
    assert [(f.name, f.first, f.last) for f in similar_python.functions(code)] == [
        ("outer", 1, 4),
        ("inner", 2, 3),
    ]


def test_python_that_tokenize_refuses_is_a_syntax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(_readline: object) -> None:
        raise tokenize.TokenError("EOF in multi-line statement", (1, 0))

    monkeypatch.setattr(tokenize, "generate_tokens", refuse)
    with pytest.raises(SyntaxError):
        similar_python.functions("x = 1\n")


def test_a_python_file_shows_as_covered_by_the_scan() -> None:
    index = scan_rows.ScanIndex(status={"similar": scan_rows.ScanStatus.RAN})
    source = next(s for s in scan_rows.SOURCES if s.name == "similar")
    assert index.status_for(source, "src/app/files.py") == "ran"
    assert index.status_for(source, "README.md") == "not covered"
