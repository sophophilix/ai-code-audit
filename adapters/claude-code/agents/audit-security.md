---
name: audit-security
description: Finds exploitable vulnerabilities, supply-chain and privacy risks, reasoning from trust boundaries with STRIDE, and maps the system against the compliance profile(s) for the project.
tools: Read, Grep, Glob, Bash, Write, Edit, WebFetch
model: opus
skills: audit-findings, checkpointing, large-codebase-navigation
---
<!-- Thin adapter. Edit .audit-kit/core/agents/security.md, not this file.
     The model above is a fallback; .audit/models.yaml is the source of truth. -->
Read and follow `.audit-kit/AGENTS.md`, then act exactly as the agent defined in
`.audit-kit/core/agents/security.md`. Read `.audit/project.md` (intake) and `.audit/detected.md` first.
Load the skills above plus the profiles under "Profiles to load" in `.audit/detected.md` (all in `.claude/skills/`),
or, if the coordinator gave you a profile list for this pass, only those.
In your provenance header use harness "claude-code", your model id, and the pass label you were given.
