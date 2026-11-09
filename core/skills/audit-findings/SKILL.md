---
name: audit-findings
description: Use whenever writing, rating, verifying or merging an audit finding, or starting an audit output file. Defines the provenance header, finding fields, IDs, stable keys, severity and confidence scales, and evidence rules.
---

# Audit findings

## Overview
Every agent writes findings in one fixed shape, so they can be verified,
merged, compared across runs and imported into a backlog. The field labels
are exact. A future findings database will parse them, so don't rename or
reorder them.

## Provenance header (top of every output file)
```
---
kit_version: 0.9.1
agent: security
pass: a                # label from .audit/models.yaml
provider: <provider>
model_family: <claude | gpt | gemini | ...>
model: <model id>
harness: <tool + version>
repository: <name>
commit: <full sha>
branch: audit/2026-11-06
scope: full            # or: partial – <paths>
status: in-progress      # complete when finished (skill: checkpointing)
sessions: 1             # sessions that worked on this file, including resumes
started_utc: 2026-11-06T01:00Z
finished_utc:           # set when status becomes complete
inputs: [project.md, detected.md, 01-discovery.md, scans/deps-audit.json]
---
```
`started_utc` and `finished_utc` come from `date -u +%Y-%m-%dT%H:%MZ`, run when
the event happens (skill `checkpointing`).

## Finding format
```
### SEC-004 Upload route accepts files of any size
- Key: NODE-UPLOAD-LIMIT:src/routes/upload.js
- Category: security
- Severity: high
- Confidence: high
- Location: src/routes/upload.js:42
- Excerpt: `const upload = multer({ dest: 'tmp/' });`
- Trigger: POST /upload with a 5 GB body fills the app's disk; no limit stops it
- Evidence: `multer({ dest: 'tmp/' })` with no `limits` option (src/routes/upload.js:42); no size limit at the edge in IaC (none in repo)
- Description: What it is and why it matters for THIS system.
- Impact: What happens to users or the organisation. For Critical/High: an exploitation scenario in words.
- Recommendation: The specific fix.
- Sources: https://github.com/expressjs/multer#limits
- Effort: S
- Frameworks: OWASP A04; NSW 3.12; WAF-Security
- Related: ENG-002; cross-ref architect
- Checked-by-author: yes | partially – <what wasn't checked> | no
```

### Field rules
<!-- brief: all -->
| Field | Rule |
|---|---|
| ID | `<PREFIX>-NNN`, numbered in order within your file. Prefixes: DISC, ARC, ENG, SEC, A11Y. If the agent has several passes, include your pass label: `SEC-b-004`. |
| Key | **Required.** `<CHECK-ID>:<primary file>`. CHECK-ID comes from a profile's check catalogue (e.g. `EXP-TRUST-PROXY`). If no check fits, use `X-<kebab-slug>`. The key is how a finding is matched across runs, so it must not depend on title wording. |
| Category | security, privacy, compliance, reliability, maintainability, operations, performance, cost, accessibility, architecture, testing, governance |
| Severity | critical, high, medium, low, info |
| Confidence | high (seen directly, no plausible mitigation), medium (seen, but a mitigation might exist elsewhere), low (inferred). Low confidence on Critical/High → make it an open question instead. |
| Verification | **File records only** (ADR 0007): `verified` when the unit's code and scan rows show everything the finding claims; `unverified` when it depends on another file, a rendered page or a scan that didn't run. A finding with an open edge is `unverified`, and Critical or High must be `verified` (OUT-U4). |
| Location | `file:line` or `file:start-end`. Several → list the primary one; others go in Evidence. |
| Excerpt | **Required when Location has a line.** One to three lines copied verbatim from the cited lines, in backticks. `kit verify` (OUT-F7) compares it with the file, ignoring whitespace. Mask secrets as `****`; mark a cut with `...`. Never paraphrase. |
| Trigger | **Required for Critical and High** (OUT-F9): a concrete input or call sequence and what happens. Without one, rate Medium at most. Security findings give where the untrusted data enters and where it does harm, each with a location. |
| Searched | **Required for a claim that something is absent** ("no rate limiting", "no SIGTERM handler"): `` `<Python regex>` in `<paths>` ``. `kit verify` (OUT-F8) re-runs it over the target and fails on any match, so name every path the claim covers. |
| Packages | **Required when the Recommendation names an npm package**: the names, comma-separated. `kit lookup` checks each exists, isn't deprecated and has had a release in two years, and says when a built-in should be used instead; `kit verify` (OUT-R12) fails on a package that doesn't exist or is deprecated. |
| Evidence | **Never empty.** What you saw, where. Excerpts ≤ 2 lines, secrets masked. |
| Sources | Official documentation. If none: `none – reviewer judgement`. |
| Effort | S (≤ 1 day), M (≤ 1 sprint), L (> 1 sprint) |

### Open questions
```
### SEC-Q-03 Is the storage account reachable only through a private endpoint?
- Owner: platform/cloud admin
- Why it matters: decides whether SEC-007 is High or Low.
```

## Severity
<!-- brief: all -->
| Severity | Criteria | Action |
|---|---|---|
| critical | Exploitable now, or a likely data breach or outage | Fix immediately; notify the security owner the same day |
| high | Exploitable under some conditions, or significant data or compliance exposure | Fix before the next release |
| medium | A real weakness with limited impact | Current or next sprint |
| low | Hygiene, defence in depth | Backlog |
| info | Observation, positive practice, roadmap | None |

## Process
<!-- brief: all -->
1. Before writing a finding, search your file so far for the same Key. One
   finding per root cause. List extra locations in Evidence (up to five).
2. Fill every field. Look up the CHECK-ID in your profiles' catalogue.
3. Rate severity on evidence and impact *for this system*. Rate confidence separately.
4. Map to frameworks where the profile gives a mapping.

## Rationalisations (and rebuttals)
<!-- brief: all -->
| Excuse | Rebuttal |
|---|---|
| "Obviously a problem, no line needed." | Unverifiable means unfixable. Find the line. |
| "Probably fine in production config." | You can't see production. Lower the confidence and ask an open question. |
| "High, to be safe." | Over-rating destroys trust in the whole audit. Rate on evidence. |
| "Same issue in 30 places, so 30 findings." | One root cause, one finding, with example locations. |
| "Generic best practice applies." | Show where *this* code falls short of it, or leave it out. |

## Red flags
<!-- brief: all -->
- Advice not tied to a location in this codebase
- Critical or High with no Impact scenario
- Key built from title words instead of a CHECK-ID
- Confidence `high` where the evidence is a single grep hit you didn't read around

## Verification (before you finish)
<!-- brief: all -->
- [ ] Provenance header complete
- [ ] Every finding has Key, Severity, Confidence, Location and Evidence
- [ ] Every excerpt copied from the file, not retyped; every High has a Trigger;
      every "not found" has a Searched line
- [ ] No duplicated Keys
- [ ] No secrets or personal data, all masked
- [ ] Limitations section present
