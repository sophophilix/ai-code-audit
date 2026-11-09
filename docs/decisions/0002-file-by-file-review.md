# ADR 0002: Review every code file on its own, then trace across files

> Status: Approved, except D7
> Created: 2026-11-06T14:57:23Z
> Last reviewed: 2026-11-07T12:03:16Z
> Next review: Not scheduled

## Review guide

Decision requested: add a file review stage in which one agent pass reads exactly one
code file and analyses it for design, secure coding, logic errors and algorithmic
complexity. A cross-file trace stage follows it, and an optional, human-run dynamic
stage turns complexity and vulnerability hypotheses into measurements.

Check these points:

- [ ] One file per pass, with cross-file questions recorded as open edges instead of answered by reading other files (D1, D3).
- [ ] The five lenses and the per-file record schema (D2, D4).
- [ ] Complexity claims stated as hypotheses with a named `n`, and metrics taken from deterministic scans, not estimated (D5).
- [ ] Execution stays with people: agents write experiment plans, and the tech lead or a pipeline runs them in an isolated environment (D7). This needs an approval nobody has given yet.
- [ ] A 10-file pilot measures cost and accuracy before the stage is switched on for a whole run (D9).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

Today one discovery pass reads the whole codebase and writes a summary. Four
specialists then work from that summary and read code to confirm or fill gaps. On
the pilot app, the summary's description of the system came largely from header comments,
and the tech lead found it matched a document the developer had written. Comments say
what someone believes the code does. They aren't evidence of behaviour.

This record proposes reading the code the other way round. First, every own code file
gets its own agent pass that reads that file and nothing else. The pass writes a
structured record: what the code in the file does, where untrusted input enters and
where it ends up, which functions grow with input size, and local defects. Anything
the file can't answer on its own, such as "does middleware elsewhere validate this?",
becomes an open edge. Second, trace passes follow each route and data flow across
files and resolve those edges. The specialists and the verifier then work from records
that are grounded in code, and still cite code themselves.

Agents still never run the target. Runtime profiling and dynamic security testing
belong in a separate stage that people run in an isolated environment, using
experiment plans the agents write. That stage follows the precedent of `scans/axe/`.

## Context

### What the pilot evaluation run showed

Evidence from the pilot eval workspace (kit 0.11.1, snapshot
`e4f5a6b`), checked on 2026-11-06:

1. Section 11 of `01-discovery.md` (the proposed project description) cites
   `server.js:1-32` for what the system does. All 32 of those lines are comment.
   The admin site's description cites `admin/server.js:1-12`, also all comment. "The CRM behind
   Azure Front Door" rests only on a header comment in `lib/scheduler.js`.
2. The tech lead reported that the developer had produced a document that matches
   this description. Header comments and handover documents can share one source,
   so agreement between them proves nothing about the code.
3. The kit invited this. `discovery.md` accepted any `file:line` as evidence and said
   later agents use the behaviour map "instead of re-reading files". `architect.md`
   said "Read code only to confirm or fill gaps in discovery". The verifier checked
   stage 2 findings only, never discovery. The 0.11.2 draft corrects the wording
   (comments are claims; discovery is a map), but one pass still covers 26,664 lines.

### Size of the work on the pilot app

Own `.js`, `.html` and `.sql` files, excluding `public/vendor` and `public/flags`,
counted from the snapshot:

| File size (lines) | Files |
|---|---|
| Over 1,000 | 6 |
| 301 to 1,000 | 13 |
| 101 to 300 | 22 |
| 100 or fewer | 72 |
| **Total** | **113 files, 26,664 lines** |

The largest are `public/index.html` (4,077), `lib/crm.js` (2,630),
`public/account.html` (1,911), `server.js` (1,610), `private/admin.html` (1,309) and
`scripts/crm.js` (1,028). `scripts/` holds 48 files and 4,160 lines.

### Constraints that still apply

- `AGENTS.md` rule 2: agents never execute the target, its scripts or its config.
- `AGENTS.md` rule 3: no network except the documentation domains in the intake.
- `AGENTS.md` rule 15: only the coordinator starts agents, one level deep. Claude
  Code subagents can't start subagents, so the coordinator fans out every pass.
- `limits.max_parallel_passes` in `models.yaml` caps concurrency (1 on the pilot app).

## Decision

### D1. One file per pass

A new stage, **1b file review**, runs after discovery. `kit units` lists the work
units from `.audit/inventory.json`, so the list is deterministic and the same on
every run. A unit is one own file of a reviewable language. Files over 1,000 lines
are split into sections at function or `<script>` boundaries. Each section is its own
unit, but it never contains code from another file.

The pass reads its unit in full. It may read `detected.md`, the inventory entry for
its file, and the deterministic scan results for its file. It doesn't read other
source files, `01-discovery.md`, other file records or any document. This isolation
is deliberate: every statement in the record can only come from the code in front
of the agent, and passes can't copy each other's mistakes.

### D2. Five lenses per file

Each pass applies five lenses, in this order, and writes what it finds through each.

1. **Behaviour from code.** What each exported function and route handler does,
   derived from its statements. Comments are listed separately, and every comment
   the code contradicts is recorded.
2. **Design.** Responsibility and cohesion, coupling (imports, exports, fan-out),
   layering (HTTP, domain and data access mixed in one function), module-level
   mutable state, side effects at import time, error-handling style, and
   configuration read outside a config boundary. Principles come from the
   architecture profile in `detected.md`.
3. **Secure coding.** Sources of untrusted data (`req.*`, headers, cookies, files,
   environment, responses from other services) and sinks (SQL, shell, file paths,
   HTML output, redirects, outbound URLs, logs, deserialisation, regular
   expressions). For each source-to-sink path inside the file: what validates or
   encodes it, at which line, and the CWE it maps to. Authentication and
   authorisation checks present in the file are listed. Checks come from the stack
   and compliance profiles.
4. **Logic errors.** Unawaited promises, swallowed errors, inverted or always-true
   conditions, off-by-one bounds, wrong equality, null and undefined handling, date
   and time zone handling, unreachable branches, races on shared state, and results
   computed but never used.
5. **Complexity.** See D5.

### D3. Open edges instead of cross-file reading

When a question can only be answered in another file, the pass doesn't guess and
doesn't go looking. It records an **open edge**:

```text
EDGE-server.js-007  req.query.folder reaches exec() at lib/legacyExport.js:12.
  Unknown here: whether any middleware validates `folder` before this handler,
  and whether this router is mounted.
  Resolve in: the file that mounts this router.
```

Open edges are the input to D6. A finding that depends on an unresolved edge can't
be rated above Medium until a trace pass resolves the edge.

### D4. The per-file record

Each pass writes `.audit/files/<path>.md` (sections as `<path>#<n>.md`), with the
usual provenance header, then fixed sections:

| Section | Contents |
|---|---|
| Facts | exports, imports, routes, environment variables read, module-level state, outbound calls, each with `file:line` |
| Comments versus code | each header or block comment that makes a claim, and whether the code agrees, disagrees or doesn't show it |
| Sources and sinks | one row per path inside the file: source line, sink line, validation or encoding line, CWE |
| Functions | name, lines, cyclomatic complexity (from scan), what `n` is, growth class, evidence lines, confidence |
| Findings | normal finding blocks (`audit-findings` skill), prefix `FILE` |
| Open edges | D3 |
| Experiment plans | D7, only where a static claim needs measuring |
| Limitations | as usual |

`kit verify` checks the schema of every record, so the coordinator's gate stays
mechanical, with no reading of content.

### D5. Complexity is a hypothesis with a named n

"This is O(n²)" means nothing until `n` is named. Each function row states:

- what `n` is (request body length, rows returned, uploaded file size, items in an
  in-memory map, number of photos)
- whether `n` is under an attacker's control, a user's, or nobody's
- the growth class and the lines that cause it (nested loops, a search inside a loop,
  a call per item, string concatenation in a loop, sort inside a loop)
- whether the work happens on the request path, at start-up, or in a timer
- regular expressions applied to untrusted input, flagged for backtracking risk

The numbers that tools can measure come from scans, not from the agent. Since
0.12.0, `kit scan` runs ESLint with the kit's own config
(`config/eslint.config.mjs`) into `.audit/scans/lint.json`. The file review
reads these rule IDs from it:

| Rule | Measures | Source |
|---|---|---|
| `complexity`, `max-depth`, `max-lines-per-function`, `max-params`, `max-nested-callbacks` | cyclomatic complexity, nesting depth, size and parameter count per function | ESLint core |
| `regexp/no-super-linear-backtracking`, `regexp/no-super-linear-move` | regular expressions that can take super-linear time | `eslint-plugin-regexp`, a community plugin, not part of ESLint |

These run on the source text with the kit's own config, so they don't load the
target's config (rule 2). The scan covers `.js` files only; inline scripts in
HTML need a separate extraction step, which D1's section rule should define.
The agent's growth class is a hypothesis. Only D7 can confirm it.

### D6. Cross-file trace stage

A new stage, **1c trace**, runs after all file records exist. One trace pass per
entry point (route group, timer, queue consumer, start-up path), listed from the file
records' Facts. A trace pass follows its flow across files, reading the code, and
resolves every open edge on the way. It writes `.audit/traces/<entry>.md`: the call
chain with `file:line`, the validations met in order, the edges resolved and what
the answer was, and findings that only exist across files (middleware order, a check
in one file that a later call undoes, data that reaches a log three calls later).

The specialists in stage 2 then read the file records and traces as their map. They
still cite code they read themselves (rule 4). Discovery stays, slimmed to inventory,
runtime, configuration, history and the project description, and the description now
cites traces instead of comments.

### D7. Dynamic stage: people run it, agents plan it

Runtime profiling, load tests and dynamic security scans all execute the target, so
no agent may run them. Instead:

1. Agents write **experiment plans** in their records. Each plan states a
   hypothesis that can be proven false: "`POST /api/reports` latency grows linearly
   with the number of photos". It also gives the input to vary and its sizes
   (geometric steps, for example 1, 2, 4, 8, 16, 32), the repeats per size, what to
   measure (latency percentiles, CPU time, memory), and the result that would refute it.
2. The tech lead or a pipeline runs the plans against an **isolated test instance**:
   - fake configuration and no production data or credentials
   - every outbound service (CRM, Graph, SMTP, Azure AI) replaced by a stub
   - no route to council systems
   - Node's built-in `--cpu-prof` for CPU profiles, and a load generator such as
     autocannon for request-rate tests
   - OWASP ZAP baseline and API scans for dynamic security testing
   - property-based tests (for example fast-check) for parsers and validators
3. Results go in `.audit/scans/perf/` and `.audit/scans/dast/`. For each growth
   hypothesis, the result is the slope of log(time) against log(n), with its
   confidence interval, so "linear" or "quadratic" is a fitted number, not an
   opinion.
4. The verifier compares each hypothesis with its measurement and reports agreement.

This mirrors `scans/axe/`, which the runbook already describes as run by a person
"against a local or test instance (optional)". A missing dynamic stage is a
limitation, not a failure.

### D8. Coordinator, checkpointing and verification

- Each unit is a pass with its own work folder and LOCK, so an interruption loses at
  most one file's work. `run-state.md` gets one summary row per stage, with unit
  counts, and per-unit status in `.audit/work/files/units.tsv`.
- `models.yaml` gets two agents, `file-reviewer` and `tracer`, so each can have its
  own model. A smaller model for files of 100 lines or fewer is allowed.
- The verifier adds a sample of file records: for every tenth unit (offset logged),
  it re-derives the Facts and the Sources and sinks rows from the code and reports
  per-lens accuracy, the same way it reports per-agent false-positive rates.

### D9. Pilot before switching it on

Nobody knows yet what a file pass costs in tokens or how accurate it is. Before a
full run:

1. Pick 10 units from the pilot eval snapshot, spread across the size bands in
   the table above, and including some of the files `kit seed` added or changed.
   The coordinator doesn't see the answer key, so the tech lead picks the units.
2. Run them and record tokens, duration and sessions per unit.
3. Score the records against the answer key and against a human reading of two files.
4. Decide from the measured cost per line whether a full run on 113 units fits the
   plan's usage limits, and at what concurrency.

The current eval run, on kit 0.11.1, is the baseline the pilot is compared with.

## Consequences

- Every statement about behaviour traces to code read in isolation, and comments
  become something checked rather than something believed.
- Cost grows with the number of files, not with one agent's context window. Large
  codebases stop depending on how much one pass can hold.
- Runs take longer and need more coordinator bookkeeping: 113 units plus traces on
  the pilot app, against one discovery pass today.
- Static review now produces explicit hypotheses about performance and exploitability
  instead of confident-sounding claims. Some stay unconfirmed when nobody runs D7.

## Rejected options

- **One agent per file, free to read other files.** This loses the isolation that
  makes the records trustworthy, duplicates reading across passes, and makes cost
  unpredictable.
- **Agents run profilers, tests or scanners against the target.** This breaks rule 2
  and puts council systems at risk through the target's own outbound calls. It also
  makes results depend on a model's command choices.
- **One unit per function.** Thousands of units would lose the file-level view of
  design and state, and functions can't be reviewed apart from their module.
- **Keep the current stages, with the 0.11.2 wording only.** This is cheaper and
  helps, but one pass still summarises 26,664 lines, and nothing measures how much
  of that summary came from code.

## Risks and open items

- **Approval for D7.** Running the target, even in isolation, needs the tech lead's
  approval, an environment and stubs. The policy file and the intake have no field
  for it yet. Decide before building D7.
- **False positives from isolation.** A file pass can't see validation done
  elsewhere. D3 caps those findings at Medium until a trace resolves them. The pilot
  will show whether that cap is enough.
- **Records as a new unquestioned map.** Rule 4 applies to them as it does to
  discovery, and the verifier samples them (D8).
- **Large HTML files.** `public/index.html` (4,077 lines) is mostly inline script. The
  section split in D1 needs a rule for `<script>` blocks, and for markup that only
  makes sense with its script.
- **Tool claims to confirm.** The ESLint core rules and the two
  `eslint-plugin-regexp` rules were checked against their documentation on
  2026-11-06. Node's `--cpu-prof`, autocannon, OWASP ZAP and fast-check are still
  named from the author's knowledge. Check each, and pin versions, before
  building D7.
- **Not yet built.** D1 to D9 are not implemented. The lint scan D5 relies on
  shipped in 0.12.0, along with the evidence rule (comments are claims) and the
  verifier's discovery sample that this record builds on.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-06T14:57:23Z | Drafted | Initial version, prompted by the pilot eval's Checkpoint 1 review. |
| 2026-11-06T15:12:20Z | Updated | D5 now uses the 0.12.0 lint scan; `eslint-plugin-regexp` marked as a community plugin; ESLint rules confirmed against their documentation. Still awaiting review. |
| 2026-11-07T12:03:16Z | Approved except D7 | Approved by the tech lead with ADR 0004, which supplies the JavaScript rulebook for the file review lenses. D7 (people run the target in isolation) is not approved; ADR 0005 proposes a smaller sandbox in its place. |
| 2026-11-07T12:38:31Z | Built | Built in 0.15.0: D1 to D6, D8 and D9 (`kit units`, the file-reviewer and tracer agents, OUT-U1 to OUT-U3, `file_review` in models.yaml). Records are `.audit/files/<path>[#<part>].md`; status per unit is in `.audit/work/files/status.tsv`. Discovery runs after the traces and reads them as a map. |
