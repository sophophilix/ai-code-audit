"""The kit's line-oriented output: results on stdout, warnings on stderr."""

from __future__ import annotations

import sys


def say(text: str = "") -> None:
    """Print a plain line."""
    print(text)


def ok(text: str) -> None:
    """Print a step that was done."""
    print(f"  ok    {text}")


def skip(text: str) -> None:
    """Print a step that was already done or isn't possible here."""
    print(f"  skip  {text}")


def warn(text: str) -> None:
    """Print a warning on stderr."""
    print(f"  warn  {text}", file=sys.stderr)
