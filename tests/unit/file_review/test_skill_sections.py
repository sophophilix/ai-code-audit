"""ADR 0007 D2: skill sections are chosen by the unit's kind."""

from __future__ import annotations

from pathlib import Path

import pytest

from audit_kit.skill_sections import KINDS, sections_for, tagged_sections

NESTED = (
    "# Skill\n"
    "## A\n<!-- brief: script -->\nintro\n"
    "### A1\n<!-- brief: markup -->\na1\n"
    "### A2\nuntagged sibling\n"
    "## B\nnot tagged\n"
)


def test_a_tagged_section_ends_at_the_next_tagged_heading() -> None:
    first = tagged_sections("x", NESTED)[0]
    assert (first.heading, first.text) == ("## A", "## A\nintro\n")


def test_a_tagged_subsection_ends_at_a_heading_of_its_own_level() -> None:
    second = tagged_sections("x", NESTED)[1]
    assert (second.heading, second.text) == ("### A1", "### A1\na1\n")


def test_untagged_sections_reach_no_brief() -> None:
    texts = "".join(s.text for s in tagged_sections("x", NESTED))
    assert "untagged sibling" not in texts
    assert "not tagged" not in texts


def test_a_tag_with_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown brief kinds"):
        tagged_sections("x", "## A\n<!-- brief: scirpt -->\n")


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_gets_the_finding_field_rules(kind: str, kit_home: Path) -> None:
    profiles = [p.name for p in (kit_home / "profiles").iterdir() if p.is_dir()]
    headings = {(s.source, s.heading) for s in sections_for(kind, kit_home, profiles)}
    assert ("core/skills/audit-findings/SKILL.md", "### Field rules") in headings


def test_a_script_gets_node_rules_and_no_design_rules(kit_home: Path) -> None:
    headings = {s.heading for s in sections_for("script", kit_home, ["node-express"])}
    assert "### Node.js" in headings
    assert "### 2. Design tokens and brand" not in headings


def test_a_stylesheet_gets_design_rules_and_no_javascript_rules(kit_home: Path) -> None:
    headings = {
        s.heading for s in sections_for("stylesheet", kit_home, ["node-express"])
    }
    assert "### 2. Design tokens and brand" in headings
    assert "### Async and the event loop" not in headings
    assert "### 8. Browser security" not in headings


def test_a_manifest_gets_dependency_checks_and_no_code_rules(kit_home: Path) -> None:
    found = sections_for("manifest", kit_home, ["node-express"])
    headings = {s.heading for s in found}
    assert {"## Dependency manifest", "## Manifest checks"} <= headings
    assert "## Check catalogue" not in headings
    assert "### Async and the event loop" not in headings


def test_a_profile_not_loaded_adds_no_sections(kit_home: Path) -> None:
    without = sections_for("markup", kit_home, [])
    assert not any("nsw-local-government" in s.source for s in without)
