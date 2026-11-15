# ADR 0013: Hooks enforce the audit rules on stage agents

> Status: Approved
> Created: 2026-11-15T05:03:39Z
> Last reviewed: 2026-11-15T05:51:26Z
> Next review: after the first audit that runs with the hooks installed

## Review guide

Decision recorded: the harness, not the prompt, enforces three of the kit's
rules on stage agents. This record takes up ADR 0008 D3, which was deferred.

Check these points:

- [ ] The list of allowed shell commands in D2 is wide enough for an agent to
      do its work.
- [ ] Sending an agent back once, not until it passes (D3), is the right limit.
- [ ] The limits under "Risks and open items" are acceptable for a client
      audit.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

Only the file review is locked down by tooling. `kit review` runs it with no
tools at all. The stage agents (discovery, architect, engineer, security,
accessibility, verifier and lead reviewer) have tools, and until now two things
held them to the rules: a permissions list and their prompts.

From 0.21.0, Claude Code hooks call the kit before each tool call and when a
stage agent finishes. The check is Python, with no model involved, so the same
input always gets the same answer.

## Evidence

| Observation | Where |
|---|---|
| Permissions match the start of a command, so they can't follow a pipe, a redirect or a second command | ADR 0008 D3 |
| `make`, `bash`, `sh` and `bun` weren't denied, though rule 2 counts a `Makefile` as code | `adapters/claude-code/settings.audit.example.json` before 0.21.0 |
| The coordinator's gate checks on an agent's output are steps in a prompt | `core/agents/coordinator.md`, "After each agent finishes" |
| A `PreToolUse` hook that exits with code 2 blocks the tool call, and the model receives the hook's stderr | [Claude Code hooks reference](https://code.claude.com/docs/en/hooks), accessed 2026-11-15 |
| Hooks in a settings file also run inside subagents. `SubagentStop` matches on the agent's name, and exit code 2 keeps the subagent running | Same page |
| `stop_hook_active` is true when the agent is already continuing because a hook blocked it | Same page |
| In a scratch folder with the example settings, Claude Code 2.1.311 refused `ls > outside.txt` with the kit's message and ran `ls > .audit/work/list.txt` | One headless run on 2026-11-15 |

## Decision

**D1. Where the hooks run.** They run in the harness, inside the audit
workspace. `kit install` writes them into `.claude/settings.json` from the
adapter's example file. Each hook runs `.audit-kit/bin/kit hook`, which reads
one event on stdin. Exit code 0 allows the event. Exit code 2 refuses it and
gives the reason on stderr. The decisions are in `src/audit_kit/guard.py`.

**D2. Before a tool call.** The hook fires for `Bash`, `Write`, `Edit`,
`MultiEdit` and `NotebookEdit`.

For a shell command, the check reads the whole command line and splits it at
every `;`, `|`, `&&`, `||` and line break. Each part must start with a command
on this list:

| Command | Limit |
|---|---|
| `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `cut`, `uniq`, `tr`, `echo`, `printf`, `pwd`, `date`, `test`, `true`, `basename`, `dirname` | None |
| `find` | No `-exec`, `-ok`, `-delete` or `-fprint` action. Wildcards must be quoted |
| `sed` | Only `sed -n` that prints a line or a range |
| `sort` | No `-o` or `--compress-program` |
| `rg` | No `--pre` |
| `git` | Only `log`, `show`, `blame`, `ls-files`, `rev-parse` and `status`, with no `--output` or `--ext-diff` |
| `.audit-kit/bin/kit` | Only `query` |
| `.audit-kit/bin/checkpoint` | None |

The check refuses shell syntax it can't follow: command substitution, a
subshell, a background command, a here-document, an unquoted `$` expansion, an
unquoted `{` and a variable set in front of a command. A redirect may write
only to `/dev/null` or to a file under `.audit/`.

For a write tool, the file must be under `.audit/`, with symbolic links
followed. An agent can't write `.audit/policy.yaml`, because that file holds
what the tech lead has allowed (`AGENTS.md` rule 11).

**D3. When a stage agent finishes.** A `SubagentStop` hook fires for the seven
stage agents. The check runs `kit verify` and keeps the failures on that
agent's own output. If there are any, or the output file doesn't exist, the
agent is sent back with the list.

The agent is sent back once. Its second attempt to finish passes, and the
coordinator's gate checks then decide. That matches the coordinator's own rule:
send the file back once, then stop. A pass whose header says
`status: in-progress` is handing over, and the check doesn't judge it.

**D4. No hook when the main session stops.** The coordinator is the main
session. It stops at both checkpoints to wait for the tech lead, so a hook
there would block the checkpoints.

**D5. A broken hook refuses.** If the event can't be read, or the check itself
fails, `kit hook` exits with code 2. Any other exit code would let the tool
call through.

**D6. A hook never grants permission.** When the check has no objection it
says nothing, and the permissions list decides as before. The list stays. It
gains `make`, `bash`, `sh`, `zsh`, `bun`, `deno`, `uv` and `pip` under `deny`,
and `.audit-kit/bin/kit query` under `allow`.

**D7. Other harnesses.** Hooks are a Claude Code feature. The `generic` adapter
lists the same checks for a person to apply with their tool's own controls.

## Consequences

- An agent that breaks rule 1 or rule 2 is stopped by a program, and it reads
  the reason.
- The hook is stricter than the old permissions. It refuses `awk`, `xargs`,
  `cd` and here-documents. The `large-codebase-navigation` skill no longer
  tells an agent to use `awk`.
- Every checked tool call starts the kit once. `audit-kit --version` took about
  0.35 seconds on the maintainer's machine. Nobody has measured the cost over a
  whole audit.
- `kit install` keeps an existing `.claude/settings.json` and warns that it
  differs. To get the hooks in an existing workspace, delete that file and run
  `kit install` again, or merge the `hooks` section by hand.
- The hooks are one more setting the evaluation can compare: the same audit
  with and without them.

## Not in this decision

- Allowed documentation domains declared by a pack. The example settings and
  the intake template still list them in one place, and some are specific to a
  stack or a sector.
- A hook on `WebFetch`. The permissions list still decides which domains an
  agent may read.
- Hooks for the headless file review. It has no tools, so there is nothing to
  check.

## Rejected

- **A deny list for shell commands.** It fails open: a command nobody thought
  of gets through. The check allows a short list and refuses the rest.
- **Sending an agent back until `kit verify` passes.** A check the agent can't
  satisfy would hold it until the harness's own limit. ADR 0008 D3 proposed
  this.
- **Letting the tool call through when the hook fails.** A fault in the kit
  would then remove the check without anyone noticing.

## Risks and open items

- **This is not a sandbox.** An allowed program still reads any file the
  account can read, inside or outside the workspace. A disposable clone and a
  container with no network remain the real isolation.
- **A file name in the target can act as an option.** With an unquoted
  wildcard, a file named like an option changes what a program does. The check
  refuses that for `find` only.
- **Nobody has run the `SubagentStop` hook inside Claude Code.** Its decisions
  are tested as functions. The one live run covered the tool-call hook only.
- **The allowed list may be too narrow.** An agent refused a harmless command
  loses a turn. The first audit with the hooks will show how often.
- **An untrusted folder.** In the live run, Claude Code ignored the `allow`
  entries because the scratch folder wasn't trusted, and the hook still ran.
  Nobody has checked how hooks behave across trust settings.

## Review history

| Date (UTC) | Reviewer | Outcome |
|---|---|---|
| 2026-11-15 | Tech lead | Approved in discussion, before the text was written |
| 2026-11-15 | Claude (author) | Written and built in 0.21.0 |
| 2026-11-15 | Tech lead | `approve` |
