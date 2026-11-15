"""Skill sections chosen by unit kind, for the file review's briefs (ADR 0007 D2).

A section is chosen by a tag on the line after its heading:

    ### 8. Browser security
    <!-- brief: markup, component, inline script -->

A tagged section runs to the next heading of the same or a higher level, or to
the next tagged heading, whichever comes first. Untagged sections are for the
stage agents and never reach a brief.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from audit_kit.units import Unit

# `file` units split by extension: a .jsx component needs the front-end rules,
# a .sql file needs neither the JavaScript nor the front-end ones, and a .py file
# needs the Python rules (ADR 0010 D4).
KINDS = (
    "script",
    "python",
    "component",
    "sql",
    "inline script",
    "markup",
    "stylesheet",
    "inline style",
    "manifest",
)
ALL = "all"
TAG = re.compile(r"^<!-- brief: (?P<kinds>[a-z ,]+) -->$")
HEADING = re.compile(r"^(?P<hashes>#{2,6}) \S")
CORE_SKILLS = (
    "audit-findings",
    "javascript-review",
    "frontend-review",
    "ai-generated-code-quality",
)


def kind_of(unit: Unit) -> str:
    """Return the kind a unit's skill sections are chosen by."""
    if unit.kind != "file":
        return unit.kind
    if unit.path.endswith(".sql"):
        return "sql"
    if unit.path.endswith((".py", ".pyi")):
        return "python"
    if unit.path.endswith((".jsx", ".tsx")):
        return "component"
    return "script"


@dataclass(frozen=True)
class Section:
    """One tagged skill section."""

    source: str
    heading: str
    kinds: frozenset[str]
    text: str

    def applies_to(self, kind: str) -> bool:
        """Return True if this section is for units of this kind."""
        return kind in self.kinds or ALL in self.kinds


@dataclass(frozen=True)
class _Start:
    index: int
    level: int
    kinds: frozenset[str]


def _starts(source: str, lines: list[str]) -> list[_Start]:
    starts: list[_Start] = []
    for i, line in enumerate(lines[:-1]):
        heading = HEADING.match(line)
        tag = TAG.match(lines[i + 1])
        if heading is None or tag is None:
            continue
        kinds = frozenset(k.strip() for k in tag.group("kinds").split(","))
        unknown = kinds - {*KINDS, ALL}
        if unknown:
            raise ValueError(f"{source}: unknown brief kinds {sorted(unknown)}")
        starts.append(_Start(i, len(heading.group("hashes")), kinds))
    return starts


def tagged_sections(source: str, text: str) -> list[Section]:
    """Return a skill file's tagged sections, in file order.

    Args:
        source: The file's path relative to the kit, for messages and grouping.
        text: The file's Markdown.

    Raises:
        ValueError: If a tag names a kind the kit doesn't know.
    """
    lines = text.split("\n")
    starts = _starts(source, lines)
    tagged = {s.index for s in starts}
    sections: list[Section] = []
    for start in starts:
        end = next(
            (
                j
                for j in range(start.index + 1, len(lines))
                if (m := HEADING.match(lines[j]))
                and (len(m.group("hashes")) <= start.level or j in tagged)
            ),
            len(lines),
        )
        body = [x for x in lines[start.index : end] if not TAG.match(x)]
        sections.append(
            Section(
                source=source,
                heading=lines[start.index],
                kinds=start.kinds,
                text="\n".join(body).rstrip() + "\n",
            )
        )
    return sections


def pack_files(folder: Path) -> list[Path]:
    """Return a pack's Markdown files a brief may draw from, in a fixed order.

    The pack's own SKILL.md comes first, then its references, then the skills
    that travel with it (ADR 0012 D2).
    """
    candidates = [
        folder / "SKILL.md",
        *sorted(folder.glob("references/*.md")),
        *sorted(folder.glob("skills/*/SKILL.md")),
    ]
    return [p for p in candidates if p.is_file()]


def skill_files(
    kit_home: Path, profiles: Iterable[str], pack_dirs: Sequence[Path] = ()
) -> list[tuple[str, Path]]:
    """Return the skill and pack files a brief may draw from, in a fixed order.

    Args:
        kit_home: The kit folder, which holds the core skills and the kit's packs.
        profiles: Names of the packs to load.
        pack_dirs: Folders of private packs, searched after the kit's own.
    """
    files = [
        (f"core/skills/{name}/SKILL.md", kit_home / f"core/skills/{name}/SKILL.md")
        for name in CORE_SKILLS
    ]
    for profile in profiles:
        folder = next(
            (
                root / profile
                for root in (kit_home / "profiles", *pack_dirs)
                if (root / profile).is_dir()
            ),
            None,
        )
        if folder is None:
            continue
        # A private pack gets the same label shape, so a brief never shows where
        # on this machine the pack lives.
        files += [
            (f"profiles/{profile}/{p.relative_to(folder).as_posix()}", p)
            for p in pack_files(folder)
        ]
    return files


def sections_for(
    kind: str, kit_home: Path, profiles: Iterable[str], pack_dirs: Sequence[Path] = ()
) -> list[Section]:
    """Return every tagged section that applies to a kind of unit."""
    return [
        section
        for source, path in skill_files(kit_home, profiles, pack_dirs)
        for section in tagged_sections(source, path.read_text(encoding="utf-8"))
        if section.applies_to(kind)
    ]


def render(sections: list[Section]) -> str:
    """Render the rules part of a brief, grouped by the file each section came from."""
    out: list[str] = []
    current = ""
    for section in sections:
        if section.source != current:
            current = section.source
            out.append(f"### From `{section.source}`\n")
        # Headings move down two levels, so they sit under the brief's "## Rules".
        out.append(re.sub(r"^(#{2,4}) ", r"\1## ", section.text, flags=re.M))
    return "\n".join(out)
