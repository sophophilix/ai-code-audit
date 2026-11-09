---
description: Run (or resume) the agent-audit-kit audit as the coordinator
argument-hint: "[resume] [scope: full | partial <paths>]"
---
<!-- Thin adapter. Edit .audit-kit/core/agents/coordinator.md, not this file.
     Runs in the MAIN session, because Claude Code subagents can't start other subagents. -->
Act as the coordinator defined in `.audit-kit/core/agents/coordinator.md`.
Follow `.audit-kit/AGENTS.md` and `.audit-kit/core/runbook.md`.
Model assignments are in `.audit/models.yaml`. Start Claude passes as the
`audit-<role>` subagents with the assigned model. Hand passes for other
harnesses to the tech lead as ready-to-run prompts.

Always start by reading `.audit/run-state.md`. If it exists, resume (see "Start or resume").

Arguments: $ARGUMENTS
