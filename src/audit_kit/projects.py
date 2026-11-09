"""Per-system project folders in ~/audit-projects/<name>, created once and reused."""

from __future__ import annotations

import re
from pathlib import Path

from audit_kit.console import ok, say, skip
from audit_kit.errors import AuditKitError
from audit_kit.workspace import Workspace

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STARTERS = {
    "eval-remove.txt": "# Paths removed from eval snapshots (in-repo answer sheets), one per line\n",
    "scan-exclude.txt": "# Extra folders excluded from scans (e.g. vendored libraries), one per line\n",
}


def project_dir(projects_dir: Path, name: str) -> Path:
    """Return a project's folder, refusing names that aren't a single safe segment."""
    if not NAME.match(name):
        raise AuditKitError(
            f"invalid project name '{name}' (letters, digits, '.', '_', '-')"
        )
    return projects_dir / name


def list_lines(path: Path) -> list[str]:
    """Return non-empty, non-comment lines of a small text file (missing means none)."""
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def create_project(kit_home: Path, projects_dir: Path, name: str) -> Path:
    """Create a project folder from the kit's templates; never overwrite a file."""
    folder = project_dir(projects_dir, name)
    folder.mkdir(parents=True, exist_ok=True)
    projects_dir.chmod(0o700)
    ws = Workspace(folder)
    ws.mkdir("keys")
    ws.mkdir("templates")
    ws.path("keys").chmod(0o700)
    sources = {
        "project.md": kit_home / "templates/project.md",
        "models.yaml": kit_home / "config/models.example.yaml",
        "policy.yaml": kit_home / "config/policy.example.yaml",
        "beliefs.md": kit_home / "templates/beliefs.md",
    }
    for target, source in sources.items():
        if ws.exists(target):
            skip(f"{target} exists")
        else:
            ws.copy_in(target, source)
            ok(f"created {target}")
    for target, text in {**STARTERS, "notes.md": f"# Kit notes for {name}\n"}.items():
        if not ws.exists(target):
            ws.write_text(target, text)
            ok(f"created {target}")
    say(f"Project folder: {folder}")
    say(
        "  required: the Intake section of project.md (six lines). Everything else is detected or discovered."
    )
    say(
        "  optional: beliefs.md (team beliefs, tested blind), models.yaml, policy.yaml (network lookups), eval-remove.txt, scan-exclude.txt"
    )
    say(
        "  answer keys go in keys/; optional Word/PowerPoint templates in templates/report.docx, templates/deck.pptx"
    )
    return folder
