"""Typed, validated view of a target repository's package.json."""

from __future__ import annotations

import json
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
