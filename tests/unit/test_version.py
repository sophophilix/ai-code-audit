"""The kit's version is the same everywhere it is written."""

from __future__ import annotations

import tomllib
from pathlib import Path

from audit_kit import __version__

KIT = Path(__file__).resolve().parents[2]


def test_package_pyproject_and_version_file_agree() -> None:
    project = tomllib.loads((KIT / "pyproject.toml").read_text())["project"]["version"]
    assert __version__ == project == (KIT / "VERSION").read_text().strip()
