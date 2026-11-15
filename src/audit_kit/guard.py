"""Checks the harness enforces on stage agents, through hooks (ADR 0013).

`kit hook` reads one hook event from Claude Code and calls `refusal`. Before a
tool call, the check refuses a shell command that isn't on the read-only list
in `AGENTS.md` rule 2, and a write outside `.audit/` (rule 1). When a stage
agent tries to finish, the check runs `kit verify` and sends the agent back
once with the failures on its own output.

The shell check reads the whole command, not its first word. It is a second
barrier behind the harness's permissions. It isn't a sandbox: it can't see
what an allowed program does with a file the target controls.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from audit_kit.verification import Status, check, parse_header
from audit_kit.workspace import Workspace

AUDIT = ".audit"
# Only the tech lead relaxes a rule (AGENTS.md rule 11), and this file holds them.
PROTECTED = (f"{AUDIT}/policy.yaml",)
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
KIT = ".audit-kit/bin/kit"
CHECKPOINT = ".audit-kit/bin/checkpoint"

SEPARATORS = frozenset({";", "|", "||", "&&", "|&"})
WRITES = frozenset({">", ">>", ">|", "&>", "&>>"})
DUPLICATES = frozenset({">&", "<&"})
GLOB = frozenset("*?[")
# Commands that only read, whatever their arguments.
READ_ONLY = frozenset(
    {
        "[",
        "basename",
        "cat",
        "cut",
        "date",
        "dirname",
        "echo",
        "grep",
        "head",
        "ls",
        "printf",
        "pwd",
        "tail",
        "test",
        "tr",
        "true",
        "uniq",
        "wc",
    }
)
GIT_READS = frozenset({"blame", "log", "ls-files", "rev-parse", "show", "status"})
FIND_ACTIONS = frozenset(
    {
        "-delete",
        "-exec",
        "-execdir",
        "-fls",
        "-fprint",
        "-fprint0",
        "-fprintf",
        "-ok",
        "-okdir",
    }
)
# `sed -n '10,20p'`: print a line or a range, and nothing else.
SED_PRINT = re.compile(r"^\s*(\d+|\$)(\s*,\s*(\d+|\$|\+\d+))?\s*p\s*$")
SED_FLAGS = re.compile(r"^-[nEr]+$")


class RefusedError(Exception):
    """A tool call breaks a rule; the message is the reason given to the agent."""


@dataclass(frozen=True)
class Word:
    """One shell word after quote removal.

    Attributes:
        text: The word as the program would receive it, before expansion.
        globbed: True if an unquoted `*`, `?` or `[` could expand to file names.
        expands: True if a `$name` inside double quotes is replaced at run time.
    """

    text: str
    globbed: bool = False
    expands: bool = False


@dataclass(frozen=True)
class Op:
    """A shell operator: a separator or a redirection."""

    text: str


class Event(BaseModel):
    """The fields of a Claude Code hook event that the checks use."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    hook_event_name: str
    cwd: str = ""
    tool_name: str = ""
    tool_input: Mapping[str, object] = {}
    agent_type: str = ""
    stop_hook_active: bool = False


@dataclass(frozen=True)
class Stage:
    """What a stage agent must leave behind before it may finish.

    Attributes:
        files: Prefixes of the output files it owns, such as `04-`.
        checks: Prefixes of the `kit verify` checks that judge only its work.
    """

    files: tuple[str, ...]
    checks: tuple[str, ...] = ()


# Keyed by the `name` in adapters/claude-code/agents/*.md.
STAGES: dict[str, Stage] = {
    "audit-discovery": Stage(("01-",)),
    "audit-architect": Stage(("02-",), ("OUT-D",)),
    "audit-engineer": Stage(("03-",)),
    "audit-security": Stage(("04-",)),
    "audit-accessibility": Stage(("05-",)),
    "audit-verifier": Stage(("06-",), ("OUT-V",)),
    "audit-lead-reviewer": Stage(("07-",), ("OUT-R", "OUT-B")),
}


class _Lexer:
    """Split a shell command into words and operators, refusing what it can't follow."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.tokens: list[Word | Op] = []
        self._text: list[str] = []
        self._quoted = False
        self._globbed = False
        self._expands = False

    def _flush(self) -> None:
        if self._text or self._quoted:
            self.tokens.append(Word("".join(self._text), self._globbed, self._expands))
        self._text, self._quoted = [], False
        self._globbed = self._expands = False

    def _substitution(self, i: int) -> None:
        """Refuse command substitution, which runs a second command unseen."""
        c = self.command
        if c[i] == "`" or c.startswith("$(", i):
            raise RefusedError("command substitution (`...` or $(...)) isn't allowed")

    def _double(self, i: int) -> int:
        """Read a double-quoted span starting after its opening quote."""
        c = self.command
        while i < len(c) and c[i] != '"':
            self._substitution(i)
            if c[i] == "\\" and i + 1 < len(c) and c[i + 1] in '$`"\\\n':
                self._text.append(c[i + 1])
                i += 2
                continue
            self._expands = self._expands or c[i] == "$"
            self._text.append(c[i])
            i += 1
        if i == len(c):
            raise RefusedError("unterminated double quote")
        return i + 1

    def _single(self, i: int) -> int:
        end = self.command.find("'", i)
        if end < 0:
            raise RefusedError("unterminated single quote")
        self._text.append(self.command[i:end])
        return end + 1

    def _operator(self, i: int) -> int:
        c = self.command
        end = i
        while end < len(c) and c[end] in "|&;<>":
            end += 1
        # `2>/dev/null`: the digits name a file descriptor, not an argument.
        if c[i] in "<>" and not self._quoted and "".join(self._text).isdigit():
            self._text = []
        self._flush()
        self.tokens.append(Op(c[i:end]))
        return end

    def _bare(self, i: int) -> int:
        """Read one unquoted character at `i`."""
        c = self.command
        ch = c[i]
        if ch == "\\":
            if i + 1 < len(c) and c[i + 1] != "\n":
                self._text.append(c[i + 1])
            return i + 2
        if ch == "$" and i + 1 < len(c) and not c[i + 1].isspace():
            raise RefusedError("an unquoted $ expansion isn't allowed; quote the text")
        if ch == "{":
            raise RefusedError("an unquoted { isn't allowed; quote the text")
        self._globbed = self._globbed or ch in GLOB
        self._text.append(ch)
        return i + 1

    def run(self) -> list[Word | Op]:
        """Return the command's tokens.

        Raises:
            RefusedError: If the command uses shell syntax the check can't follow.
        """
        c = self.command
        i = 0
        while i < len(c):
            ch = c[i]
            self._substitution(i)
            if ch in "()":
                raise RefusedError("a subshell or process substitution isn't allowed")
            if ch == "\n":
                self._flush()
                self.tokens.append(Op(";"))
                i += 1
            elif ch.isspace():
                self._flush()
                i += 1
            elif ch == "#" and not self._text and not self._quoted:
                end = c.find("\n", i)
                i = len(c) if end < 0 else end
            elif ch in "|&;<>":
                i = self._operator(i)
            elif ch == "'":
                self._quoted = True
                i = self._single(i + 1)
            elif ch == '"':
                self._quoted = True
                i = self._double(i + 1)
            else:
                i = self._bare(i)
        self._flush()
        return self.tokens


def _resolve(cwd: Path, target: str) -> Path:
    """Return the file a path names, with symlinks followed."""
    path = Path(target).expanduser()
    return (path if path.is_absolute() else cwd / path).resolve()


def _inside_audit(root: Path, cwd: Path, target: str) -> bool:
    """Say whether a path is under the root's `.audit/`."""
    return _resolve(cwd, target).is_relative_to((root / AUDIT).resolve())


def _redirect(op: str, target: Word | Op | None, root: Path, cwd: Path) -> None:
    if not isinstance(target, Word):
        raise RefusedError(f"'{op}' needs a target")
    if op in DUPLICATES:
        if not target.text.isdigit() and target.text != "-":
            raise RefusedError(f"'{op}' may only name a file descriptor")
    elif op in WRITES:
        if target.text == "/dev/null":
            return
        if target.expands or target.globbed:
            raise RefusedError(f"can't tell where '{op} {target.text}' writes")
        if not _inside_audit(root, cwd, target.text):
            raise RefusedError(
                f"'{op} {target.text}' writes outside {AUDIT}/ (AGENTS.md rule 1)"
            )
    elif op != "<":
        raise RefusedError(f"the shell operator '{op}' isn't allowed")


def _commands(command: str, root: Path, cwd: Path) -> list[list[Word]]:
    """Split a command line into simple commands, checking each redirection."""
    tokens = _Lexer(command).run()
    found: list[list[Word]] = [[]]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if isinstance(token, Word):
            found[-1].append(token)
        elif token.text in SEPARATORS:
            found.append([])
        elif token.text == "&":
            raise RefusedError("a background command (&) isn't allowed")
        else:
            _redirect(
                token.text, tokens[i + 1] if i + 1 < len(tokens) else None, root, cwd
            )
            i += 1
        i += 1
    return [words for words in found if words]


def _find(args: Sequence[Word]) -> None:
    for arg in args:
        if arg.text in FIND_ACTIONS:
            raise RefusedError(f"find {arg.text} runs or changes something")
        if arg.globbed:
            raise RefusedError(
                f"quote '{arg.text}': a file named like an option would change "
                "what find does"
            )


def _sed(args: Sequence[Word]) -> None:
    flags = [a.text for a in args if a.text.startswith("-")]
    rest = [a.text for a in args if not a.text.startswith("-")]
    if not flags or not all(SED_FLAGS.match(f) for f in flags):
        raise RefusedError("only `sed -n` is allowed (optionally with -E)")
    if not any("n" in f for f in flags):
        raise RefusedError("only `sed -n` is allowed")
    if not rest or not SED_PRINT.match(rest[0]):
        raise RefusedError(
            "sed may only print a line or a range, such as `sed -n '10,20p'`"
        )


def _sort(args: Sequence[Word]) -> None:
    for arg in args:
        text = arg.text
        long_write = text.startswith(("--output", "--compress-program"))
        short_write = text.startswith("-") and not text.startswith("--") and "o" in text
        if long_write or short_write:
            raise RefusedError(f"sort {text} writes a file or runs a program")


def _rg(args: Sequence[Word]) -> None:
    for arg in args:
        if arg.text.startswith(("--pre", "--hostname-bin")):
            raise RefusedError(f"rg {arg.text} runs a program")


def _git(args: Sequence[Word]) -> None:
    sub = args[0].text if args else ""
    if sub not in GIT_READS:
        raise RefusedError(
            f"git {sub or '(no subcommand)'} isn't allowed; "
            f"allowed: {', '.join(sorted(GIT_READS))}"
        )
    for arg in args[1:]:
        if arg.text.startswith("--output") or arg.text == "--ext-diff":
            raise RefusedError(f"git {sub} {arg.text} writes a file or runs a program")


def _kit(args: Sequence[Word]) -> None:
    if not args or args[0].text != "query":
        raise RefusedError("an agent may run only `kit query`; a person runs the rest")


def _any(_args: Sequence[Word]) -> None:
    return None


CHECKERS: dict[str, Callable[[Sequence[Word]], None]] = {
    **dict.fromkeys(READ_ONLY, _any),
    "find": _find,
    "sed": _sed,
    "sort": _sort,
    "rg": _rg,
    "git": _git,
    KIT: _kit,
    f"./{KIT}": _kit,
    CHECKPOINT: _any,
    f"./{CHECKPOINT}": _any,
}


def check_command(command: str, root: Path, cwd: Path) -> None:
    """Check one shell command line against the read-only list.

    Args:
        command: The full command line the agent wants to run.
        root: The workspace root.
        cwd: The folder the command would run in.

    Raises:
        RefusedError: If any part of the command could execute, install, reach the
            network or write outside `.audit/`.
    """
    for words in _commands(command, root, cwd):
        name = words[0].text
        checker = CHECKERS.get(name)
        if words[0].globbed or words[0].expands or checker is None:
            raise RefusedError(
                f"'{name}' isn't a read-only command the audit allows "
                "(AGENTS.md rule 2)"
            )
        checker(words[1:])


def check_write(tool_input: Mapping[str, object], root: Path, cwd: Path) -> None:
    """Check the path a write tool names.

    Raises:
        RefusedError: If the path is missing, outside `.audit/` or protected.
    """
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(target, str) or not target:
        raise RefusedError("the write names no file")
    if not _inside_audit(root, cwd, target):
        raise RefusedError(f"{target} is outside {AUDIT}/ (AGENTS.md rule 1)")
    for rel in PROTECTED:
        if _resolve(cwd, target) == (root / rel).resolve():
            raise RefusedError(f"only the tech lead changes {rel} (AGENTS.md rule 11)")


def tool_refusal(event: Event, root: Path) -> str | None:
    """Return why a tool call is refused, or None to leave it to the permissions."""
    cwd = Path(event.cwd) if event.cwd else root
    try:
        if event.tool_name == "Bash":
            command = event.tool_input.get("command")
            if not isinstance(command, str):
                raise RefusedError("the Bash call names no command")
            check_command(command, root, cwd)
        elif event.tool_name in WRITE_TOOLS:
            check_write(event.tool_input, root, cwd)
    except RefusedError as exc:
        return f"Refused by the audit kit: {exc}"
    return None


def stop_refusal(event: Event, root: Path) -> str | None:
    """Return the failed checks on a stage agent's output, or None to let it finish.

    The agent is sent back once. A second attempt to finish passes, and the
    coordinator's gate checks then decide (core/agents/coordinator.md).
    """
    stage = STAGES.get(event.agent_type)
    if stage is None or event.stop_hook_active:
        return None
    ws = Workspace(root)
    outputs = sorted(
        p.name for prefix in stage.files for p in (root / AUDIT).glob(f"{prefix}*.md")
    )
    if not outputs:
        return (
            f"You haven't written your output file ({AUDIT}/{stage.files[0]}*.md). "
            "Write it, or save your progress with status: in-progress, then finish."
        )
    # A pass that hands over mid-way says so in its header and is resumed, not judged.
    handed_over = {
        name
        for name in outputs
        if parse_header(ws.read_text(f"{AUDIT}/{name}", limit=50_000_000)).get("status")
        == "in-progress"
    }
    judged = tuple(name for name in outputs if name not in handed_over)
    if not judged:
        return None
    failures = [
        r.line()
        for r in check(ws).results
        if r.status is Status.FAIL
        and (r.detail.startswith(judged) or r.check.startswith(stage.checks or ("\0",)))
    ]
    if not failures:
        return None
    return (
        f"kit verify: {len(failures)} check(s) fail on your output. Fix them, then "
        "finish. If one can't pass, say why under Limitations.\n" + "\n".join(failures)
    )


def refusal(event: Event, root: Path) -> str | None:
    """Return the reason to block a hook event, or None to allow it."""
    if event.hook_event_name == "PreToolUse":
        return tool_refusal(event, root)
    if event.hook_event_name == "SubagentStop":
        return stop_refusal(event, root)
    return None
