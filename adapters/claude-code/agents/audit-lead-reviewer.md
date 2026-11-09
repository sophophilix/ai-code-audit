---
name: audit-lead-reviewer
description: Merges verified findings into one decision-ready report for management and governance committees, finalises proposed ADRs, and produces a backlog that imports into Azure DevOps Boards.
tools: Read, Grep, Glob, Bash, Write, Edit, WebFetch
model: opus
skills: audit-findings, checkpointing, audit-publishing
---
<!-- Thin adapter. Edit .audit-kit/core/agents/lead-reviewer.md, not this file.
     The model above is a fallback; .audit/models.yaml is the source of truth. -->
Read and follow `.audit-kit/AGENTS.md`, then act exactly as the agent defined in
`.audit-kit/core/agents/lead-reviewer.md`. Read `.audit/project.md` (intake) and `.audit/detected.md` first.
Load the skills above plus the profiles under "Profiles to load" in `.audit/detected.md` (all in `.claude/skills/`),
or, if the coordinator gave you a profile list for this pass, only those.
In your provenance header use harness "claude-code", your model id, and the pass label you were given.
