from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from audit_kit import cli
from audit_kit.intake import parse_intake
from audit_kit.models_config import ModelsConfig, check_models
from audit_kit.validation import models_schema, validate
from audit_kit.workspace import Workspace

KIT = Path(__file__).resolve().parents[2]
PROFILES = frozenset(p.name for p in (KIT / "profiles").iterdir() if p.is_dir())
INTAKE = """## Intake (required)
- Organisation and jurisdiction: NSW local council
- Repository and commit to audit: demo @ abc123
- Tech lead (passes checkpoints): Tech Lead
- Security owner (gets Critical findings the same day): CISO
- AI use approved by (name, date, scope): ICT manager, 2026-11-01, named ICT staff
- Where the AI provider processes data (region, confirmed by): Australia East, ICT
"""


def claude(label: str = "a", model: str = "claude-sonnet-5-5") -> dict[str, str]:
    return {
        "label": label,
        "provider": "anthropic",
        "model": model,
        "harness": "claude-code",
    }


@pytest.fixture
def config() -> dict[str, Any]:
    agents: dict[str, Any] = {
        a: {"passes": [claude()]}
        for a in (
            "discovery",
            "architect",
            "engineer",
            "security",
            "accessibility",
            "verifier",
            "lead-reviewer",
        )
    }
    agents["coordinator"] = {
        "model": {
            "provider": "anthropic",
            "model": "claude-opus-5-5",
            "harness": "claude-code",
        }
    }
    return {
        "version": 1,
        "limits": {
            "max_parallel_passes": 1,
            "lock_stale_minutes": 30,
            "on_rate_limit": "stop",
        },
        "providers": {
            "anthropic": {
                "family": "claude",
                "approved_in_project_md": True,
                "region": "Australia East",
            }
        },
        "harnesses": {"claude-code": {"providers": ["anthropic"], "invoke": "claude"}},
        "agents": agents,
    }


def errors(cfg: dict[str, Any]) -> list[str]:
    return [
        f"{i.where}: {i.message}"
        for i in check_models(ModelsConfig.model_validate(cfg), PROFILES)
        if i.level == "error"
    ]


def test_a_complete_single_provider_config_has_no_errors(
    config: dict[str, Any],
) -> None:
    assert errors(config) == []


def test_single_family_verifier_without_rule_is_a_warning(
    config: dict[str, Any],
) -> None:
    issues = check_models(ModelsConfig.model_validate(config), PROFILES)
    assert [i.level for i in issues] == ["warning"]


def test_unknown_agent_is_rejected(config: dict[str, Any]) -> None:
    config["agents"]["reviewer"] = {"passes": [claude()]}
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ModelsConfig.model_validate(config)


def test_missing_agent_is_rejected(config: dict[str, Any]) -> None:
    del config["agents"]["lead-reviewer"]
    with pytest.raises(ValueError, match="lead-reviewer"):
        ModelsConfig.model_validate(config)


def test_misspelt_field_is_rejected(config: dict[str, Any]) -> None:
    config["limits"]["max_paralel_passes"] = 2
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ModelsConfig.model_validate(config)


def test_unapproved_provider_in_use_is_an_error(config: dict[str, Any]) -> None:
    config["providers"]["openai"] = {
        "family": "gpt",
        "approved_in_project_md": False,
        "region": "us",
    }
    config["harnesses"]["codex"] = {"providers": ["openai"]}
    config["agents"]["security"]["passes"].append(
        {"label": "b", "provider": "openai", "model": "gpt-x", "harness": "codex"}
    )
    assert (
        "providers.openai: used by a pass but not approved (approved_in_project_md: false)"
        in errors(config)
    )


def test_unused_unapproved_provider_is_fine(config: dict[str, Any]) -> None:
    config["providers"]["openai"] = {"family": "gpt", "approved_in_project_md": False}
    assert errors(config) == []


def test_undefined_provider_and_mismatched_harness_are_errors(
    config: dict[str, Any],
) -> None:
    config["agents"]["engineer"]["passes"] = [
        {"label": "a", "provider": "nobody", "model": "m", "harness": "claude-code"}
    ]
    found = errors(config)
    assert (
        "agents.engineer.passes[a]: provider 'nobody' isn't defined under providers"
        in found
    )
    assert (
        "agents.engineer.passes[a]: harness 'claude-code' can't run provider 'nobody'"
        in found
    )


def test_placeholder_model_and_region_are_errors(config: dict[str, Any]) -> None:
    config["agents"]["security"]["passes"] = [claude(model="<openai-model-id>")]
    config["providers"]["anthropic"]["region"] = "<as confirmed by ICT>"
    found = errors(config)
    assert (
        "agents.security.passes[a]: model id not filled in ('<openai-model-id>')"
        in found
    )
    assert "providers.anthropic: processing region not recorded" in found


def test_duplicate_labels_and_unknown_profiles_are_errors(
    config: dict[str, Any],
) -> None:
    config["agents"]["security"]["passes"] = [
        claude("a"),
        {**claude("a"), "profiles": ["msql"]},
    ]
    found = errors(config)
    assert "agents.security: pass label 'a' used more than once" in found
    assert "agents.security.passes[a]: unknown profile 'msql'" in found


def test_unsatisfiable_verifier_rule_is_an_error(config: dict[str, Any]) -> None:
    config["agents"]["verifier"]["rule"] = "different_family_from_author"
    assert any(
        e.startswith(
            "agents.verifier.rule: no verifier pass from a family other than claude"
        )
        for e in errors(config)
    )


def test_verifier_rule_satisfied_by_a_second_family(config: dict[str, Any]) -> None:
    second = copy.deepcopy(config)
    second["providers"]["openai"] = {
        "family": "gpt",
        "approved_in_project_md": True,
        "region": "Australia East",
    }
    second["harnesses"]["codex"] = {"providers": ["openai"]}
    second["agents"]["verifier"] = {
        "rule": "different_family_from_author",
        "passes": [
            {"label": "gpt", "provider": "openai", "model": "gpt-x", "harness": "codex"}
        ],
    }
    assert errors(second) == []


def test_example_config_parses_and_only_flags_approvals_placeholders_and_regions() -> (
    None
):
    raw = yaml.safe_load((KIT / "config/models.example.yaml").read_text())
    found = errors(raw)
    assert found
    assert all(
        ("not approved" in e or "not filled in" in e or "region not recorded" in e)
        for e in found
    )


def test_committed_schema_matches_the_model() -> None:
    assert (KIT / "config/models.schema.json").read_text() == models_schema()
    assert json.loads(models_schema())["title"] == "agent-audit-kit models.yaml"


def test_intake_reports_placeholders_and_reads_overrides() -> None:
    doc = parse_intake("- Organisation and jurisdiction: <e.g. NSW>\n- add: x, y\n")
    assert "Organisation and jurisdiction" in doc.missing()
    assert doc.add == ("x", "y")
    assert parse_intake(INTAKE).missing() == []


def write_workspace(
    root: Path, cfg: dict[str, Any] | str, intake: str = INTAKE
) -> Workspace:
    (root / ".audit").mkdir(parents=True)
    text = cfg if isinstance(cfg, str) else yaml.safe_dump(cfg, sort_keys=False)
    (root / ".audit/models.yaml").write_text(text)
    (root / ".audit/project.md").write_text(intake)
    return Workspace(root)


def test_valid_workspace_passes_and_writes_a_stable_report(
    tmp_path: Path, config: dict[str, Any]
) -> None:
    ws = write_workspace(tmp_path / "ws", config)
    assert (
        cli.main(["validate", str(ws.root), "--profiles-dir", str(KIT / "profiles")])
        == cli.EXIT_OK
    )
    first = (ws.root / ".audit/validation.md").read_text()
    assert "result: pass" in first
    assert "sha256 .audit/models.yaml:" in first
    cli.main(["validate", str(ws.root)])
    assert (ws.root / ".audit/validation.md").read_text() == first


def test_invalid_yaml_fails_with_its_line(tmp_path: Path) -> None:
    ws = write_workspace(tmp_path / "ws", "version: 1\nagents: [\n")
    result = validate(ws)
    assert not result.passed
    assert "invalid YAML" in result.issues[0].message


def test_missing_files_fail(tmp_path: Path) -> None:
    (tmp_path / "ws").mkdir()
    assert cli.main(["validate", str(tmp_path / "ws")]) == cli.EXIT_CHECKS_FAILED


def test_incomplete_intake_fails(tmp_path: Path, config: dict[str, Any]) -> None:
    ws = write_workspace(
        tmp_path / "ws", config, intake="- Tech lead (passes checkpoints): <name>\n"
    )
    messages = [i.message for i in validate(ws).issues]
    assert (
        "'Tech lead (passes checkpoints)' is empty or still a placeholder" in messages
    )


SOURCE = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
SNAPSHOT = "e4f5a6b7c8d90a1b2c3d4e5f6a7b8c9d0e1f2a3b"


def source_issues(
    root: Path, config: dict[str, Any], repository: str, state: str
) -> list[tuple[str, str]]:
    intake = INTAKE.replace("demo @ abc123", repository)
    ws = write_workspace(root, config, intake=intake)
    (root / ".audit/.workspace").write_text(state)
    return [
        (i.level, i.message)
        for i in validate(ws).issues
        if i.message.startswith(("'Repository", "the eval snapshot"))
    ]


@pytest.mark.parametrize(
    ("repository", "state", "expected"),
    [
        pytest.param(
            "example-app @ a1b2c3d",
            f"mode: real\nsource_commit: {SOURCE}\nsnapshot: {SOURCE}\n",
            [],
            id="real-match",
        ),
        pytest.param(
            "example-app @ 1234abcd",
            f"mode: real\nsource_commit: {SOURCE}\nsnapshot: {SOURCE}\n",
            [("error", "names 1234abcd, but the workspace was made from a1b2c3d4e5f6")],
            id="real-mismatch",
        ),
        pytest.param(
            "example-app @ main",
            f"mode: real\nsource_commit: {SOURCE}\nsnapshot: {SOURCE}\n",
            [("warning", "names no commit id")],
            id="no-commit-id",
        ),
        pytest.param(
            "example-app @ a1b2c3d",
            f"mode: eval\nsource_commit: {SOURCE}\nsource_delta: 15\nsnapshot: {SNAPSHOT}\n",
            [("warning", "differs from a1b2c3d4e5f6 by design (15 path(s)")],
            id="eval-snapshot-not-named",
        ),
        pytest.param(
            "example-app @ a1b2c3d + seeded eval changes (snapshot e4f5a6b)",
            f"mode: eval\nsource_commit: {SOURCE}\nsource_delta: 15\nsnapshot: {SNAPSHOT}\n",
            [],
            id="eval-both-named",
        ),
        pytest.param(
            "example-app @ a1b2c3d",
            "mode: real\nsource_sha256: ab\nsnapshot: x\n",
            [],
            id="folder-source-not-checked",
        ),
    ],
)
def test_intake_commit_is_checked_against_the_workspace_source(
    tmp_path: Path,
    config: dict[str, Any],
    repository: str,
    state: str,
    expected: list[tuple[str, str]],
) -> None:
    found = source_issues(tmp_path / "ws", config, repository, state)
    assert [level for level, _ in found] == [level for level, _ in expected]
    for (_, message), (_, part) in zip(found, expected, strict=True):
        assert part in message


def test_schema_command_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["schema"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["title"] == "agent-audit-kit models.yaml"


def test_file_review_needs_its_agents_and_pilot_units(config: dict[str, Any]) -> None:
    assert errors(config) == []  # off by default; the two agents are optional
    config["file_review"] = {"mode": "pilot"}
    found = errors(config)
    assert any("needs agents.file-reviewer" in e for e in found)
    assert any("pilot needs the tech lead's units" in e for e in found)
    config["agents"]["file-reviewer"] = {
        "passes": [
            claude(),
            {**claude("small", "claude-haiku-5-5"), "max_unit_lines": 100},
        ]
    }
    config["file_review"] = {"mode": "pilot", "pilot_units": ["u001", "u042"]}
    assert errors(config) == []
    config["file_review"]["mode"] = "full"
    assert errors(config) == ["file_review.mode: 'full' needs agents.tracer passes"]
    config["agents"]["tracer"] = {"passes": [claude()]}
    config["agents"]["file-reviewer"]["passes"][0]["max_unit_lines"] = 300
    assert errors(config) == [
        "agents.file-reviewer: every pass has max_unit_lines; one pass must take units of any size"
    ]
    with pytest.raises(ValueError, match="unit ids"):
        ModelsConfig.model_validate({**config, "file_review": {"pilot_units": ["42"]}})


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ("<link or path, version; or none / unknown>", "missing"),
        ("https://brand.example.invalid/kit v4.2", "recorded"),
        ("none", "none"),
        ("Unknown", "unknown"),
    ],
)
def test_the_approved_design_system_is_recorded_missing_or_a_deliberate_answer(
    answer: str, status: str
) -> None:
    text = (
        INTAKE
        + f"- Approved design system or brand kit (location, version): {answer}\n"
    )
    assert parse_intake(text).design_status() == status


def test_a_ui_target_without_a_design_answer_gets_a_warning_not_an_error(
    tmp_path: Path, config: dict[str, Any]
) -> None:
    # The code shows what was built, not what the brand owner approved.
    ws = write_workspace(tmp_path / "ws", config)
    (ws.root / ".audit/detected.md").write_text(
        "## Profiles to load\n\nnode-express, web-accessibility, ai-governance\n"
    )
    result = validate(ws, PROFILES)
    warnings = [i for i in result.issues if i.where.endswith("design system")]
    assert [i.level for i in warnings] == ["warning"]
    assert "ask the brand owner" in warnings[0].message
    assert result.passed
    (ws.root / ".audit/project.md").write_text(
        INTAKE + "- Approved design system or brand kit (location, version): unknown\n"
    )
    assert not any(
        i.where.endswith("design system") for i in validate(ws, PROFILES).issues
    )
    (ws.root / ".audit/detected.md").write_text("## Profiles to load\n\nnode-express\n")
    (ws.root / ".audit/project.md").write_text(INTAKE)
    assert not any(
        i.where.endswith("design system") for i in validate(ws, PROFILES).issues
    )
