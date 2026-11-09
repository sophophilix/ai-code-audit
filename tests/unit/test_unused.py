"""The static unused-code analysis, on a small CommonJS project written to disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from audit_kit.inventory import build
from audit_kit.unused import analyse, package_name, strip_comments
from audit_kit.workspace import Workspace

Report = dict[str, Any]
FILES = {
    "package.json": json.dumps(
        {
            "main": "server.js",
            "scripts": {"dev": "nodemon server.js", "check": "node scripts/check.js"},
            "dependencies": {"express": "4.22.3", "left-pad": "1.3.0"},
            "devDependencies": {"nodemon": "3.0.0"},
        }
    ),
    "server.js": (
        "const express = require('express');\n"
        "const crypto = require('node:crypto');\n"
        "const _ = require('lodash/fp');\n"
        "const a = require('./lib/a');\n"
        "// const ghost = require('./lib/ghost');\n"
        "const url = 'http://example.invalid/orphanName';\n"
        "const plugin = require(`./plugins/${process.env.PLUGIN}`);\n"
        "a.used(); a.helper();\n"
    ),
    "lib/a.js": (
        "function used() {}\n"
        "module.exports = { used, unusedFn: () => 1, async helper() {} };\n"
        "exports.other = 1;\n"
    ),
    "lib/orphanName.js": "module.exports = 1;\n",
    "lib/ghost.js": "module.exports = 2;\n",
    "scripts/check.js": (
        "const path = require('path'), ROOT = path.join(__dirname, '..');\n"
        "require('../lib/a');\n"
        "require(path.join(ROOT, 'lib', 'joined'));\n"
        "require(path.resolve(__dirname, '../lib/resolved.js'));\n"
    ),
    "lib/joined.js": "module.exports = 3;\n",
    "lib/resolved.js": "module.exports = 4;\n",
    "public/index.html": '<script src="/app.js?v=2"></script>\n',
    "public/app.js": "console.log('hi');\n",
    "public/vendor/lib.js": "require('./nothing');\n",
}


@pytest.fixture
def report(tmp_path: Path) -> Report:
    for rel, text in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    ws = Workspace(tmp_path)
    return analyse(ws, build(ws), ("public/vendor",))


def test_entry_points_come_from_package_json_and_html(report: Report) -> None:
    assert {e["file"]: e["why"] for e in report["entry_points"]} == {
        "server.js": "package.json main",
        "scripts/check.js": "package.json scripts.check",
        "public/app.js": "<script src> in public/index.html",
    }


def test_unreachable_files_say_where_their_name_appears(report: Report) -> None:
    unreachable = {u["file"]: u for u in report["unreachable_files"]}
    assert set(unreachable) == {"lib/ghost.js", "lib/orphanName.js"}
    # A require that is only in a comment doesn't count, and doesn't mention it.
    assert unreachable["lib/ghost.js"]["name_mentioned_in"] == []
    assert unreachable["lib/orphanName.js"]["name_mentioned_in"] == ["server.js"]


def test_dynamic_requires_are_listed_not_followed(report: Report) -> None:
    assert [(d["file"], d["line"]) for d in report["dynamic_requires"]] == [
        ("server.js", 7)
    ]


def test_dependencies_declared_but_unused_and_used_but_undeclared(
    report: Report,
) -> None:
    assert report["unused_dependencies"] == [
        {
            "name": "left-pad",
            "section": "dependencies",
            "file": "package.json",
            "line": 1,
        }
    ]  # nodemon is used by a script
    assert report["undeclared_dependencies"] == [
        {"name": "lodash", "file": "server.js", "line": 3}
    ]


def test_exports_no_other_file_names(report: Report) -> None:
    assert {(u["file"], u["name"]) for u in report["unused_exports"]} == {
        ("lib/a.js", "unusedFn"),
        ("lib/a.js", "other"),
    }


def test_excluded_folders_are_not_analysed(report: Report) -> None:
    assert report["counts"]["files"] == 8
    assert all("vendor" not in d["file"] for d in report["dynamic_requires"])


def test_comment_stripping_keeps_strings_offsets_and_lines() -> None:
    text = "a('//x'); // gone\n/* b\nc */ d"
    out = strip_comments(text)
    assert out.startswith("a('//x');")
    assert "gone" not in out
    assert len(out) == len(text)
    assert out.count("\n") == 2
    assert out.endswith(" d")


@pytest.mark.parametrize(
    ("spec", "name"),
    [
        ("express", "express"),
        ("lodash/fp", "lodash"),
        ("@azure/identity/x", "@azure/identity"),
        ("fs/promises", None),
        ("node:crypto", None),
    ],
)
def test_package_names(spec: str, name: str | None) -> None:
    assert package_name(spec) == name
