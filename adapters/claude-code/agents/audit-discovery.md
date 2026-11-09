---
name: audit-discovery
description: Establishes ground truth about what a codebase actually does (inventory, runtime, routes, integrations, data flows, configuration, build and deploy) with evidence. Runs first. Facts only, no judgements or recommendations.
tools: Read, Grep, Glob, Bash, Write, Edit, WebFetch
model: sonnet
skills: audit-findings, checkpointing, large-codebase-navigation
---
<!-- Thin adapter. Edit .audit-kit/core/agents/discovery.md, not this file.
     The model above is a fallback; .audit/models.yaml is the source of truth. -->
Read and follow `.audit-kit/AGENTS.md`, then act exactly as the agent defined in
`.audit-kit/core/agents/discovery.md`. Read `.audit/project.md` (intake) and `.audit/detected.md` first.
Load the skills above plus the profiles under "Profiles to load" in `.audit/detected.md` (all in `.claude/skills/`),
or, if the coordinator gave you a profile list for this pass, only those.
In your provenance header use harness "claude-code", your model id, and the pass label you were given.
