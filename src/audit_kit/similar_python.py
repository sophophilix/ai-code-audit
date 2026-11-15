"""Named Python functions as tokens, for the near-duplicate check (no AI).

A file is parsed with `ast` and split into tokens with `tokenize`. It is never
imported or run (AGENTS.md rule 2). Comments, docstrings, decorators and layout
are left out, so two copies that differ only in those still match.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass

LAYOUT = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)
Place = tuple[int, int]


@dataclass(frozen=True)
class Found:
    """One named function: its name, its lines, and its tokens after the name."""

    name: str
    first: int
    last: int
    tokens: tuple[str, ...]


def _docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[Place, Place]:
    """Return where a function's docstring starts and ends, or an empty span."""
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        value = first.value
        return (value.lineno, value.col_offset), (
            value.end_lineno or value.lineno,
            value.end_col_offset or 0,
        )
    return (0, 0), (0, 0)


def functions(code: str) -> list[Found]:
    """Return every named function in a Python file, nested ones included.

    Raises:
        SyntaxError: If the file isn't valid Python for the kit's interpreter.
    """
    tree = ast.parse(code)
    try:
        tokens = [
            t
            for t in tokenize.generate_tokens(io.StringIO(code).readline)
            if t.type not in LAYOUT
        ]
    except tokenize.TokenError as exc:
        raise SyntaxError(str(exc)) from exc
    out: list[Found] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        start = (node.lineno, node.col_offset)
        end = (node.end_lineno or node.lineno, node.end_col_offset or 0)
        doc_start, doc_end = _docstring(node)
        body = [
            t.string
            for t in tokens
            if start <= t.start < end and not doc_start <= t.start < doc_end
        ]
        # `def name` or `async def name`: the name isn't part of what is compared.
        if node.name in body:
            body = body[body.index(node.name) + 1 :]
        out.append(Found(node.name, start[0], end[0], tuple(body)))
    return sorted(out, key=lambda f: (f.first, f.name))
