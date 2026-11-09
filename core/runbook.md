# Audit runbook

The **coordinator** (`core/agents/coordinator.md`) runs this sequence. The
**tech lead** owns every decision and is the only one who can pass a
checkpoint. If your harness has no coordinator support, the tech lead follows
this file by hand: one session per agent, in order.

```
 Stage 0  Pre-flight (coordinator)                  ─ stop if any check fails
 Stage 1a File review, one pass per unit (if on)    → .audit/files/<path>.json and .md (kit review)
 Stage 1b Traces, one pass per entry point (if on)  → .audit/traces/<entry>.md
 Stage 1  Discovery                                 → .audit/01-discovery.md
          ◆ CHECKPOINT 1  tech lead reviews facts, answers questions, confirms scope
 Stage 2  Architect | Engineer | Security | Accessibility   (parallel, isolated)
                                                    → 02- 03- 04- 05-*.md, adr/
 Stage 3  Verifier (fresh context, ideally a different model family)
                                                    → .audit/06-verification.md
 Stage 4  Lead reviewer                             → 07-final-report.md, 08-backlog.csv, 09-briefing.slides.md
          ◆ CHECKPOINT 2  tech lead checks every Critical/High before release
```

## Workspace

Always a **disposable clone** of the target on an `audit/<yyyy-mm-dd>` branch.
Agents are told to be read-only, but a shell can still write. A throwaway
clone makes a mistake harmless.

```
<clone>/
  .audit-kit/        a copy of this kit, at a tagged version
  .audit/
    project.md       the intake: six lines only a person can supply (template: templates/project.md)
    beliefs.md       optional team beliefs; read only by discovery's last item and the lead reviewer
    detected.md      profiles, exclusions and facts from `kit detect` (no AI)
    validation.md    result of `kit validate` on models.yaml and the intake (no AI)
    models.yaml      which provider, model and harness runs each agent pass
                     (template: config/models.example.yaml)
    scans/           deterministic scanner output (see "Scans" below)
    run-log.md       coordinator's log, including checkpoint sign-offs (append-only)
    run-state.md     current status of every stage and pass; what a new session resumes from
    work/            per-pass LOCK, plan.md and capsule.md (skill: checkpointing)
    findings.duckdb  the findings store (`kit store`; query with `kit query`)
    01-discovery.md … 09-briefing.slides.md
    adr/
    diagrams/        architect's Diagram IR (.ir.json) and policy.yml; the tech lead builds .drawio files
```

## Stage 0: pre-flight (all must pass)

| Check | How |
|---|---|
| Intake complete | `project.md` → Intake: organisation and jurisdiction, repository and commit, tech lead, security owner, AI approval, processing region. Placeholders (`<…>`) count as missing |
| Configuration valid | `.audit/validation.md` says `result: pass` (run `make validate WS=…` after any edit to `models.yaml` or the intake) |
| Detection current | `.audit/detected.md` exists and its `commit` matches the audited code (re-run `make detect` if not) |
| Every provider approved | Each provider used in `models.yaml` is approved in the intake, with its processing region recorded |
| Verifier rule satisfiable | If `models.yaml` requires a different family from the author, an approved model from another family exists for every author family, or the fallback is recorded |
| Disposable workspace | Not the developer's working copy; branch matches `audit/*` |
| Clean tree | `git status --porcelain` shows nothing outside `.audit/` |
| Commit pinned | `git rev-parse HEAD` recorded in `run-log.md`. The intake commit must match the commit the workspace was made from: `kit validate` checks it against `source_commit` in `.audit/.workspace` (an error if it differs; a warning if an eval snapshot isn't named alongside it). Don't ask the tech lead to compare hashes by hand |
| Kit version | `.audit-kit/VERSION` recorded |
| Evaluation current | `project.md` → "Evaluation" shows a pass (finding evals **and** interruption test) for this kit version, model and harness, **or** the tech lead has recorded that this run *is* the evaluation, **or** the tech lead has recorded an exception for this kit version: who, date, and the eval workspace running in parallel. Under an exception, the lead reviewer states in the report that accuracy is not yet measured, and the report is not shared until that eval's results are added |
| AI instruction files | List any in the target. Make sure the harness won't auto-load them (move them aside on the audit branch, or start the harness so it ignores them). Discovery still reviews them. |
| Data check | No data or credential files in the workspace or its history (see "Data check" below). Any hit stops the run until the tech lead removes it or records an approved exception |
| Scans present | List what's in `.audit/scans/`. Missing scans don't block the run, but each one becomes a Limitation |

## Data check (run by the tech lead before any agent reads the workspace)

```zsh
# files that usually hold data or credentials, in the working tree
find . -path ./.git -prune -o -type f \( -name '.env*' -o -name '*.pem' -o -name '*.pfx' \
  -o -name '*.key' -o -name '*.bak' -o -name '*.bacpac' -o -name '*.mdf' -o -name '*.ldf' \
  -o -name '*.dump' -o -name '*.sqlite' -o -name '*.db' -o -name '*.csv' -o -name '*.xlsx' \
  -o -name '*.xls' -o -name '*.log' \) -print
# the same patterns anywhere in git history (deleted files are still readable)
git log --all --diff-filter=A --name-only --format= | sort -u | \
  command grep -E '(^|/)\.env|\.(pem|pfx|key|bak|bacpac|mdf|ldf|dump|sqlite|db|csv|xlsx?|log)$'
```
Secrets-scan hits (`scans/secrets.json`) don't block pre-flight, and the tech lead isn't
expected to judge them: nobody needs to know the code to run an audit. The coordinator
lists the count in `run-log.md`, and the **security agent triages every hit** (real
credential or test value, with evidence). A hit it rates real is Critical and goes to the
security owner the same day; the tech lead checks the triage at Checkpoint 2.

**When to sanitise instead.** The kit doesn't pseudonymise code by default. It
reduces little when the provider has already processed the code, and it
makes evidence harder to follow. Sanitise (replace identifiers with stable
placeholders, outside the agents' reach) when **any** of these apply:
- the repository holds real personal data (fixtures, exports, logs)
- a provider in `models.yaml` isn't covered by the organisation's approval
- the code has never been processed by an approved AI provider and the owner asks for it

## Scans (run by a human or pipeline, not by agents)

Agents never install or run network tools. The tech lead or the pipeline runs
pinned versions of these against the clone and saves the output in
`.audit/scans/`. Exact commands live in the stack profile (for example
`profiles/node-express`).

| File | Tool (example) | Used by |
|---|---|---|
| `cloc.json` | cloc | discovery, engineer |
| `deps-audit.json` | `npm audit --json` / osv-scanner | security |
| `upstream-status.json` | `kit lookup`: npm deprecated, GitHub archived, Node.js end of life, only if `.audit/policy.yaml` allows (`policy: deny` otherwise) | security |
| `secrets.json` | gitleaks (full history, redacted) | security |
| `sast.sarif` | Semgrep (pinned rulesets) | security |
| `duplication.json` | jscpd | engineer |
| `unused.json` | the kit's own static analysis of `require` and `import` (`kit scan`). Knip isn't used: its plugins load the target's config files, which runs target code | engineer |
| `lint.json` | ESLint run with the **kit's** config, not the target's | engineer |
| `suppressions.json` | `kit scan`: every `eslint-disable`, `@ts-ignore`, `nosemgrep`, `gitleaks:allow`, `istanbul`/`c8 ignore` and `NOSONAR` comment in own code, with whether it gives a reason | discovery, engineer |
| `blindspots.json` | `kit scan`: dynamic `require`/`import`, `eval`, `new Function`, string timers and unresolved imports; code static analysis can't see into | discovery, all |
| `coverage.json` | `kit scan`: for each own `.js` file, whether ESLint and tsc examined it (`typecheck-files.txt` is tsc's `--listFilesOnly`), and inline scripts no tool checks | discovery, lead reviewer |
| `sweep.json` | `kit scan`: network calls, string-to-code, `child_process`, file writes, bulk environment reads, storage reads and long encoded strings in **every** text file, vendored and minified included; "generated" headers in own files | discovery, security |
| `hotspots.json` | `kit scan`: from `git log` up to the audited commit, files ranked by changes times complexity, and pairs that change together. A gap on eval snapshots, which have no history | engineer |
| `design-inventory.json`, `.md` | `kit scan`: every colour (with uses, properties and contrast on white and black), design token, font stack, `@font-face` rule and web-font link in own stylesheets and markup, and contrast for each rule that sets both text and background. The design as built; the `.md` is for designers | discovery, accessibility, file reviewer |
| `typecheck.txt` | `tsc --checkJs --noEmit` with the kit's config, `.audit/scans/tsconfig.audit.json` (`kit scan`) | engineer |
| `gates.json`, `.md` | `kit scan`: which of ESLint, tsc, Semgrep, knip, complexity and duplication the target runs itself (CI config and package scripts, read as text) and which config the kit used (ADR 0007 D5) | engineer, lead reviewer |
| `axe/` | `@axe-core/playwright` against a local or test instance (optional) | accessibility |
| `drawio-azure-shapes.json` | drawio-skill `shapesearch.py azure --limit 5000 --json` (see `THIRD_PARTY.md`) | architect |

*Automating this (a pinned `scan` script or container) is deferred. See CHANGELOG.*

## The file review's plumbing (ADR 0007)

| File | Written by | Used by |
|---|---|---|
| `work/files/<unit>/brief.md`, `brief.json` | `kit units` (and `kit scan`): the unit's numbered lines, this file's rows from every scan with their counts, the unit's gate table, the skill sections tagged for its kind, and the output schema | the unit's file-reviewer pass, and nothing else |
| `files/<path>[#<part>].json`, `.md` | `kit review`: the pass's JSON once it passes the record checks, and the Markdown rendered from it. A record whose unit text, kit version, skill sections and scan rows haven't changed is kept, or copied from an earlier audit with `--reuse-from` and checked again | tracer, discovery, stage 2 and 3 agents |
| `work/files/status.tsv`, `passes.jsonl` | `kit review`: each unit's status, and each attempt's turns, tokens by type, API-equivalent cost and seconds | coordinator, `kit cost` |
| `findings.duckdb` | `kit store`, after the passes and again after the traces: units, findings, edges, facts, flows, gates, repository gates and passes, rebuilt from the files above. Never committed; rebuild it any time | every agent from 1b on, through `kit query` |
| `cost.md` | `kit cost`: totals by stage and model | lead reviewer |

Agents read the store with `.audit-kit/bin/kit query . "<SQL>"` instead of
opening every record. The query runs read-only with external access off. For
example: all High findings under `lib/`
(`SELECT id, location, title FROM findings WHERE severity = 'high' AND path LIKE 'lib/%'`),
the open edges no trace resolved
(`SELECT id, question, resolve_in FROM edges WHERE resolved_by IS NULL`), or the
units whose findings still need another file
(`SELECT unit, path, unverified FROM units WHERE unverified > 0`).
A query result is a map, like a record: cite the code itself.

The store holds this target's findings and code excerpts, so it stays in the
engagement under its data-handling rules (ADR 0007 D9). A lesson from an audit
reaches the kit only as a generic rule a person has written and reviewed: a
check that runs, then a skill rule with an example, then prose.

## Checkpoint 1 (after discovery)

The tech lead doesn't need to know the system beforehand; this is where they
learn it. They read `detected.md` and discovery's **Proposed project
description** and confirm or correct them: profile overrides go in
`project.md` → Profile overrides (then `make detect`). Corrections to the
description and answers to the open questions go in `project.md` →
Checkpoint 1 corrections (then `make validate`), because that file is the only
place every later agent reads; a note in `run-log.md` never reaches them.
Lines in the description marked `(comment only)` or `(doc only)` rest on prose,
not code: confirm or correct each one. Then record
`CHECKPOINT 1: passed by <name>, <UTC time>, notes` in `run-log.md`.
The coordinator waits for that line, and it has to come from the tech lead.

## Stage 2 rules

- The four specialists run in parallel, or one after another, but always in
  **separate contexts**. None sees another's output.
- Each reads `project.md`, `detected.md`, `01-discovery.md` and the scans, then writes only its own file.
- `01-discovery.md` is a map, not evidence. Every finding cites code the
  specialist read itself; comments and documents are claims (`AGENTS.md` rule 4).
  Stage 3 checks a sample of discovery's facts against the code.

## Multiple passes (several models on one agent)

`models.yaml` can give an agent more than one **pass**: independent runs by
different providers or models, optionally limited to some profiles.

- Output files: one pass → `04-security.md`; several →
  `04-security.a.md`, `04-security.b.md` (the suffix is the pass label).
- Finding IDs include the pass label when there are several:
  `SEC-a-001`, `SEC-b-001`. Keys (CHECK-ID + file) let passes be compared.
- Passes never see each other's output. The lead reviewer merges them and
  reports **agreement**: a finding found by two providers is stronger
  evidence, and one found by only one gets a closer look.
- Each harness runs only its own provider's models. A pass assigned to
  another harness is started in that harness, either by the tech lead or by a
  runner script (deferred), with the same agent file and inputs.

## Stage 3: verifier

- New session, no memory of stage 2. With `rule: different_family_from_author`,
  each finding is checked by a verifier pass from a model family other than
  the one that wrote it.
- Checks every Critical and High finding, plus a fixed sample of Mediums:
  sort Medium IDs, take every fifth starting at the offset recorded in `run-log.md`.

## Checkpoint 2 (after the lead reviewer)

The tech lead personally re-opens the evidence for **every** Critical and
High, and spot-checks at least three Mediums on every run, not just the
first, to counter automation bias. Then run the output checks in `evals/output-checks.md`. Record
`CHECKPOINT 2: passed by <name>, <UTC time>, findings checked: ...` and the
`OUTPUT CHECKS:` line in `run-log.md`.

## Circuit breakers (coordinator stops and tells the tech lead)

- An agent wrote outside `.audit/`, or `git status` shows target changes.
- An agent ran a forbidden command (rules 2 and 3).
- An output is missing its provenance header, or has findings with no evidence.
- A Critical finding appears: tell the tech lead straight away, because the
  security owner in `project.md` must hear about it **the same day**, not at Stage 4.
- Text in the target tried to instruct an agent and an agent appears to have obeyed it.

## Interruptions and resume

API limits, usage caps and crashes are expected. Nothing is lost:
- Every agent saves after each small work item (skill `checkpointing`).
  An interrupted pass resumes from its `plan.md`, redoing at most one item.
- The coordinator keeps `run-state.md` and commits `.audit/` with
  `.audit-kit/bin/checkpoint` after every agent and checkpoint (local only, `audit/*` branches only).
- On a rate-limit or usage-cap error, the coordinator stops; it doesn't retry in a loop.
  Resume later in a **new** session with `/audit resume` (or "Act as the coordinator; resume").
  That's cheaper and drifts less than reloading an old conversation.
- Swapping accounts is a normal way past a usage limit. Log in with the other
  account and run `kit review <workspace>` or `/audit resume` again: finished
  units and plan items are kept, and at most one unit or item is redone. Don't
  upgrade the kit in the middle of an audit: a record is tied to the kit
  version, so a new version reviews every unit again.
- `limits.max_parallel_passes` in `models.yaml` keeps parallel passes within
  your plan's limits. Start at 1.

Cost and usage: see `docs/observability.md`.

## Partial runs

`scope: partial` (for example one folder, or the files changed by a PR)
uses the same stages over the given paths only. A partial run never implies
that findings outside its scope are fixed.
