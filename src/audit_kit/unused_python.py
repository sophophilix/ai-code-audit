"""Python dependencies declared but not imported, and imported but not declared.

Read from `pyproject.toml` and the `import` statements of the target's own
`.py` files. The files are parsed, never imported or run (AGENTS.md rule 2).

A row is a fact, not a verdict. A distribution's import name isn't recorded in
`pyproject.toml`, so the names looked for are a guess that each row states. A
package can also be used with no import: a plugin, a command-line tool or an
optional backend.
"""

from __future__ import annotations

import ast
import posixpath
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from audit_kit.workspace import Workspace

MANIFEST = "pyproject.toml"
PYTHON = (".py", ".pyi")
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}
# Distributions whose import name can't be worked out from their own name.
IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "attrs": ("attr", "attrs"),
    "beautifulsoup4": ("bs4",),
    "dnspython": ("dns",),
    "grpcio": ("grpc",),
    "msgpack-python": ("msgpack",),
    "opencv-python": ("cv2",),
    "opencv-python-headless": ("cv2",),
    "pdfminer-six": ("pdfminer",),
    "pillow": ("PIL",),
    "protobuf": ("google",),
    "pycryptodome": ("Crypto",),
    "pyjwt": ("jwt",),
    "pymupdf": ("fitz", "pymupdf"),
    "pyserial": ("serial",),
    "python-magic": ("magic",),
    "pyyaml": ("yaml",),
    "scikit-image": ("skimage",),
    "scikit-learn": ("sklearn",),
    "setuptools": ("setuptools", "pkg_resources"),
}
# Calls that load a module from a string; a literal first argument is followed.
LOADERS = frozenset({"import_module", "__import__", "find_spec"})
METHOD = (
    "Python: every own pyproject.toml is read with a TOML parser, and every own "
    ".py file under it is parsed for import statements and for import_module, "
    "__import__ and find_spec calls with a literal name. A dependency in "
    "[project] dependencies or optional-dependencies is listed as unused when no "
    "file imports any of the names looked for. An import is listed as undeclared "
    "when it isn't the standard library, an own package, or a name that a declared "
    "dependency (dependency groups included) could provide."
)
LIMITS = (
    "Python: an import name is guessed from the distribution name (dashes to "
    "underscores, a python- prefix or -python suffix removed, the first word of the "
    "name, and a short table of known exceptions). Each row lists the names tried.",
    "Python: dependency groups and development dependencies aren't checked for "
    "use, because tools are run, not imported.",
    "Python: a module loaded from a computed name, an entry point or a plugin "
    "isn't followed.",
    "Python: only pyproject.toml is read; requirements files and setup.py aren't.",
)


@dataclass(frozen=True)
class Declared:
    """One dependency as a manifest declares it."""

    name: str
    section: str
    runtime: bool


@dataclass
class Report:
    """The Python part of the unused-code report."""

    unused: list[dict[str, Any]] = field(default_factory=list)
    undeclared: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    manifests: int = 0
    files: int = 0


def normalise(name: str) -> str:
    """Return a distribution name in its normal form (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def import_names(distribution: str) -> tuple[str, ...]:
    """Return the import names a distribution might provide, most likely first."""
    name = normalise(distribution)
    plain = name.removeprefix("python-").removesuffix("-python")
    guesses = [
        *IMPORT_NAMES.get(name, ()),
        name.replace("-", "_"),
        plain.replace("-", "_"),
        # A namespace package: opentelemetry-sdk provides `opentelemetry`.
        name.split("-", 1)[0],
    ]
    return tuple(dict.fromkeys(guesses))


def _requirements(items: object) -> Iterable[str]:
    for item in items if isinstance(items, list) else ():
        match = REQUIREMENT.match(item) if isinstance(item, str) else None
        if match:
            yield match.group(1)


def declared(manifest: Mapping[str, Any]) -> list[Declared]:
    """Return every dependency a parsed pyproject.toml declares."""
    project = manifest.get("project")
    project = project if isinstance(project, dict) else {}
    own = normalise(str(project.get("name") or ""))
    found = [
        Declared(n, "[project] dependencies", True)
        for n in _requirements(project.get("dependencies"))
    ]
    extras = project.get("optional-dependencies")
    for extra, items in (extras if isinstance(extras, dict) else {}).items():
        found += [
            Declared(n, f"[project.optional-dependencies] {extra}", True)
            for n in _requirements(items)
        ]
    groups = manifest.get("dependency-groups")
    for group, items in (groups if isinstance(groups, dict) else {}).items():
        found += [
            Declared(n, f"[dependency-groups] {group}", False)
            for n in _requirements(items)
        ]
    tool = manifest.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    found += [
        Declared(n, "[tool.uv] dev-dependencies", False)
        for n in _requirements(
            uv.get("dev-dependencies") if isinstance(uv, dict) else None
        )
    ]
    # An extra that names the project itself (`myapp[office]`) isn't a dependency.
    return [d for d in found if normalise(d.name) != own]


def _loader(func: ast.expr) -> bool:
    """Say whether a call loads a module by name, such as `import_module("x")`."""
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name in LOADERS


def imports(text: str) -> dict[str, int]:
    """Return each top-level module a Python file imports or loads by name.

    Raises:
        SyntaxError: If the file isn't valid Python for the kit's interpreter.
    """
    found: dict[str, int] = {}
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        elif isinstance(node, ast.Call) and _loader(node.func) and node.args:
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            names = [first.value]
        else:
            continue
        for name in names:
            top = name.split(".", 1)[0]
            found[top] = min(found.get(top, node.lineno), node.lineno)
    return found


def _folder(manifest: str) -> str:
    return posixpath.dirname(manifest)


def _owner(path: str, folders: list[str]) -> str | None:
    """Return the nearest manifest folder above a file, or None."""
    for folder in folders:  # deepest first
        if not folder or path.startswith(folder + "/"):
            return folder
    return None


def _own_module(path: str, folder: str) -> str:
    """Return the top-level module or package a file belongs to."""
    parts = posixpath.relpath(path, folder or ".").split("/")
    if parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    return posixpath.splitext(parts[0])[0]


def _line(text: str, name: str) -> int | None:
    quoted = re.compile(rf"""["']{re.escape(name)}(?![A-Za-z0-9._-])""", re.I)
    for number, line in enumerate(text.splitlines(), 1):
        if quoted.search(line):
            return number
    return None


def analyse(ws: Workspace, own: Iterable[str]) -> Report:
    """Compare declared Python dependencies with what the own files import.

    Args:
        ws: The workspace.
        own: Paths of the target's own files that are in scope.
    """
    paths = sorted(own)
    manifests = [p for p in paths if posixpath.basename(p) == MANIFEST]
    folders = sorted({_folder(m) for m in manifests}, key=len, reverse=True)
    report = Report(manifests=len(manifests))

    imported: dict[str, dict[str, tuple[str, int]]] = {f: {} for f in folders}
    first_party: set[str] = set()
    for path in (p for p in paths if p.endswith(PYTHON)):
        folder = _owner(path, folders)
        if folder is None:
            continue
        report.files += 1
        first_party.add(_own_module(path, folder))
        try:
            found = imports(ws.read_text(path))
        except SyntaxError as exc:
            report.problems.append(f"{path}: not parsed (line {exc.lineno})")
            continue
        for name, line in found.items():
            imported[folder].setdefault(name, (path, line))

    for manifest in manifests:
        text = ws.read_text(manifest)
        try:
            deps = declared(tomllib.loads(text))
        except tomllib.TOMLDecodeError:
            report.problems.append(f"{manifest}: not valid TOML")
            continue
        seen = imported[_folder(manifest)]
        provided: set[str] = set()
        for dep in deps:
            names = import_names(dep.name)
            provided.update(names)
            if dep.runtime and not any(n in seen for n in names):
                report.unused.append(
                    {
                        "name": dep.name,
                        "section": dep.section,
                        "file": manifest,
                        "line": _line(text, dep.name),
                        "note": (
                            f"`{dep.name}` is declared in {dep.section}, and no own "
                            f".py file under this manifest imports it (looked for: "
                            f"{', '.join(names)}). A package can be used with no "
                            "import: a plugin, a command-line tool or a backend"
                        ),
                    }
                )
        for name, (path, line) in sorted(seen.items()):
            if name in STDLIB or name in first_party or name in provided:
                continue
            report.undeclared.append(
                {
                    "name": name,
                    "file": path,
                    "line": line,
                    "note": (
                        f"`{name}` is imported, and no dependency in {manifest} "
                        "provides that name (the standard library and own "
                        "packages are left out)"
                    ),
                }
            )
    return report
