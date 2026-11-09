# ADR 0004: Discovery that checks its own evidence and says what it didn't see

> Status: Approved
> Created: 2026-11-07T11:29:45Z
> Last reviewed: 2026-11-07T12:03:16Z
> Next review: Not scheduled

## Review guide

Decision requested: make discovery's evidence mechanically checkable, record what
each tool did and didn't examine, stop path labels from taking files out of review,
and add a JavaScript review skill that the file review stage of ADR 0002 applies to
every `.js` file and inline script.

Check these points:

- [ ] The excerpt check (D1) and the search record for "not found" claims (D6) are
  strict enough to catch made-up evidence, and cheap enough for agents to fill in.
- [ ] Vendored and generated files get a sweep for dangerous calls and secrets, and a
  "generated" label needs evidence of a generator (D2). This changes ADR 0001's
  classification rule for build folders.
- [ ] The per-file coverage record (D3) and the "Not examined" section become required.
- [ ] The JavaScript review skill (D10) and its source rules. It needs ADR 0002's file
  review stage to run on every file, so this record asks to approve 0002 at the same
  time, without its dynamic stage (0002 D7).
- [ ] Build order (D12).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

Discovery is the bottleneck. Every later agent and the tech lead build on it, and
today nothing checks that it read what it says it read. `kit verify` confirms that a
cited file exists and that the line range is inside it. It doesn't confirm that the
lines say what the finding says. Path rules take vendored and generated files out of
semgrep and ESLint, so a modified library in `vendor/` that calls `eval` is never
looked at. And a tool that silently skips a file leaves no trace.

The tech lead built a JavaScript audit design, jsaudit, whose principles answer these
gaps: never decide not to look, labels are claims, evidence is checked mechanically,
and failures are loud. This record takes the parts that fit the kit's rules (no
execution of the target, no network outside the allow list) and turns them into
deterministic checks, scan files and agent duties. It also turns jsaudit's
JavaScript rulebook into a review skill that one agent pass applies to one file at a
time.

## Context

### What the kit does today

| Area | Today | Gap |
|---|---|---|
| Evidence | `kit verify` OUT-F4: the file exists and the cited lines are in range | A wrong line, a paraphrase or an invented excerpt passes |
| Inventory | Every file recorded with a class and reason (ADR 0001) | Vendored and generated classes come from path rules; those files then skip semgrep and ESLint |
| Tool coverage | `MISSING.txt` when a tool didn't run; ScanCode and Syft cross-checks | No record of a tool that ran but skipped files |
| Suppressions | ESLint runs with `--no-inline-config` | No inventory of `eslint-disable`, `@ts-ignore`, `nosemgrep` and similar comments, or whether they give a reason |
| Code static analysis can't see | Dangerous sinks are a node-express check | Dynamic `require`, `import(expr)`, `eval` and unresolved imports aren't listed as places nobody could see into |
| "Missing" claims | Free text | "No rate limiting" can't be re-checked |
| Severity | Severity criteria in `audit-findings` | Critical and High don't need a concrete trigger |
| Library recommendations | `kit lookup` checks the target's dependencies | A package an agent recommends isn't checked at all |
| Where to look first | File sizes from cloc | No change history weighting |
| Per-file review | ADR 0002 proposes it; not approved or built | One discovery pass reads 26,664 lines on the pilot app |

### What jsaudit contributes

The tech lead's jsaudit design (`PLAN.md`, 19 build prompts and
`docs/rules/javascript-craft.md`, read on 2026-11-07) has eight principles. Five
map directly onto the gaps above:

1. Never decide not to look: every file is recorded and the tool decides how deeply
   to analyse it, never whether it exists.
2. Labels are claims: folder names, "generated" headers and `.min.js` names are
   evidence to verify, never a reason to skip.
3. Evidence or it didn't happen: every finding carries a verbatim snippet, checked
   mechanically against the file.
4. Failures are loud: a tool that skips a file produces a coverage gap.
5. Deterministic before judgement: agents reason over facts the tools produced.

The rest of jsaudit's design either already exists in the kit (a full inventory,
pinned tools, read-only scans, seeded evals) or conflicts with its rules (see
Rejected options).

### Constraints

- `AGENTS.md` rule 2: never execute the target or load its config.
- Rule 3: no network except the allow list. `kit lookup` already obeys
  `.audit/policy.yaml`.
- Constraint C4: deterministic output, byte-identical on re-runs.
- Constraint C2: every write goes through `Workspace`.

## Decision

### D1. Excerpts are checked against the file

Every finding with a line location gets a required field:

```text
- Excerpt: `const folder = req.query.folder;`
```

One to three lines, copied verbatim from the cited lines, with secrets masked as
today. `kit verify` (new check OUT-F7) collapses whitespace on both sides and
checks that the excerpt appears inside the cited range. A masked secret matches
on the text before the mask. A mismatch fails the check and names the finding.

Discovery's tables for entry points, routes, integrations, data flows and state
(items 2 to 6) get an Excerpt column, checked the same way (OUT-F10). A row that rests on a
comment keeps its `(comment only)` mark, and its excerpt is the comment.

### D2. Labels are claims: sweep everything, and prove "generated"

1. **A sweep of every text file**, including vendored, generated and minified ones.
   `kit scan` writes `scans/sweep.json`. It's deterministic Python with no AI. It
   records:
   - calls that run strings as code (`eval`, `new Function`, string `setTimeout`)
   - `child_process`, `vm`, raw network calls (`fetch`, `XMLHttpRequest`,
     `WebSocket`, `http.request`, `net`)
   - file writes and bulk reads of `process.env`
   - `document.cookie` and `localStorage` reads next to a network call
   - long encoded strings (base64 or hex over 200 characters) in code

   For vendored code each hit is a lead for the supply-chain review: "this library
   makes network calls". It isn't a finding by itself. Gitleaks already scans the
   whole tree, and the sweep records whether vendored folders were in its scope.
2. **"Generated" needs a generator.** A file stays `generated` only when something
   in the repository produces it: a `package.json` script, a build config or a
   pipeline step that names its folder or file. A path rule alone (`dist/`,
   `build/`) or a "generated, do not edit" header alone makes it `own`, with the
   reason `generated claim unverified`, and discovery records an `info` finding.
   This changes ADR 0001's rule for build folders.
3. **Vendored files keep their class**, because many have no published copy to
   compare with offline. Their `upstream` and `version` leads stay. Comparing a
   vendored file's hash with the published package needs network access, so it's
   an option for `kit lookup` under `.audit/policy.yaml` (open item).

### D3. Coverage per file and tool

`kit scan` writes `scans/coverage.json`: for every own file in a language a tool
covers, which tools examined it and with what result: `examined`, `skipped`,
`failed`, `tool missing` or `not reported`. Sources:

| Tool | What it reports |
|---|---|
| ESLint | `filePath` of every result in `lint.json`, including files with no messages |
| tsc | a second run with `--listFilesOnly` |
| semgrep | the scanned paths, if the pinned version reports them alongside SARIF (to confirm) |
| jscpd, gitleaks | `not reported` until their output is shown to list files |

A file a tool should have examined but didn't is a coverage gap. The lead reviewer's
report always has a **Not examined or partly examined** section, built from this
file, the sweep, MISSING.txt and D5. `kit verify` checks that the section exists
(OUT-R11). Whether it names every gap is for a person to check, because gaps are
grouped by reason rather than listed one by one.

### D4. An inventory of comments that switch checks off

`scans/suppressions.json`, from deterministic Python over own files:

- `eslint-disable`, `eslint-disable-line`, `eslint-disable-next-line`
- `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`
- `nosemgrep`, `gitleaks:allow`, `istanbul ignore`, `c8 ignore`, `NOSONAR`

Each entry has its location, the rules it names (or `all`), and whether a reason
follows it (ESLint's `-- reason` form, or text after the directive). The engineer
agent and the JavaScript review skill read it. A directive with no reason over a
correctness rule is a finding; an inventory entry alone isn't.

### D5. Blind spots are listed, never treated as safe

`scans/blindspots.json` lists code static analysis can't see into:

- `require(<expression>)` and `import(<expression>)`
- `eval`, `new Function` and string timers in own code
- relative imports that don't resolve to a file (reusing the import graph that
  `kit scan` already builds for `unused.json`)

Discovery copies the count and the top locations into Limitations. A specialist
that relies on "nothing calls this" must check the list first.

### D6. "Not found" claims record their search

A finding or discovery row that says something is absent ("no rate limiting", "no
tests for the report journey", "no SIGTERM handler") gets a field:

```text
- Searched: `rateLimit|express-rate-limit|limiter` in `server.js lib/ routes/`
```

`kit verify` (OUT-F8) re-runs each search as a Python regular expression over the
named paths in the target and fails if anything matches. The agent stays honest
about what "not found" covered, and the verifier can see the scope.

### D7. Higher bars for higher severity

- **Critical and High need a trigger:** `- Trigger:` gives a concrete input or call
  sequence and the result. Without one, the finding is at most Medium (OUT-F9).
- **Security findings cite both ends:** where untrusted data enters and where it
  does harm, each with a location and an excerpt.
- **The verifier sees the finding, not the argument:** for Critical and High it
  reads the finding block and the code. It doesn't read the rest of the producing
  agent's report until after its first verdict.

### D8. Recommended packages are checked

Any recommendation that names an npm package goes in `.audit/recommended-packages.txt`
(written by the agent that recommends it). `kit lookup`, where the policy allows,
checks that each one exists, isn't deprecated, and has been published in the last
two years. Where the platform has a built-in replacement, for example
`structuredClone` for `lodash.clonedeep`, the report recommends that. A package that
doesn't exist is removed from the report and logged. Without network access, the
report marks each one `not checked`.

### D9. Where to look first

When the snapshot has Git history, `kit scan` writes `scans/hotspots.json`:

- changes and authors per file from `git log --numstat --no-renames`, ending at the
  audit commit (not at today's date), so re-runs match
- a hotspot score: normalised changes times normalised complexity from `lint.json`
- pairs of files that change together in at least five commits

Without history, it's a recorded gap, and nothing is estimated. The engineer agent
uses the ranking to order its reading. Pairs that change together help tell real
duplication from coincidental duplication.

### D10. A JavaScript review skill

`core/skills/javascript-review/SKILL.md` restates the rules in jsaudit's
`javascript-craft.md` as a check catalogue the kit can apply:

- check IDs `JS-*`, grouped like the source: language, async, errors, Node,
  data, security, UI frameworks and tests
- each check names what to look for, the `lint.json` rule that already detects it
  (if any), a severity guide and the official source
- checks the node-express profile or the `ai-generated-code-quality` skill already
  have keep those IDs; the skill points to them instead of repeating them
- every finding gives rule, line, consequence and fix, plus the D1 excerpt
- comments that make a claim ("already validated", "never null", "safe") are
  listed and checked against the code, following rule 4
- V8 engine-performance advice (object shapes, holey arrays) is never a finding
  without a measurement, in line with ADR 0002 D5
- jsaudit's "run a 3-line snippet with `node -e`" is replaced by citing the
  documentation, because agents run no code

**How it runs.** The file review stage of ADR 0002 runs one agent pass per own
`.js`, `.cjs` and `.mjs` file, and per inline `<script>` block in HTML, with this
skill as its rulebook for the design, logic and secure coding lenses. Until that
stage exists, the engineer agent applies it to the top hotspot files (D9) and the
files over 300 lines. This record asks to approve ADR 0002 D1 to D6, D8 and D9 with
it. ADR 0002 D7 (people run the target in isolation) stays unapproved.

### D11. Small planted fixtures for every deterministic check

`tests/fixtures/<case>/` holds a few files per case, with an `expected.json` that
lists what must be found and what must not be found. The starting set:

| Fixture | What it plants |
|---|---|
| `vendor-eval` | a library in `vendor/` with an added `eval` |
| `fake-generated` | a "generated, do not edit" header and no generator |
| `dist-with-script` | a `dist/` folder a `package.json` script builds |
| `suppressed` | `eslint-disable-next-line` with and without a reason |
| `dynamic-require` | `require(name)` from a variable |
| `excerpts` | findings with a right excerpt, a wrong line and a paraphrase |
| `absent` | a "not found" claim that a search proves wrong |
| `hostile` | an AI-directed comment and a symlink out of the root |

These test the Python. The seeded-issue evals still measure the agents.

### D12. Build order

1. **0.14.0, discovery:** D1, D3, D4, D5, D6, with fixtures, the discovery and
   lead-reviewer changes, and `kit verify` checks OUT-F7 to OUT-F10 and OUT-R11.
2. **0.14.1, labels:** D2, which changes the inventory and needs a re-run of the
   pilot eval to see what moves into review.
3. **0.15.0, file review:** the D10 skill and ADR 0002's stage, piloted on 10 files
   as ADR 0002 D9 describes.
4. **Alongside:** D7, D8 and D9, which are mostly agent definition changes and one
   scan each.

The solution designer (ADR 0003) follows, so the design starts from checked facts.

## Consequences

- An invented or misremembered excerpt fails `kit verify` before a person reads it.
- No file leaves review because of its folder name, and the report says what nobody
  examined.
- Findings get longer: an excerpt on every finding, a search on every absence claim,
  a trigger on every High.
- `kit scan` writes four more files. The sweep adds a full pass over every text file;
  its cost on large repositories isn't measured yet.
- More files move from `generated` into review, so the first run after 0.14.1 shows
  more findings than the one before.

## Rejected options

- **jsaudit's sandboxed bug-proof step.** It runs the target's tests, which breaks
  rule 2. ADR 0002 D7 covers people running experiments in isolation.
- **knip for unused code.** Its plugins load the target's config files. The kit's own
  `unused.json` stays.
- **Recording and replaying model calls.** The kit runs inside the tech lead's agent
  harness, not its own model client. The run log already records the model.
- **Keeping only findings two runs both produce.** It doubles the cost and loses real
  findings. The verifier and the seeded evals measure precision instead.
- **A score computed from findings.** Possible later. The kit's report rates
  consequence, and a single number would hide the coverage this record makes visible.
- **Excerpt checks by an agent.** A model checking a model's quotes repeats the
  error the check is there to catch. The check is string comparison.

## Risks and open items

- **Sources to confirm.** The JavaScript rules come from jsaudit's rulebook, which
  cites TC39, V8, Node.js, MDN, the framework teams, OWASP and named practitioners.
  The skill lists each source URL from that rulebook. They haven't been fetched for
  this record. Check them before 0.15.0.
- **Tool output to confirm.** Whether semgrep's pinned version reports scanned paths
  alongside SARIF, and whether jscpd and gitleaks list the files they read, needs a
  run of each real tool.
- **Excerpts in minified files.** One line can be thousands of characters. The
  excerpt for a long line needs a column range; the format isn't decided.
- **Vendored hash lookups.** Comparing a vendored file with its published version
  needs network access and the council's approval of hash-only lookups (ADR 0001
  open item).
- **Agent cost.** Excerpts and search records add tokens to every finding. The
  pilot eval re-run will measure it.
- **Not yet built.** D1 to D12 are not implemented.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-07T11:29:45Z | Drafted | Initial version, from the tech lead's jsaudit design and the request to fix discovery and add a JavaScript review skill. |
| 2026-11-07T12:03:16Z | Approved | Approved by the tech lead, with ADR 0002 except its D7. Corrected the check IDs: OUT-F6 was already in use, so the new checks are OUT-F7 (excerpts), OUT-F8 (searches), OUT-F9 (triggers), OUT-F10 (discovery tables) and OUT-R11 (Not examined section). |
| 2026-11-07T12:38:31Z | Built | Built: D1, D3 to D7 and D11 in 0.14.0; D2, D8 to D10 in 0.15.0. D8 changed in the build: agents list packages in a `Packages:` field on the finding instead of a shared `recommended-packages.txt`, because rule 1 lets each agent write only its own output. OUT-R12 checks them. |
