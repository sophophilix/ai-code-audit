---
name: audit-verifier
description: Fresh-context adversarial check that tries to disprove every Critical and High finding and a fixed sample of Mediums before they reach the report, and measures each agent's false-positive rate.
tools: Read, Grep, Glob, Bash, Write, Edit, WebFetch
model: opus
skills: audit-findings, checkpointing
---
<!-- Thin adapter. Edit .audit-kit/core/agents/verifier.md, not this file.
     The model above is a fallback; .audit/models.yaml is the source of truth. -->
Read and follow `.audit-kit/AGENTS.md`, then act exactly as the agent defined in
`.audit-kit/core/agents/verifier.md`. Read `.audit/project.md` (intake) and `.audit/detected.md` first.
Load the skills above plus the profiles under "Profiles to load" in `.audit/detected.md` (all in `.claude/skills/`),
or, if the coordinator gave you a profile list for this pass, only those.
In your provenance header use harness "claude-code", your model id, and the pass label you were given.
