"""One headless Claude Code pass: the brief in, the reply and its cost out.

ADR 0007 D1 and D8. The pass runs with no tools, `--safe-mode` (no CLAUDE.md,
skills, plugins, hooks or MCP servers), no session kept, and an empty
temporary working folder, so the brief on stdin is all it can read. Claude
Code's JSON envelope is tool output, parsed by a boundary model.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from audit_kit.runner import CommandError, run

PASS_SECONDS = 900.0
ERROR_CHARS = 300
# Refusals another login or a later reset can get past, in the words `claude -p`
# uses ("You've hit your session limit"). Retrying them can't help.
RATE_LIMIT = re.compile(
    r"rate.?limit|usage.?limit|(?:session|weekly|monthly) limit|hit your .*limit"
    r"|quota|overloaded|\b429\b|limit (?:will )?reset"
    r"|not logged in|/login|invalid api key|oauth token|credit balance",
    re.I,
)


@dataclass(frozen=True)
class Usage:
    """Tokens one call used, by type."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @property
    def total(self) -> int:
        """Return every token of every type."""
        return self.input + self.output + self.cache_read + self.cache_write


@dataclass(frozen=True)
class Reply:
    """What one pass returned, and what it cost."""

    ok: bool
    text: str
    turns: int = 0
    usage: Usage = field(default_factory=Usage)
    cost_usd: float | None = None
    seconds: float = 0.0
    session: str = ""
    error: str = ""

    @property
    def rate_limited(self) -> bool:
        """Return True if the account in use can't run a pass right now."""
        return not self.ok and bool(RATE_LIMIT.search(self.error))


class PassRunner(Protocol):
    """Runs one pass; `call_claude` in use, a fake in tests."""

    def __call__(self, claude: Path, model: str, system: str, prompt: str) -> Reply:
        """Run a pass and return its reply."""
        ...


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class _Envelope(BaseModel):
    """The fields of `claude -p --output-format json` the kit uses."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    is_error: bool = False
    subtype: str = ""
    result: str = ""
    num_turns: int = 0
    total_cost_usd: float | None = None
    duration_ms: float | None = None
    session_id: str = ""
    usage: _Usage = Field(default_factory=_Usage)


def command(claude: Path, model: str, system: str) -> list[str | Path]:
    """Return the `claude -p` command line for one pass."""
    return [
        claude,
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--tools",
        "",
        "--safe-mode",
        "--no-session-persistence",
        "--system-prompt",
        system,
    ]


def call_claude(
    claude: Path,
    model: str,
    system: str,
    prompt: str,
    *,
    timeout: float = PASS_SECONDS,
) -> Reply:
    """Run one pass with the prompt on stdin, and read Claude Code's envelope.

    A failure (timeout, crash, unreadable output, or an error the envelope
    reports) is a Reply with `ok` false and the reason in `error`, so the caller
    decides whether to run it again.
    """
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="kit-pass-") as cwd:
        try:
            result = run(
                command(claude, model, system),
                cwd=Path(cwd),
                timeout=timeout,
                check=False,
                stdin=prompt.encode("utf-8"),
            )
        except CommandError as exc:
            return Reply(False, "", seconds=time.monotonic() - started, error=str(exc))
    measured = time.monotonic() - started
    try:
        envelope = _Envelope.model_validate_json(result.stdout)
    except ValidationError:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace")
        error = f"exit {result.code}: {detail.strip()[-ERROR_CHARS:]}"
        return Reply(False, "", seconds=measured, error=error)
    failed = envelope.is_error or result.code != 0
    u = envelope.usage
    return Reply(
        ok=not failed,
        text=envelope.result,
        turns=envelope.num_turns,
        usage=Usage(
            u.input_tokens,
            u.output_tokens,
            u.cache_read_input_tokens,
            u.cache_creation_input_tokens,
        ),
        cost_usd=envelope.total_cost_usd,
        seconds=(envelope.duration_ms / 1000) if envelope.duration_ms else measured,
        session=envelope.session_id,
        error=(envelope.result or envelope.subtype)[:ERROR_CHARS] if failed else "",
    )
