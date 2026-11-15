"""The checks the hooks enforce on stage agents (ADR 0013).

These prove the kit's decisions on a hook event. They don't prove that Claude
Code sends the event or honours the answer (python-testing, optional adapters).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from audit_kit import cli, guard
from audit_kit.guard import Event, RefusedError, check_command, refusal

KIT = Path(__file__).resolve().parents[2]
ADAPTER = KIT / "adapters/claude-code"
HEADER = "---\nkit_version: 0.7.1\nagent: security\nmodel: m\ncommit: abc\nstatus: {status}\n---\n"
FINDING = (
    "### SEC-001 Title\n- Key: X-demo:app.js\n- Category: security\n- Severity: low\n"
    "- Confidence: high\n- Location: app.js:2\n- Evidence: seen\n- Excerpt: `b`\n"
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".audit/work").mkdir(parents=True)
    (tmp_path / "app.js").write_text("a\nb\nc\n")
    return tmp_path


def bash(command: str, cwd: Path) -> Event:
    return Event(
        hook_event_name="PreToolUse",
        cwd=str(cwd),
        tool_name="Bash",
        tool_input={"command": command},
    )


def write(tool: str, path: str, cwd: Path, key: str = "file_path") -> Event:
    return Event(
        hook_event_name="PreToolUse",
        cwd=str(cwd),
        tool_name=tool,
        tool_input={key: path},
    )


def stop(agent: str, cwd: Path, *, active: bool = False) -> Event:
    return Event(
        hook_event_name="SubagentStop",
        cwd=str(cwd),
        agent_type=agent,
        stop_hook_active=active,
    )


@pytest.mark.parametrize(
    "command",
    [
        "ls -la src",
        "grep -rn 'eval(' lib | head -20",
        "rg -n \"child_process\" --glob '*.js' | sort | uniq -c",
        "find . -name '*.py' -not -path './.venv/*'",
        "sed -n '10,20p' app.js",
        "sed -n 5p app.js",
        "sed -nE '1,$p' app.js",
        "wc -l app.js 2>/dev/null",
        "cat app.js > .audit/work/copy.txt",
        "grep -c x app.js >> .audit/work/counts.txt 2>&1",
        "git log --oneline -5 -- app.js",
        "git show HEAD:app.js | head -5",
        "git blame -L 1,3 app.js",
        "git status --porcelain",
        "date -u +%Y-%m-%dT%H:%MZ",
        '.audit-kit/bin/kit query . "select count(*) from findings"',
        '.audit-kit/bin/checkpoint "stage 1 discovery pass a: done"',
        "grep -n '$(' app.js",
        "grep -n '`' app.js",
        'grep -n "price is \\$5" app.js',
        "grep -n foo$ app.js",
        "ls   # list the files",
        "grep -n a app.js && grep -n b app.js || true",
        "wc -l < app.js",
    ],
)
def test_read_only_commands_pass(command: str, root: Path) -> None:
    check_command(command, root, root)


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        ("npm install", "'npm' isn't a read-only command"),
        ("node server.js", "'node'"),
        ("python3 -c 'print(1)'", "'python3'"),
        ("make build", "'make'"),
        ("bash scripts/run.sh", "'bash'"),
        ("sh -c 'ls'", "'sh'"),
        ("./scripts/run.sh", "'./scripts/run.sh'"),
        ("/bin/ls", "'/bin/ls'"),
        ("curl https://example.com", "'curl'"),
        ("rm -rf lib", "'rm'"),
        ("xargs rm", "'xargs'"),
        ("awk '{print $1}' app.js", "'awk'"),
        ("ls; npm test", "'npm'"),
        ("ls && node x.js", "'node'"),
        ("ls | sh", "'sh'"),
        ("ls\nnpm test", "'npm'"),
        ("ls \\\n; npm test", "'npm'"),
        ("NODE_ENV=prod ls", "'NODE_ENV=prod'"),
        ("ls $(npm test)", "command substitution"),
        ("ls `npm test`", "command substitution"),
        ('grep "$(npm test)" app.js', "command substitution"),
        ("cat <(npm test)", "subshell or process substitution"),
        ("(npm test)", "subshell or process substitution"),
        ("ls $HOME", "unquoted $ expansion"),
        ("find . {-exec,rm,x}", "unquoted {"),
        ("ls &", "background command"),
        ("cat app.js > copy.js", "writes outside .audit/"),
        ("cat app.js > .audit/../copy.js", "writes outside .audit/"),
        ("cat app.js >> /tmp/x", "writes outside .audit/"),
        ("ls &> out.txt", "writes outside .audit/"),
        ('ls > "$HOME/x"', "can't tell where"),
        ("ls > .audit/*", "can't tell where"),
        ("ls >& out.txt", "may only name a file descriptor"),
        ("cat << EOF", "'<<' isn't allowed"),
        ("ls >", "needs a target"),
        ("grep 'unterminated app.js", "unterminated single quote"),
        ('grep "unterminated app.js', "unterminated double quote"),
        ("find . -name '*.js' -exec rm '{}' ;", "find -exec"),
        ("find . -delete", "find -delete"),
        ("find *", "quote '*'"),
        ("sed -i 's/a/b/' app.js", "only `sed -n`"),
        ("sed -E 's/a/b/' app.js", "only `sed -n`"),
        ("sed -n '1e npm test' app.js", "sed may only print"),
        ("sed -n '1,5w out.txt' app.js", "sed may only print"),
        ("sed -n", "sed may only print"),
        ("sort -o app.js app.js", "sort -o"),
        ("sort --output=app.js app.js", "sort --output"),
        ("rg --pre ./run.sh x", "rg --pre"),
        ("git push origin main", "git push isn't allowed"),
        ("git commit -m x", "git commit"),
        ("git -c core.pager=sh log", "git -c"),
        ("git", "git (no subcommand)"),
        ("git log --output=x.txt", "git log --output=x.txt"),
        ("git show --ext-diff", "git show --ext-diff"),
        (".audit-kit/bin/kit sandbox . prove", "only `kit query`"),
        (".audit-kit/bin/kit", "only `kit query`"),
        ("l* app.js", "'l*'"),
        ('"$CMD" app.js', "'$CMD'"),
    ],
)
def test_other_commands_are_refused(command: str, reason: str, root: Path) -> None:
    with pytest.raises(
        RefusedError,
        match=reason.replace("(", r"\(")
        .replace(")", r"\)")
        .replace("*", r"\*")
        .replace("$", r"\$")
        .replace("{", r"\{"),
    ):
        check_command(command, root, root)


def test_a_redirect_is_judged_from_the_folder_the_command_runs_in(root: Path) -> None:
    check_command("ls > work/x.txt", root, root / ".audit")
    with pytest.raises(RefusedError, match="writes outside"):
        check_command("ls > ../x.txt", root, root / ".audit")


def test_a_redirect_through_a_symlink_is_refused(root: Path) -> None:
    (root / ".audit/out").symlink_to(root)
    with pytest.raises(RefusedError, match="writes outside"):
        check_command("ls > .audit/out/app.js", root, root)


def test_a_refused_command_says_why(root: Path) -> None:
    reason = refusal(bash("npm ci", root), root)
    assert reason == (
        "Refused by the audit kit: 'npm' isn't a read-only command the audit "
        "allows (AGENTS.md rule 2)"
    )


def test_an_allowed_command_is_left_to_the_permissions(root: Path) -> None:
    assert refusal(bash("ls", root), root) is None


def test_a_bash_call_without_a_command_is_refused(root: Path) -> None:
    event = Event(hook_event_name="PreToolUse", tool_name="Bash", tool_input={})
    assert "names no command" in (refusal(event, root) or "")


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_writes_inside_the_audit_folder_pass(tool: str, root: Path) -> None:
    assert (
        refusal(write(tool, str(root / ".audit/01-discovery.md"), root), root) is None
    )
    assert refusal(write(tool, ".audit/work/01-discovery/plan.md", root), root) is None


@pytest.mark.parametrize(
    "path",
    [
        "app.js",
        "../elsewhere.md",
        ".audit/../app.js",
        ".claude/settings.json",
        "/etc/hosts",
    ],
)
def test_writes_outside_the_audit_folder_are_refused(path: str, root: Path) -> None:
    reason = refusal(write("Write", path, root), root)
    assert reason is not None
    assert "outside .audit/ (AGENTS.md rule 1)" in reason


def test_a_write_through_a_symlink_is_refused(root: Path) -> None:
    (root / ".audit/out").symlink_to(root)
    assert refusal(write("Edit", ".audit/out/app.js", root), root) is not None


def test_a_notebook_edit_is_checked_by_its_own_path_field(root: Path) -> None:
    event = write("NotebookEdit", "analysis.ipynb", root, key="notebook_path")
    assert "outside .audit/" in (refusal(event, root) or "")


def test_a_write_that_names_no_file_is_refused(root: Path) -> None:
    event = Event(hook_event_name="PreToolUse", tool_name="Write", tool_input={})
    assert "names no file" in (refusal(event, root) or "")


def test_an_agent_cannot_change_the_policy(root: Path) -> None:
    reason = refusal(write("Edit", ".audit/policy.yaml", root), root)
    assert reason is not None
    assert "only the tech lead changes .audit/policy.yaml" in reason


@pytest.mark.parametrize("tool", ["Read", "Grep", "WebFetch", "Agent"])
def test_other_tools_are_left_to_the_permissions(tool: str, root: Path) -> None:
    event = Event(hook_event_name="PreToolUse", tool_name=tool, tool_input={"x": 1})
    assert refusal(event, root) is None


def test_other_events_are_allowed(root: Path) -> None:
    assert refusal(Event(hook_event_name="Stop"), root) is None


def test_an_agent_with_no_output_is_sent_back(root: Path) -> None:
    reason = refusal(stop("audit-security", root), root)
    assert reason is not None
    assert "haven't written your output file (.audit/04-*.md)" in reason


def test_an_agent_with_a_failing_output_is_sent_back_with_the_failures(
    root: Path,
) -> None:
    (root / ".audit/04-security.md").write_text(
        HEADER.format(status="complete") + FINDING.replace("app.js:2", "missing.js:9")
    )
    reason = refusal(stop("audit-security", root), root)
    assert reason is not None
    assert "check(s) fail on your output" in reason
    assert "04-security.md: locations not found" in reason


def test_another_agents_failures_are_not_sent_to_this_agent(root: Path) -> None:
    (root / ".audit/03-engineering.md").write_text("no header\n")
    (root / ".audit/04-security.md").write_text(
        HEADER.format(status="complete") + FINDING + "\n## Limitations\nNone.\n"
    )
    reason = refusal(stop("audit-security", root), root)
    assert "03-engineering.md" not in (reason or "")


def test_an_agent_is_sent_back_only_once(root: Path) -> None:
    assert refusal(stop("audit-security", root, active=True), root) is None


def test_a_pass_that_hands_over_is_not_judged(root: Path) -> None:
    (root / ".audit/04-security.md").write_text(HEADER.format(status="in-progress"))
    assert refusal(stop("audit-security", root), root) is None


def test_the_verifier_is_sent_back_for_a_high_finding_without_a_verdict(
    root: Path,
) -> None:
    (root / ".audit/04-security.md").write_text(
        HEADER.format(status="complete") + FINDING.replace("low", "high")
    )
    (root / ".audit/06-verification.md").write_text(HEADER.format(status="complete"))
    reason = refusal(stop("audit-verifier", root), root)
    assert reason is not None
    assert "OUT-V1" in reason


@pytest.mark.parametrize("agent", ["Explore", "general-purpose", ""])
def test_agents_the_kit_does_not_own_finish_freely(agent: str, root: Path) -> None:
    assert refusal(stop(agent, root), root) is None


def test_every_adapter_agent_has_a_stage_and_a_stop_hook() -> None:
    agents = {p.stem for p in (ADAPTER / "agents").glob("*.md")}
    settings = json.loads((ADAPTER / "settings.audit.example.json").read_text())
    (stop_hook,) = settings["hooks"]["SubagentStop"]
    assert set(guard.STAGES) == agents
    assert set(stop_hook["matcher"].split("|")) == agents


def test_the_example_settings_send_tool_calls_to_the_hook() -> None:
    settings = json.loads((ADAPTER / "settings.audit.example.json").read_text())
    (tool_hook,) = settings["hooks"]["PreToolUse"]
    assert set(tool_hook["matcher"].split("|")) == guard.WRITE_TOOLS | {"Bash"}
    assert tool_hook["hooks"][0]["command"].endswith("/.audit-kit/bin/kit hook")


def run_hook(payload: str, monkeypatch: pytest.MonkeyPatch, root: Path) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return cli.main(["hook"])


def test_the_hook_command_exits_2_with_the_reason_on_stderr(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = bash("npm ci", root / "lib").model_dump_json()
    assert run_hook(payload, monkeypatch, root) == cli.EXIT_INVALID
    captured = capsys.readouterr()
    assert "'npm' isn't a read-only command" in captured.err
    assert captured.out == ""


def test_the_hook_command_is_silent_when_it_allows(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        run_hook(bash("ls", root).model_dump_json(), monkeypatch, root) == cli.EXIT_OK
    )
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_the_hook_command_uses_the_project_folder_not_the_current_one(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "lib/.audit").mkdir(parents=True)
    payload = write("Write", ".audit/x.md", root / "lib").model_dump_json()
    assert run_hook(payload, monkeypatch, root) == cli.EXIT_INVALID


@pytest.mark.parametrize("payload", ["", "not json", "[]", '{"tool_name": "Bash"}'])
def test_the_hook_command_refuses_input_it_cannot_read(
    payload: str,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_hook(payload, monkeypatch, root) == cli.EXIT_INVALID
    assert "isn't one the kit can read" in capsys.readouterr().err


def test_the_hook_command_refuses_when_the_check_itself_fails(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(guard, "refusal", boom)
    assert (
        run_hook(bash("ls", root).model_dump_json(), monkeypatch, root)
        == cli.EXIT_INVALID
    )
    assert "kit hook: RuntimeError: unexpected" in capsys.readouterr().err
