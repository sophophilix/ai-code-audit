from __future__ import annotations

import json
from pathlib import Path

from audit_kit.manifest import load_manifest, load_pyproject, requirement_name
from audit_kit.workspace import Workspace


def write_package(tmp_path: Path, content: str) -> Workspace:
    (tmp_path / "package.json").write_text(content)
    return Workspace(tmp_path)


def test_absent_package_json_is_not_a_problem(tmp_path: Path) -> None:
    result = load_manifest(Workspace(tmp_path))
    assert result.manifest is None
    assert result.problem is None


def test_valid_manifest_merges_dev_dependencies(tmp_path: Path) -> None:
    ws = write_package(
        tmp_path,
        json.dumps(
            {
                "main": "s.js",
                "dependencies": {"express": "4"},
                "devDependencies": {"jest": "29"},
            }
        ),
    )
    manifest = load_manifest(ws).manifest
    assert manifest is not None
    assert manifest.all_dependencies() == {"express": "4", "jest": "29"}


def test_list_shaped_dependencies_is_reported_not_raised(tmp_path: Path) -> None:
    # Regression for review finding F3: this used to raise TypeError.
    result = load_manifest(
        write_package(tmp_path, json.dumps({"dependencies": ["express"]}))
    )
    assert result.manifest is None
    assert result.problem is not None
    assert "unexpected shape" in result.problem


def test_non_string_version_is_rejected(tmp_path: Path) -> None:
    result = load_manifest(
        write_package(tmp_path, json.dumps({"dependencies": {"express": 4}}))
    )
    assert result.manifest is None


def test_invalid_json_is_reported(tmp_path: Path) -> None:
    result = load_manifest(write_package(tmp_path, "{not json"))
    assert result.problem is not None
    assert "invalid JSON" in result.problem


def write_pyproject(tmp_path: Path, content: str) -> Workspace:
    (tmp_path / "pyproject.toml").write_text(content)
    return Workspace(tmp_path)


def test_pyproject_names_runtime_extras_and_groups(tmp_path: Path) -> None:
    ws = write_pyproject(
        tmp_path,
        """
[project]
name = "app"
dependencies = ["OpenAI>=1", "pydantic[email]>=2; python_version>'3.10'"]
[project.optional-dependencies]
office = ["markitdown>=0.1"]
[dependency-groups]
dev = [{ include-group = "test" }, "ruff>=0.15"]
test = ["pytest>=9", "pydantic>=2"]
""",
    )
    pyproject = load_pyproject(ws).pyproject
    assert pyproject is not None
    assert pyproject.runtime() == ("markitdown", "openai", "pydantic")
    assert pyproject.development() == ("pytest", "ruff")


def test_requirement_names_are_normalised() -> None:
    assert requirement_name("Typing_Extensions >= 4") == "typing-extensions"
    assert requirement_name("  ") is None


def test_invalid_pyproject_is_reported_not_raised(tmp_path: Path) -> None:
    result = load_pyproject(write_pyproject(tmp_path, "[project\nname = 1"))
    assert result.pyproject is None
    assert result.problem is not None and "invalid TOML" in result.problem


def test_pyproject_with_a_wrong_shape_is_reported(tmp_path: Path) -> None:
    result = load_pyproject(
        write_pyproject(tmp_path, '[project]\ndependencies = "x"\n')
    )
    assert result.problem is not None and "unexpected shape" in result.problem
