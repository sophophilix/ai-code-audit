"""Near-duplicate named functions across the target's own JavaScript (no AI).

jscpd finds copied blocks of 50 tokens or more, so a one-line helper copied
into a second file and changed slightly is invisible to it, and a review that
reads one file at a time can't see the other copy. This module tokenises each
named function, compares functions of similar length, and lists pairs whose
tokens mostly match, with where they differ. Nothing is imported, built or run
(AGENTS.md rule 2).

A pair is a lead, not a verdict: two small functions can match by coincidence,
and a copy may be deliberate (Chesterton's Fence).
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from audit_kit.errors import WorkspaceError
from audit_kit.inventory import Inventory
from audit_kit.unused import JS, strip_comments
from audit_kit.workspace import Workspace

OUTPUT = ".audit/scans/similar.json"
MAX_BYTES = 5_000_000
# Below this a body is too generic to compare; above it jscpd finds the copy.
MIN_TOKENS = 12
MAX_TOKENS = 400
SIMILARITY = 0.85
SHINGLE = 4
# A shingle shared by more functions than this is boilerplate, not evidence.
COMMON = 40
PER_FUNCTION = 3
DIFFERENCES = 3
SHOWN_CHARS = 40
TOKEN = re.compile(
    r"""[A-Za-z_$][\w$]*|\d[\w.]*|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'"""
    r"""|`(?:\\.|[^`\\])*`|=>|\S"""
)
IDENT = re.compile(r"[A-Za-z_$][\w$]*")
KEYWORDS = frozenset(
    [
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
        "typeof",
        "new",
        "await",
        "yield",
        "do",
        "else",
        "try",
        "with",
        "delete",
        "void",
        "in",
        "of",
        "instanceof",
    ]
)
BEFORE_METHOD = frozenset(["{", "}", ";", "async", "static", "get", "set"])


@dataclass(frozen=True)
class Function:
    """One named function's body, as tokens without its own name."""

    file: str
    name: str
    line: int
    first: int
    last: int
    tokens: tuple[str, ...]


def tokenise(code: str) -> list[tuple[str, int]]:
    """Return each token and its line, from code with comments already removed."""
    breaks = [m.start() for m in re.finditer("\n", code)]
    out: list[tuple[str, int]] = []
    line, seen = 1, 0
    for m in TOKEN.finditer(code):
        while seen < len(breaks) and breaks[seen] < m.start():
            seen += 1
            line += 1
        out.append((m.group(), line))
    return out


def _match(tokens: list[str], i: int, step: int) -> int | None:
    """Return the index of the bracket that closes (step 1) or opens (step -1) i."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    if step < 0:
        pairs = {v: k for k, v in pairs.items()}
    opening, closing = tokens[i], pairs.get(tokens[i])
    if closing is None:
        return None
    depth = 0
    j = i
    while 0 <= j < len(tokens):
        if tokens[j] == opening:
            depth += 1
        elif tokens[j] == closing:
            depth -= 1
            if depth == 0:
                return j
        j += step
    return None


def _expression_end(tokens: list[str], i: int) -> int:
    """Return the last token of an arrow function's expression body starting at i."""
    depth = 0
    j = i
    while j < len(tokens):
        t = tokens[j]
        if t in "([{":
            depth += 1
        elif t in ")]}":
            if depth == 0:
                return j - 1
            depth -= 1
        elif t in ";," and depth == 0:
            return j - 1
        j += 1
    return len(tokens) - 1


def _name_before(tokens: list[str], i: int) -> int | None:
    """Return the index of `name` in `name = <i>` or `name: <i>`, skipping `async`."""
    j = i - 1
    if j >= 0 and tokens[j] == "async":
        j -= 1
    if j >= 1 and tokens[j] in ("=", ":") and IDENT.fullmatch(tokens[j - 1]):
        return j - 1
    return None


def _spans(tokens: list[str]) -> list[tuple[int, int, int]]:
    """Return (name, first, last) token indexes of each named function."""
    found: list[tuple[int, int, int]] = []
    for i, t in enumerate(tokens):
        if t == "function":
            j = i + 1 + (tokens[i + 1 : i + 2] == ["*"])
            name: int | None = (
                j if j < len(tokens) and IDENT.fullmatch(tokens[j]) else None
            )
            if name is not None:
                j += 1
            else:
                name = _name_before(tokens, i)
            if name is None or j >= len(tokens) or tokens[j] != "(":
                continue
            params = _match(tokens, j, 1)
            if params is None or params + 1 >= len(tokens) or tokens[params + 1] != "{":
                continue
            end = _match(tokens, params + 1, 1)
            if end is not None:
                found.append((name, j, end))
        elif t == "=>" and i > 0:
            start = _match(tokens, i - 1, -1) if tokens[i - 1] == ")" else i - 1
            if start is None:
                continue
            name = _name_before(tokens, start)
            if name is None or i + 1 >= len(tokens):
                continue
            end = (
                _match(tokens, i + 1, 1)
                if tokens[i + 1] == "{"
                else _expression_end(tokens, i + 1)
            )
            if end is not None:
                found.append((name, start, end))
        elif (
            IDENT.fullmatch(t)
            and t not in KEYWORDS
            and i > 0
            and tokens[i - 1] in BEFORE_METHOD
            and tokens[i + 1 : i + 2] == ["("]
        ):
            params = _match(tokens, i + 1, 1)
            if params is None or tokens[params + 1 : params + 2] != ["{"]:
                continue
            end = _match(tokens, params + 1, 1)
            if end is not None:
                found.append((i, i + 1, end))
    return found


def functions(path: str, code: str) -> list[Function]:
    """Return the named functions in one file's code, comments removed first."""
    pairs = tokenise(strip_comments(code))
    tokens = [t for t, _ in pairs]
    out: list[Function] = []
    for name, first, last in _spans(tokens):
        body = tuple(tokens[first : last + 1])
        if MIN_TOKENS <= len(body) <= MAX_TOKENS:
            out.append(
                Function(
                    path,
                    tokens[name],
                    pairs[name][1],
                    pairs[first][1],
                    pairs[last][1],
                    body,
                )
            )
    return out


def _nested(a: Function, b: Function) -> bool:
    return a.file == b.file and (
        a.first <= b.first <= b.last <= a.last or b.first <= a.first <= a.last <= b.last
    )


def _shingles(f: Function) -> set[tuple[str, ...]]:
    t = f.tokens
    return {t[i : i + SHINGLE] for i in range(len(t) - SHINGLE + 1)}


def _differences(a: Function, b: Function) -> list[dict[str, str]]:
    matcher = difflib.SequenceMatcher(None, a.tokens, b.tokens, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op != "equal":
            out.append(
                {
                    "first": " ".join(a.tokens[i1:i2])[:SHOWN_CHARS],
                    "second": " ".join(b.tokens[j1:j2])[:SHOWN_CHARS],
                }
            )
    return out[:DIFFERENCES]


def pairs(found: list[Function]) -> list[dict[str, Any]]:
    """Return near-duplicate pairs, most similar first, at most PER_FUNCTION each."""
    shingles = [_shingles(f) for f in found]
    postings: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for n, s in enumerate(shingles):
        for sh in s:
            postings[sh].append(n)
    shared: dict[tuple[int, int], int] = defaultdict(int)
    for ids in postings.values():
        if len(ids) > COMMON:
            continue
        for x, a in enumerate(ids):
            for b in ids[x + 1 :]:
                shared[(a, b)] += 1
    scored: list[tuple[float, int, int]] = []
    for (a, b), count in shared.items():
        fa, fb = found[a], found[b]
        small, large = sorted((len(fa.tokens), len(fb.tokens)))
        if small / large < SIMILARITY - 0.1 or _nested(fa, fb):
            continue
        if count < 0.5 * min(len(shingles[a]), len(shingles[b])):
            continue
        ratio = difflib.SequenceMatcher(
            None, fa.tokens, fb.tokens, autojunk=False
        ).ratio()
        if ratio >= SIMILARITY:
            scored.append((ratio, a, b))
    taken: dict[int, int] = defaultdict(int)
    out: list[dict[str, Any]] = []
    for ratio, a, b in sorted(scored, key=lambda s: (-s[0], s[1], s[2])):
        if taken[a] >= PER_FUNCTION or taken[b] >= PER_FUNCTION:
            continue
        taken[a] += 1
        taken[b] += 1
        fa, fb = found[a], found[b]
        out.append(
            {
                "similarity": round(ratio, 2),
                "first": {"file": fa.file, "name": fa.name, "line": fa.line},
                "second": {"file": fb.file, "name": fb.name, "line": fb.line},
                "differences": _differences(fa, fb),
            }
        )
    return out


def report(ws: Workspace, inv: Inventory, excluded: tuple[str, ...]) -> dict[str, Any]:
    """Build the near-duplicate report from the target's own JavaScript files."""

    def kept(path: str) -> bool:
        return not any(
            path == e or path.startswith(e.rstrip("/") + "/") for e in excluded
        )

    found: list[Function] = []
    problems: list[str] = []
    paths = sorted(
        e.path
        for e in inv.of("own")
        if e.kind == "file" and e.path.endswith(JS) and kept(e.path)
    )
    for path in paths:
        try:
            found += functions(path, ws.read_text(path, limit=MAX_BYTES))
        except WorkspaceError as exc:
            problems.append(f"not read: {exc}")
    listed = pairs(found)
    return {
        "generated_by": "kit scan: near-duplicate named functions (deterministic, no execution)",
        "method": (
            f"Own {'/'.join(JS)} files, comments removed, tokenised. Each named "
            f"function of {MIN_TOKENS}-{MAX_TOKENS} tokens is compared, without its "
            f"name, with functions of similar length that share {SHINGLE}-token "
            f"runs; a pair is listed when at least {SIMILARITY:.0%} of the tokens "
            "match in order."
        ),
        "limits": [
            "Inline scripts in HTML and anonymous callbacks aren't compared.",
            "Functions longer than the maximum are left to jscpd.",
            "A pair is a lead: small functions can match by coincidence, and a "
            "copy may be deliberate.",
        ],
        "counts": {"files": len(paths), "functions": len(found), "pairs": len(listed)},
        "problems": problems,
        "pairs": listed,
    }
