"""ADR 0007 D1, D8: one `claude -p` pass, at the subprocess boundary.

A shell script stands in for the Claude Code CLI: it records its arguments and
stdin and prints a saved envelope, so the real command line and parsing run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_kit.headless import Reply, Usage, call_claude

ENVELOPE = {
    "type": "result",
    "is_error": False,
    "result": "{}",
    "num_turns": 1,
    "total_cost_usd": 0.42,
    "duration_ms": 3000,
    "session_id": "abc",
    "usage": {
        "input_tokens": 5,
        "output_tokens": 7,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 50,
    },
}


def fake_claude(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "claude"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return script


def replying(tmp_path: Path, envelope: dict[str, object]) -> Path:
    seen = tmp_path / "seen.txt"
    return fake_claude(
        tmp_path,
        f"printf '%s\\n' \"$@\" > {seen}\ncat >> {seen}\necho '{json.dumps(envelope)}'",
    )


def test_a_reply_carries_its_text_cost_and_time(tmp_path: Path) -> None:
    got = call_claude(replying(tmp_path, ENVELOPE), "m", "system", "the brief")
    assert (got.ok, got.text, got.cost_usd, got.seconds) == (True, "{}", 0.42, 3.0)


def test_a_reply_carries_tokens_by_type(tmp_path: Path) -> None:
    got = call_claude(replying(tmp_path, ENVELOPE), "m", "system", "the brief")
    assert got.usage == Usage(input=5, output=7, cache_read=100, cache_write=50)


@pytest.mark.parametrize("flag", ["--safe-mode", "--no-session-persistence"])
def test_the_pass_runs_without_customisations_or_a_session(
    tmp_path: Path, flag: str
) -> None:
    call_claude(replying(tmp_path, ENVELOPE), "m", "system", "the brief")
    assert flag in (tmp_path / "seen.txt").read_text().splitlines()


def test_the_pass_has_no_tools(tmp_path: Path) -> None:
    call_claude(replying(tmp_path, ENVELOPE), "m", "system", "the brief")
    args = (tmp_path / "seen.txt").read_text().splitlines()
    assert args[args.index("--tools") + 1] == ""


def test_the_brief_goes_on_stdin(tmp_path: Path) -> None:
    call_claude(replying(tmp_path, ENVELOPE), "m", "system", "the brief")
    assert (tmp_path / "seen.txt").read_text().rstrip().endswith("the brief")


def test_a_rate_limit_error_is_recognised(tmp_path: Path) -> None:
    envelope = ENVELOPE | {"is_error": True, "result": "API Error: 429 rate limit"}
    got = call_claude(replying(tmp_path, envelope), "m", "s", "p")
    assert not got.ok and got.rate_limited


@pytest.mark.parametrize(
    "message",
    [
        "You've hit your session limit · resets 12:40pm (Australia/Sydney)",
        "You've hit your weekly limit · resets Mon 9am",
        "Not logged in · Please run /login",
        "Invalid API key · Please run /login",
        "Credit balance is too low",
    ],
)
def test_what_another_login_can_get_past_stops_the_run(message: str) -> None:
    assert Reply(False, "", error=message).rate_limited


def test_an_ordinary_error_is_not_a_rate_limit(tmp_path: Path) -> None:
    envelope = ENVELOPE | {"is_error": True, "result": "invalid model"}
    got = call_claude(replying(tmp_path, envelope), "m", "s", "p")
    assert not got.ok and not got.rate_limited


def test_a_crash_with_no_envelope_reports_its_exit(tmp_path: Path) -> None:
    got = call_claude(fake_claude(tmp_path, "echo crashed >&2\nexit 3"), "m", "s", "p")
    assert not got.ok and "exit 3" in got.error and "crashed" in got.error


@pytest.mark.integration
def test_a_pass_that_overruns_its_timeout_fails(tmp_path: Path) -> None:
    script = fake_claude(tmp_path, "exec sleep 10")
    got = call_claude(script, "m", "s", "p", timeout=0.5)
    assert not got.ok and "timed out" in got.error


def test_a_missing_cli_is_a_failed_pass(tmp_path: Path) -> None:
    got = call_claude(tmp_path / "no-claude", "m", "s", "p")
    assert not got.ok and "not found" in got.error
