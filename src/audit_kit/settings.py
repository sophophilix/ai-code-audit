"""Kit settings, loaded once at the CLI's composition root."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from audit_kit.errors import AuditKitError

DRAWIO_COMMIT = "053600a"


@dataclass(frozen=True)
class KitSettings:
    """Where the kit, projects, workspaces and external tools live."""

    kit_home: Path
    version: str
    projects_dir: Path
    workspaces_dir: Path
    drawio_dir: Path
    jscpd: Path
    eslint: Path
    tsc: Path
    claude: Path

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> KitSettings:
        """Build settings from the environment.

        Environment variables: AUDIT_KIT_HOME, AUDIT_PROJECTS_DIR,
        AUDIT_WORKSPACES_DIR, DRAWIO_SKILL_DIR, JSCPD_BIN, ESLINT_BIN, TSC_BIN,
        CLAUDE_BIN (the Claude Code CLI that `kit review` runs passes with).

        Raises:
            AuditKitError: If the kit folder (with its VERSION file) can't be found.
        """
        env = os.environ if environ is None else environ
        home = Path.home()
        kit_home = Path(
            env.get("AUDIT_KIT_HOME") or Path(__file__).resolve().parents[2]
        )
        version_file = kit_home / "VERSION"
        if not version_file.is_file():
            raise AuditKitError(
                f"kit folder not found at {kit_home} (set AUDIT_KIT_HOME)"
            )
        default_drawio = (
            home
            / f".local/share/agent-skills/drawio-skill-{DRAWIO_COMMIT}/skills/drawio-skill"
        )
        return cls(
            kit_home=kit_home,
            version=version_file.read_text(encoding="utf-8").strip(),
            projects_dir=Path(env.get("AUDIT_PROJECTS_DIR") or home / "audit-projects"),
            workspaces_dir=Path(
                env.get("AUDIT_WORKSPACES_DIR") or home / "code/audits"
            ),
            drawio_dir=Path(env.get("DRAWIO_SKILL_DIR") or default_drawio),
            jscpd=Path(
                env.get("JSCPD_BIN") or home / "audit-tools/node_modules/.bin/jscpd"
            ),
            eslint=Path(
                env.get("ESLINT_BIN") or home / "audit-tools/node_modules/.bin/eslint"
            ),
            tsc=Path(env.get("TSC_BIN") or home / "audit-tools/node_modules/.bin/tsc"),
            claude=Path(env.get("CLAUDE_BIN") or "claude"),
        )
