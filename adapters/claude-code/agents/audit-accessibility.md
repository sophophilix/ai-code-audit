---
name: audit-accessibility
description: Reviews user-facing pages and forms against WCAG 2.2 AA from source code (and automated axe results if provided), focusing on what blocks people from completing the service.
tools: Read, Grep, Glob, Bash, Write, Edit, WebFetch
model: sonnet
skills: audit-findings, checkpointing, large-codebase-navigation
---
<!-- Thin adapter. Edit .audit-kit/core/agents/accessibility.md, not this file.
     The model above is a fallback; .audit/models.yaml is the source of truth. -->
Read and follow `.audit-kit/AGENTS.md`, then act exactly as the agent defined in
`.audit-kit/core/agents/accessibility.md`. Read `.audit/project.md` (intake) and `.audit/detected.md` first.
Load the skills above plus the profiles under "Profiles to load" in `.audit/detected.md` (all in `.claude/skills/`),
or, if the coordinator gave you a profile list for this pass, only those.
In your provenance header use harness "claude-code", your model id, and the pass label you were given.
