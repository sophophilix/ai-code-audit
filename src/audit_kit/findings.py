"""Finding blocks in agent outputs: their IDs, and a parser for them.

Shared by `kit verify` and `kit lookup`, which reads the packages a finding
recommends. The format is defined in `core/skills/audit-findings/SKILL.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ID_RE = r"(?:DISC|ARC|ENG|SEC|A11Y|FILE|TRACE)(?:-[a-z0-9]+)?-\d{3}"
HEADING = re.compile(rf"^### ({ID_RE})\b\s*(.*)$")
FIELD = re.compile(r"^- ([A-Za-z-]+): ?(.*)$")


@dataclass(frozen=True)
class Finding:
    """A finding block parsed from an agent output file."""

    id: str
    fields: dict[str, str]

    def get(self, name: str) -> str:
        """Return a field value, or an empty string if absent."""
        return self.fields.get(name, "")


def parse_findings(text: str) -> list[Finding]:
    """Parse `### ID title` blocks and their `- Field: value` lines."""
    found: list[Finding] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = {"Title": heading.group(2)}
            found.append(Finding(heading.group(1), current))
            continue
        if line.startswith("#"):
            current = None
            continue
        item = FIELD.match(line)
        if current is not None and item:
            current[item.group(1)] = item.group(2).strip()
    return found
