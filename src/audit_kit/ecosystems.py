"""Which package ecosystems a target holds, from its file paths alone (ADR 0010 D1).

Scanners, unit boundaries and manifests are chosen by ecosystem, so a Python
repository gets Python scans and a repository holding both gets both.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Literal

Ecosystem = Literal["javascript", "python"]

JS_FILES = (".js", ".cjs", ".mjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")
PY_FILES = (".py", ".pyi")
PY_MANIFESTS = re.compile(
    r"^(?:pyproject\.toml|setup\.py|setup\.cfg|requirements[\w.-]*\.txt)$"
)
# Lockfiles osv-scanner reads, by ecosystem, matched by file name at any depth.
LOCKFILES: dict[Ecosystem, tuple[str, ...]] = {
    "javascript": ("package-lock.json", "yarn.lock", "pnpm-lock.yaml"),
    "python": ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile.lock"),
}


def of_paths(paths: Iterable[str]) -> frozenset[Ecosystem]:
    """Return the ecosystems that the given relative paths show.

    Args:
        paths: Paths of the files to be reviewed, relative to the target root.
    """
    found: set[Ecosystem] = set()
    for path in paths:
        name = PurePosixPath(path).name
        if name == "package.json" or name.endswith(JS_FILES):
            found.add("javascript")
        elif PY_MANIFESTS.match(name) or name.endswith(PY_FILES):
            found.add("python")
    return frozenset(found)


def lockfiles(paths: Iterable[str]) -> tuple[str, ...]:
    """Return every recognised lockfile among the paths, in path order."""
    names = {name for names in LOCKFILES.values() for name in names}
    return tuple(sorted(p for p in paths if PurePosixPath(p).name in names))
