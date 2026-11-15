"""Where the values the secret scan found are in the target's files.

`secrets.json` is written redacted, so it holds no value. Each finding gives a
line, the columns of what the rule matched, and that match with the value
replaced. That is enough to find the value again in the file, in memory, so
the kit can mask it in a brief before a model sees it, and check that no
output holds it (OUT-R7). A value is never written anywhere.
"""

from __future__ import annotations

import json
import posixpath
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from audit_kit.errors import WorkspaceError
from audit_kit.workspace import Workspace

SCAN = PurePosixPath(".audit/scans/secrets.json")
SCAN_BYTES = 50_000_000
FILE_BYTES = 16_000_000
# What gitleaks writes in place of the value when run with --redact.
REDACTED = "REDACTED"
MASK = "****"
# A shorter value would match ordinary words in an output.
MIN_VALUE = 8
KIT_FOLDERS = (".audit", ".audit-kit", ".claude", ".git")
# Outputs that are text. Anything else, such as the store or a .docx, isn't read.
TEXT = frozenset(
    {".md", ".json", ".jsonl", ".csv", ".txt", ".yaml", ".yml", ".html", ".xml"}
    | {".drawio", ".svg", ".log", ".py", ".js", ".ts", ".sh"}
)

Match = Callable[[str], str | None]


class _Leak(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    File: str
    StartLine: int = 0
    EndLine: int = 0
    StartColumn: int = 0
    EndColumn: int = 0
    Match: str = ""


_LEAKS = TypeAdapter(list[_Leak])


@dataclass(frozen=True)
class Span:
    """One value's place in a file: a 1-based line and 0-based columns."""

    line: int
    start: int
    end: int


@dataclass
class Leaks:
    """The located values of one workspace. Held in memory only."""

    spans: dict[str, list[Span]] = field(default_factory=dict)
    values: frozenset[str] = frozenset()
    total: int = 0
    unlocated: int = 0
    problem: str = ""

    def mask(self, path: str, lines: list[str]) -> list[str]:
        """Return a file's lines with every located value replaced by the mask."""
        spans = self.spans.get(path)
        if not spans:
            return lines
        out = list(lines)
        # Right to left, so a replacement never moves a span still to be applied.
        for span in sorted(spans, key=lambda s: (s.line, s.start), reverse=True):
            if span.line <= len(out):
                line = out[span.line - 1]
                out[span.line - 1] = line[: span.start] + MASK + line[span.end :]
        return out

    def lines_holding(self, text: str) -> list[int]:
        """Return the 1-based lines of a text that hold a located value."""
        wanted = [v for v in self.values if len(v) >= MIN_VALUE]
        if not wanted or not any(v in text for v in wanted):
            return []
        return [
            number
            for number, line in enumerate(text.split("\n"), 1)
            if any(v in line for v in wanted)
        ]


def _template(leak: _Leak) -> tuple[str, str, int] | None:
    """Return what the rule matched before and after the value, and its length."""
    if leak.Match.count(REDACTED) != 1:
        return None
    prefix, suffix = leak.Match.split(REDACTED)
    length = leak.EndColumn - leak.StartColumn + 1 - len(prefix) - len(suffix)
    return (prefix, suffix, length) if length > 0 else None


def _in_line(
    line: str, template: tuple[str, str, int], near: int
) -> tuple[int, int] | None:
    """Return the value's columns in one line: the fit nearest the reported one.

    A fit is a place where the text before and after the value is what the rule
    matched. gitleaks counts columns from 1 on a file's first line and from 2
    after it, so the reported column picks between fits and is never trusted
    alone, unless the rule matched nothing but the value.
    """
    prefix, suffix, length = template
    fits = [
        start
        for start in range(len(prefix), len(line) - length - len(suffix) + 1)
        if line.startswith(prefix, start - len(prefix))
        and line.startswith(suffix, start + length)
    ]
    if not fits:
        return None
    start = min(fits, key=lambda s: abs(s - near))
    return start, start + length


def locate(leak: _Leak, lines: list[str]) -> list[Span]:
    """Return where one finding's value is in the file as it is now."""
    if not 1 <= leak.StartLine <= len(lines):
        return []
    if leak.EndLine > leak.StartLine:
        # A value over several lines, such as a private key: the whole lines.
        return [
            Span(n, len(text) - len(text.lstrip()), len(text.rstrip()))
            for n in range(leak.StartLine, min(leak.EndLine, len(lines)) + 1)
            if (text := lines[n - 1]).strip()
        ]
    template = _template(leak)
    if template is None:
        return []
    prefix, suffix, _length = template
    near = leak.StartColumn - (2 if leak.StartLine > 1 else 1) + len(prefix)
    found = _in_line(lines[leak.StartLine - 1], template, near)
    if found:
        return [Span(leak.StartLine, *found)]
    if not prefix and not suffix:
        return []
    # A history scan gives the line in an old commit: look for the same text.
    return [
        Span(n, *at)
        for n, text in enumerate(lines, 1)
        if (at := _in_line(text, template, near))
    ]


def _kit_path(name: str) -> bool:
    return posixpath.normpath(name).split("/", 1)[0] in KIT_FOLDERS


def relative(ws: Workspace) -> Match:
    """Return a matcher for paths that gitleaks wrote relative to the target."""

    def match(name: str) -> str | None:
        rel = posixpath.normpath(name)
        if rel.startswith(("/", "..")) or _kit_path(rel):
            return None
        return rel if ws.is_file(rel) else None

    return match


def _read(ws: Workspace) -> list[_Leak] | str:
    try:
        return _LEAKS.validate_json(ws.read_text(SCAN, SCAN_BYTES))
    except (WorkspaceError, ValidationError, json.JSONDecodeError) as exc:
        return type(exc).__name__


def _by_file(found: Iterable[_Leak], match: Match) -> dict[str, list[_Leak]]:
    by_file: dict[str, list[_Leak]] = {}
    for leak in found:
        path = match(leak.File)
        if path is not None:
            by_file.setdefault(path, []).append(leak)
    return by_file


def load(ws: Workspace, match: Match | None = None) -> Leaks:
    """Locate every value in secrets.json that is in the target's files now.

    Args:
        ws: The workspace.
        match: Maps a path as gitleaks wrote it to a path in the target, or
            None to leave the finding out. Defaults to the path as written.
    """
    if not ws.is_file(SCAN) or not ws.size(SCAN):
        return Leaks()
    found = _read(ws)
    if isinstance(found, str):
        return Leaks(problem=found)
    # In an eval snapshot gitleaks reads the kit's folders too: not the target.
    found = [f for f in found if not _kit_path(f.File)]
    leaks = Leaks(total=len(found))
    values: set[str] = set()
    by_file = _by_file(found, match or relative(ws))
    leaks.unlocated = len(found) - sum(len(v) for v in by_file.values())
    for path, group in sorted(by_file.items()):
        try:
            lines = ws.read_text(path, FILE_BYTES).split("\n")
        except WorkspaceError:
            leaks.unlocated += len(group)
            continue
        for leak in group:
            spans = locate(leak, lines)
            if not spans:
                leaks.unlocated += 1
                continue
            for span in spans:
                if span not in leaks.spans.setdefault(path, []):
                    leaks.spans[path].append(span)
                value = lines[span.line - 1][span.start : span.end]
                # The first and last line of a key block are the same in every key.
                if not value.startswith("-----"):
                    values.add(value)
    leaks.spans = {p: _merged(s) for p, s in leaks.spans.items()}
    leaks.values = frozenset(values)
    return leaks


def _merged(spans: list[Span]) -> list[Span]:
    """Join spans that overlap, so two rules on one value leave one mask."""
    out: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.line, s.start)):
        last = out[-1] if out else None
        if last and last.line == span.line and span.start <= last.end:
            out[-1] = Span(last.line, last.start, max(last.end, span.end))
        else:
            out.append(span)
    return out


def searchable(rel: PurePosixPath) -> bool:
    """Say whether an output is text the kit can search for a value."""
    return rel.suffix.lower() in TEXT
