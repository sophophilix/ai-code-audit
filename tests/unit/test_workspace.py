from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

from audit_kit.errors import OutsideWorkspaceError, WorkspaceError
from audit_kit.workspace import Change, Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    (root / "lib").mkdir(parents=True)
    (root / "lib/a.js").write_text("a\n")
    (tmp_path / "outside.txt").write_text("secret\n")
    return Workspace(root)


@pytest.mark.parametrize(
    "rel", ["../outside.txt", "lib/../../outside.txt", "/etc/hosts"]
)
def test_path_refuses_escapes(ws: Workspace, rel: str) -> None:
    with pytest.raises(OutsideWorkspaceError):
        ws.path(rel)


def test_path_refuses_symlinked_file_and_folder(ws: Workspace, tmp_path: Path) -> None:
    os.symlink(tmp_path / "outside.txt", ws.root / "lib/link.txt")
    os.symlink(tmp_path, ws.root / "linkdir")
    with pytest.raises(OutsideWorkspaceError):
        ws.path("lib/link.txt")
    with pytest.raises(OutsideWorkspaceError):
        ws.path("linkdir/outside.txt")
    assert not ws.is_file("lib/link.txt")


def test_tree_lists_regular_files_and_reports_symlinks(
    ws: Workspace, tmp_path: Path
) -> None:
    os.symlink(tmp_path / "outside.txt", ws.root / "lib/link.txt")
    (ws.root / "node_modules/x").mkdir(parents=True)
    (ws.root / "node_modules/x/i.js").write_text("x\n")
    (ws.root / ".git").mkdir()
    (ws.root / ".git/HEAD").write_text("ref\n")
    tree = ws.tree()
    assert tree.files == (
        PurePosixPath("lib/a.js"),
        PurePosixPath("node_modules/x/i.js"),
    )
    assert tree.skipped_symlinks == (PurePosixPath("lib/link.txt"),)


def test_digest_matches_git_blob_ids(ws: Workspace) -> None:
    digest = ws.digest("lib/a.js")
    # `printf 'a\n' | git hash-object --stdin`
    assert digest.git_blob == "78981922613b2afb6025042ff6bd878ac1994e85"
    assert digest.size == 2
    assert digest.head == b"a\n"


def test_read_text_refuses_files_over_the_limit(ws: Workspace) -> None:
    with pytest.raises(WorkspaceError, match="larger than"):
        ws.read_text("lib/a.js", limit=1)


def test_read_text_reports_a_missing_file(ws: Workspace) -> None:
    with pytest.raises(WorkspaceError):
        ws.read_text("lib/missing.js")


def test_apply_writes_nothing_when_a_check_fails(ws: Workspace) -> None:
    changes = [
        Change(PurePosixPath("lib/new.js"), "n\n", create=True),
        Change(PurePosixPath("lib/a.js"), "changed\n", create=True),  # exists: refused
    ]
    with pytest.raises(WorkspaceError, match="already exists"):
        ws.apply(changes)
    assert not (ws.root / "lib/new.js").exists()
    assert (ws.root / "lib/a.js").read_text() == "a\n"


def test_apply_rolls_back_when_a_write_fails(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_write = Path.write_text

    def failing_write(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self.name == "z.js":
            raise OSError("disk full")
        return real_write(self, data, encoding="utf-8")

    monkeypatch.setattr(Path, "write_text", failing_write)
    changes = [
        Change(PurePosixPath("lib/a.js"), "changed\n", create=False),
        Change(PurePosixPath("lib/new.js"), "n\n", create=True),
        Change(PurePosixPath("lib/z.js"), "z\n", create=True),
    ]
    with pytest.raises(WorkspaceError, match="could not apply"):
        ws.apply(changes)
    assert (ws.root / "lib/a.js").read_bytes() == b"a\n"
    assert not (ws.root / "lib/new.js").exists()


def test_apply_refuses_a_path_planned_twice(ws: Workspace) -> None:
    change = Change(PurePosixPath("lib/n.js"), "n\n", create=True)
    with pytest.raises(WorkspaceError, match="planned twice"):
        ws.apply([change, change])


def test_workspace_must_be_a_directory(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        Workspace(tmp_path / "missing")
