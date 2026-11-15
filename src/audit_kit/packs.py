"""Knowledge packs: the contract a pack folder meets, and where packs live (ADR 0012).

A pack is a folder of stack, platform, concern or sector knowledge that the kit
loads by name. The kit's own packs are in `profiles/`. A person's private packs
are in the folders named by `AUDIT_KIT_PACKS`, outside this repository.

    <name>/
      pack.toml              manifest (this module's `Manifest`)
      SKILL.md               what the stage agents load
      references/*.md        optional, loaded on demand
      skills/<skill>/SKILL.md  optional skills that travel with the pack
      patterns/<id>.md       optional pattern entries (this module's `PatternMeta`)
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from audit_kit.errors import AuditKitError
from audit_kit.models_config import Issue
from audit_kit.skill_sections import pack_files, tagged_sections

PACK_FILE = "pack.toml"
SKILL_FILE = "SKILL.md"
BUILTIN = Path(__file__).resolve().parents[2] / "profiles"
PATTERN_HEADINGS = ("## Principle", "## How to check", "## Good", "## Bad")
# A catalogue row starts with its CHECK-ID: `| PYAPP-LOCK | ...`.
CHECK_ROW = re.compile(r"^\| (?P<prefix>[A-Z][A-Z0-9]*)-[A-Z0-9][A-Za-z0-9.-]*", re.M)
FRONT_MATTER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n(?P<body>.*)\Z", re.S)
URL = re.compile(r"https://\S+")

Name = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]
Prefix = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]*$")]
Version = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
PatternId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")]
Text = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class PackError(AuditKitError):
    """A pack folder is missing, unreadable or named twice."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Manifest(_Strict):
    """A pack's `pack.toml`."""

    name: Name
    type: Literal["stack", "platform", "concern", "sector"]
    version: Version
    summary: Text
    # Languages, as `kit detect` names them, that this pack's rules cover.
    languages: tuple[Text, ...] = ()
    # CHECK-ID prefixes this pack owns, and prefixes it uses but another owns.
    check_prefixes: tuple[Prefix, ...] = ()
    borrows: tuple[Prefix, ...] = ()


class Source(_Strict):
    """A published source for a pattern."""

    title: Text
    url: Annotated[str, StringConstraints(pattern=r"^https://\S+$")]


class Sighting(_Strict):
    """One time the author met a pattern, described without naming the client."""

    date: date
    context: Text


class PatternMeta(_Strict):
    """The front matter of a pattern entry."""

    id: PatternId
    title: Text
    status: Literal["draft", "accepted"]
    applies_to: tuple[Text, ...] = Field(min_length=1)
    sources: tuple[Source, ...] = ()
    seen: tuple[Sighting, ...] = ()
    check: PatternId | None = None
    post: Annotated[str, StringConstraints(pattern=r"^https://\S+$")] | None = None
    recall: Text | None = None


@dataclass(frozen=True)
class Pack:
    """A pack folder and its manifest."""

    folder: Path
    manifest: Manifest

    @property
    def name(self) -> str:
        """The name the kit loads this pack by."""
        return self.manifest.name

    def files(self) -> list[Path]:
        """Return the Markdown files a brief may draw from, in a fixed order."""
        return pack_files(self.folder)

    def skills(self) -> list[Path]:
        """Return the folders of the skills that travel with this pack."""
        return sorted(p.parent for p in self.folder.glob(f"skills/*/{SKILL_FILE}"))


def _problems(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}"
        for e in exc.errors()
    )


def load(folder: Path) -> Pack:
    """Read one pack folder's manifest.

    Raises:
        PackError: If `pack.toml` is missing, isn't TOML or breaks the contract.
    """
    path = folder / PACK_FILE
    if not path.is_file():
        raise PackError(f"{folder}: no {PACK_FILE} (ADR 0012)")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise PackError(f"{path}: not valid TOML: {exc}") from exc
    try:
        # TOML arrays are lists; the frozen model holds tuples.
        manifest = Manifest.model_validate(raw, strict=False)
    except ValidationError as exc:
        raise PackError(f"{path}: {_problems(exc)}") from exc
    return Pack(folder, manifest)


def find(roots: Iterable[Path]) -> dict[str, Pack]:
    """Return every pack under the given folders, by name.

    Args:
        roots: Folders that hold pack folders. One that doesn't exist is skipped.

    Raises:
        PackError: If a pack is invalid, or two packs share a name.
    """
    found: dict[str, Pack] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            if folder.name.startswith("."):
                continue
            pack = load(folder)
            if pack.name in found:
                raise PackError(
                    f"pack '{pack.name}' is in both {found[pack.name].folder} and {folder}"
                )
            found[pack.name] = pack
    return found


def roots(kit_home: Path, pack_dirs: Sequence[Path] = ()) -> tuple[Path, ...]:
    """Return the kit's own pack folder followed by the private ones."""
    return (kit_home / "profiles", *pack_dirs)


def languages(packs: Iterable[Pack]) -> dict[str, frozenset[str]]:
    """Return the languages each pack covers, by pack name."""
    return {p.name: frozenset(p.manifest.languages) for p in packs}


def _front_matter(text: str) -> tuple[object, str] | None:
    match = FRONT_MATTER.match(text)
    if match is None:
        return None
    try:
        return yaml.safe_load(match.group("meta")), match.group("body")
    except yaml.YAMLError:
        return None


def _skill_issues(pack: Pack) -> list[Issue]:
    path = pack.folder / SKILL_FILE
    if not path.is_file():
        return [Issue("error", SKILL_FILE, "missing")]
    parsed = _front_matter(path.read_text(encoding="utf-8"))
    meta = parsed[0] if parsed else None
    if not isinstance(meta, dict):
        return [Issue("error", SKILL_FILE, "no YAML front matter")]
    issues: list[Issue] = []
    if meta.get("name") != pack.name:
        issues.append(
            Issue("error", SKILL_FILE, f"front matter name must be '{pack.name}'")
        )
    if not str(meta.get("description") or "").strip():
        issues.append(Issue("error", SKILL_FILE, "front matter needs a description"))
    return issues


def _content_issues(pack: Pack) -> list[Issue]:
    issues: list[Issue] = []
    allowed = {*pack.manifest.check_prefixes, *pack.manifest.borrows}
    used: set[str] = set()
    cited = False
    for path in pack.files():
        where = path.relative_to(pack.folder).as_posix()
        text = path.read_text(encoding="utf-8")
        cited = cited or URL.search(text) is not None
        try:
            tagged_sections(where, text)
        except ValueError as exc:
            issues.append(Issue("error", where, str(exc)))
        prefixes = {m.group("prefix") for m in CHECK_ROW.finditer(text)} - {"CHECK"}
        used |= prefixes
        issues += [
            Issue("error", where, f"CHECK-ID prefix '{p}' isn't in {PACK_FILE}")
            for p in sorted(prefixes - allowed)
        ]
    issues += [
        Issue("error", PACK_FILE, f"no check uses the prefix '{p}'")
        for p in pack.manifest.check_prefixes
        if p not in used
    ]
    if not cited:
        issues.append(
            Issue("error", SKILL_FILE, "the pack cites no source (no https URL)")
        )
    return issues


def _pattern_issues(pack: Pack) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted(pack.folder.glob("patterns/*.md")):
        where = path.relative_to(pack.folder).as_posix()
        parsed = _front_matter(path.read_text(encoding="utf-8"))
        if parsed is None:
            issues.append(Issue("error", where, "no YAML front matter"))
            continue
        raw, body = parsed
        try:
            meta = PatternMeta.model_validate(raw, strict=False)
        except ValidationError as exc:
            issues.append(Issue("error", where, _problems(exc)))
            continue
        if path.stem != meta.id.lower():
            issues.append(
                Issue("error", where, f"file must be named {meta.id.lower()}.md")
            )
        if meta.id.split("-", 1)[0] not in pack.manifest.check_prefixes:
            issues.append(
                Issue("error", where, f"id '{meta.id}' needs a prefix this pack owns")
            )
        if not meta.sources and not meta.seen:
            issues.append(
                Issue("error", where, "needs a source or a dated sighting (`seen`)")
            )
        lines = set(body.splitlines())
        issues += [
            Issue("error", where, f"missing the heading '{h}'")
            for h in PATTERN_HEADINGS
            if h not in lines
        ]
    return issues


def check(folder: Path, known_languages: frozenset[str] | None = None) -> list[Issue]:
    """Check one pack folder against the contract.

    Args:
        folder: The pack folder.
        known_languages: Language names `kit detect` reports, or None to skip
            that check.

    Returns:
        Every breach found. An empty list means the pack meets the contract.
    """
    try:
        pack = load(folder)
    except PackError as exc:
        return [Issue("error", PACK_FILE, str(exc))]
    issues: list[Issue] = []
    if pack.name != folder.name:
        issues.append(
            Issue("error", PACK_FILE, f"name must match the folder '{folder.name}'")
        )
    if known_languages is not None:
        issues += [
            Issue("error", PACK_FILE, f"unknown language '{lang}'")
            for lang in pack.manifest.languages
            if lang not in known_languages
        ]
    return issues + _skill_issues(pack) + _content_issues(pack) + _pattern_issues(pack)
