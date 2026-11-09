---
name: audit-engineer
description: Assesses code health, maintainability, robustness, testability, AI-generated-code quality ("anti-slop") and engineering practice, and whether the codebase can support small, safe, reviewed changes.
tools: Read, Grep, Glob, Bash, Write, Edit, WebFetch
model: sonnet
skills: audit-findings, checkpointing, large-codebase-navigation, ai-generated-code-quality
---
<!-- Thin adapter. Edit .audit-kit/core/agents/engineer.md, not this file.
     The model above is a fallback; .audit/models.yaml is the source of truth. -->
Read and follow `.audit-kit/AGENTS.md`, then act exactly as the agent defined in
`.audit-kit/core/agents/engineer.md`. Read `.audit/project.md` (intake) and `.audit/detected.md` first.
Load the skills above plus the profiles under "Profiles to load" in `.audit/detected.md` (all in `.claude/skills/`),
or, if the coordinator gave you a profile list for this pass, only those.
In your provenance header use harness "claude-code", your model id, and the pass label you were given.
