"""ADR 0012: the pack contract, private pack folders and what reaches a brief."""

from __future__ import annotations

from pathlib import Path

import pytest

from audit_kit import cli, packs
from audit_kit.detection import LANGUAGES, detect
from audit_kit.settings import KitSettings
from audit_kit.skill_sections import sections_for
from audit_kit.workspace import Workspace

KIT = Path(__file__).resolve().parents[2]
SKILL = """---
name: {name}
description: Use when testing the pack contract.
---

# Demo pack

## Sources
- Example standard: https://example.org/standard

## Check catalogue
<!-- brief: python -->

| CHECK-ID | Check |
|---|---|
| DEMO-ONE | The first check |
"""
PATTERN = """---
id: DEMO-STATE-OUTSIDE
title: Keep state outside the process
status: accepted
applies_to: [hosting]
sources:
  - title: The Twelve-Factor App, VI. Processes
    url: https://12factor.net/processes
seen:
  - date: 2025-03-01
    context: a bank's customer portal
recall: An app keeps sessions in memory behind a load balancer. What breaks?
---

## Principle
A process holds no state that a second instance needs.

## How to check
Search for in-memory session stores.

## Good
Sessions are in a shared cache.

## Bad
Sessions are in a module-level dictionary.
"""


def make_pack(root: Path, folder_name: str = "demo", **manifest: str) -> Path:
    """Write a pack that meets the contract, and return its folder."""
    fields = {
        "name": f'"{folder_name}"',
        "type": '"stack"',
        "version": '"1.0.0"',
        "summary": '"A pack for tests."',
        "languages": '["Python"]',
        "check_prefixes": '["DEMO"]',
        **manifest,
    }
    folder = root / folder_name
    folder.mkdir(parents=True)
    (folder / "pack.toml").write_text(
        "".join(f"{key} = {value}\n" for key, value in fields.items())
    )
    (folder / "SKILL.md").write_text(SKILL.format(name=folder_name))
    return folder


def messages(folder: Path) -> str:
    return "\n".join(
        f"{i.where}: {i.message}"
        for i in packs.check(folder, frozenset(LANGUAGES.values()))
    )


@pytest.mark.parametrize(
    "folder",
    sorted(p for p in (KIT / "profiles").iterdir() if p.is_dir()),
    ids=lambda p: p.name,
)
def test_every_pack_in_the_kit_meets_the_contract(folder: Path) -> None:
    assert packs.check(folder, frozenset(LANGUAGES.values())) == []


def test_a_pack_that_meets_the_contract_has_no_issues(tmp_path: Path) -> None:
    assert messages(make_pack(tmp_path)) == ""


def test_a_folder_without_a_manifest_is_refused(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    with pytest.raises(packs.PackError, match=r"no pack\.toml"):
        packs.load(tmp_path / "demo")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("type", '"language"', "type"),
        ("version", '"1.0"', "version"),
        ("name", '"Demo Pack"', "name"),
        ("check_prefixes", '["demo"]', "check_prefixes"),
        ("owner", '"someone"', "owner"),
    ],
)
def test_a_manifest_field_outside_the_contract_is_refused(
    tmp_path: Path, field: str, value: str, expected: str
) -> None:
    folder = make_pack(tmp_path, **{field: value})
    with pytest.raises(packs.PackError, match=expected):
        packs.load(folder)


def test_a_manifest_that_is_not_toml_is_refused(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    (folder / "pack.toml").write_text("name = \n")
    with pytest.raises(packs.PackError, match="not valid TOML"):
        packs.load(folder)


def test_the_manifest_name_must_match_the_folder(tmp_path: Path) -> None:
    folder = make_pack(tmp_path, name='"other"')
    assert "name must match the folder 'demo'" in messages(folder)


def test_a_check_prefix_the_manifest_does_not_declare_is_an_error(
    tmp_path: Path,
) -> None:
    folder = make_pack(tmp_path)
    with (folder / "SKILL.md").open("a") as skill:
        skill.write("| OTHER-TWO | Someone else's check |\n")
    assert "CHECK-ID prefix 'OTHER' isn't in pack.toml" in messages(folder)


def test_a_borrowed_prefix_is_allowed(tmp_path: Path) -> None:
    folder = make_pack(tmp_path, borrows='["OTHER"]')
    with (folder / "SKILL.md").open("a") as skill:
        skill.write("| OTHER-TWO | Someone else's check |\n")
    assert messages(folder) == ""


def test_a_declared_prefix_that_no_check_uses_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path, check_prefixes='["DEMO", "SPARE"]')
    assert "no check uses the prefix 'SPARE'" in messages(folder)


def test_a_pack_that_cites_no_source_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    skill = folder / "SKILL.md"
    skill.write_text(skill.read_text().replace("https://example.org/standard", "none"))
    assert "cites no source" in messages(folder)


def test_a_brief_tag_with_an_unknown_kind_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    skill = folder / "SKILL.md"
    skill.write_text(skill.read_text().replace("brief: python", "brief: pyhton"))
    assert "unknown brief kinds" in messages(folder)


def test_a_language_detection_does_not_know_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path, languages='["Klingon"]')
    assert "unknown language 'Klingon'" in messages(folder)


def test_a_skill_named_differently_from_the_pack_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    (folder / "SKILL.md").write_text(SKILL.format(name="other"))
    assert "front matter name must be 'demo'" in messages(folder)


def test_a_pack_without_a_skill_file_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    (folder / "SKILL.md").unlink()
    assert "SKILL.md: missing" in messages(folder)


def write_pattern(folder: Path, text: str = PATTERN, stem: str = "") -> None:
    (folder / "patterns").mkdir(exist_ok=True)
    (folder / "patterns" / f"{stem or 'demo-state-outside'}.md").write_text(text)


def test_a_pattern_with_a_source_and_every_heading_passes(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    write_pattern(folder)
    assert messages(folder) == ""


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("## How to check", "## Checking", "missing the heading '## How to check'"),
        ("id: DEMO-STATE-OUTSIDE", "id: OTHER-STATE-OUTSIDE", "prefix this pack owns"),
        ("status: accepted", "status: maybe", "status"),
        ("applies_to: [hosting]", "applies_to: []", "applies_to"),
        ("date: 2025-03-01", "date: last March", "seen.0.date"),
        ("url: https://12factor.net/processes", "url: 12factor.net", "sources.0.url"),
    ],
)
def test_a_pattern_outside_the_contract_is_an_error(
    tmp_path: Path, old: str, new: str, expected: str
) -> None:
    folder = make_pack(tmp_path)
    write_pattern(folder, PATTERN.replace(old, new))
    assert expected in messages(folder)


def test_a_pattern_needs_a_source_or_a_sighting(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    start, end = PATTERN.index("sources:"), PATTERN.index("recall:")
    write_pattern(folder, PATTERN[:start] + PATTERN[end:])
    assert "needs a source or a dated sighting" in messages(folder)


def test_a_pattern_file_is_named_after_its_id(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    write_pattern(folder, stem="notes")
    assert "file must be named demo-state-outside.md" in messages(folder)


def test_a_pattern_without_front_matter_is_an_error(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    write_pattern(folder, "## Principle\nNo front matter.\n")
    assert "no YAML front matter" in messages(folder)


def test_packs_are_found_in_every_folder_and_missing_folders_are_skipped(
    tmp_path: Path,
) -> None:
    make_pack(tmp_path / "a", "one")
    make_pack(tmp_path / "b", "two")
    (tmp_path / "b/.git").mkdir()
    found = packs.find([tmp_path / "a", tmp_path / "absent", tmp_path / "b"])
    assert sorted(found) == ["one", "two"]


def test_two_packs_with_one_name_are_refused(tmp_path: Path) -> None:
    make_pack(tmp_path / "a")
    make_pack(tmp_path / "b")
    with pytest.raises(packs.PackError, match="'demo' is in both"):
        packs.find([tmp_path / "a", tmp_path / "b"])


def test_a_private_pack_reaches_a_brief_without_its_location(tmp_path: Path) -> None:
    make_pack(tmp_path / "private")
    found = sections_for("python", KIT, ["demo"], [tmp_path / "private"])
    sources = {s.source for s in found if "DEMO-ONE" in s.text}
    assert sources == {"profiles/demo/SKILL.md"}


def test_the_python_language_rules_travel_with_the_python_pack() -> None:
    source = "profiles/python/skills/python-review/SKILL.md"
    with_pack = {s.source for s in sections_for("python", KIT, ["python"])}
    without = {s.source for s in sections_for("python", KIT, [])}
    assert source in with_pack
    assert source not in without


def test_a_private_pack_covers_the_languages_it_names(tmp_path: Path) -> None:
    make_pack(tmp_path / "private", languages='["Go"]')
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo/main.go").write_text("package main\n" * 40)
    ws = Workspace(tmp_path / "repo")
    private = packs.languages(packs.find([tmp_path / "private"]).values())
    assert detect(ws).uncovered == ("Go",)
    assert detect(ws, pack_languages=private).uncovered == ("Go",)
    (tmp_path / "repo/.audit").mkdir()
    (tmp_path / "repo/.audit/project.md").write_text("- add: demo\n")
    assert detect(ws, pack_languages=private).uncovered == ()


def test_a_pack_the_intake_adds_but_nobody_installed_is_reported(
    tmp_path: Path,
) -> None:
    (tmp_path / ".audit").mkdir()
    (tmp_path / ".audit/project.md").write_text("- add: banking\n")
    problems = detect(Workspace(tmp_path)).problems
    assert any("'banking', which isn't installed" in p for p in problems)


def test_private_pack_folders_come_from_the_environment(tmp_path: Path) -> None:
    settings = KitSettings.load(
        {"AUDIT_KIT_HOME": str(KIT), "AUDIT_KIT_PACKS": f"{tmp_path}/a:{tmp_path}/b"}
    )
    assert settings.pack_dirs == (tmp_path / "a", tmp_path / "b")
    assert KitSettings.load({"AUDIT_KIT_HOME": str(KIT)}).pack_dirs == ()


def test_pack_check_passes_a_good_pack_and_fails_a_bad_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = make_pack(tmp_path / "good")
    bad = make_pack(tmp_path / "bad", languages='["Klingon"]')
    assert cli.main(["pack-check", str(good)]) == cli.EXIT_OK
    assert cli.main(["pack-check", str(good), str(bad)]) == cli.EXIT_CHECKS_FAILED
    assert "unknown language 'Klingon'" in capsys.readouterr().out
