"""Validate a workspace's models.yaml and intake before an audit run.

Writes .audit/validation.md, which pre-flight reads. The file has no timestamp;
it records the inputs' SHA-256 so a stale result can be spotted.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError

from audit_kit.detection import loaded_profiles
from audit_kit.errors import WorkspaceError
from audit_kit.intake import DESIGN_LABELS, IntakeDoc, parse_intake
from audit_kit.models_config import Issue, ModelsConfig, check_models
from audit_kit.state import State
from audit_kit.workspace import Workspace

MODELS = PurePosixPath(".audit/models.yaml")
PROJECT = PurePosixPath(".audit/project.md")
OUTPUT = PurePosixPath(".audit/validation.md")
COMMIT_ID = re.compile(r"\b[0-9a-f]{7,40}\b")
REPOSITORY = "'Repository and commit to audit'"


@dataclass(frozen=True)
class ValidationResult:
    """Issues found, and fingerprints of the files checked."""

    issues: tuple[Issue, ...]
    fingerprints: tuple[tuple[str, str], ...]

    @property
    def passed(self) -> bool:
        """Return True when there are no errors (warnings allowed)."""
        return not any(i.level == "error" for i in self.issues)


def known_profiles(profiles_dir: Path | None) -> frozenset[str] | None:
    """Return the kit's profile names, or None when no folder is given."""
    if profiles_dir is None or not profiles_dir.is_dir():
        return None
    return frozenset(p.name for p in profiles_dir.iterdir() if p.is_dir())


def _read(
    ws: Workspace,
    rel: PurePosixPath,
    issues: list[Issue],
    prints: list[tuple[str, str]],
) -> str | None:
    if not ws.is_file(rel):
        issues.append(
            Issue(
                "error",
                str(rel),
                "missing (copy it from the project folder with `kit install`)",
            )
        )
        return None
    try:
        text = ws.read_text(rel)
    except WorkspaceError as exc:
        issues.append(Issue("error", str(rel), str(exc)))
        return None
    prints.append((str(rel), hashlib.sha256(text.encode()).hexdigest()))
    return text


def _models_issues(text: str, profiles: frozenset[str] | None) -> list[Issue]:
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = f" (line {mark.line + 1})" if mark is not None else ""
        return [Issue("error", str(MODELS), f"invalid YAML{line}")]
    try:
        cfg = ModelsConfig.model_validate(raw)
    except ValidationError as exc:
        return [
            Issue(
                "error",
                ".".join(str(p) for p in err["loc"]) or "models.yaml",
                err["msg"],
            )
            for err in exc.errors()
        ]
    return check_models(cfg, profiles)


def _source_issues(repository: str, state: State) -> list[Issue]:
    """Check the intake's commit against the commit the workspace was made from.

    Workspaces made from a folder or archive have no source commit and aren't checked.
    """
    source, snapshot = state.get("source_commit"), state.get("snapshot")
    if not source or not repository:
        return []
    where = f"{PROJECT} intake"
    named = COMMIT_ID.findall(repository.lower())
    if not named:
        return [
            Issue(
                "warning",
                where,
                f"{REPOSITORY} names no commit id; the workspace was made from {source[:12]}",
            )
        ]
    if not any(source.startswith(n) or snapshot.startswith(n) for n in named):
        return [
            Issue(
                "error",
                where,
                f"{REPOSITORY} names {', '.join(named)}, but the workspace was made from {source[:12]}",
            )
        ]
    snapshot_named = any(snapshot.startswith(n) for n in named)
    if (
        state.get("mode") == "eval"
        and snapshot not in ("", source)
        and not snapshot_named
    ):
        changed = state.get("source_delta") or "some"
        return [
            Issue(
                "warning",
                where,
                f"the eval snapshot {snapshot[:12]} differs from {source[:12]} by design "
                f"({changed} path(s) removed or seeded, listed in the project's keys/); "
                f"name both, e.g. '@ {source[:7]} + seeded eval changes (snapshot {snapshot[:7]})'",
            )
        ]
    return []


def validate(ws: Workspace, profiles: frozenset[str] | None = None) -> ValidationResult:
    """Validate models.yaml and the intake in project.md."""
    issues: list[Issue] = []
    prints: list[tuple[str, str]] = []
    models = _read(ws, MODELS, issues, prints)
    if models is not None:
        issues += _models_issues(models, profiles)
    project = _read(ws, PROJECT, issues, prints)
    if project is not None:
        intake = parse_intake(project)
        issues += [
            Issue(
                "error",
                f"{PROJECT} intake",
                f"'{label}' is empty or still a placeholder",
            )
            for label in intake.missing()
        ]
        issues += _source_issues(intake.get("repository"), State(ws))
        issues += _design_issues(ws, intake)
    return ValidationResult(issues=tuple(issues), fingerprints=tuple(prints))


def _design_issues(ws: Workspace, intake: IntakeDoc) -> list[Issue]:
    """Warn when a target with a user interface has no answer on its approved design.

    The code and the live site show what was built, not what the brand owner
    approved, so the audit has to ask. A warning, not an error: `none` and
    `unknown` are valid answers, and the agents then treat tokens as as-built.
    """
    detected = ".audit/detected.md"
    if not ws.is_file(detected) or "web-accessibility" not in loaded_profiles(
        ws.read_text(detected)
    ):
        return []
    if intake.design_status() != "missing":
        return []
    label = DESIGN_LABELS["design_system"]
    return [
        Issue(
            "warning",
            f"{PROJECT} design system",
            f"the target has a user interface but '{label}' is empty: ask the brand "
            "owner, or write 'none' or 'unknown'. Until then, tokens and fonts in "
            "the code are treated as as-built, not approved",
        )
    ]


def render(result: ValidationResult) -> str:
    """Render validation.md (no timestamp, so re-runs on the same inputs are identical)."""
    out = [
        "---",
        "generated_by: kit validate (deterministic, no AI)",
        f"result: {'pass' if result.passed else 'fail'}",
    ]
    out += [f"sha256 {name}: {digest}" for name, digest in result.fingerprints]
    out += ["---", "# Configuration validation", ""]
    if not result.issues:
        out.append("No issues.")
    else:
        out += ["| Level | Where | Issue |", "|---|---|---|"]
        out += [f"| {i.level} | `{i.where}` | {i.message} |" for i in result.issues]
    out += [
        "",
        "Re-run `make validate WS=<workspace>` after editing models.yaml or project.md.",
    ]
    return "\n".join(out) + "\n"


def models_schema() -> str:
    """Return the JSON Schema for models.yaml, for editors and other languages."""
    schema = ModelsConfig.model_json_schema(by_alias=True)
    schema["title"] = "agent-audit-kit models.yaml"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
