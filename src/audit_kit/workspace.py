"""Confined access to an audit workspace.

The workspace holds an untrusted target repository and AI-written outputs, so
every read and write goes through `Workspace`, which refuses paths that leave
the root or pass through a symlink (architecture constraint C2).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from audit_kit.errors import OutsideWorkspaceError, WorkspaceError

MAX_READ_BYTES = 1_500_000
HEAD_BYTES = 8000
_CHUNK = 1 << 20


@dataclass(frozen=True)
class Tree:
    """Regular files under the root, plus symlinks that were deliberately skipped."""

    files: tuple[PurePosixPath, ...]
    skipped_symlinks: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class Digest:
    """A file's size, hashes and first bytes, read in one pass.

    Attributes:
        size: Size in bytes.
        sha256: Hex SHA-256 of the content.
        git_blob: Hex git blob id (SHA-1 of a "blob <size>" header, a NUL and the content), also
            the content part of a Software Heritage identifier.
        head: The first HEAD_BYTES bytes, for binary and banner checks.
    """

    size: int
    sha256: str
    git_blob: str
    head: bytes


@dataclass(frozen=True)
class Change:
    """One planned write: the full new text of a file.

    Attributes:
        path: Path relative to the workspace root.
        text: Complete file content after the change.
        create: True if the file must not exist yet; False if it must exist.
    """

    path: PurePosixPath
    text: str
    create: bool


class Workspace:
    """Read and write files under one root, never outside it."""

    def __init__(self, root: Path) -> None:
        """Bind to an existing directory.

        Args:
            root: The workspace directory.

        Raises:
            WorkspaceError: If root is not a directory.
        """
        if not root.is_dir():
            raise WorkspaceError(f"not a directory: {root}")
        self.root = root.resolve()

    def path(self, rel: str | PurePosixPath) -> Path:
        """Return the absolute path for a relative path, refusing escapes.

        The check is lexical first (so `..` can't climb out), then every existing
        component is checked for symlinks, which are never followed.

        Args:
            rel: A path relative to the workspace root.

        Returns:
            The absolute, normalised path inside the root.

        Raises:
            OutsideWorkspaceError: If the path leaves the root or uses a symlink.
        """
        lexical = Path(os.path.normpath(self.root / rel))
        if lexical != self.root and self.root not in lexical.parents:
            raise OutsideWorkspaceError(f"path outside the workspace: {rel}")
        current = self.root
        for part in lexical.relative_to(self.root).parts:
            current = current / part
            if current.is_symlink():
                raise OutsideWorkspaceError(f"symlink not followed: {rel}")
        return lexical

    def is_file(self, rel: str | PurePosixPath) -> bool:
        """Return True if rel is a regular file inside the root (never a symlink)."""
        try:
            return self.path(rel).is_file()
        except OutsideWorkspaceError:
            return False

    def exists(self, rel: str | PurePosixPath) -> bool:
        """Return True if anything, including a symlink, exists at rel inside the root."""
        lexical = Path(os.path.normpath(self.root / rel))
        if self.root not in lexical.parents:
            return False
        return os.path.lexists(lexical)

    def tree(self, skip_root: frozenset[str] = frozenset({".git"})) -> Tree:
        """List every regular file in sorted order; symlinks are listed, never followed.

        Nothing is skipped by name except the root-level entries in skip_root (by
        default the workspace's own `.git`). Ignore files are not consulted.

        Args:
            skip_root: Names of top-level folders to leave out.

        Returns:
            Regular files and symlinks, each sorted.
        """
        files: list[PurePosixPath] = []
        links: list[PurePosixPath] = []
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            base = Path(dirpath)
            rel_dir = PurePosixPath(base.relative_to(self.root).as_posix())
            at_root = base == self.root
            for name in sorted(dirnames):
                if (base / name).is_symlink():
                    links.append(rel_dir / name)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not (at_root and d in skip_root) and not (base / d).is_symlink()
            )
            if at_root:
                filenames = [f for f in filenames if f not in skip_root]
            for name in sorted(filenames):
                full = base / name
                rel = rel_dir / name
                if full.is_symlink():
                    links.append(rel)
                elif full.is_file():
                    files.append(rel)
        return Tree(files=tuple(sorted(files)), skipped_symlinks=tuple(sorted(links)))

    def size(self, rel: str | PurePosixPath) -> int:
        """Return a file's size in bytes."""
        return self.path(rel).stat().st_size

    def digest(self, rel: str | PurePosixPath) -> Digest:
        """Hash a regular file of any size in one streaming pass.

        Raises:
            WorkspaceError: If the file can't be read.
        """
        path = self.path(rel)
        try:
            size = path.stat().st_size
            sha256 = hashlib.sha256()
            blob = hashlib.sha1(f"blob {size}\0".encode(), usedforsecurity=False)
            head = b""
            with path.open("rb") as handle:
                while chunk := handle.read(_CHUNK):
                    if len(head) < HEAD_BYTES:
                        head += chunk[: HEAD_BYTES - len(head)]
                    sha256.update(chunk)
                    blob.update(chunk)
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc
        return Digest(size, sha256.hexdigest(), blob.hexdigest(), head)

    def link_target(self, rel: str | PurePosixPath) -> str:
        """Return the text a symlink points to, without following it.

        Raises:
            OutsideWorkspaceError: If a parent folder of rel is a symlink or rel leaves the root.
            WorkspaceError: If rel isn't a symlink.
        """
        rel = PurePosixPath(rel)
        parent = (
            self.path(rel.parent) if rel.parent != PurePosixPath(".") else self.root
        )
        link = parent / rel.name
        if not link.is_symlink():
            raise WorkspaceError(f"{rel}: not a symlink")
        return os.readlink(link)

    def read_text(self, rel: str | PurePosixPath, limit: int = MAX_READ_BYTES) -> str:
        """Read a UTF-8 text file, replacing undecodable bytes.

        Args:
            rel: Path relative to the root.
            limit: Largest size in bytes to read.

        Returns:
            The file's text.

        Raises:
            WorkspaceError: If the file is missing, too large or unreadable.
        """
        path = self.path(rel)
        try:
            if path.stat().st_size > limit:
                raise WorkspaceError(f"{rel}: larger than {limit} bytes, not read")
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc

    def write_text(self, rel: str | PurePosixPath, text: str) -> None:
        """Create or replace a file inside the root (used for .audit outputs)."""
        path = self.path(rel)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc

    def append_text(self, rel: str | PurePosixPath, text: str) -> None:
        """Add text to the end of a file inside the root, creating it if needed."""
        path = self.path(rel)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc

    def write_bytes(self, rel: str | PurePosixPath, data: bytes) -> None:
        """Create or replace a file with exact bytes (used to restore snapshot files)."""
        path = self.path(rel)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc

    def mkdir(self, rel: str | PurePosixPath) -> None:
        """Create a folder (and parents) inside the root."""
        self.path(rel).mkdir(parents=True, exist_ok=True)

    def remove(self, rel: str | PurePosixPath) -> bool:
        """Delete a file or folder inside the root; return False if it didn't exist."""
        path = self.path(rel)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        else:
            return False
        return True

    def copy_file(self, rel: str | PurePosixPath, source: Path) -> None:
        """Stream one regular file to rel, without reading it into memory.

        Raises:
            WorkspaceError: If source is a symlink or not a regular file, or the
                copy fails.
        """
        if source.is_symlink() or not source.is_file():
            raise WorkspaceError(f"{source}: not a regular file, not copied")
        dest = self.path(rel)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest, follow_symlinks=False)
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc

    def copy_in(self, rel: str | PurePosixPath, source: Path) -> None:
        """Copy a trusted file or folder (from the kit) to rel, replacing a folder there.

        Symlinks in the source are copied as links' targets are not followed out of
        the kit; the kit itself contains none.
        """
        dest = self.path(rel)
        try:
            if source.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source, dest, symlinks=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
        except OSError as exc:
            raise WorkspaceError(f"{rel}: {exc.strerror or exc}") from exc

    def move(self, rel: str | PurePosixPath, to: str | PurePosixPath) -> None:
        """Move a file or folder to another place inside the root."""
        src, dest = self.path(rel), self.path(to)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)

    def apply(self, changes: Sequence[Change]) -> None:
        """Apply every change or none of them.

        All targets are checked before anything is written; if a write fails, files
        already written are restored (created files are removed).

        Args:
            changes: Planned writes. Each path may appear only once.

        Raises:
            WorkspaceError: If a target is refused, exists when it must not (or the
                reverse), or a write fails.
        """
        seen: set[PurePosixPath] = set()
        targets: list[tuple[Path, Change]] = []
        for change in changes:
            if change.path in seen:
                raise WorkspaceError(f"{change.path}: planned twice")
            seen.add(change.path)
            path = self.path(change.path)
            if change.create and os.path.lexists(path):
                raise WorkspaceError(f"{change.path}: already exists")
            if not change.create and not path.is_file():
                raise WorkspaceError(f"{change.path}: expected an existing file")
            targets.append((path, change))
        written: list[tuple[Path, bytes | None]] = []
        try:
            for path, change in targets:
                original = None if change.create else path.read_bytes()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(change.text, encoding="utf-8")
                written.append((path, original))
        except OSError as exc:
            for path, original in reversed(written):
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            raise WorkspaceError(f"could not apply changes: {exc}") from exc
