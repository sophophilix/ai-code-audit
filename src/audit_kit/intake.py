"""Parse the intake section of project.md: the facts only a person can supply."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Label text as written in templates/project.md, in display order.
REQUIRED_LABELS: dict[str, str] = {
    "organisation": "Organisation and jurisdiction",
    "repository": "Repository and commit to audit",
    "tech_lead": "Tech lead (passes checkpoints)",
    "security_owner": "Security owner (gets Critical findings the same day)",
    "ai_approval": "AI use approved by (name, date, scope)",
    "processing_region": "Where the AI provider processes data (region, confirmed by)",
}

# Optional: only a person can say which design is approved. The code and the live
# site show what was built, which may not be what the brand owner signed off.
DESIGN_LABELS: dict[str, str] = {
    "design_system": "Approved design system or brand kit (location, version)",
    "brand_owner": "Brand owner (approves brand and design changes)",
    "fonts": "Approved fonts and licences",
}
# Answers that are deliberate, not missing: there isn't one, or nobody knows yet.
DESIGN_ANSWERS = frozenset({"none", "unknown"})


@dataclass(frozen=True)
class IntakeDoc:
    """Intake values; an empty string means missing or still a `<placeholder>`."""

    values: dict[str, str]
    add: tuple[str, ...]
    remove: tuple[str, ...]
    design: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        """Return one required field's value, or an empty string."""
        return self.values.get(name, "")

    def design_status(self) -> str:
        """`recorded`, `none`, `unknown`, or `missing` for the approved design system."""
        value = self.design.get("design_system", "").strip().lower()
        if not value:
            return "missing"
        return value if value in DESIGN_ANSWERS else "recorded"

    def missing(self) -> list[str]:
        """Return the labels of required fields that are empty or placeholders."""
        return [label for key, label in REQUIRED_LABELS.items() if not self.get(key)]


def field_value(text: str, label: str) -> str:
    """Return the value after `- <label>:`; placeholders like `<name>` count as empty."""
    match = re.search(rf"^- {re.escape(label)}:[ \t]*(.*)$", text, re.M | re.I)
    value = match.group(1).strip() if match else ""
    return "" if value.startswith("<") else value


def parse_intake(text: str) -> IntakeDoc:
    """Parse the intake and profile overrides from project.md text."""

    def names(label: str) -> tuple[str, ...]:
        return tuple(
            n.strip() for n in field_value(text, label).split(",") if n.strip()
        )

    return IntakeDoc(
        values={
            key: field_value(text, label) for key, label in REQUIRED_LABELS.items()
        },
        add=names("add"),
        remove=names("remove"),
        design={key: field_value(text, label) for key, label in DESIGN_LABELS.items()},
    )
