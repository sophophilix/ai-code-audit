"""Shared fixtures: a small synthetic Express repository."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

SERVER = 'const express = require("express");\nconst app = express();\napp.get("/", (q, s) => s.send("hi"));\n'


def build_repo(
    root: Path,
    *,
    dependencies: object | None = None,
    jurisdiction: str = "NSW local council",
    catch_all: bool = False,
) -> Path:
    """Write a small Express repository with vendored, minified and licence files."""
    deps = (
        dependencies
        if dependencies is not None
        else {
            "express": "^4.21.0",
            "mssql": "^11.0.0",
            "@azure/identity": "^4.0.0",
        }
    )
    for folder in ("lib", "public/vendor", "public/flags", "scripts", "sql", ".audit"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps(
            {"name": "demo", "main": "server.js", "dependencies": deps}, indent=2
        )
        + "\n"
    )
    server = (
        SERVER
        + ("app.use((req, res) => res.status(404).end());\n" if catch_all else "")
        + "app.listen(8080);\n"
    )
    (root / "server.js").write_text(server)
    (root / "lib/a.js").write_text("module.exports = 1;\n" * 30)
    (root / "lib/b.js").write_text('const u = "https://x.openai.azure.com";\n')
    (root / "public/index.html").write_text("<html><body><h1>Hi</h1></body></html>\n")
    (root / "public/licence.html").write_text("<html>site licence page</html>\n")
    (root / "public/site.css").write_text("body { margin: 0; }\n")
    (root / "public/vendor/lib.js").write_text("vendored\n")
    (root / "public/flags/LICENSE.txt").write_text("MIT\n")
    (root / "public/app.min.js").write_text("min\n")
    (root / "scripts/a-check.js").write_text('console.log("PASS");\n')
    (root / "sql/t.sql").write_text("CREATE TABLE t (id INT);\n")
    (root / ".audit/project.md").write_text(
        f"- Organisation and jurisdiction: {jurisdiction}\n- add: \n- remove: \n"
    )
    return root


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., Path]:
    """Provide a builder for a synthetic repository with chosen options."""

    def make(**options: object) -> Path:
        return build_repo(tmp_path / "ws", **options)  # type: ignore[arg-type]

    return make


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Provide a fresh synthetic repository in its own directory."""
    return build_repo(tmp_path / "ws")
