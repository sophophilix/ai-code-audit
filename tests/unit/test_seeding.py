from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from audit_kit.errors import SeedError, WorkspaceError
from audit_kit.seeding import import_path, seed
from audit_kit.workspace import Workspace


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_plants_issues_and_writes_the_key_outside(repo: Path, tmp_path: Path) -> None:
    key = tmp_path / "keys/seeded.md"
    plan = seed(Workspace(repo), key)
    text = key.read_text()
    assert len(plan.plants) == 19
    for expected in (
        "SQL-INJECTION:lib/wardLookup.js",
        "X-hardcoded-secret:lib/mapsConfig.js",
        "SLOP-FAKE-TEST:scripts/lookup-check.js",
        "WCAG-1.3.1:public/index.html",
        "WCAG-2.4.7:public/site.css",
        "X-ai-directed-text:lib/a.js",
        "SLOP-PHANTOM-DEP:package.json",
        "EXP-SESSION:lib/wardLookup.js",
        "NODE-EMITTER-ERROR:lib/statusLog.js",
        "NODE-AWAIT-RETURN:lib/statusLog.js",
    ):
        assert expected in text
    assert (
        (repo / "server.js")
        .read_text()
        .rstrip()
        .endswith('app.use(require("./lib/wardLookup"));')
    )


def test_every_recorded_location_points_at_its_plant(
    repo: Path, tmp_path: Path
) -> None:
    plan = seed(Workspace(repo), tmp_path / "key.md")
    for plant in plan.plants:
        path, line = plant.location.rsplit(":", 1)
        assert len((repo / path).read_text().splitlines()) >= int(line), plant


def test_package_json_keeps_its_formatting(repo: Path, tmp_path: Path) -> None:
    before = (repo / "package.json").read_text()
    seed(Workspace(repo), tmp_path / "key.md")
    after = (repo / "package.json").read_text()
    deps = json.loads(after)["dependencies"]
    assert deps["left-pad"] == "^1.3.0"
    assert deps["express-session"] == "^1.18.1"
    assert (
        after.replace('    "left-pad": "^1.3.0",\n', "").replace(
            '    "express-session": "^1.18.1",\n', ""
        )
        == before
    )


def test_session_dependency_already_declared_is_not_added_twice(
    tmp_path: Path, make_repo: Callable[..., Path]
) -> None:
    root = make_repo()
    (root / "package.json").write_text(
        '{\n  "main": "server.js",\n  "dependencies": {\n    "express": "4",\n    "express-session": "1"\n  }\n}\n'
    )
    seed(Workspace(root), tmp_path / "key.md")
    text = (root / "package.json").read_text()
    assert text.count('"express-session"') == 1
    assert json.loads(text)["dependencies"]["express-session"] == "1"


def test_empty_dependencies_stay_valid_json(
    tmp_path: Path, make_repo: Callable[..., Path]
) -> None:
    root = make_repo()
    (root / "package.json").write_text(
        '{\n  "main": "server.js",\n  "dependencies": {\n    "express": "4"\n  },\n  "devDependencies": {}\n}\n'
    )
    seed(Workspace(root), tmp_path / "key.md")
    assert (
        json.loads((root / "package.json").read_text())["dependencies"]["left-pad"]
        == "^1.3.0"
    )


def test_mounts_before_a_catch_all_handler(
    tmp_path: Path, make_repo: Callable[..., Path]
) -> None:
    root = make_repo(catch_all=True)
    seed(Workspace(root), tmp_path / "key.md")
    server = (root / "server.js").read_text()
    assert server.index("wardLookup") < server.index("res.status(404)")


def test_no_sql_plant_without_mssql(
    tmp_path: Path, make_repo: Callable[..., Path]
) -> None:
    root = make_repo(dependencies={"express": "^4.21.0"})
    seed(Workspace(root), tmp_path / "key.md")
    assert "SQL-INJECTION" not in (tmp_path / "key.md").read_text()


def test_package_main_outside_the_workspace_is_never_written(
    repo: Path, tmp_path: Path
) -> None:
    # Regression for review finding F2.
    outside = tmp_path / "outside.js"
    outside.write_text('const express = require("express");\nconst app = express();\n')
    data = json.loads((repo / "package.json").read_text())
    data["main"] = "../outside.js"
    (repo / "package.json").write_text(json.dumps(data, indent=2) + "\n")
    seed(Workspace(repo), tmp_path / "key.md")
    assert "wardLookup" not in outside.read_text()
    assert "wardLookup" in (repo / "server.js").read_text()


def test_symlinked_files_are_never_written(repo: Path, tmp_path: Path) -> None:
    # Regression for review finding F2: a symlinked stylesheet must not receive a plant.
    victim = tmp_path / "victim.css"
    victim.write_text("/* outside */\n")
    (repo / "public/site.css").unlink()
    os.symlink(victim, repo / "public/site.css")
    seed(Workspace(repo), tmp_path / "key.md")
    assert victim.read_text() == "/* outside */\n"


def test_a_name_collision_changes_nothing(repo: Path, tmp_path: Path) -> None:
    # Regression for review finding F6: all or nothing.
    (repo / "lib/mapsConfig.js").write_text("existing\n")
    before = snapshot(repo)
    with pytest.raises(SeedError, match="already exists"):
        seed(Workspace(repo), tmp_path / "key.md")
    assert snapshot(repo) == before
    assert not (tmp_path / "key.md").exists()


def test_a_failed_write_leaves_no_plants_and_no_key(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = snapshot(repo)
    real_write = Path.write_text

    def failing_write(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self.name == "notify.js":
            raise OSError("disk full")
        return real_write(self, data, encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", failing_write)
    with pytest.raises(WorkspaceError):
        seed(Workspace(repo), tmp_path / "key.md")
    assert snapshot(repo) == before
    assert not list(tmp_path.glob("key.md*"))


def test_refuses_a_key_inside_the_workspace(repo: Path) -> None:
    with pytest.raises(SeedError, match="outside the workspace"):
        seed(Workspace(repo), repo / "key.md")


def test_refuses_a_repository_without_package_json(tmp_path: Path) -> None:
    (tmp_path / "ws").mkdir()
    with pytest.raises(SeedError, match=r"no package\.json"):
        seed(Workspace(tmp_path / "ws"), tmp_path / "key.md")


def test_require_paths_are_relative_and_clean() -> None:
    from pathlib import PurePosixPath as P

    assert import_path(P("server.js"), P("lib/wardLookup.js")) == "./lib/wardLookup"
    assert import_path(P("scripts/c.js"), P("lib/notify.js")) == "../lib/notify"


@pytest.mark.node
def test_plants_are_valid_javascript(repo: Path, tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    seed(Workspace(repo), tmp_path / "key.md")
    for path in [
        *sorted((repo / "lib").glob("*.js")),
        repo / "server.js",
        repo / "scripts/lookup-check.js",
    ]:
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, f"{path}: {result.stderr}"
