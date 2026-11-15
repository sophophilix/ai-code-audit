# Claude Code adapter

These are thin wrappers that point Claude Code at the portable kit. Edit the
kit (`core/`, `profiles/`), never the wrappers.

## Install into an audit workspace

Use `make ready WS=<workspace>` (or `bin/kit install <ws>`) from the kit repo.
It does the steps below idempotently. By hand:

From the root of a **disposable clone** of the target, on an `audit/<date>` branch:

```bash
KIT=~/code/github.com/sophophilix/agent-audit-kit
git -C "$KIT" describe --tags --always          # record the kit version you're using
mkdir -p .audit-kit .audit/scans .audit/adr .claude/agents .claude/commands .claude/skills
cp -R "$KIT"/{AGENTS.md,VERSION,core,profiles,evals,templates,config} .audit-kit/
cp "$KIT"/adapters/claude-code/agents/*.md   .claude/agents/
cp "$KIT"/adapters/claude-code/commands/*.md .claude/commands/
cp -R "$KIT"/core/skills/* "$KIT"/profiles/* "$KIT"/profiles/*/skills/* .claude/skills/
cp "$KIT"/templates/project.md        .audit/project.md     # fill in the six-line Intake
uv run --frozen --project "$KIT" audit-kit detect .      # writes .audit/detected.md
cp "$KIT"/config/models.example.yaml  .audit/models.yaml    # then edit it
```
Then review `settings.audit.example.json` and merge it into `.claude/settings.json` by hand.

If the target already has `CLAUDE.md`, `.claude/` or other AI instruction
files, move them aside on the audit branch first (pre-flight lists them).
Claude Code loads them automatically, and they're untrusted.

## Run
- Start Claude Code in the workspace and type `/audit`. The main session
  becomes the coordinator. Claude Code subagents can't start subagents, so
  the coordinator must be the main session, not a subagent.
- Claude passes run as the `audit-<role>` subagents with the model from
  `.audit/models.yaml` (the `model:` in each wrapper is only a fallback).
- Passes for other providers (Codex, Gemini CLI, …) are handed to you as
  ready-to-run prompts.
- Verifier: always a fresh context. A subagent gives that by default.

## Hooks (ADR 0013)
`settings.audit.example.json` also sets two hooks. Both run
`.audit-kit/bin/kit hook`, which is Python with no model involved.
- **Before `Bash`, `Write`, `Edit`, `MultiEdit` and `NotebookEdit`.** The hook
  refuses a shell command that isn't on the read-only list, and a write
  outside `.audit/` or to `.audit/policy.yaml`. It reads the whole command, so
  a pipe, a redirect or a second command doesn't get past it.
- **When an `audit-<role>` subagent finishes.** The hook runs `kit verify` and
  sends the agent back once with the failures on its own output.

A hook never grants permission. When it has no objection, the permissions
above decide. If the hook itself fails, it refuses.

`kit install` keeps a `.claude/settings.json` that already exists. To get the
hooks in an older workspace, delete that file and run `kit install` again.

## Limits to be aware of
- Permission rules and hooks aren't a sandbox: an allowed shell command can still write
  files. Use Claude Code's sandbox mode or a container with no network for
  real isolation. That's why the workspace is disposable.
- `Edit(./.audit/**)` allows writes only under `.audit/`. Other writes prompt
  you. Say no.
