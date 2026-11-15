# ADR 0011: A stack-neutral framework, knowledge packs and measured support

> Status: Approved
> Created: 2026-11-14T15:03:02Z
> Last reviewed: 2026-11-15T05:51:26Z
> Next review: after the first evaluation run on a Python target

## Review guide

Decision requested: change what the kit is. It stops being a code auditor shaped
around one Node.js web application. It becomes a framework that assesses a
system's current state and proposes its future state, loads its knowledge from
packs, and calls a pack supported only after an evaluation has passed.

Check these points:

- [x] The purpose in D1 is the job you want the kit to do for a client.
- [x] The line between the public kit and private packs (D4) protects client
      confidentiality.
- [x] The stopping rule in D7 is one you will keep.
- [x] Nothing in "Dropped from the plan" (D8) is something you still want.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The kit was built to audit one kind of system: a public Node.js and Express web
application hosted on Azure. Its knowledge of that stack sits in the core. The
first Python target produced no file-review units until ADR 0010 added Python in
seven modules. Adding each new stack to the core that way doesn't scale for one
maintainer, and it puts the effort into application-language rules, which
scanners and vendor tools already cover.

This record sets a different shape. The core is a pipeline that knows no stack.
Knowledge comes from packs. The maintainer's own practice knowledge lives in
private packs outside this repository. A claim that the kit supports something
rests on a measured result.

## Evidence

| Observation | Where |
|---|---|
| The first Python audit produced 0 file-review units, and the kit assumed Node.js in seven modules | ADR 0010, Summary |
| JavaScript and front-end review rules total about 620 lines. The Azure pack is 89 lines, and it is a scorecard applied by judgement | `core/skills/javascript-review`, `core/skills/frontend-review`, `profiles/azure-architecture` |
| Bicep and Terraform files are detected but get no rules of their own | `src/audit_kit/detection.py` |
| The evaluation method exists, but nobody has run it for 0.19.0. Seeding supports Node.js only | `evals/README.md`, `src/audit_kit/seeding.py` |
| The human decision on each finding at Checkpoint 2 isn't recorded | `core/runbook.md`; `docs/reviews/industry-ai-code-review-practice-20261114T122013Z.md` |
| The discovery agent's 14 items assume a web application: item 3 is routes, and item 5 is user-facing forms and endpoints | `core/agents/discovery.md` |
| arc42 is a free template that describes a system's architecture in 12 sections, none tied to a stack | [arc42 overview](https://arc42.org/overview), accessed 2026-11-15 |
| Microsoft's Azure Review Checklists repository holds about 20 design review checklists under the MIT licence, including Well-Architected, Landing Zone, AKS and Cost. It offers Azure Resource Graph queries as one way to use them | [Azure/review-checklists](https://github.com/Azure/review-checklists), accessed 2026-11-15 |
| PSRule for Azure publishes rules mapped to the Well-Architected Framework pillars and reads Bicep files directly. It reads Terraform only from plan output | [PSRule for Azure](https://azure.github.io/PSRule.Rules.Azure/about), [Terraform support](https://azure.github.io/PSRule.Rules.Azure/using-terraform/), accessed 2026-11-14 |
| AWS publishes Well-Architected Framework guidance as skills for coding agents | [aws-samples/sample-well-architected-skills-and-steering](https://github.com/aws-samples/sample-well-architected-skills-and-steering), accessed 2026-11-14 |

The last two rows came from web search summaries on 2026-11-14. Nobody has
checked the rule counts or the Terraform limit against the tools themselves.
The Azure Review Checklists row comes from the repository's front page. Nobody
has inspected the format of a checklist item.

## Decision

**D1. Purpose.** The kit helps the person accountable for a system answer two
questions with evidence: what is the system's current state, and what should
change. The assessment covers how the project is structured and built, how
configuration is loaded, where state lives, how the system is hosted, its data
store, its network and identity design, how it is deployed, and the health of
its code. Those questions follow published practice: the Azure Well-Architected
Framework, the Twelve-Factor App and production readiness review.

**D2. The core is a stack-neutral pipeline.** The core holds the pipeline, the
rules in `AGENTS.md`, the evidence discipline, the findings store and the
evaluation harness. Knowledge of a language, a platform, a concern or a sector
belongs in a pack. ADR 0012 defines the pack contract.

**D3. Four pack types.**

| Type | Holds | Examples |
|---|---|---|
| `stack` | A language or framework | Node.js and Express, Python |
| `platform` | A cloud or hosting platform | Azure |
| `concern` | A cross-cutting quality | Accessibility, AI governance |
| `sector` | A regulated sector or jurisdiction | Local government |

**D4. Public framework, private practice knowledge.** This repository holds the
framework and packs built from published sources. A person's own patterns from
client work live in private packs outside this repository, in the same format.
A private pack records the general lesson. It never records a client's name,
systems, decisions or data, even in a private repository.

**D5. Tools first, the model second.** A check runs at the most deterministic
level that can decide it: a fact or metric, then a scanner rule, then a
structural query, then a model applying a written rubric. A pack wraps an
existing maintained rule set before it writes its own. For Azure infrastructure
code, that means reading the output of PSRule for Azure as a scan. Bicep comes
first. PSRule reads Terraform only from plan output, and producing a plan runs
the target's tooling (`AGENTS.md` rule 2).

**D6. Support is measured.** A pack is `supported` when the kit has passed the
evaluation in `evals/README.md` on a target for that pack. Until then it is
`experimental`, and the audit says so at the start. Three sources of truth feed
the measurement:

1. Seeded issues: defects planted in a copy of a codebase, with the answer key
   kept outside the workspace.
2. Known real issues from an earlier review of a real system.
3. The tech lead's decision on each finding at Checkpoint 2: accepted, rejected
   or downgraded.

A change to the kit is accepted only when the measured results don't get worse.

**D7. Order of work, and when to stop.**

1. The pack contract (ADR 0012).
2. The Python pack rebuilt to the contract, as the reference. Python comes
   before Node.js because the next real audit is a Python application.
3. Private pack loading.
4. A baseline evaluation on a Python target, with hand-planted issues.
5. The Azure pack, deepened by wrapping PSRule for Azure, with a seeded
   infrastructure target. Azure Review Checklists is a second source for the
   pack's checks.
6. A capture skill that turns a raw note into a pattern entry.

Steps 1 to 3 are built in 0.20.0. Work stops after step 4 until the kit has been
used on a real audit. No new pack type, agent or stage is added before then.

**D8. Dropped from the plan.**

- ISO/IEC 25010 as the backbone of the check catalogue. It may return as a tag
  on a check.
- A research agent that fills gaps in the catalogue. There is no gap data to
  give it yet.
- Sector packs written ahead of a real engagement in that sector.
- A judgement on whether the system handles its business domain correctly. The
  kit records the facts and asks the owner.
- Supporting each new language by adding rules to the core.

## Consequences

- The kit's weight moves from application-language rules to architecture,
  infrastructure code, pipelines and identity. Language defects come mainly
  from scanners.
- The core still holds stack-specific code. Each item below is follow-up work,
  and none of it is done in 0.20.0:
  - unit boundaries and file extensions (`units.py`)
  - brief kinds chosen by extension (`skill_sections.py`)
  - gates per ecosystem (`gates.py`) and scanner choice (`scans.py`)
  - Node.js-only seeding (`seeding.py`)
  - the rules that propose a pack from the files (`detection.py`)
  - the `javascript-review` and `frontend-review` core skills
  - the discovery agent's item list (`core/agents/discovery.md`). The arc42
    sections are the reference for a stack-neutral list. Items such as routes
    move into packs.
- Hooks enforce rules 1 and 2 and the output checks on the stage agents from
  0.21.0 (ADR 0013). That enforces existing rules. It isn't a new pack, agent
  or stage, so the stopping rule in D7 still holds.
- A pack has no `supported` or `experimental` status field yet. D6 is a policy
  until an evaluation result exists to record.
- Checkpoint 2 decisions are still not stored. D6 needs that before the third
  source of truth exists.

## Rejected

- **An infrastructure-only standard, with the auditor dropped.** The maintainer
  reviews whole systems: code, hosting and delivery together. The auditor is the
  part that reads the system.
- **A workflow language or engine for the pipeline.** The harness already runs
  subagents, skills and hooks. Writing the pipeline in one explicit place is
  worth doing. A new language is not.
- **A vector store for pack knowledge.** A few hundred entries fit in files
  that are loaded by rule, and that keeps loading deterministic. Retrieval is
  reconsidered when a pack no longer fits a model's context.
- **More languages in the core.** That is the approach ADR 0010 took, and it
  cost seven modules for one language.

## Risks and open items

- The maintainer is one person. The full order in D7 is months of work, so the
  stopping rule matters more than the plan.
- Private packs depend on a capture habit that doesn't exist yet. Without step
  6, they stay empty.
- The evaluation costs model usage: three runs for each configuration. The
  file review of one 30,000-line target cost about USD 34 at API prices.
- Planted issues only measure what someone thought to plant. Results on a
  seeded target can rise while results on real systems don't. A second target
  that is never tuned against would show that. It doesn't exist yet.

## Review history

| Date (UTC) | Reviewer | Outcome |
|---|---|---|
| 2026-11-14 | Claude (author) | Proposed, from a design discussion with the tech lead |
| 2026-11-15 | Claude (author) | Added arc42 as the reference for a stack-neutral discovery list, and Azure Review Checklists as a source for the Azure pack, at the tech lead's request |
| 2026-11-15 | Claude (author) | Added the pointer to ADR 0013 under Consequences |
| 2026-11-15 | Tech lead | `approve` |
