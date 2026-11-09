"""Typed model of .audit/models.yaml and the checks no schema can express.

The Pydantic models forbid unknown keys, so a typo in an agent, provider or field
name is an error rather than a silently ignored setting. `check_models` adds the
cross-references: providers and harnesses exist, used providers are approved,
model IDs are filled in, and the verifier rule can be satisfied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The file reviewer and tracer write findings too (FILE, TRACE); they are optional
# until the file review stage is switched on (ADR 0002).
AUTHOR_AGENTS = (
    "discovery",
    "architect",
    "engineer",
    "security",
    "accessibility",
    "file-reviewer",
    "tracer",
)
PASS_AGENTS = (*AUTHOR_AGENTS, "verifier", "lead-reviewer")


class _Strict(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, populate_by_name=True
    )


class Limits(_Strict):
    """Concurrency and interruption settings."""

    max_parallel_passes: int = Field(default=1, ge=1)
    lock_stale_minutes: int = Field(default=30, ge=1)
    on_rate_limit: Literal["stop"] = "stop"


class Price(_Strict):
    """USD per million tokens, for estimates only."""

    input: float | None = None
    output: float | None = None
    cache_read: float | None = None


class Provider(_Strict):
    """Who runs a model, and whether that use is approved."""

    family: str = Field(min_length=1)
    approved_in_project_md: bool = False
    region: str = ""


class Harness(_Strict):
    """An agent tool and the providers it can run."""

    providers: list[str] = Field(min_length=1)
    invoke: str = ""


class ModelChoice(_Strict):
    """A provider, model and harness."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    harness: str = Field(min_length=1)


class Pass(ModelChoice):
    """One independent run of an agent."""

    label: str = Field(pattern=r"^[a-z0-9-]+$")
    profiles: list[str] | None = None
    # File reviewer only: this pass takes units of at most this many lines, so a
    # smaller model can review short files (ADR 0002 D8).
    max_unit_lines: int | None = Field(default=None, ge=1)


class Coordinator(_Strict):
    """The coordinator runs once, on one model."""

    model: ModelChoice


class AgentPasses(_Strict):
    """An agent's passes, plus the verifier's optional rule."""

    passes: list[Pass] = Field(min_length=1)
    rule: Literal["different_family_from_author"] | None = None


class FileReview(_Strict):
    """Whether the file review stage runs, and on which units for a pilot."""

    mode: Literal["off", "pilot", "full"] = "off"
    # Picked by the tech lead across size bands (ADR 0002 D9), from units.tsv.
    pilot_units: list[str] = Field(default_factory=list)

    @field_validator("mode", mode="before")
    @classmethod
    def _yaml_off(cls, value: object) -> object:
        """YAML 1.1 reads a bare `off` as false; treat it as the word it was."""
        return "off" if value is False else value

    @field_validator("pilot_units")
    @classmethod
    def _unit_ids(cls, value: list[str]) -> list[str]:
        bad = [u for u in value if not re.fullmatch(r"u\d{3,}", u)]
        if bad:
            raise ValueError(f"unit ids look like u042, not {bad[:3]}")
        return value


class Agents(_Strict):
    """Every agent the runbook starts. The file review's two are optional."""

    coordinator: Coordinator
    discovery: AgentPasses
    architect: AgentPasses
    engineer: AgentPasses
    security: AgentPasses
    accessibility: AgentPasses
    verifier: AgentPasses
    lead_reviewer: AgentPasses = Field(alias="lead-reviewer")
    file_reviewer: AgentPasses | None = Field(default=None, alias="file-reviewer")
    tracer: AgentPasses | None = None

    def passes_of(self, agent: str) -> list[Pass]:
        """Return the passes of an agent named as in models.yaml (none if absent)."""
        group: AgentPasses | None = getattr(self, agent.replace("-", "_"))
        return group.passes if group else []


class ModelsConfig(_Strict):
    """The whole of .audit/models.yaml."""

    version: Literal[1]
    limits: Limits = Field(default_factory=Limits)
    prices: dict[str, Price] = Field(default_factory=dict)
    providers: dict[str, Provider] = Field(min_length=1)
    harnesses: dict[str, Harness] = Field(min_length=1)
    agents: Agents
    file_review: FileReview = Field(default_factory=FileReview)

    @field_validator("prices", mode="before")
    @classmethod
    def _empty_prices(cls, value: object) -> object:
        """Treat `prices:` with only commented-out entries (YAML null) as no prices."""
        return {} if value is None else value


@dataclass(frozen=True)
class Issue:
    """One validation result. Errors block a run; warnings don't."""

    level: Literal["error", "warning"]
    where: str
    message: str


def _placeholder(value: str) -> bool:
    return not value.strip() or value.strip().startswith("<")


def check_models(
    cfg: ModelsConfig, known_profiles: frozenset[str] | None = None
) -> list[Issue]:
    """Check cross-references in a structurally valid config.

    Args:
        cfg: The parsed config.
        known_profiles: Profile folder names in the kit, or None to skip that check.

    Returns:
        Errors and warnings, in a stable order.
    """
    issues: list[Issue] = []
    choices: list[tuple[str, ModelChoice]] = [
        ("agents.coordinator.model", cfg.agents.coordinator.model)
    ]
    for agent in PASS_AGENTS:
        passes = cfg.agents.passes_of(agent)
        labels = [p.label for p in passes]
        for dup in sorted({x for x in labels if labels.count(x) > 1}):
            issues.append(
                Issue(
                    "error",
                    f"agents.{agent}",
                    f"pass label '{dup}' used more than once",
                )
            )
        choices += [(f"agents.{agent}.passes[{p.label}]", p) for p in passes]

    used: set[str] = set()
    for where, choice in choices:
        provider = cfg.providers.get(choice.provider)
        if provider is None:
            issues.append(
                Issue(
                    "error",
                    where,
                    f"provider '{choice.provider}' isn't defined under providers",
                )
            )
        else:
            used.add(choice.provider)
        harness = cfg.harnesses.get(choice.harness)
        if harness is None:
            issues.append(
                Issue(
                    "error",
                    where,
                    f"harness '{choice.harness}' isn't defined under harnesses",
                )
            )
        elif choice.provider not in harness.providers:
            issues.append(
                Issue(
                    "error",
                    where,
                    f"harness '{choice.harness}' can't run provider '{choice.provider}'",
                )
            )
        if _placeholder(choice.model):
            issues.append(
                Issue("error", where, f"model id not filled in ('{choice.model}')")
            )
        if known_profiles is not None and isinstance(choice, Pass):
            for profile in choice.profiles or []:
                if profile not in known_profiles:
                    issues.append(Issue("error", where, f"unknown profile '{profile}'"))

    for name in sorted(used):
        provider = cfg.providers[name]
        if not provider.approved_in_project_md:
            issues.append(
                Issue(
                    "error",
                    f"providers.{name}",
                    "used by a pass but not approved (approved_in_project_md: false)",
                )
            )
        if _placeholder(provider.region):
            issues.append(
                Issue("error", f"providers.{name}", "processing region not recorded")
            )

    issues += _verifier_issues(cfg)
    issues += _file_review_issues(cfg)
    return issues


def _file_review_issues(cfg: ModelsConfig) -> list[Issue]:
    review = cfg.file_review
    issues: list[Issue] = []
    if review.mode != "off" and not cfg.agents.passes_of("file-reviewer"):
        issues.append(
            Issue(
                "error",
                "file_review.mode",
                f"'{review.mode}' needs agents.file-reviewer passes",
            )
        )
    if review.mode == "full" and not cfg.agents.passes_of("tracer"):
        issues.append(
            Issue("error", "file_review.mode", "'full' needs agents.tracer passes")
        )
    if review.mode == "pilot" and not review.pilot_units:
        issues.append(
            Issue(
                "error",
                "file_review.pilot_units",
                "a pilot needs the tech lead's units from .audit/work/files/units.tsv",
            )
        )
    passes = cfg.agents.passes_of("file-reviewer")
    if passes and all(p.max_unit_lines for p in passes):
        issues.append(
            Issue(
                "error",
                "agents.file-reviewer",
                "every pass has max_unit_lines; one pass must take units of any size",
            )
        )
    return issues


def _verifier_issues(cfg: ModelsConfig) -> list[Issue]:
    def family(choice: ModelChoice) -> str | None:
        provider = cfg.providers.get(choice.provider)
        return provider.family if provider else None

    author_families = sorted(
        {f for a in AUTHOR_AGENTS for p in cfg.agents.passes_of(a) if (f := family(p))}
    )
    verifier_families = {f for p in cfg.agents.verifier.passes if (f := family(p))}
    if cfg.agents.verifier.rule == "different_family_from_author":
        blocked = [f for f in author_families if not verifier_families - {f}]
        if blocked:
            return [
                Issue(
                    "error",
                    "agents.verifier.rule",
                    f"no verifier pass from a family other than {', '.join(blocked)}; add one, or remove the rule "
                    "and record the limitation in project.md",
                )
            ]
        return []
    if verifier_families <= set(author_families):
        return [
            Issue(
                "warning",
                "agents.verifier",
                "verifier shares a model family with the authors; record this as a limitation in project.md",
            )
        ]
    return []
