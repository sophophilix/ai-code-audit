"""Record every file in the target, with a class and the reason for it (no AI).

Nothing is left out. Vendored, generated, binary, ignored and hidden files all get
a record; a class decides what scans and agents review, never what is recorded
(docs/decisions/0001-target-inventory.md). The output depends only on the files,
so a re-run on the same snapshot is byte-identical (constraint C4).
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from functools import cache
from importlib import resources
from pathlib import PurePosixPath

import yaml

from audit_kit.errors import WorkspaceError
from audit_kit.workspace import Workspace

# Rule data, pinned: github-linguist v9.7.0 (commit e0c78d6), MIT. See THIRD_PARTY.md.
RULES = "linguist v9.7.0 (e0c78d6) + kit rules"
INVENTORY_PATH = ".audit/inventory.json"
QUARANTINE = PurePosixPath(".audit/quarantine")
# Top-level folders the kit owns. `.claude` is the kit's only once the kit is
# installed; a target's own `.claude` is quarantined first.
KIT_ROOT = frozenset({".git", ".audit", ".audit-kit"})
KIT_INSTALLED = ".audit-kit/VERSION"

AI_INSTRUCTION_FILES = (
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    ".cursorrules",
    ".windsurfrules",
    ".github/copilot-instructions.md",
    ".cursor/rules",
    ".claude",
)
DATA_PATTERNS = re.compile(
    r"(^|/)\.env|\.(pem|pfx|key|bak|bacpac|mdf|ldf|dump|sqlite|db|csv|xlsx?|log)$"
)
# Folder names that hold build output. Linguist counts some of these as vendored;
# the kit calls them generated so a report says what they are.
GENERATED_DIRS = re.compile(r"(^|/)(dist|build|coverage|\.next|out)/")
# Linguist vendors these for language statistics, but they are the repository's
# own pipelines and configuration, which an audit must review.
UNVENDOR = re.compile(
    r"(^|/)(\.github/|\.teamcity/|Jenkinsfile$|\.gitpod\.Dockerfile$|Vagrantfile$"
    r"|\.gitignore$|\.gitattributes$|\.gitmodules$|env/|fabfile\.py$)"
)
# A licence file shipped with third-party code (LICENSE, COPYING.md,
# face-api.LICENSE.txt), but not a site's own licence page such as licence.html.
LICENCE_FILE = re.compile(
    r"^(?:.+\.)?(?:licen[cs]e|copying|notice)(?:\.(?:txt|md))?$", re.I
)
# Clues for identifying a vendored file's upstream and version. They are leads for
# the supply-chain review, not proof: a bundle can carry several libraries.
UPSTREAM = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[\w.-]+/[\w.-]+"
)
VERSION = re.compile(
    r"""(?:@version\s+|\bversion\b\s*[:=]\s*["']|\bv)(\d+\.\d+(?:\.\d+)?)""",
    re.I,
)
MAX_CLUE_BYTES = 16_000_000
# Files that can build a folder: scripts, bundler and compiler configs, pipelines.
# They are read as text for the folder's name, never loaded (AGENTS.md rule 2).
GENERATOR_FILES = re.compile(
    r"(^|/)(package\.json|tsconfig[\w.-]*\.json|Makefile|Dockerfile[\w.-]*|Jenkinsfile"
    r"|(?:webpack|vite|rollup|esbuild|tsup|parcel|babel|gulpfile|gruntfile|next|nuxt|svelte"
    r"|astro|angular|jest|vitest|nyc|c8)[\w.-]*\.(?:c|m)?[jt]s(?:on)?|\.nycrc[\w.]*|\.c8rc[\w.]*"
    r"|azure-pipelines[\w.-]*\.ya?ml|\.gitlab-ci\.yml|\.github/workflows/[^/]+\.ya?ml)$",
    re.I,
)
GENERATOR_BYTES = 2_000_000
LINGUIST_ATTRS = {
    "linguist-vendored": "vendored",
    "linguist-generated": "generated",
    "linguist-documentation": "documentation",
}
# Classes left out of scans and specialist review (still recorded and inventoried).
NOT_REVIEWED = frozenset({"vendored", "generated"})


@dataclass(frozen=True)
class Entry:
    """One path in the target.

    Attributes:
        path: Path relative to the target root.
        kind: "file", "symlink" or "submodule".
        cls: own, vendored, generated, documentation, binary, ai-instructions,
            data-candidate, symlink or submodule.
        reason: The rule that set the class.
        scope: The folder or file the rule matched (used for scan exclusions).
        size: Size in bytes (0 for symlinks and submodules).
        sha256: Content hash ("" for symlinks and submodules).
        git_blob: Git blob id of the content, or the commit for a submodule.
        binary: True if the first 8,000 bytes contain a NUL byte.
        target: A symlink's target text, otherwise "".
        upstream: For vendored text files, the first repository URL in the header.
        version: For vendored text files, the first version marker in the file.
    """

    path: str
    kind: str
    cls: str
    reason: str
    scope: str
    size: int
    sha256: str
    git_blob: str
    binary: bool
    target: str
    upstream: str
    version: str


@dataclass(frozen=True)
class Inventory:
    """Every path in the target, sorted, plus files that couldn't be read."""

    entries: tuple[Entry, ...]
    problems: tuple[str, ...]

    def of(self, *classes: str) -> tuple[Entry, ...]:
        """Return entries in any of the given classes."""
        return tuple(e for e in self.entries if e.cls in classes)

    def counts(self) -> dict[str, int]:
        """Return the number of entries per class, sorted by class name."""
        return dict(sorted(Counter(e.cls for e in self.entries).items()))

    def to_json(self, commit: str) -> str:
        """Serialise for .audit/inventory.json (no timestamp, so re-runs match)."""
        body = {
            "generated_by": "kit inventory (deterministic, no AI)",
            "rules": RULES,
            "commit": commit,
            "counts": self.counts(),
            "problems": list(self.problems),
            "entries": [asdict(e) for e in self.entries],
        }
        return json.dumps(body, indent=1, sort_keys=False) + "\n"


@cache
def _linguist(name: str) -> tuple[re.Pattern[str], ...]:
    text = (resources.files("audit_kit") / "rules/linguist" / name).read_text("utf-8")
    patterns = yaml.safe_load(text)
    return tuple(re.compile(p) for p in patterns)


def _attributes(ws: Workspace) -> list[tuple[str, str, bool]]:
    """Read linguist overrides from the target's root .gitattributes (as data)."""
    if not ws.is_file(".gitattributes"):
        return []
    rules: list[tuple[str, str, bool]] = []
    for line in ws.read_text(".gitattributes").splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        for attr in parts[1:]:
            negated = attr.startswith("-") or attr.endswith("=false")
            name = attr.lstrip("-").split("=")[0]
            if name in LINGUIST_ATTRS:
                rules.append((parts[0], LINGUIST_ATTRS[name], not negated))
    return rules


def _attr_matches(pattern: str, path: str) -> bool:
    """Match a gitattributes pattern: no slash matches the name at any depth."""
    pattern = pattern.lstrip("/")
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/")
    if "/" not in pattern:
        return fnmatch.fnmatchcase(PurePosixPath(path).name, pattern)
    return fnmatch.fnmatchcase(path, pattern)


def _ai_instruction(path: str) -> bool:
    return any(path == f or path.startswith(f + "/") for f in AI_INSTRUCTION_FILES)


def _rule_scope(match: re.Match[str], path: str) -> str:
    """A rule ending in "/" names a folder; otherwise the file itself."""
    matched = match.group(0)
    if matched.endswith("/"):
        return path[: match.end()].rstrip("/")
    return path


def classify(
    path: str,
    binary: bool,
    licensed_folders: frozenset[str],
    attributes: list[tuple[str, str, bool]],
) -> tuple[str, str, str]:
    """Return (class, reason, scope) for a regular file. First matching rule wins."""
    if _ai_instruction(path):
        return "ai-instructions", "AI instruction file", path
    if DATA_PATTERNS.search(path):
        return "data-candidate", "name suggests data or credentials", path
    forced: tuple[str, str, str] | None = None
    unset: set[str] = set()
    for pattern, cls, on in attributes:
        if _attr_matches(pattern, path):
            if on:
                forced = (cls, f".gitattributes: {pattern} linguist-{cls}", path)
            else:
                unset.add(cls)
                forced = None
    if forced:
        return forced
    if "generated" not in unset and (m := GENERATED_DIRS.search(path)):
        return "generated", f"build output folder '{m.group(2)}'", _rule_scope(m, path)
    if "vendored" not in unset and not UNVENDOR.search(path):
        for rx in _linguist("vendor.yml"):
            if m := rx.search(path):
                return (
                    "vendored",
                    f"linguist vendor.yml: {rx.pattern}",
                    _rule_scope(m, path),
                )
        folder = str(PurePosixPath(path).parent)
        for lic in sorted(licensed_folders):
            if folder == lic or folder.startswith(lic + "/"):
                return "vendored", "folder holds a third-party licence file", lic
    if "documentation" not in unset:
        for rx in _linguist("documentation.yml"):
            if rx.search(path):
                return (
                    "documentation",
                    f"linguist documentation.yml: {rx.pattern}",
                    path,
                )
    if binary:
        return "binary", "NUL byte in the first 8,000 bytes", path
    return "own", "no rule matched", path


def _clues(ws: Workspace, rel: PurePosixPath, head: bytes) -> tuple[str, str]:
    """Return (upstream URL, version) clues from a vendored text file."""
    header = head.decode("utf-8", errors="replace")
    upstream = m.group(0).rstrip(".>)'\"") if (m := UPSTREAM.search(header)) else ""
    try:
        body = ws.read_text(rel, limit=MAX_CLUE_BYTES)
    except WorkspaceError:
        body = header
    version = m.group(1) if (m := VERSION.search(body)) else ""
    return upstream, version


def build(ws: Workspace, gitlinks: tuple[tuple[str, str], ...] = ()) -> Inventory:
    """Record every path in the target part of a workspace.

    The kit's own folders are left out, and files the kit quarantined are recorded
    at their original paths.

    Args:
        ws: The workspace (before or after the kit is installed).
        gitlinks: Submodules as (path, commit), from the snapshot's git tree.

    Returns:
        The inventory, sorted by path.
    """
    skip = set(KIT_ROOT)
    if ws.is_file(KIT_INSTALLED):
        skip.add(".claude")
    tree = ws.tree(frozenset(skip))
    located: dict[str, PurePosixPath] = {r.as_posix(): r for r in tree.files}
    if ws.exists(QUARANTINE):
        for rel in Workspace(ws.path(QUARANTINE)).tree(frozenset()).files:
            located[rel.as_posix()] = QUARANTINE / rel
    licensed = frozenset(
        str(PurePosixPath(p).parent)
        for p in located
        if "/" in p and LICENCE_FILE.search(PurePosixPath(p).name)
    )
    attributes = _attributes(ws)
    entries: list[Entry] = []
    problems: list[str] = []
    for path, rel in sorted(located.items()):
        try:
            d = ws.digest(rel)
        except WorkspaceError as exc:
            problems.append(str(exc))
            continue
        binary = b"\0" in d.head
        cls, reason, scope = classify(path, binary, licensed, attributes)
        upstream, version = (
            _clues(ws, rel, d.head) if cls == "vendored" and not binary else ("", "")
        )
        entries.append(
            Entry(
                path,
                "file",
                cls,
                reason,
                scope,
                d.size,
                d.sha256,
                d.git_blob,
                binary,
                "",
                upstream,
                version,
            )
        )
    for rel in tree.skipped_symlinks:
        target = ws.link_target(rel)
        entries.append(
            Entry(
                rel.as_posix(),
                "symlink",
                "symlink",
                f"symlink to {target}, not followed",
                rel.as_posix(),
                0,
                "",
                "",
                False,
                target,
                "",
                "",
            )
        )
    for path, commit in gitlinks:
        entries.append(
            Entry(
                path,
                "submodule",
                "submodule",
                "git submodule, contents not in the snapshot",
                path,
                0,
                "",
                commit,
                False,
                "",
                "",
                "",
            )
        )
    entries.sort(key=lambda e: e.path)
    return Inventory(tuple(_prove_generated(ws, entries, located)), tuple(problems))


def _build_text(path: str, text: str) -> str:
    """The part of a generator file that can say where output goes.

    For package.json that's the script commands and the output fields, not the
    keys: a script named "build" doesn't mean it writes to build/. Other files
    are searched whole.
    """
    if PurePosixPath(path).name != "package.json":
        return text
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(manifest, dict):
        return ""
    scripts = manifest.get("scripts")
    commands = [str(v) for v in scripts.values()] if isinstance(scripts, dict) else []
    outputs = [
        json.dumps(manifest.get(k, ""))
        for k in ("main", "module", "bin", "files", "exports")
    ]
    return "\n".join(commands + outputs)


def _prove_generated(
    ws: Workspace, entries: list[Entry], located: dict[str, PurePosixPath]
) -> list[Entry]:
    """Keep a build-folder file `generated` only if something builds that folder.

    A folder name is a claim (ADR 0004 D2): `dist/` holds a build only if a script,
    a build config or a pipeline names it. Otherwise the file is reviewed as own.
    """
    claimed = {
        e.scope
        for e in entries
        if e.cls == "generated" and e.reason.startswith("build output folder")
    }
    if not claimed:
        return entries
    builders: dict[str, str] = {}
    for path, rel in sorted(located.items()):
        if not GENERATOR_FILES.search(path) or path.startswith("node_modules/"):
            continue
        try:
            text = ws.read_text(rel, limit=GENERATOR_BYTES)
        except WorkspaceError:
            continue
        builders[path] = _build_text(path, text)
    built: dict[str, str] = {}
    for scope in sorted(claimed):
        name = PurePosixPath(scope).name
        word = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        by = sorted(
            p
            for p, text in builders.items()
            if not p.startswith(scope + "/") and word.search(text)
        )
        if by:
            built[scope] = ", ".join(by[:3])
    out: list[Entry] = []
    for e in entries:
        if e.cls == "generated" and e.reason.startswith("build output folder"):
            if e.scope in built:
                e = replace(e, reason=f"{e.reason}, built by {built[e.scope]}")
            else:
                e = replace(
                    e,
                    cls="own",
                    reason=f"generated claim unverified: {e.reason}, and no script, "
                    "build config or pipeline names it",
                    scope=e.path,
                )
        out.append(e)
    return out


def exclusions(inv: Inventory) -> tuple[tuple[str, str], ...]:
    """Return (pattern, reason) for each folder or file left out of scans."""
    found: dict[str, str] = {}
    for e in inv.of(*NOT_REVIEWED):
        found.setdefault(e.scope, e.reason)
    folders = [p for p in found if any(q.startswith(p + "/") for q in found)]
    return tuple(
        (p, r)
        for p, r in sorted(found.items())
        if not any(p.startswith(f + "/") for f in folders)
    )
