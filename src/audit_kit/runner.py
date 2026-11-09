"""The only place the kit starts other programs.

Arguments are always a sequence (no shell), and every call has a timeout
(python-style-guide: all subprocess boundaries set an explicit timeout).
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404  the kit's single, reviewed subprocess boundary
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from audit_kit.errors import AuditKitError

QUICK = 60.0
LONG = 1800.0


class CommandError(AuditKitError):
    """A program was missing, timed out, or failed."""


@dataclass(frozen=True)
class Result:
    """Exit code and captured output of a finished program."""

    code: int
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        """Return stdout as text with trailing whitespace removed."""
        return self.stdout.decode("utf-8", errors="replace").strip()


def have(tool: str | Path) -> bool:
    """Return True if a program is on PATH, or is an executable path."""
    path = Path(tool)
    if path.is_absolute():
        return path.is_file() and bool(path.stat().st_mode & 0o111)
    return shutil.which(str(tool)) is not None


def run(
    args: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    timeout: float = QUICK,
    check: bool = True,
    stdin: bytes | None = None,
) -> Result:
    """Run a program and capture its output.

    Args:
        args: Program and arguments.
        cwd: Working directory.
        timeout: Seconds before the program is stopped.
        check: Raise if the exit code isn't 0.
        stdin: Bytes to send to the program.

    Returns:
        The exit code and output.

    Raises:
        CommandError: If the program is missing, times out, or (with check) fails.
    """
    argv = [str(a) for a in args]
    name = Path(argv[0]).name
    try:
        done = subprocess.run(  # noqa: S603  # nosec B603  argument list, no shell
            argv,
            cwd=cwd,
            input=stdin,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"{name} not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"{name} timed out after {timeout:.0f}s") from exc
    if check and done.returncode != 0:
        detail = done.stderr.decode("utf-8", errors="replace").strip().splitlines()[
            -1:
        ] or [""]
        raise CommandError(
            f"{name} failed (exit {done.returncode}) {detail[0]}".rstrip()
        )
    return Result(done.returncode, done.stdout, done.stderr)


def git(*args: str | Path, cwd: Path | None = None, timeout: float = QUICK) -> str:
    """Run git and return its output as text."""
    return run(["git", *args], cwd=cwd, timeout=timeout).text
