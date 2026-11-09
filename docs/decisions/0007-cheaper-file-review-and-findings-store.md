# ADR 0007: A cheaper file review, and a findings store you can query

> Status: Approved
> Created: 2026-11-08T02:40:16Z
> Last reviewed: 2026-11-08T03:22:57Z
> Next review: Not scheduled

## Review guide

Decision requested: change how a file-review pass gets its input and returns its
output, so a unit costs about a tenth of today's tokens; keep every finding in a
DuckDB file that later stages query; and reuse a unit's record when nothing it
depends on has changed. ADR 0002's file-by-file review and ADR 0004's checks stay
as they are; this changes the plumbing around them.

Check these points:

- [ ] A unit pass reads one prepared brief and nothing else (D1), and that is enough.
- [ ] Returning JSON that Python checks and renders (D3) is worth losing free-form records.
- [ ] The findings store (D6) and reuse by content hash (D7) are worth one new dependency.
- [ ] Nothing here lets a target's findings leave the engagement (D9).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The pilot eval of kit 0.16.0 measured the file review for the first time:

| Measure | Value |
|---|---|
| Units | 157 |
| Tokens per pass, average | 224k (Sonnet), 382k (Haiku) |
| Tokens for the first 120 units | 121.5M, mostly cached context sent again on each turn |
| Cost, at API prices | $37.07 for those 120 units (Claude Code's estimate; a plan is billed differently) |
| Rules and skills each pass loads | about 84 KB, including both review skills whatever the unit's kind |
| `scans/lint.json` | 1.3 MB; several records say the agent couldn't read its file's rows |
| Records failing `kit verify` on first write | 49 of 157 (31%): 41 of 94 Haiku units (44%), 8 of 63 Sonnet units (13%) |
| Cost per pass, at API prices | $0.05 (Haiku, units of 100 lines or fewer), $0.49 (Sonnet) |

A pass's tokens are its turns multiplied by its context. The code under review is
a small part of either. Most turns go on finding things: the lock and plan files,
searching large scan files, and editing the record several times. Running more
passes in parallel doesn't help, because the plan's usage limit is the constraint.

The fix is to do the finding in Python, once, before the pass starts, and to have
the pass return data that Python checks, rather than a document it edits.

## Decision

### D1. One brief per unit, built by the kit

`kit units` writes `.audit/work/files/<unit>/brief.md` for every unit. It holds:

- the unit's lines, numbered;
- this file's rows from every scan: ESLint, `tsc`, Semgrep, sweep, duplication,
  suppressions, knip, secrets, and the design inventory's pairs for the file;
- the skill sections for the unit's kind (D2);
- the output schema (D3).

The pass reads the brief and nothing else. Open edges still go to the tracers
(ADR 0002 D6), so a unit pass never needs another file. Target: three turns or
fewer for a unit under 600 lines.

### D2. Skills loaded by unit kind

The javascript-review and frontend-review catalogues are tagged by the unit kinds
they apply to (file, inline script, stylesheet, inline style, markup). The brief
includes only the matching sections, plus `audit-findings`' field rules. Check IDs
don't change, so keys stay stable across versions.

### D3. JSON out; Python checks and renders

The pass returns one JSON object that matches `config/file-record.schema.json`:
facts, findings, open edges and limitations. The kit then:

1. validates it against the schema;
2. runs the record checks from ADR 0004 (OUT-F1, F3, F7, F8, U1 to U3);
3. on a failure, sends it back once with the failed checks listed, which closes
   gap #9, the repair step done by hand in this eval;
4. writes `.audit/files/<path>.json` and renders the Markdown record from it.

Evidence is built from Location and Excerpt when the pass gives no more, so a
finding can't miss it. Free text stays in Description, Trigger and Impact.

### D4. No checkpointing inside a unit pass

A unit pass is short and either produces a valid JSON object or doesn't. If it
fails, the kit runs it again. The lock, plan and capsule files stay for the stage
agents, whose passes run for minutes and can be interrupted.

### D5. Gate tables, built by Python

Each record gets a gate table for its file: ESLint, `tsc --checkJs`, Semgrep,
knip, complexity and duplication. Each is `pass`, `fail`, `unavailable` or
`not_applicable`, with the evidence. A tool that didn't run is never a pass.

The final report gets one table for the repository. It shows which of those gates
the target runs itself (from its CI config and package scripts, read as text) and
which config the kit used. The kit's ESLint config is a baseline. The target's own
config is code under rule 2, so it runs only in the sandbox (ADR 0005).

### D6. A findings store

`kit store` loads every record's JSON, the traces, the gate tables and the pass
records into `.audit/findings.duckdb`, with one table each for units, findings,
edges, gates and passes. One process writes it, after the passes finish. Parallel
passes only write their own JSON files.

The JSON files are the source of truth, and the store can always be rebuilt from
them, so output stays deterministic. Stage 1 to 4 agents run `kit query "<SQL>"`,
read-only, in place of reading 157 records: for example, all High findings under
`lib/`, or the open edges that no trace resolved. `kit query` joins the read-only
commands listed in `AGENTS.md` rule 2.

### D7. Reuse a record when nothing it depends on changed

Each record stores three hashes: the unit's text, the kit version, and the skill
sections in its brief. On a later audit, a unit with all three unchanged keeps its
record, and `kit verify` checks its excerpts again against the new commit. The
report lists reused records separately. A re-audit then costs roughly what
changed, not the whole codebase.

### D8. Cost and time recorded per pass

From `claude -p --output-format json`, the kit records each pass's turns, tokens
by type (input, output, cache read, cache write), cost and seconds in the passes
table. `kit cost` prints totals by stage and model, and the final report includes
them, labelled as API-equivalent cost. The session and weekly percentages shown
by `/status` aren't used: there's no supported way to read them from a script.
OpenTelemetry stays optional, as `docs/observability.md` describes.

### D9. Two kinds of knowledge, kept apart

| Kind | Contents | Where it goes |
|---|---|---|
| Kit and rule pack | Generic rules, checks, Semgrep rules, skills, known false-positive patterns | Published with the kit, versioned and tagged |
| Findings store | One target's findings, facts and code excerpts | Stays in the engagement, under its data-handling rules |

A lesson from an audit is made portable in this order of preference: a check that
runs (a `kit verify` check, a Semgrep rule, a test), then a skill rule with an
example, then prose. Nothing moves from a findings store into the rule pack except
as a generic rule a person has written and reviewed.

## Consequences

- A unit pass should need about 25k to 40k tokens rather than 224k to 382k.
  The next eval measures this against the 0.16.0 baseline above.
- Records are consistent in shape, so most first-write failures (31% today)
  become schema errors caught before anything is written.
- Later stages read query results, not every record, which also cuts their tokens.
- Agents can't explore other scan files from a unit pass. If the brief is wrong
  or incomplete, the pass can't make up for it, so the brief builder needs tests.
- One new runtime dependency, the `duckdb` Python package, pinned to a release at
  least two weeks old.

## Rejected options

| Option | Why not |
|---|---|
| More passes in parallel | The plan's usage limit is the constraint; more parallel passes reach it sooner. |
| One session reviewing many files | Context from one file leaks into the next, and ADR 0002 chose per-file isolation for that reason. |
| A vector database, or embeddings now | Findings stand on exact evidence. Similarity search answers "probably related", and Anthropic offers no embedding model, so it would add a third party. DuckDB's `vss` extension is there if a measured need appears, such as near-duplicates that keys miss. |
| Agents writing to DuckDB directly | DuckDB allows one writer, and writes must go through the kit's workspace. |
| The Messages API with the Batches API | Half the price and shared prompt caching, but it needs API billing. Kept as an option for councils running on Bedrock or Foundry, not the default. |

## Risks and open items

- **The brief leaves out a scan row.** Mitigation: tests that build a brief from
  fixture scans and check every row for the file is present, and a count in the
  brief that `kit verify` compares.
- **The schema loses nuance.** Mitigation: the free-text fields stay; the schema
  constrains structure, not wording.
- **A reused record carries a wrong finding forward.** Mitigation: excerpts are
  checked again on every audit, and reused records are listed as reused.
- **Recall drops because passes read less.** The next eval scores seeded issues
  against the 0.16.0 run. If recall falls, D1's brief grows before D1 is dropped.
- **Which model reviews short units.** Haiku is ten times cheaper per pass but
  failed the checks three times as often in 0.16.0. The next eval, with D1 and D3
  in place, compares the two on the same units, including seeded issues found. If
  Haiku still falls short, Sonnet reviews every unit.
- **Checked fixes** (a patch for a High finding, applied and tested in the
  sandbox) are out of scope here. They go in a separate ADR.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-08T02:40:16Z | Drafted | From the 0.16.0 pilot eval's measurements, while the eval runs. |
| 2026-11-08T02:43:32Z | Approved | Approved by the tech lead. Added the Haiku and Sonnet comparison to the evidence and risks. |
| 2026-11-08T03:22:57Z | Built | Built in 0.17.0, D1 to D9. `kit units` writes `work/files/<unit>/brief.md` and `brief.json`; skill sections are chosen by a `<!-- brief: <kinds> -->` tag after their heading. `kit review` runs `claude -p` with `--tools ""`, `--safe-mode`, `--no-session-persistence` and the file-reviewer definition as the system prompt, from an empty folder. Records are `files/<path>[#<part>].json` plus the rendered `.md`. New checks OUT-U4 (no High on an open edge) and OUT-U5 (brief row counts). `kit store` adds a `flows` table for sources and sinks, beyond D6's list, and `repo_gates`. `duckdb==1.5.6`. Not yet measured: the token target, recall and Haiku against Sonnet, which the next eval measures. |
| 2026-11-08T18:40:39Z | Updated | From a `python-review` of the build: reuse also needs the brief's scan rows unchanged (a fourth hash, `scans_sha256`), because a pass reads them; a reused record takes this audit's gates and counts. Added `verified` or `unverified` on each finding and a per-unit summary, after `python-review`'s pattern. |
| 2026-11-08T19:11:47Z | Updated | Pilot results and accuracy tuning. Ten units by size: about 34k tokens and $0.19 a unit (target met), but medium findings fell from 12 to 2 against 0.16.0. Eleven seeded units: 15 of the 18 seeded issues a file can show were found, against 16 for 0.16.0. Graph scope was missed because the NSW requirements never reached the brief, and the AI-reviewer comment was found but its record was rejected on a two-line excerpt. Following this ADR's risk plan ("the brief grows before D1 is dropped"): briefs now carry the missing rule sections, every answer must cover every check (OUT-U6), the pass is told to put accuracy before length, and repairs show the cited lines, with three attempts. |
