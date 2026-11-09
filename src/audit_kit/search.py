"""Run one "not found" search in its own process, so `kit verify` can time it out.

The pattern comes from an agent's finding, and Python's `re` has no time limit:
a pattern that backtracks badly would hang the caller. `kit verify` runs this
module through `runner.run` with a timeout (ADR 0004 D6). Exit codes are the
contract, so a crash can never read as "nothing found":

- 0: searched everything; stdout is `path:line` of the first match, or empty
- 2: bad arguments or an invalid pattern
- 3: stopped at TOTAL_LIMIT before finishing

Usage: python -I -m audit_kit.search <workspace root> <pattern> <path>...
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from audit_kit.errors import WorkspaceError
from audit_kit.workspace import Workspace

SKIP = frozenset({".git", ".audit", ".audit-kit"})
FILE_LIMIT = 5_000_000
# Stop after this many characters in all, so a huge tree can't run past the
# timeout silently; the caller reports the cap as a failed search.
TOTAL_LIMIT = 200_000_000
FOUND_OR_NONE, BAD_INPUT, LIMIT_REACHED = 0, 2, 3


class LimitReachedError(Exception):
    """More than TOTAL_LIMIT characters would be searched."""


def files_under(ws: Workspace, paths: list[str]) -> list[str]:
    """The files the named paths cover, walking only those paths, sorted.

    Kit folders are never searched, and symlinks are never followed.
    """
    found: set[str] = set()
    for path in paths:
        if path == ".":
            found.update(r.as_posix() for r in ws.tree(skip_root=SKIP).files)
        elif ws.is_file(path):
            found.add(path)
        elif ws.exists(path) and ws.path(path).is_dir():
            sub = Workspace(ws.path(path)).tree(skip_root=frozenset())
            found.update(f"{path}/{r.as_posix()}" for r in sub.files)
    return sorted(p for p in found if p.split("/", 1)[0] not in SKIP)


def first_match(ws: Workspace, regex: re.Pattern[str], paths: list[str]) -> str:
    """Return `path:line` of the first match under the given paths, or "".

    Raises:
        LimitReachedError: If the files to search exceed TOTAL_LIMIT characters.
    """
    read = 0
    for name in files_under(ws, paths):
        try:
            text = ws.read_text(name, limit=FILE_LIMIT)
        except WorkspaceError:
            continue
        read += len(text)
        if read > TOTAL_LIMIT:
            raise LimitReachedError
        hit = regex.search(text)
        if hit:
            return f"{name}:{text.count(chr(10), 0, hit.start()) + 1}"
    return ""


def main(argv: list[str]) -> int:
    """Search for argv = [root, pattern, *paths]; see the module docstring for codes."""
    if len(argv) < 3:
        print("usage: audit_kit.search <root> <pattern> <path>...", file=sys.stderr)
        return BAD_INPUT
    root, pattern, *paths = argv
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        print(f"invalid pattern ({exc})", file=sys.stderr)
        return BAD_INPUT
    try:
        print(first_match(Workspace(Path(root)), regex, paths))
    except LimitReachedError:
        return LIMIT_REACHED
    return FOUND_OR_NONE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
