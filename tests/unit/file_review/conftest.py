"""Shared fixtures for the ADR 0007 file review: a small workspace with scans."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from audit_kit import review
from audit_kit.headless import Reply, Usage
from audit_kit.inventory import build
from audit_kit.settings import KitSettings
from audit_kit.units import OUTPUT as UNITS
from audit_kit.units import Unit, build_units, render
from audit_kit.workspace import Workspace

KIT = Path(__file__).resolve().parents[3]
CODE = (
    'const express = require("express");\n'  # 1
    "const router = express.Router();\n"  # 2
    "// The folder is already validated by middleware.\n"  # 3
    'router.get("/export", (req, res) => {\n'  # 4
    "  const folder = req.query.folder;\n"  # 5
    "  exec(`zip -r out.zip ${folder}`);\n"  # 6
    '  res.send("ok");\n'  # 7
    "});\n"  # 8
    "module.exports = router;\n"  # 9
)
PAGE = (
    "<html>\n<body>\n<main>\n<h1>Hi</h1>\n</main>\n"
    "<script>\n  document.body.innerHTML = location.hash;\n</script>\n"
    "</body>\n</html>\n"
)


def _scans(root: Path) -> None:
    scans = root / ".audit/scans"
    lint = [
        {
            "filePath": str(root / "lib/export.js"),
            "messages": [
                {"ruleId": "no-undef", "message": "'exec' is not defined.", "line": 6},
                {"ruleId": "complexity", "message": "complexity of 12", "line": 4},
            ],
        },
        {
            "filePath": str(root / "lib/other.js"),
            "messages": [{"ruleId": "eqeqeq", "message": "Expected '==='", "line": 1}],
        },
    ]
    (scans / "lint.json").write_text(json.dumps(lint))
    (scans / "typecheck-files.txt").write_text(
        f"{root}/lib/export.js\n{root}/lib/other.js\n"
    )
    (scans / "typecheck.txt").write_text(
        "lib/export.js(6,3): error TS2304: Cannot find name 'exec'.\n"
        "lib/export.js(40,1): error TS1005: outside the unit.\n"
    )
    leak = {
        "File": "lib/export.js",
        "StartLine": 2,
        "RuleID": "generic-api-key",
        "Description": "Generic key",
        "Match": "SECRETVALUE",
        "Secret": "SECRETVALUE",
    }
    (scans / "secrets.json").write_text(json.dumps([leak]))
    sweep = {
        "entries": [
            {
                "file": "lib/export.js",
                "line": 6,
                "kind": "child_process",
                "text": "exec(",
            }
        ]
    }
    (scans / "sweep.json").write_text(json.dumps(sweep))
    (scans / "suppressions.json").write_text(json.dumps({"entries": []}))
    (scans / "duplication.json").write_text(json.dumps({"duplicates": []}))


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    """Provide a workspace with one route file, one other file, a page and scans."""
    root = tmp_path / "ws"
    for folder in ("lib", "public", ".audit/scans"):
        (root / folder).mkdir(parents=True)
    (root / "lib/export.js").write_text(CODE)
    (root / "lib/other.js").write_text("if (a == b) {}\n")
    (root / "public/index.html").write_text(PAGE)
    (root / ".audit/detected.md").write_text("## Profiles to load\n\nnode-express\n")
    _scans(root)
    return Workspace(root)


def list_units(ws: Workspace) -> list[Unit]:
    """List the workspace's units and write units.tsv, as `kit units` does."""
    found, _ = build_units(ws, build(ws), (".audit",))
    ws.write_text(UNITS, render(found))
    return found


@pytest.fixture
def units(ws: Workspace) -> list[Unit]:
    """Provide the workspace's units, with units.tsv written."""
    return list_units(ws)


@pytest.fixture
def route(units: list[Unit]) -> Unit:
    """Provide the unit for lib/export.js."""
    return next(u for u in units if u.path == "lib/export.js")


@pytest.fixture
def briefs(ws: Workspace, units: list[Unit]) -> list[Unit]:
    """Provide the units with their briefs written."""
    review.prepare(ws, units, KIT, "9.9.9")
    return units


def finding(u: Unit, **changes: Any) -> dict[str, Any]:
    """Return a valid finding for the route unit, with fields overridden."""
    base: dict[str, Any] = {
        "key": f"NODE-DANGEROUS-SINK:{u.path}",
        "title": "Query string reaches a shell command",
        "category": "security",
        "severity": "medium",
        "confidence": "medium",
        "verification": "unverified",
        "location": f"{u.path}:6",
        "excerpt": "exec(`zip -r out.zip ${folder}`);",
        "description": "d",
        "impact": "i",
        "recommendation": "r",
        "sources": "https://nodejs.org/api/child_process.html",
        "effort": "S",
        "edges": [1],
    }
    return base | changes


def output(
    u: Unit, check_ids: list[str] | None = None, **changes: Any
) -> dict[str, Any]:
    """Return a valid pass output for the route unit, its finding overridden.

    Every check in `check_ids` is answered: `found` for the finding's CHECK-ID,
    `not found` for the rest.
    """
    key = finding(u, **changes)["key"].split(":", 1)[0]
    checks = [
        {"check": c, "result": "found" if c == key else "not found"}
        for c in check_ids or []
    ]
    return {
        "unit": u.id,
        "checks": checks,
        "facts": [
            {
                "kind": "route",
                "name": "GET /export",
                "location": f"{u.path}:4",
                "excerpt": 'router.get("/export", (req, res) => {',
            }
        ],
        "comments": [
            {
                "claim": "folder already validated",
                "location": f"{u.path}:3",
                "excerpt": "// The folder is already validated by middleware.",
                "code_lines": "4-8",
                "verdict": "not shown here",
            }
        ],
        "flows": [
            {
                "source": f"{u.path}:5",
                "source_excerpt": "const folder = req.query.folder;",
                "sink": f"{u.path}:6",
                "sink_excerpt": "exec(`zip -r out.zip ${folder}`);",
                "validation": "none in this file",
                "cwe": "CWE-78",
            }
        ],
        "functions": [],
        "findings": [finding(u, **changes)],
        "edges": [
            {
                "question": "Is folder validated before this handler?",
                "unknown": "middleware",
                "resolve_in": "the file mounting this router",
            }
        ],
        "limitations": ["scans/sast.sarif not run"],
    }


def reply(text: str, *, ok: bool = True, error: str = "") -> Reply:
    """Return a reply as `claude -p` would, with a fixed cost."""
    return Reply(
        ok=ok,
        text=text,
        turns=1,
        usage=Usage(input=10, output=20, cache_read=1000),
        cost_usd=0.05,
        seconds=12.0,
        session="s",
        error=error,
    )


class FakeRunner:
    """Stands in for `claude -p`: gives replies in order and records each call."""

    def __init__(self, *replies: Reply) -> None:
        """Queue the replies to give."""
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.models: list[str] = []
        self.systems: list[str] = []

    def __call__(self, claude: Path, model: str, system: str, prompt: str) -> Reply:
        """Give the next reply."""
        self.prompts.append(prompt)
        self.models.append(model)
        self.systems.append(system)
        return self.replies.pop(0)


@pytest.fixture
def settings(tmp_path: Path) -> KitSettings:
    """Provide kit settings with no real Claude Code CLI."""
    return KitSettings.load(
        {
            "AUDIT_KIT_HOME": str(KIT),
            "AUDIT_PROJECTS_DIR": str(tmp_path / "projects"),
            "AUDIT_WORKSPACES_DIR": str(tmp_path),
            "CLAUDE_BIN": str(tmp_path / "no-claude"),
        }
    )


def configure(
    ws: Workspace, *, mode: str = "full", snapshot: str = "abc123", parallel: int = 1
) -> None:
    """Make the workspace a kit workspace with a validated models.yaml."""
    ws.write_text(
        ".audit/.workspace", f"project: demo\nmode: eval\nsnapshot: {snapshot}\n"
    )
    cfg = yaml.safe_load((KIT / "config/models.example.yaml").read_text())
    cfg["file_review"] = {"mode": mode, "pilot_units": ["u001"]}
    cfg["limits"]["max_parallel_passes"] = parallel
    ws.write_text(".audit/models.yaml", yaml.safe_dump(cfg))
    ws.write_text(".audit/validation.md", "result: pass\n")


@pytest.fixture
def ready(ws: Workspace, settings: KitSettings) -> Callable[..., list[Unit]]:
    """Provide a function that configures the workspace and writes its briefs."""

    def make(**options: Any) -> list[Unit]:
        configure(ws, **options)
        found = list_units(ws)
        review.prepare(ws, found, KIT, settings.version)
        return found

    return make


@pytest.fixture
def make_finding() -> Callable[..., dict[str, Any]]:
    """Provide `finding`: a valid finding with fields overridden."""
    return finding


@pytest.fixture
def make_output() -> Callable[..., dict[str, Any]]:
    """Provide `output`: a valid pass output with its finding overridden."""
    return output


@pytest.fixture
def make_reply() -> Callable[..., Reply]:
    """Provide `reply`: a reply as `claude -p` would give it."""
    return reply


@pytest.fixture
def fake_runner() -> type[FakeRunner]:
    """Provide the fake `claude -p`."""
    return FakeRunner


@pytest.fixture
def kit_home() -> Path:
    """Provide the kit's own folder, for its skills and schema."""
    return KIT
