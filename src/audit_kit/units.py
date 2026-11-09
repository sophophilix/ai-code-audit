"""The file review's work units, listed from the inventory (no AI).

ADR 0002 D1: one unit is one own code file or stylesheet, one section of a file
over 1,000 lines, one inline `<script>` block, one stretch of markup between
scripts in an HTML page or template, or one dependency manifest. A unit never holds code from two files. The
list depends only on the files, so it's the same on every run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from audit_kit.errors import WorkspaceError
from audit_kit.inventory import Inventory
from audit_kit.workspace import Workspace

OUTPUT = ".audit/work/files/units.tsv"
RECORDS = PurePosixPath(".audit/files")
CODE = (".js", ".cjs", ".mjs", ".jsx", ".ts", ".tsx", ".mts", ".cts", ".sql")
STYLESHEETS = (".css", ".scss", ".sass", ".less")
# Pages and templates: their scripts and their markup are reviewed separately.
MARKUP = (
    ".html", ".htm", ".ejs", ".hbs", ".handlebars", ".njk", ".pug",
    ".vue", ".svelte", ".cshtml", ".razor",
)  # fmt: skip
# Dependency manifests: the only place a declared-but-unused package shows.
MANIFESTS = ("package.json",)
# A stretch of markup this short between scripts (a closing </body></html>)
# isn't worth a pass of its own.
MIN_MARKUP_LINES = 3
MAX_LINES = 1000
# A section aims at this size, cut at the last top-level boundary before it.
TARGET_LINES = 600
SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script\s*>", re.I | re.S)
STYLE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.I | re.S)
# Lines that start a top-level declaration, after the block's own indentation.
BOUNDARY = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\b|class\s|(?:const|let|var)\s+[\w$]+\s*="
    r"|module\.exports\b|exports\.\w+\s*=|(?:app|router)\.\w+\(|CREATE\s|ALTER\s|GO\s*$",
    re.I,
)
# Separate patterns, so HTML in a script's template string never cuts a script.
MARKUP_BOUNDARY = re.compile(
    r"<(?:section|main|header|footer|nav|form|article|aside|template|body|div)\b", re.I
)
STYLE_BOUNDARY = re.compile(
    r"@(?:media|layer|font-face|supports|container)\b|[.#:\w\[][^{;]*\{\s*$"
)
HEADER = "unit\tpath\tpart\tstart\tend\tlines\tkind\trecord\n"


@dataclass(frozen=True)
class Unit:
    """One file review pass's input."""

    id: str
    path: str
    part: str
    start: int
    end: int
    kind: str

    @property
    def lines(self) -> int:
        """Number of lines in the unit."""
        return self.end - self.start + 1

    @property
    def record(self) -> str:
        """Where the pass writes its record."""
        suffix = f"#{self.part}" if self.part else ""
        return f"{RECORDS}/{self.path}{suffix}.md"


def sections(
    lines: list[str], first: int = 1, boundary: re.Pattern[str] = BOUNDARY
) -> list[tuple[int, int]]:
    """Split lines into sections of at most MAX_LINES, at top-level boundaries.

    Args:
        lines: The code, one string per line.
        first: The line number of lines[0] in its file.
        boundary: What starts a top-level declaration for this kind of unit.

    Returns:
        (start, end) line numbers, covering every line once.
    """
    if len(lines) <= MAX_LINES:
        return [(first, first + len(lines) - 1)] if lines else []
    # Top level is the shallowest indent that starts at least two declarations;
    # lines inside template strings often sit at column 0, so the shallowest
    # indent of all lines would miss every boundary in an inline script.
    starts = [
        (len(x) - len(x.lstrip()), i)
        for i, x in enumerate(lines)
        if x.strip() and boundary.match(x.strip())
    ]
    counts: dict[int, int] = {}
    for indent, _ in starts:
        counts[indent] = counts.get(indent, 0) + 1
    base = min((d for d, n in counts.items() if n >= 2), default=0)
    top = {i for indent, i in starts if indent == base}
    cuts: list[tuple[int, int]] = []
    start = 0
    while start < len(lines):
        if len(lines) - start <= MAX_LINES:
            cuts.append((start, len(lines) - 1))
            break
        candidates = [i for i in top if start + 50 <= i <= start + TARGET_LINES]
        later = [i for i in top if start + TARGET_LINES < i <= start + MAX_LINES]
        cut = max(candidates) if candidates else min(later, default=start + MAX_LINES)
        cuts.append((start, cut - 1))
        start = cut
    return [(first + a, first + b) for a, b in cuts]


def build_units(
    ws: Workspace, inv: Inventory, excluded: tuple[str, ...]
) -> tuple[list[Unit], list[str]]:
    """List every unit, in path order; returns (units, problems)."""

    def kept(path: str) -> bool:
        return not any(
            path == e or path.startswith(e.rstrip("/") + "/") for e in excluded
        )

    found: list[tuple[str, str, int, int, str]] = []
    problems: list[str] = []
    for entry in inv.of("own"):
        path = entry.path
        manifest = PurePosixPath(path).name in MANIFESTS
        if (
            entry.kind != "file"
            or not kept(path)
            or not (manifest or path.endswith((*CODE, *STYLESHEETS, *MARKUP)))
        ):
            continue
        try:
            text = ws.read_text(path, limit=16_000_000)
        except WorkspaceError as exc:
            problems.append(f"not listed: {exc}")
            continue
        if manifest:
            found.append((path, "", 1, max(1, len(text.splitlines())), "manifest"))
            continue
        if path.endswith((*CODE, *STYLESHEETS)):
            style = path.endswith(STYLESHEETS)
            kind = "stylesheet" if style else "file"
            spans = sections(
                text.splitlines(), 1, STYLE_BOUNDARY if style else BOUNDARY
            )
            for n, (a, b) in enumerate(spans, 1):
                found.append((path, str(n) if len(spans) > 1 else "", a, b, kind))
            continue
        found += _page_units(path, text)
    units = [Unit(f"u{i:03d}", *row) for i, row in enumerate(sorted(found), 1)]
    return units, problems


def _page_units(path: str, text: str) -> list[tuple[str, str, int, int, str]]:
    """Units for a page or template: inline scripts and styles, and the markup between."""
    found: list[tuple[str, str, int, int, str]] = []
    lines = text.split("\n")
    embedded: set[int] = set()
    blocks = (
        (SCRIPT, "script", "inline script", BOUNDARY),
        (STYLE, "style", "inline style", STYLE_BOUNDARY),
    )
    for pattern, name, kind, boundary in blocks:
        for s, m in enumerate(pattern.finditer(text), 1):
            if not m.group(1).strip():
                continue
            first = text.count("\n", 0, m.start(1)) + 1
            body = m.group(1).split("\n")
            embedded.update(range(first, first + len(body)))
            spans = sections(body, first, boundary)
            for n, (a, b) in enumerate(spans, 1):
                part = f"{name}-{s}" + (f".{n}" if len(spans) > 1 else "")
                found.append((path, part, a, b, kind))
    stretches: list[tuple[int, int]] = []
    start: int | None = None
    for number in range(1, len(lines) + 1):
        if number in embedded:
            if start is not None:
                stretches.append((start, number - 1))
                start = None
        elif start is None:
            start = number
    if start is not None:
        stretches.append((start, len(lines)))
    markup = [
        span
        for a, b in stretches
        if sum(1 for x in lines[a - 1 : b] if x.strip()) >= MIN_MARKUP_LINES
        for span in sections(lines[a - 1 : b], a, MARKUP_BOUNDARY)
    ]
    for n, (a, b) in enumerate(markup, 1):
        part = "markup" + (f".{n}" if len(markup) > 1 else "")
        found.append((path, part, a, b, "markup"))
    return found


def render(units: list[Unit]) -> str:
    """Serialise for units.tsv; the coordinator adds status in its own state."""
    rows = (
        f"{u.id}\t{u.path}\t{u.part or '-'}\t{u.start}\t{u.end}\t{u.lines}\t{u.kind}\t{u.record}\n"
        for u in units
    )
    return HEADER + "".join(rows)


def parse(text: str) -> list[Unit]:
    """Read units.tsv back."""
    units: list[Unit] = []
    for line in text.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 7:
            units.append(
                Unit(
                    cols[0],
                    cols[1],
                    "" if cols[2] == "-" else cols[2],
                    int(cols[3]),
                    int(cols[4]),
                    cols[6],
                )
            )
    return units
