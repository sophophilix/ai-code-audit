from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from audit_kit.detection import detect, parse_intake, render, write_outputs
from audit_kit.workspace import Workspace


def test_profiles_come_from_evidence(repo: Path) -> None:
    found = detect(Workspace(repo))
    assert found.resolved == (
        "node-express",
        "mssql",
        "azure-architecture",
        "web-accessibility",
        "nsw-local-government",
        "ai-governance",
    )


def test_vendored_minified_and_licensed_folders_are_excluded(repo: Path) -> None:
    patterns = [e.pattern for e in detect(Workspace(repo)).scope.exclusions]
    assert patterns == ["public/app.min.js", "public/flags", "public/vendor"]


def test_a_site_licence_page_does_not_exclude_its_folder(repo: Path) -> None:
    patterns = [e.pattern for e in detect(Workspace(repo)).scope.exclusions]
    assert "public" not in patterns


def test_ai_service_hostnames_are_signalled(repo: Path) -> None:
    assert any("lib/b.js" in s for s in detect(Workspace(repo)).ai_signals)


def test_placeholder_jurisdiction_selects_no_compliance_profile(
    tmp_path: Path, make_repo: Callable[..., Path]
) -> None:
    root = make_repo(jurisdiction="<e.g. NSW local council>")
    found = detect(Workspace(root))
    assert "nsw-local-government" not in found.resolved
    assert "Organisation and jurisdiction aren't in the intake" in render(
        found, "c", "v"
    )


def test_intake_overrides_add_and_remove_profiles() -> None:
    intake = parse_intake(
        "- Organisation and jurisdiction: NSW council\n- add: python-django, x\n- remove: mssql\n"
    )
    assert intake.add == ("python-django", "x")
    assert intake.remove == ("mssql",)


def test_malformed_package_json_is_listed_for_a_person(
    make_repo: Callable[..., Path],
) -> None:
    # Regression for review findings F3 and F9: detect continues and says why.
    root = make_repo(dependencies=["express"])
    found = detect(Workspace(root))
    assert "node-express" not in found.resolved
    assert "Couldn't use: package.json: unexpected shape" in render(found, "c", "v")


def test_symlinks_are_not_followed_and_are_reported(repo: Path, tmp_path: Path) -> None:
    (tmp_path / "secret.js").write_text('const k = "https://x.openai.azure.com";\n')
    os.symlink(tmp_path / "secret.js", repo / "lib/link.js")
    found = detect(Workspace(repo))
    assert "lib/link.js" not in [str(r) for r in found.scope.own]
    assert "Symlink not followed (check what it points to): `lib/link.js`" in render(
        found, "c", "v"
    )


def test_outputs_are_byte_identical_on_rerun(repo: Path) -> None:
    ws = Workspace(repo)
    write_outputs(ws, detect(ws), "abc", "0.7.1")
    first = (repo / ".audit/detected.md").read_bytes()
    write_outputs(ws, detect(ws), "abc", "0.7.1")
    assert (repo / ".audit/detected.md").read_bytes() == first
    assert (
        repo / ".audit/detected-excludes.txt"
    ).read_text() == "public/app.min.js\npublic/flags\npublic/vendor\n"
    assert (repo / ".audit/inventory.json").is_file()


def test_a_language_no_profile_covers_needs_a_person(repo: Path) -> None:
    (repo / "worker").mkdir()
    (repo / "worker/jobs.py").write_text("import os\n" * 400)
    found = detect(Workspace(repo))
    assert found.uncovered == ("Python",)
    text = render(found, "c", "v")
    assert "No profile covers Python" in text
    assert "Languages (lines in reviewed files): Python 400" in text


def test_languages_the_profiles_cover_are_not_flagged(repo: Path) -> None:
    assert detect(Workspace(repo)).uncovered == ()
