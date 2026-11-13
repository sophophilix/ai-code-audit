"""Typed, validated views of a target's package.json and pyproject.toml."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from audit_kit.errors import WorkspaceError
from audit_kit.workspace import Workspace


class PackageManifest(BaseModel):
    """The package.json fields the kit relies on; other fields are ignored."""

    model_config = ConfigDict(
        extra="ignore", frozen=True, strict=True, populate_by_name=True
    )

    name: str | None = None
    main: str | None = None
    scripts: dict[str, str] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    dev_dependencies: dict[str, str] = Field(
        default_factory=dict, alias="devDependencies"
    )

    def all_dependencies(self) -> dict[str, str]:
        """Return runtime and development dependencies together."""
        return {**self.dependencies, **self.dev_dependencies}


@dataclass(frozen=True)
class ManifestResult:
    """Outcome of loading package.json.

    Attributes:
        manifest: The validated manifest, or None if absent or invalid.
        problem: Why a present package.json couldn't be used, or None.
    """

    manifest: PackageManifest | None
    problem: str | None


def load_manifest(ws: Workspace) -> ManifestResult:
    """Read and validate package.json at the workspace root.

    Args:
        ws: The workspace.

    Returns:
        The manifest, nothing (no package.json), or a problem description.
    """
    if not ws.exists("package.json"):
        return ManifestResult(manifest=None, problem=None)
    try:
        raw = json.loads(ws.read_text("package.json"))
    except WorkspaceError as exc:
        return ManifestResult(manifest=None, problem=str(exc))
    except json.JSONDecodeError as exc:
        return ManifestResult(
            manifest=None,
            problem=f"package.json: invalid JSON ({exc.msg}, line {exc.lineno})",
        )
    try:
        return ManifestResult(
            manifest=PackageManifest.model_validate(raw), problem=None
        )
    except ValidationError as exc:
        where = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}"
            for err in exc.errors()[:3]
        )
        return ManifestResult(
            manifest=None, problem=f"package.json: unexpected shape ({where})"
        )


# A requirement's distribution name: what comes before any extra, version or marker.
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def requirement_name(requirement: str) -> str | None:
    """Return the normalised distribution name of a PEP 508 requirement string.

    Names are lowercased with runs of `-`, `_` and `.` made one `-` (PEP 503).
    """
    m = _REQUIREMENT_NAME.match(requirement)
    return re.sub(r"[-_.]+", "-", m.group(1)).lower() if m else None


class _PyProjectTable(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    name: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    optional_dependencies: dict[str, list[str]] = Field(
        default_factory=dict, alias="optional-dependencies"
    )


class PyProject(BaseModel):
    """The pyproject.toml fields the kit relies on (ADR 0010 D2)."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    project: _PyProjectTable = Field(default_factory=_PyProjectTable)
    # PEP 735 groups; an entry may be a table such as {include-group = "test"}.
    dependency_groups: dict[str, list[str | dict[str, str]]] = Field(
        default_factory=dict, alias="dependency-groups"
    )

    def runtime(self) -> tuple[str, ...]:
        """Return the names of runtime dependencies, extras included."""
        found = [*self.project.dependencies]
        for extra in self.project.optional_dependencies.values():
            found += extra
        return _names(found)

    def development(self) -> tuple[str, ...]:
        """Return the names of dependency-group entries that aren't also runtime."""
        runtime = set(self.runtime())
        found = [
            e
            for group in self.dependency_groups.values()
            for e in group
            if isinstance(e, str)
        ]
        return tuple(n for n in _names(found) if n not in runtime)


def _names(requirements: list[str]) -> tuple[str, ...]:
    return tuple(sorted({n for r in requirements if (n := requirement_name(r))}))


@dataclass(frozen=True)
class PyProjectResult:
    """Outcome of loading pyproject.toml.

    Attributes:
        pyproject: The validated file, or None if absent or invalid.
        problem: Why a present pyproject.toml couldn't be used, or None.
    """

    pyproject: PyProject | None
    problem: str | None


def load_pyproject(ws: Workspace) -> PyProjectResult:
    """Read and validate pyproject.toml at the workspace root."""
    if not ws.exists("pyproject.toml"):
        return PyProjectResult(pyproject=None, problem=None)
    try:
        raw = tomllib.loads(ws.read_text("pyproject.toml"))
    except WorkspaceError as exc:
        return PyProjectResult(pyproject=None, problem=str(exc))
    except tomllib.TOMLDecodeError as exc:
        return PyProjectResult(
            pyproject=None, problem=f"pyproject.toml: invalid TOML ({exc})"
        )
    try:
        return PyProjectResult(pyproject=PyProject.model_validate(raw), problem=None)
    except ValidationError as exc:
        where = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}"
            for err in exc.errors()[:3]
        )
        return PyProjectResult(
            pyproject=None, problem=f"pyproject.toml: unexpected shape ({where})"
        )
