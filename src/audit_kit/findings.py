"""Finding blocks in agent outputs: their IDs, and a parser for them.

Shared by `kit verify`, `kit register` and `kit lookup`, which reads the packages
a finding recommends. The format is defined in
`core/skills/audit-findings/SKILL.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ID_RE = r"(?:DISC|ARC|ENG|SEC|A11Y|FILE|TRACE)(?:-[a-z0-9]+)?-\d{3}"
HEADING = re.compile(rf"^### ({ID_RE})\b\s*(.*)$")
FIELD = re.compile(r"^- ([A-Za-z-]+): ?(.*)$")
LOCATION = re.compile(r"^([^\s:]+?)(?::(\d+)(?:-(\d+))?)?(?:\s|$)")


@dataclass(frozen=True)
class Finding:
    """A finding block parsed from an agent output file."""

    id: str
    fields: dict[str, str]
    lines: list[str] = field(default_factory=list)

    def get(self, name: str) -> str:
        """Return a field value, or an empty string if absent."""
        return self.fields.get(name, "")

    @property
    def text(self) -> str:
        """Return the block's lines under its heading, up to the next heading."""
        return "\n".join(self.lines)


def parse_findings(text: str) -> list[Finding]:
    """Parse `### ID title` blocks and their `- Field: value` lines."""
    found: list[Finding] = []
    current: Finding | None = None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = Finding(heading.group(1), {"Title": heading.group(2)})
            found.append(current)
            continue
        if line.startswith("#"):
            current = None
            continue
        if current is None:
            continue
        current.lines.append(line)
        item = FIELD.match(line)
        if item:
            current.fields[item.group(1)] = item.group(2).strip()
    return found
