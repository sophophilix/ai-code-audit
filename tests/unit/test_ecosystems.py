"""Ecosystems come from file paths alone (ADR 0010 D1)."""

from __future__ import annotations

from audit_kit.ecosystems import lockfiles, of_paths


def test_a_python_repository_is_python_only() -> None:
    assert of_paths(["pyproject.toml", "src/app/cli.py", "README.md"]) == {"python"}


def test_requirements_files_and_stubs_count_as_python() -> None:
    assert of_paths(["requirements-dev.txt"]) == {"python"}
    assert of_paths(["typings/x.pyi"]) == {"python"}


def test_a_repository_can_hold_both() -> None:
    assert of_paths(["web/package.json", "api/main.py"]) == {"javascript", "python"}


def test_prose_and_config_show_no_ecosystem() -> None:
    assert of_paths(["README.md", ".github/workflows/ci.yml"]) == frozenset()


def test_lockfiles_are_found_at_any_depth_in_path_order() -> None:
    found = lockfiles(
        ["uv.lock", "web/package-lock.json", "plugins/x/uv.lock", "a.lock"]
    )
    assert found == ("plugins/x/uv.lock", "uv.lock", "web/package-lock.json")
