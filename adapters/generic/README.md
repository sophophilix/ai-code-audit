# Using the kit with any agent tool

The kit needs three things from a harness: it must read files, run read-only
shell commands, and load instructions. Everything else is optional.

1. Copy the kit into the workspace as `.audit-kit/` and create `.audit/`
   (see the Claude Code adapter's install steps; skip the `.claude/` parts).
2. Point the tool's project instructions at `.audit-kit/AGENTS.md`
   (e.g. an `AGENTS.md` at the workspace root that says "Follow `.audit-kit/AGENTS.md`").
3. Load skills from `.audit-kit/core/skills/` and the profiles that
   `.audit/detected.md` lists under "Profiles to load". Tools that support the Agent Skills folder format
   can load them directly; otherwise paste the SKILL.md text into the session.
4. For each pass in `.audit/models.yaml`, start a **new session** with that
   pass's model and say:
   "Act as the agent defined in `.audit-kit/core/agents/<role>.md`. Pass label `<x>`.
   Profiles: `<list or 'from detected.md'>`. Write `.audit/<NN>-<role>[.<x>].md`."
5. Restrict permissions with the tool's own controls: read-only on source,
   no package managers, no network except the allowed documentation domains.
   Use the tool's sandbox or a container where it has one.
6. No coordinator support? The tech lead follows `core/runbook.md` by hand.
   The coordinator file is still a useful checklist.
7. Verifier: always a fresh session, from a different model family than the
   author when `models.yaml` says so.

Frontmatter fields `model-tier` and `tools-hint` in agent files are advice.
Map them to your tool's own settings.
