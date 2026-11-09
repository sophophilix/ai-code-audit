"""The inventory records every path; classes decide review, never recording.

Each test pins one failure found in the first pilot run (ADR 0001).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from audit_kit.inventory import Inventory, build, exclusions
from audit_kit.workspace import Workspace
from audit_kit.workspaces import cross_check


def write(root: Path, rel: str, data: str | bytes = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)


def classes(inv: Inventory) -> dict[str, str]:
    return {e.path: e.cls for e in inv.entries}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def test_nothing_is_skipped_by_name_or_ignore_rules(root: Path) -> None:
    write(root, ".gitignore", "dist/\n.hidden\nnode_modules/\n")
    write(root, ".hidden")
    write(root, "node_modules/left-pad/index.js")
    write(root, "src/app.js")
    write(root, ".git/HEAD", "ref\n")
    paths = classes(build(Workspace(root)))
    assert set(paths) == {
        ".gitignore",
        ".hidden",
        "node_modules/left-pad/index.js",
        "src/app.js",
    }
    assert paths["node_modules/left-pad/index.js"] == "vendored"


def test_vendored_files_get_a_reason_a_scope_and_identification_clues(
    root: Path,
) -> None:
    # Shaped like the pilot app's face-api.js: upstream in the header, version deep inside.
    header = "/*\n  homepage: <https://github.com/vladmandic/face-api>\n*/\n"
    body = header + "var a;" * 3000 + 'VERSION:"1.7.12"'
    write(root, "public/vendor/face-api.js", body)
    entry = build(Workspace(root)).entries[0]
    assert (entry.cls, entry.scope) == ("vendored", "public/vendor")
    assert "linguist vendor.yml" in entry.reason
    assert entry.upstream == "https://github.com/vladmandic/face-api"
    assert entry.version == "1.7.12"
    assert len(entry.sha256) == 64


def test_files_inside_an_excluded_folder_are_not_listed_twice(root: Path) -> None:
    write(root, "public/vendor/a.min.js")
    write(root, "public/vendor/b.js")
    write(root, "public/app.min.js")
    patterns = [p for p, _ in exclusions(build(Workspace(root)))]
    assert patterns == ["public/app.min.js", "public/vendor"]


def test_pipelines_and_config_stay_reviewed(root: Path) -> None:
    for rel in (
        ".github/workflows/ci.yml",
        "Jenkinsfile",
        ".gitignore",
        "env/prod.json",
    ):
        write(root, rel)
    assert set(classes(build(Workspace(root))).values()) == {"own"}


def test_build_output_is_generated_when_a_script_builds_it(root: Path) -> None:
    write(root, "dist/bundle.js")
    write(root, "package.json", '{"scripts": {"build": "webpack --output-path dist"}}')
    inv = build(Workspace(root))
    assert classes(inv) == {"dist/bundle.js": "generated", "package.json": "own"}
    assert "built by package.json" in inv.entries[0].reason
    assert [p for p, _ in exclusions(inv)] == ["dist"]


def test_a_script_named_build_does_not_prove_the_build_folder(root: Path) -> None:
    # Review finding F4: the key "build" isn't evidence; the command writes to lib/.
    write(root, "build/a.js")
    write(root, "package.json", '{"scripts": {"build": "tsc --outDir lib"}}')
    entry = next(e for e in build(Workspace(root)).entries if e.path == "build/a.js")
    assert entry.cls == "own" and entry.reason.startswith("generated claim unverified")


def test_package_json_output_fields_prove_a_build_folder(root: Path) -> None:
    write(root, "out/index.js")
    write(root, "package.json", '{"main": "out/index.js", "scripts": {}}')
    entry = next(e for e in build(Workspace(root)).entries if e.path == "out/index.js")
    assert entry.cls == "generated"


def test_a_build_folder_nothing_builds_stays_in_review(root: Path) -> None:
    # Labels are claims (ADR 0004 D2): a folder name alone doesn't hide code.
    write(root, "dist/bundle.js")
    write(root, "dist/package.json", '{"files": ["dist"]}')
    inv = build(Workspace(root))
    entry = inv.entries[0]
    assert (entry.cls, entry.scope) == ("own", "dist/bundle.js")
    assert entry.reason.startswith("generated claim unverified")
    assert exclusions(inv) == ()


def test_binary_files_are_recorded(root: Path) -> None:
    write(root, "models/weights.bin", b"\x00\x01\x02")
    assert classes(build(Workspace(root))) == {"models/weights.bin": "binary"}


def test_symlinks_are_recorded_with_their_target_and_not_followed(
    root: Path, tmp_path: Path
) -> None:
    (tmp_path / "secret.txt").write_text("s\n")
    os.symlink(tmp_path / "secret.txt", root / "link.txt")
    (entry,) = build(Workspace(root)).entries
    assert (entry.kind, entry.cls, entry.sha256) == ("symlink", "symlink", "")
    assert entry.target == str(tmp_path / "secret.txt")


def test_a_targets_claude_folder_is_reported_but_the_kits_is_not(root: Path) -> None:
    write(root, ".claude/settings.json", "{}\n")
    assert classes(build(Workspace(root))) == {
        ".claude/settings.json": "ai-instructions"
    }
    write(root, ".audit-kit/VERSION", "0.10.0\n")
    assert classes(build(Workspace(root))) == {}


def test_quarantined_files_are_recorded_at_their_original_path(root: Path) -> None:
    write(root, ".audit/quarantine/CLAUDE.md", "# rules\n")
    write(root, ".audit/detected.md", "kit output\n")
    assert classes(build(Workspace(root))) == {"CLAUDE.md": "ai-instructions"}


def test_gitattributes_overrides_linguist(root: Path) -> None:
    write(
        root,
        ".gitattributes",
        "third/** linguist-vendored\nvendor/ours.js -linguist-vendored\n",
    )
    write(root, "third/lib.js")
    write(root, "vendor/ours.js")
    found = classes(build(Workspace(root)))
    assert found["third/lib.js"] == "vendored"
    assert found["vendor/ours.js"] == "own"


def test_data_files_are_flagged_even_inside_vendored_folders(root: Path) -> None:
    write(root, "vendor/.env", "K=v\n")
    assert classes(build(Workspace(root))) == {"vendor/.env": "data-candidate"}


def test_gitlinks_become_submodule_entries(root: Path) -> None:
    (entry,) = build(Workspace(root), (("libs/shared", "a" * 40),)).entries
    assert (entry.kind, entry.cls, entry.git_blob) == (
        "submodule",
        "submodule",
        "a" * 40,
    )


def test_json_is_byte_identical_on_rerun(root: Path) -> None:
    write(root, "a.js")
    write(root, "public/vendor/b.js")
    ws = Workspace(root)
    assert build(ws).to_json("c") == build(ws).to_json("c")


def test_cross_check_reports_missing_extra_and_changed_paths(root: Path) -> None:
    write(root, "kept.js", "a\n")
    write(root, "extra.js", "e\n")
    inv = build(Workspace(root))
    tree = {
        "kept.js": ("blob", "0" * 40),
        "gone.js": ("blob", "1" * 40),
        "libs/shared": ("commit", "2" * 40),
    }
    assert cross_check(inv, tree) == [
        "in the snapshot commit, not on disk: gone.js",
        "on disk, not in the snapshot commit: extra.js",
        "content differs from the snapshot commit: kept.js",
    ]
