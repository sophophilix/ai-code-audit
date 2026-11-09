# Changelog

## Unreleased: a final report a manager can read
- **The lead reviewer writes with `technical-writing`.** It loads the
  `technical-writing` and `humanizer` skills from sophophilix/agent-skills,
  pinned to `c33d852` (`THIRD_PARTY.md`). `audit-publishing` lists where the
  kit's rules win: outputs stay in `.audit/`, the provenance header replaces
  the skill's document-control block, Checkpoint 2 is the review, and agents
  don't run `ste-lint.py`.
- **The report has three parts.** Part A is for decision-makers (executive
  summary, decisions needed, top five issues, roadmap), Part B for technical
  teams, Part C for scope, method and limits. Impact comes before cause, and
  finding IDs go at the end of a sentence. The section headings that
  `kit verify` checks (OUT-R11, OUT-R13) are unchanged.
- **New person checks.** OUT-R14 (Part A stands on its own) and OUT-R15
  (`ste-lint.py` run on the report, advisory).

## 0.18.0 – 2026-11-09: what one file can't show reaches the file review
From the tuned 0.17.0 seeded pilot. Two seeded issues couldn't be found by any
pass: their evidence is in another file, and the brief never carried it.
- **Dependency manifests are units.** Each own `package.json` is one unit of
  kind `manifest`. Its brief has the unused-code rows for the file and two new
  sections tagged `manifest`: `SLOP-PHANTOM-DEP` (`ai-generated-code-quality`)
  and the node-express checks a manifest can show (`NODE-RUNTIME-LTS`,
  `EXP-VERSION`, `NODE-LOCKFILE`, `NODE-INSTALL-SCRIPTS`, `NODE-START-CMD`).
- **Unused dependencies reach a brief.** `unused.json` gives each one its file
  and line, and the scan reader passes them on; it used to drop them. Reports
  written by earlier versions still read, with no line.
- **Near-duplicate functions (`scans/similar.json`).** `kit scan` tokenises each
  named function of 12 to 400 tokens in own `.js`, `.cjs` and `.mjs` files and
  lists pairs whose tokens match at least 85% in order, with up to three places
  they differ. jscpd needs 50 tokens, so a copied one-line helper was invisible
  to it. Both functions' briefs get a `similar` row naming the other; `SLOP-DUP`
  names the file as evidence. Deterministic, no execution.
- **Text addressed to an AI reviewer** is `X-instructions-in-code`, never
  `SLOP-COMMENT`, and Medium at least.
- **Swapping accounts mid-audit.** `kit review` now stops at "You've hit your
  session limit" and at login or credit errors; it used to miss them, retry each
  unit and mark the rest gate-failed. Run it again after logging in and it carries
  on from the unit that stopped. The coordinator can release the `LOCK` of a
  session the tech lead says has ended. `kit cost` counts each unit once and
  leaves out passes refused before any work.

## 0.17.0 – 2026-11-08: a cheaper file review, and a findings store you can query
ADR 0007, from the 0.16.0 pilot eval's measurements (224k to 382k tokens a
pass, 31% of records failing `kit verify` on first write).
- **One brief per unit (D1).** `kit units` (and `kit scan`) writes
  `.audit/work/files/<unit>/brief.md` and `brief.json`: the unit's lines,
  numbered; this file's rows from every scan (ESLint, tsc, Semgrep, the sweep,
  jscpd, suppressions, blind spots, unused code, knip, gitleaks and the design
  inventory's contrast pairs), limited to the unit's lines and counted; the
  unit's gate table; the skill sections for its kind; and the output schema.
  Secrets appear as rule and line only. A section of a large file also gets the
  file's import lines as context it mustn't cite.
- **Skills by unit kind (D2).** A `<!-- brief: <kinds> -->` line after a heading
  tags a section for `script`, `component` (`.jsx`, `.tsx`), `sql`,
  `inline script`, `markup`, `stylesheet` or `inline style`. Tagged:
  `javascript-review`, `frontend-review`, `ai-generated-code-quality`, the
  `audit-findings` field rules and severity scale, and the catalogues of
  `node-express`, `web-accessibility`, `mssql` and NSW council digital (loaded
  only with their profile). Untagged sections stay with the stage agents. Check
  IDs don't change. Rules come to about 3k to 15k tokens a brief, by kind.
- **JSON out, checked by Python (D3).** The pass returns one object matching
  `config/file-record.schema.json`. The kit validates it and runs OUT-F1 to F4,
  F7 to F9, U2 and the new OUT-U4 (no Critical or High on an open edge or
  unverified, and no verified finding on an open edge) over
  every excerpt (facts, comments, sources and sinks, findings), not only the
  findings'. A failure goes back once with the failed checks listed. The kit
  writes a record only when every check passes: `.audit/files/<path>[#<part>].json`,
  plus the Markdown record rendered from it, with the kit's provenance header, IDs and
  gate table. Evidence is built from Location and Excerpt when the pass leaves it
  empty. Two failures leave no record, and the answer and problems are kept in
  the unit's work folder.
- **`kit review` (D3, D4).** Runs one `claude -p` pass per unit (to
  `max_parallel_passes` at a time) with no tools, `--safe-mode`, no session
  kept, the file-reviewer definition as the whole system prompt, the brief on
  stdin, and an empty working folder, so the pass reads the brief and nothing
  else. Picks the pass by `max_unit_lines`, follows `file_review.mode` (or
  `--units`), stops on a usage or rate limit with the unit `interrupted`, keeps
  `status.tsv`, and resumes on a re-run. `--dry-run` lists each unit's pass and
  model. Unit passes don't checkpoint; the coordinator asks the tech lead to run
  `kit review` instead of starting file-reviewer subagents.
- **Gate tables (D5).** Each record has a `## Gates` section (now required by
  OUT-U1): ESLint, tsc, Semgrep, knip, complexity and duplication, each `pass`,
  `fail`, `unavailable` or `not_applicable` with evidence. A tool that didn't run
  or didn't examine the file is never a pass; inline scripts are `unavailable`
  for the JavaScript tools. `kit scan` writes `scans/gates.json` and `gates.md`:
  which gates the target runs in CI or package scripts (read as text) and which
  config the kit used. The lead reviewer puts it in the report.
- **The findings store (D6).** `kit store` rebuilds `.audit/findings.duckdb`
  from the JSON records, traces, gates and pass ledger: tables `units`,
  `findings`, `edges` (with the trace that resolved each), `facts`, `flows`,
  `gates`, `repo_gates` and `passes`. `kit query "<SQL>"` reads it read-only with
  external access off and the configuration locked; it joins the read-only
  commands in `AGENTS.md` rule 2. The coordinator lists entry points and edges
  with it; discovery, engineer, security and the lead reviewer query it instead
  of reading every record. The store is git-ignored in the workspace.
- **Reuse by hash (D7).** Each record keeps the unit text's SHA-256, the kit
  version, and hashes of its skill sections and of its brief's scan rows. `kit
  review` keeps a record when all four are unchanged, and `--reuse-from <earlier workspace>` copies one from an
  earlier audit after checking its excerpts against this commit. Reused records
  say `reused_from` and are listed separately in the report.
- **Cost per pass (D8).** Each attempt's turns, tokens by type, cost and seconds
  go in `.audit/work/files/passes.jsonl`. `kit cost` prints totals by stage and
  model as API-equivalent cost and writes `.audit/cost.md`.
- **Kept apart (D9).** The store stays in the engagement. The runbook says how a
  lesson from an audit reaches the kit: only as a generic rule that a person has
  written and reviewed.
- **Verified or unverified, and a summary per unit** (from `python-review`'s
  pattern). Every finding says `verified` (this unit's code and scan rows show
  everything it claims) or `unverified` (it depends on another file, a rendered
  page or a scan that didn't run). Each record starts with a `## Summary` that the kit
  computes from the JSON: findings by severity, verified and unverified, open
  edges, facts, sources and sinks, and gates failed or unavailable. OUT-U1 now
  requires it, and the store's `units` table carries the counts.
- **Tuned for accuracy** after the first pilot, where the medium findings on ten
  units fell from 12 (0.16.0) to 2:
  - Every answer covers every check. The brief lists each CHECK-ID in its rules,
    and the pass answers each one `found`, `not found` or `not applicable`.
    OUT-U6 refuses an answer that skips a check, or that marks one `found`
    without a finding. Records gain a `## Checks` section, and the store a
    `checks` table.
  - Briefs carry the rules they had left out: the skills' "Before you start",
    "Verification" and rationalisation sections, the NSW requirements that code
    can show (least privilege for app identities and API scopes, the check a
    pilot missed), and the AI governance checks for AI features and
    AI-generated code.
  - The pass is told that accuracy comes first: report every issue, rate
    severity from the catalogue's guide, apply the caps to High and Critical
    only, and record positives.
  - A repair round shows the exact cited lines for each excerpt that failed, and
    a pass gets three attempts. In the pilot, one record with a correct finding
    was thrown away because a two-line excerpt lost its second `//`.
- New OUT-U5: the brief shows every row its scan table counts, and the record's
  counts match the brief. `evals/output-checks.md` now lists OUT-U1 to U5.
- `kit workspace ... --name <folder>` (Makefile `WS_NAME=`) names the workspace
  folder, so a second audit of the same kind can start on the same day. The
  default is still `<project>-<mode>-<date>`. A name must be one folder: letters,
  digits, `.`, `_` and `-`, starting with a letter or digit.
- New runtime dependency `duckdb==1.5.6` (MIT, published 2026-09-28). New setting
  `CLAUDE_BIN`. Makefile targets `units`, `review`, `store`, `cost`.
- The file-reviewer pass for short units on Haiku is gone from
  `models.example.yaml` until the next eval compares the two on the same units.
- Not measured yet: tokens per pass against the 25k to 40k target, recall
  against the 0.16.0 run, and Haiku against Sonnet. The next eval does that.

## 0.16.0 – 2026-11-07: front-end review, and council checks only for councils
- New core skill `frontend-review`: the FE-* check catalogue for markup,
  templates, stylesheets, design tokens, forms, the page skeleton, browser
  security headers, caching and front-end performance, from the tech lead's
  jsaudit `frontend-craft` rulebook. Every check has a kind: `static` (source),
  `runtime` (a rendered page), `agent` (judgement) or `manual` (a person).
  WCAG criteria keep their `WCAG-*` IDs from the `web-accessibility` profile.
  The client's design system wins on look; a brand that fails a standard gets an
  accessible variant within the brand, never a replacement. All 27 source URLs
  resolved on 2026-11-08.
- From the tech lead's search on NSW government front-end rules, checked against
  Digital NSW, the NSW Design System and WCAG before use: text over images,
  gradients, blur or see-through overlays is measured against the part of the
  background most like the text (WCAG F83); text shadows as the only contrast;
  focus rings drawn with `box-shadow` and then overridden; functional and
  complex images (charts and maps need a long description or data table);
  flashing; justified text and text spacing; `prefers-contrast`. Large text is
  24px or about 18.5px bold (WCAG G18). The skill lists the tools for the hand
  checks, starting with the NSW Colour Contrast Checker. The search summary's
  claims that councils must use the NSW Design System, and that the DDA itself
  names WCAG 2.2 AA, weren't supported by the pages and aren't in the kit.
- `nsw-local-government` gains `references/council-digital.md`: NSW-* checks for
  GIPA open access pages and applications, IP&R exhibition periods, meeting
  recordings and speaker consent, records capture, PPIP collection notices,
  health information, offshore data, breach readiness, personal information in
  analytics, session replay on form pages, staff surveillance, PID
  confidentiality and Sydney time, plus NSW-DESIGN-SYSTEM-BRAND (a council
  using NSW Design System code re-themes it with its own brand and drops the NSW
  Government masthead) and NSW-EASY-READ. The profile still loads only when the intake
  names an NSW council. legislation.nsw.gov.au refuses automated reading, so no
  section, fee or timeframe has been checked by the kit: agents open the section
  before citing it.
- `kit units` reviews the front end too: stylesheets, inline `<style>` blocks
  and the stretches of page markup between scripts become units, each cut at its
  own kind of boundary (functions for scripts, page regions for markup, rules for
  CSS). On the pilot app's snapshot that's 157 units: 112 files, 20 markup, 15
  inline scripts, 9 inline styles and 1 stylesheet.
- **Whose design is this?** The code and the live site show what was built, not
  what the brand owner approved. The intake gains an optional "Design system and
  brand" section (approved design system or brand kit, brand owner, approved
  fonts; `none` and `unknown` are valid answers). `kit validate` warns when the
  target has a user interface and the section is empty. `frontend-review` rates
  each area (Meets, Partly meets, Doesn't meet, Not determinable) against the
  approved design when one is recorded, and otherwise against what's built,
  with recommendations written as "if this is the approved brand" and an open
  question for the brand owner. New checks FE-DS-DRIFT and FE-DS-UNCONFIRMED.
- `kit scan` writes a **design inventory** (`scans/design-inventory.json` and a
  `.md` for designers): every colour with its uses, properties and contrast on
  white and on black (translucent uses listed apart, since their contrast
  depends on what's behind them); every token with its uses; font stacks
  (resolving `var()` and the `font` shorthand), `@font-face` rules with formats
  and `font-display`, and web-font links; and WCAG contrast, unrounded, for each
  rule that sets both text and background colours. A background that includes
  an image or gradient isn't measured (WCAG F83); it's listed for a rendered
  check. Pairs whose colours a theme, media query or `light-dark()` redefines
  are marked, because only the first value was measured. On the pilot app's
  snapshot it listed 419 colour uses (302 outside the 98 tokens), the
  self-hosted Brandsans brand font, and 7 text/background pairs below 4.5:1, with
  16 pairs over images or gradients left for a rendered check.
- A `python-review` pass over this code found that a background mixing a colour
  with an image was measured against the colour (the pilot app's hero had been
  reported at 2.12:1 from its gradient's first stop), that `url(#id)` was read
  as a colour, and that `var()` fallbacks and redefined tokens were ignored. All
  fixed, each with a regression test.
- The file reviewer picks its rulebook by unit kind; the accessibility, engineer
  and security agents load the frontend sections in their lane, and the council
  checks when the NSW profile applies. Manual checks are collected into a "Still
  to check by hand" list, which the report must have when the target has a user
  interface (`kit verify` OUT-R13).

## 0.15.0 – 2026-11-07: every JavaScript file reviewed on its own, and a sandbox
Builds the rest of ADR 0004, ADR 0002 (except D7) and ADR 0005, all approved.

**Labels are claims (ADR 0004 D2).**
- A file in `dist/`, `build/`, `coverage/`, `.next/` or `out/` stays `generated`
  only if a `package.json` script, a build config or a pipeline names the folder.
  Otherwise it's reviewed as own code, with the reason `generated claim
  unverified`. This changes ADR 0001's build-folder rule, so a re-run can show
  more files in review than before.
- `kit scan` writes `sweep.json`: network calls, string-to-code, `child_process`,
  `vm`, file writes, bulk environment reads, cookie and storage reads, and long
  encoded strings in **every** text file, vendored and minified included, plus own
  files whose header claims they're generated. On the pilot app's snapshot it found
  35 network calls and 3 string-to-code calls in vendored `face-api.js`, in 0.7 s.

**Where to look first, and what to recommend (D8, D9).**
- `hotspots.json`: changes and authors (counted, never named) per own file from
  `git log` up to the audited commit, a score of changes times ESLint complexity,
  and pairs of files that change together in at least five commits (bulk commits
  ignored). Eval snapshots have no history, so they record a gap.
- A finding that recommends an npm package lists it in `Packages:`. `kit lookup`
  checks each one exists, isn't deprecated and has had a release in two years,
  and names the built-in to use instead for ten common packages
  (`lodash.clonedeep` → `structuredClone()`, `uuid` → `crypto.randomUUID()`, ...).
  `kit verify` OUT-R12 fails on a recommended package that doesn't exist or is
  deprecated.

**File review (ADR 0002 D1 to D6, D8, D9).**
- `kit units` (and `kit scan`) writes `.audit/work/files/units.tsv`: one unit per
  own code file (`.js`, `.cjs`, `.mjs`, `.jsx`, TypeScript, `.sql`), per section
  of a file over 1,000 lines (cut at top-level declarations), and per inline
  `<script>` block, with host-file line numbers.
- New agents: `file-reviewer` (one unit per pass, reads nothing but its own file
  and that file's scan rows, applies `javascript-review` or the `mssql` profile,
  writes a fixed-section record with open edges) and `tracer` (one entry point
  per pass, resolves the edges, finds what only exists across files).
- `models.yaml`: optional `file-reviewer` and `tracer` agents, `max_unit_lines`
  so a smaller model can take short units, and `file_review.mode` (`off`,
  `pilot` with the tech lead's `pilot_units`, or `full`). The coordinator runs
  stages 1a and 1b before discovery, which then reads records and traces as its
  map.
- `kit verify` checks records and traces like other findings (they're folded to
  one line per check): OUT-U1 the record's sections, OUT-U2 every Location inside
  the unit's own file and lines, OUT-U3 a record for every unit (or every pilot
  unit). Finding IDs `FILE-u042-001` and `TRACE-t03-001`.
- `javascript-review` is loaded by the file reviewer, the tracer and the
  engineer. All 43 source URLs resolved on 2026-11-07.

**Sandbox (ADR 0005).**
- `kit sandbox <ws> structure|tests|prove|try`, only with `sandbox: allow` in
  `.audit/policy.yaml`. One image (`config/sandbox/Dockerfile`: the target's Node.js
  major, knip 6.42.1, dependency-cruiser 18.7.0). The snapshot is copied without
  kit folders, symlinks or `node_modules`; install is `npm ci --ignore-scripts`
  with network; every other step runs with `--network none`, a read-only root,
  `--cap-drop ALL`, no new privileges, pid, memory and CPU limits, as `node`, with
  no environment or host files. Agent-written tests and snippets must be under
  `.audit/work/` (paths are normalised first), and snippets are at most 20 lines.
  Outputs go to `.audit/scans/dynamic/`, and `jobs.log` records each image id.
- A `python-review` pass over the new code found 13 issues, all fixed with
  regression tests: an agent file name could set Docker mount options (names are
  now limited to letters, digits, `.`, `_` and `-`, and mount values are checked);
  a timed-out container kept running (each job now has `--name`, an in-container
  `timeout`, and `docker rm --force` on a client timeout); a symlinked record
  crashed `kit verify`; a `package.json` script *named* `build` proved `build/` was
  generated (only script commands and output fields count now); searches run in
  their own process with a 30 s limit (`audit_kit.search`); a failed `git log`
  is a gap, not an aborted scan; hotspots match lint paths from a moved
  workspace; the sandbox copy streams files; "not found" comes from the HTTP
  status; finding parsing moved to `audit_kit.findings`; cited files are read
  once per `kit verify`. Hypothesis 6.170.9 (dev only) adds property tests for
  sections, excerpts and sandbox paths. A second review, of the fix code
  itself, found five more: a crashed search process read as "nothing found"
  (exit codes are now the contract, and any failure fails the claim); containers
  ran as the image's `node` user, whose files the host may not delete (they now
  run as the host's uid and gid, never root); `tests` had a read-only copy that
  test runners can't write caches to; a container killed by its own time limit
  wasn't reported as timed out; and temporary-folder cleanup could hide results.
- `AGENTS.md` rule 2 names the sandbox as its one exception: a person runs it;
  agents only write the files it runs.
- Run against a real daemon (Docker 29.2.1 under colima, arm64) on a synthetic
  target. All four jobs work: `tests` ran the target's suite, `prove` failed for
  the claimed reason (an off-by-one read past the array), `try` showed network
  calls fail (`EAI_AGAIN`), and `structure` produced knip and dependency-cruiser
  JSON (knip exits 1 when it finds issues). Inside the container `/` and `/work`
  are read-only, only `/tmp` is writable, the user is the host's uid, and the
  environment holds only the image's own variables. An infinite loop stops at
  the container's limit, and a client timeout removes the container. The live
  run found three bugs the fake-Docker tests couldn't: `--mount` takes
  `readonly`, not `ro` or `rw`; colima and Docker Desktop see only the home
  folder, so the copy now lives under `~/.cache/audit-kit/sandbox`; and agent
  files are staged there too rather than mounted from the workspace.

## 0.14.0 – 2026-11-07: discovery that checks its own evidence
ADR 0004 (approved with ADR 0002, except 0002's D7). Prompted by the tech lead's
jsaudit design: labels are claims, evidence is checked mechanically, and
failures are loud.
- Findings gain three fields (`audit-findings` skill): `Excerpt`, copied verbatim
  from the cited lines; `Trigger`, required for Critical and High; and
  `Searched`, the search behind any claim that something is absent.
- `kit verify` checks them: OUT-F7 compares every excerpt with the file
  (whitespace ignored, `****` and `...` split it into pieces matched in order);
  OUT-F8 re-runs every `- Searched:` line over the target and fails on a match
  (patterns over 300 characters or with nested quantifiers are refused); OUT-F9
  requires a Trigger on Critical and High; OUT-F10 checks the Excerpt column of
  discovery's tables; OUT-R11 requires a "Not examined" section in the report.
  Discovery (`01-discovery.md`) is now checked like the other findings files.
- `kit scan` writes three more files, recomputed on every run:
  `suppressions.json` (every `eslint-disable`, `@ts-ignore`, `nosemgrep`,
  `gitleaks:allow`, `istanbul`/`c8 ignore` and `NOSONAR` comment, and whether it
  gives a reason), `blindspots.json` (dynamic `require` and `import`, `eval`,
  `new Function`, string timers, unresolved relative imports) and
  `coverage.json` (which own `.js` files ESLint and tsc examined, from
  `lint.json` and a new `tsc --listFilesOnly` run, and HTML with inline scripts
  no tool checks). `unused.json` also lists unresolved imports.
- Discovery adds an Excerpt column to items 2 to 6, a Searched line for every
  absence claim, and coverage gaps and blind spots in Limitations. The lead
  reviewer writes the "Not examined" section; the verifier reads a Critical or
  High finding and its code before the producing agent's reasoning; the engineer
  reports suppressions.
- `tests/fixtures/`: planted cases (`suppressed`, `dynamic-require`, `excerpts`,
  `absent`), each with an `expected.json` of what must and must not be found.
- New `core/skills/javascript-review`: the JS-* check catalogue for the file
  review stage (ADR 0002), from the jsaudit rulebook. Not loaded by any agent
  until 0.15.0; its source URLs still need checking.

## 0.13.2 – 2026-11-07: diagrams people want to read
- `kit diagrams` now groups nodes into trust zones (from `group`, or else
  `properties.trust_boundary`), lays them out left to right, and applies a house
  style after drawio-skill builds them (`src/audit_kit/diagram_style.py`):
  rounded, tinted zones; rounded cards with the Azure icon at a fixed size on the
  left; curved edges, dashed for `async`; data stores as cylinders; a hand-drawn
  stroke. `--style clean` drops the hand-drawn stroke. Layout is kept, so `sync`
  and manual tidying still work. drawio-skill itself runs unchanged.
- `architecture-diagrams` and the architect: context diagrams have at most 15
  nodes and 20 edges, labels are a name plus a short role, sibling services fold
  into one node, and detail goes in extra one-question diagrams. The 0.12.1 eval's
  as-is diagram (24 nodes, 30 edges, sentence-long labels) prompted this.

## 0.13.1 – 2026-11-07: seeds for the new checks
- `kit seed` plants three more issues (19 in all), in code the seeded router
  reaches: sessions in the default `MemoryStore` with `resave` and
  `saveUninitialized` left on (`EXP-SESSION`), a module-level write stream with no
  `'error'` listener (`NODE-EMITTER-ERROR`), and `return` of a promise without
  `await` inside `try`, so the `catch` never runs (`NODE-AWAIT-RETURN`).
  `express-session` is added to `package.json` unless already declared.
- The 0.12.1 eval (the pilot eval) was stopped at Checkpoint 1 by the
  tech lead: discovery loads the stack profile, so its output can't carry into a
  0.13.x run. The workspace is kept for comparison.

## 0.13.0 – 2026-11-07: service structure, entry point and Express middleware
- New `profiles/node-express/references/service-structure.md`: the recommended
  layout (business components with entry points, domain and data access;
  libraries), a minimal `server.js` that only starts and stops, a matching
  `createApp`, the default middleware stack, and how to assess a target against
  them. A large file is a pointer; the finding is what is mixed into it.
- New checks: `NODE-ENTRY-SPLIT`, `NODE-ENTRY-LIFECYCLE`, `NODE-COMPONENTS`,
  `NODE-LAYER-LEAK`, `NODE-START-CMD`, `NODE-ENV-PROD`, `EXP-ASYNC-ERRORS`,
  `EXP-SESSION`, `EXP-TIMEOUT`.
- Tightened from each Express-team module's own docs: `EXP-BODY-LIMIT`,
  `EXP-UPLOAD`, `EXP-STATIC`, `EXP-CORS`, `EXP-ERROR-LEAK`, `EXP-SEC-HEADERS`.
  `NODE-UNHANDLED` now fails only a handler that keeps running (Node: "not safe to
  resume"; Express: "dangerous"). `NODE-SHUTDOWN` and `NODE-LOGGING` list the steps.
- Sources: the Express performance page's new address, the health-check, middleware
  and Express 5 migration pages, and Node's `process` and `http` docs. Community
  sources nodebestpractices (CC BY-SA 4.0) and Practica.js (MIT) are cited by item
  number, pinned in `THIRD_PARTY.md`, and not added to the allowed domains.
- New `profiles/node-express/references/error-handling.md`, from nodebestpractices
  section 2: one app error class (operational vs catastrophic), one central handler
  for routes, jobs and start-up, sample code, `return await`, `'error'` listeners on
  emitters and streams, and how to trace one failure per critical journey. New checks:
  `NODE-ERROR-TYPES`, `NODE-ERROR-CENTRAL`, `NODE-AWAIT-RETURN`, `NODE-EMITTER-ERROR`,
  `NODE-INPUT-VALIDATION`, `NODE-ERROR-CONTRACT`. The 2016 blog checklist behind
  section 2 is superseded and not cited.
- New search patterns: entry point and lifecycle, start command, web objects past
  the routes, Express-team middleware, async route handlers, error types and
  handlers, emitters and streams, validation libraries.

## 0.12.1 – 2026-11-07: unused-code and type-check scans
- `kit scan` writes `.audit/scans/unused.json` from the kit's own static analysis
  (`src/audit_kit/unused.py`): entry points from `package.json` and `<script src>`
  in own HTML, files no entry point reaches through relative `require`/`import`
  (with where else each name appears), dynamic requires, dependencies declared but
  never required or required but undeclared, and exports no other file names.
  `require(path.join(__dirname, ...))`, or a constant built from `__dirname`, with
  literal parts is followed; other computed paths are listed. It reads files as
  text and runs nothing. Knip was rejected: its plugins dynamically
  load the target's config files.
- `kit scan` runs `tsc --checkJs --noEmit` with the kit's own
  `.audit/scans/tsconfig.audit.json` into `.audit/scans/typecheck.txt`. Node.js
  types come from `@types/node` beside `tsc`, since the target's dependencies are
  never installed, so imports of its packages report as unresolved.
- `make tools` installs `typescript` and `@types/node` into `~/audit-tools`
  (override with `TSC_BIN`).
- All three code scans cover `.js` files only; HTML inline scripts stay a
  recorded limitation.

## 0.12.0 – 2026-11-07: evidence from code, and lessons from the first 0.11.1 eval
The problems behind each change came from a private review of that eval. See
`docs/decisions/0002-file-by-file-review.md` (in review) for the
larger redesign that isn't built yet.

- `kit scan` runs ESLint with the kit's own config (`config/eslint.config.mjs`) into
  `.audit/scans/lint.json`, with inline config disabled so the target's
  `eslint-disable` comments can't hide results. It runs ESLint core rules, grouped by
  kit check, plus `regexp/no-super-linear-backtracking` and `no-super-linear-move`
  from the community `eslint-plugin-regexp`. `make tools` installs both into
  `~/audit-tools` (override with `ESLINT_BIN`). Tested with a fake binary only.
  `.js` files only; HTML inline scripts are a recorded limitation.
- The `ai-generated-code-quality` skill names its sources (OpenSSF's guide for AI code
  assistants, ESLint, Node.js) and ties each `SLOP-*` check to lint rules. New checks:
  `SLOP-ASYNC`, `SLOP-LOGIC`, `SLOP-QUADRATIC`. `SLOP-COMMENT` puts comments that
  contradict code first, and adds lower-weight patterns from the community
  `miqdadbadjuber/anti-slop`, marked as reviewer judgement.
- The `node-express` profile adds checks from Node's *Don't Block the Event Loop*:
  `NODE-REDOS`, `NODE-BLOCKING-SYNC`, `NODE-JSON-DOS`, `NODE-CPU-ON-LOOP`. The `mssql`
  profile lists Microsoft's T-SQL code analysis rules SR0001 to SR0016.
- Checkpoint 1 corrections go in `project.md` → `## Checkpoint 1 corrections`, which
  every later agent reads; a sign-off note in `run-log.md` never reached them.
- Times: every `*_utc` value and every coordinator log time comes from `date -u`
  (now in the harness allow list); the coordinator checks header times at the gate.
  The coordinator runs `.audit-kit/bin/checkpoint` as a command on its own.
- Agents keep scratch notes in `capsule.md`, not shell temp files they can't delete.
- `eslint.org`, `best.openssf.org` and `ota-meshi.github.io` added to the template's
  allowed documentation domains and the Claude Code allow list.

## 0.11.2 – 2026-11-07 (not released separately; folded into 0.12.0)
- `kit workspace` checks that a snapshot's files match the source commit, by git blob id
  for every path, before anything else runs. A copy that differs (for example through
  `export-subst`) is refused. `.audit/.workspace` records `source_tree`.
- Eval workspaces list every path they deliberately change, removed by `eval-remove.txt`
  or planted by `kit seed`, in the project's `keys/source-delta-<workspace>.txt`. The
  list stays outside the workspace, because agents can read `.audit/`. Only the count
  (`source_delta`) goes in `.audit/.workspace`.
- `kit validate` checks the intake's "Repository and commit to audit" against the
  workspace's `source_commit`: an error if it names a different commit, a warning if it
  names none, and a warning if an eval snapshot isn't named alongside its source.
  Pre-flight no longer needs the tech lead to compare commits by hand.
- Comments and documents are claims, not evidence of behaviour (`AGENTS.md` rule 4).
  Discovery follows header comments into the code, marks anything only prose
  supports `(comment only)` or `(doc only)`, and records comment/code contradictions.
  Its behaviour map is a map for later agents, no longer a substitute for reading
  code, and the architect reads the code its findings rest on.
- The verifier also checks discovery: every line of the project description and a
  sample of route, integration and data-flow rows, reporting discovery accuracy.

## 0.11.1 – 2026-11-06
- Pre-flight accepts a tech-lead exception for "evaluation current": a real run can go
  ahead while an eval of the same kit version runs in parallel. The lead reviewer then
  states near the top of the report that accuracy isn't measured yet, and the report
  isn't shared until the eval's results are added.

## 0.11.0 – 2026-11-06: engagement policy and supply-chain lookups
- New per-project `policy.yaml` (copied to `.audit/policy.yaml`): the rules that change
  per client, separate from the kit's fixed safety rules. Every default denies.
- `kit lookup` (`make lookup`, also run by `make ready`): npm deprecation of each direct
  dependency's locked version, GitHub archived status of dependency and vendored-file
  upstreams, and Node.js end of life for `engines.node`, written to
  `.audit/scans/upstream-status.json`. Runs only when `network.metadata_lookups: allow`;
  sends names and versions only, to three allow-listed https hosts. Denied runs are
  recorded as a limitation.
- Detection lists languages by reviewed lines and flags any language over 5% that no
  profile covers.
- Optional ScanCode (`--info --classify --generated`) and Syft (every file, sha256)
  scans, with `.audit/scans/inventory-crosscheck.txt` comparing their file lists and
  hashes with the inventory. Tested with fakes only so far.

## 0.10.0 – 2026-11-06: a complete, checked inventory of the target (ADR 0001)
- New `.audit/inventory.json`: one record per path in the target, with class, the rule
  that set it, size, sha256, git blob id, and for vendored files an `upstream` URL and
  `version` marker as leads. Nothing is skipped by name or by ignore rules; vendored,
  generated, binary and hidden files are recorded, and only their review is skipped.
- Detection checks the inventory against `git ls-tree` of the snapshot commit and stops
  on any missing, extra or changed path. `detected.md` records the snapshot commit and
  the inventory's sha256.
- Classification uses Linguist's `vendor.yml` and `documentation.yml` (pinned, v9.7.0)
  plus `.gitattributes` `linguist-*` overrides, replacing rules tuned to the pilot app. The kit
  un-vendors what Linguist hides but an audit must review: `.github/`, `Jenkinsfile`,
  `.teamcity/`, `.gitignore`, `.gitattributes`, `env/` and others.
- Sources: a plain folder or a `.tar`/`.tar.gz`/`.tgz` archive now works, as well as git.
  Snapshots are committed with `git add --force`, so the target's `.gitignore` can't drop
  files, and paths `git archive` leaves out (`export-ignore`) are restored from git objects.
  The state file records the source commit or a sha256 manifest of a non-git source.
  Zip is refused until it has a safe extraction filter; a source with its own `.audit/` or
  `.audit-kit/` is refused.
- Fixed: the kit's own `.claude/` adapter was reported as the target's AI instruction file.
- Fixed: `detected.md` kept an old kit version after a reinstall; install now re-runs
  detection when it exists.
- The `-check.js` test-file rule (one pilot app's convention) is gone.
- Discovery and security read vendored files from the inventory; security identifies each
  vendored library and records its maintenance status, or the missing lookup.

## 0.9.1 – 2026-11-06
- Secrets-scan hits no longer block pre-flight or ask the tech lead to judge code they
  don't know. The security agent triages every hit with evidence (test value: info;
  plausible real credential: critical, escalated the same day); the tech lead checks the
  triage at Checkpoint 2. Found in the first pilot test run.

## 0.9.0 – 2026-11-06: bin/kit ported to Python
- Every `bin/kit` command now lives in the `audit_kit` package (`doctor`, `tools`, `tag`,
  `project`, `workspace`, `seed`, `install`, `detect`, `check-data`, `validate`, `scan`,
  `ready`, `diagrams`, `publish`, `verify`, `status`, `list`, `selftest`); `bin/kit` is a
  three-line wrapper for `uv run audit-kit`. Same commands, messages and exit behaviour:
  the unchanged bash end-to-end test passed all 60 checks against the Python version
  before it was retired.
- Every program the kit starts goes through `runner`, with an argument list and an explicit
  timeout (git, scanners, pandoc, marp, drawio-skill, brew, npm). Enforced by a new
  Semgrep rule, `subprocess-only-in-runner`.
- Eval snapshots are extracted with `tarfile`'s `data` filter, so archive entries can't
  escape the workspace (the bash `git archive | tar` had no such guard).
- Project names must be a single safe path segment.
- Tests: 106 (pytest unit, end-to-end, and adapter tests with recording fakes for every
  external tool), replacing the bash end-to-end test; branch coverage 91%.
- A repository without `package-lock.json` is recorded as "nothing to audit" for the
  dependency scan, instead of a failed scan.
- Architecture record: exceptions E1 and E2 removed; constraints C7 (programs only through
  the runner) and C8 (thin shell entry points); next boundary proposed: a findings store.

## 0.8.0 – 2026-11-06: deterministic validation of models.yaml and the intake
- `audit-kit validate` (`make validate`, also run by `make ready`): Pydantic models for
  `models.yaml` forbid unknown keys (misspelt agents and fields are errors); cross-checks
  that every provider and harness exists and fit together, used providers are approved with
  a recorded region, model ids aren't placeholders, pass labels are unique, profiles exist,
  and the verifier's different-family rule can be met (warning when off and single-family).
  Also checks the six intake fields. Writes `.audit/validation.md` (result, input SHA-256).
- Pre-flight and the coordinator require `validation.md` to say `result: pass`.
- `config/models.schema.json` (from `audit-kit schema`, drift-tested) and a
  `yaml-language-server` comment in the example so editors validate as you type.
- Fixed: the Makefile defined `check` twice; the data check is now `make check-data`.
- Architecture record updated (E4 removed); next boundary proposed: port `bin/kit` to Python.

## 0.7.1 – 2026-11-06: the Python tooling meets python-standards
- Python tools rebuilt as the typed package `src/audit_kit` (`uv run audit-kit detect|seed|verify`)
  with `pyproject.toml` and a committed `uv.lock`. Architecture record:
  `docs/architecture/ARCHITECTURE.md` (in review).
- Fixes every finding from the python-review at 6374dc7 (verdict: rejected):
  - F2: all reads and writes go through a confined `Workspace` that refuses `..`, absolute
    paths and symlinks; seeding can no longer write outside the workspace.
  - F3: `package.json` is validated with Pydantic; a malformed file is reported in
    `detected.md` instead of crashing.
  - F4: strict mypy clean. F5: OUT-R2 reads exact verdicts only. F6: seeding is all or
    nothing (staged writes with rollback; key written last). F8: cited locations are confined.
  - F9: unreadable input is listed under "Needs a person". F10: frozen dataclasses replace dicts.
  - F11 to F17: docstrings, Ruff clean and formatted, pytest under `tests/`, CLI exit codes
    0/1/2/3 tested, `bin/kit` runs tools from the lock, package.json formatting preserved.
- Quality gates from the lock (`make check`): Ruff, mypy strict, Bandit, Semgrep with
  repository rules (`.semgrep.yml`, including a rule that only the workspace adapter may
  write), pytest with 93% branch coverage (floor 80%), pip-audit. `.pre-commit-config.yaml`
  runs Ruff and mypy through `uv run --frozen`.

## 0.7.0 – 2026-11-06: start from zero knowledge
- **Minimal intake.** `project.md` is now six required lines only a person can supply
  (organisation and jurisdiction, repo and commit, tech lead, security owner, AI approval,
  processing region). Everything else is optional.
- **`kit detect`** (`tools/detect.py`, no AI, deterministic): profiles from evidence
  (package.json, SQL, Azure packages, IaC and hostnames, UI files, intake jurisdiction;
  ai-governance always), vendored, generated and minified code excluded from scans,
  facts (sizes, pipelines, IaC, tests, AI instruction files, AI service signals).
  Writes `.audit/detected.md`; agents load profiles from it. Runs in `make ready`.
- **Blind discovery.** Discovery proposes the project description (purpose, users,
  data, dependencies, hosting, profile corrections) from code alone. Team beliefs moved
  to an optional `beliefs.md`, read only by discovery's last item and the lead reviewer.
- **Checkpoint 1 is confirm, not author.**
- **`kit seed`** (`tools/seed.py`): plants about 15 stack-specific issues (Node/Express)
  plus a control, mounted before any catch-all handler, and writes the answer key to the
  project's `keys/`, outside the workspace.
- Tests: 20 unit tests (detect, seed including `node --check` of every plant, verify);
  end-to-end test extended to the seed → seal → detect → ready flow.

## 0.6.1 – 2026-11-06
- `kit tools` / `make tools` (with `--dry-run`): installs only what `doctor` reports
  missing: Homebrew formulae, draw.io, jscpd (exact version, no install scripts) and
  drawio-skill at the reviewed commit. `doctor` points to it.

## 0.6.0 – 2026-11-06
- **`bin/kit` + `Makefile`**: idempotent commands for the whole lifecycle: `doctor`,
  `tag`, `project` (reusable per-system folder in `~/audit-projects/<name>`),
  `workspace` (eval = history-free snapshot with answer sheets removed; real =
  clone on an `audit/<date>` branch), `install` (seals seeded issues into the
  snapshot, quarantines AI instruction files, refreshes kit and adapter, never
  overwrites settings or project files), `check` (data check), `scan` (installed
  scanners only, missing ones recorded), `ready`, `diagrams`, `publish`,
  `verify`, `status`, `list`, `selftest`. Works on bash 3.2 and later.
- **`tools/verify_outputs.py`**: automates the scriptable output checks (F1–F5,
  P5, P7, V1, R1, R2, R6, B1, B3, D3, D4). 10 unit tests.
- `tools/test_kit.sh`: 35 end-to-end checks of `bin/kit` on a throwaway repo,
  including idempotency (re-runs make no new commits).

## 0.5.1 – 2026-11-06
- New `evals/interruption-test.md`: six required scenarios (killed mid-item, crash
  between save steps, concurrent session, stale lock, coordinator killed, early
  handover) plus rate limits when they occur; measures T1–T11 (completeness, no
  lost or duplicate findings, ID continuity, recall parity, resume overhead ≤ 1.25×,
  lean resume, capsule size, locks, coordinator resume, drift).
- Pre-flight now requires the interruption test as part of a current evaluation;
  the Evaluation table has Interruption and Cost columns.

## 0.5.0 – 2026-11-06
- **Resumable runs.** New skill `checkpointing`, loaded by every agent: work split
  into small items derived from the inputs; output built incrementally
  (`status: in-progress|complete`); per-pass `LOCK`, `plan.md` and `capsule.md`
  (≤ 60 lines) in `.audit/work/`; resume reads only those files and the ID and
  Key lines, redoing at most one item, never renumbering.
- Coordinator keeps `.audit/run-state.md`, resumes runs, handles rate limits and
  usage caps (stop, checkpoint, report; never retry in a loop), records usage
  per pass, and commits `.audit/` after each agent with `bin/checkpoint` (tested:
  refuses outside `audit/*` branches and when anything outside `.audit/` changed).
- `models.yaml`: `limits` (max_parallel_passes, lock_stale_minutes, on_rate_limit)
  and an optional price table.
- `docs/observability.md`: Claude Code OpenTelemetry (token and cost metrics by
  `agent.name`, api_error 429s, beta traces), `audit.*` resource attributes,
  Azure Monitor or local backends, and metrics for improving the kit.
- Output checks OUT-P5 to P7 (complete outputs, usage recorded, resume integrity).

## 0.4.0 – 2026-11-06
- Pre-flight **data check**: data, credential and dump files in the tree or git history
  stop the run; the secrets scan is reviewed by a person. Sanitising is not the default;
  the runbook lists when it becomes necessary.
- New skill `audit-publishing`: Markdown is the single source; Marp for slides and PDF,
  Pandoc for editable Word and PowerPoint using the organisation's templates.
  Lead reviewer now also writes `09-briefing.slides.md`.
- New `evals/output-checks.md`: checks for findings, verification, report, briefing,
  backlog, diagrams and the run log (automated where possible; scripts deferred).
- drawio story mode dropped from the kit's guidance in favour of Markdown slides.

## 0.3.0 – 2026-11-06
- Diagrams now use **drawio-skill** (Agents365-ai, MIT), pinned to `053600a`
  after a targeted review (`THIRD_PARTY.md`). The in-house `diagram.py`
  from 0.2.0 is removed, so there's one way to draw diagrams.
- `architecture-diagrams` is now a rules skill: Diagram IR route, official
  `img/lib/azure2/` icons only (not legacy `mxgraph.azure`), offline features
  only, architecture contracts, what-if, views, and story mode for workshops.
- Architect writes Diagram IR with provenance, plus optional `policy.yml` contracts.

## 0.2.0 – 2026-11-06
- New skill `architecture-diagrams`: JSON spec → editable draw.io file with the
  official vendor icon pack embedded (`scripts/diagram.py`, standard library only,
  12 tests). Icon names are checked against the pack, never guessed; the pack
  version is recorded in the footer.
- Architect writes diagram specs to `.audit/diagrams/`; the tech lead builds them.
  New scan input `icon-index.txt`.
- How-to: icon pack download, building and exporting diagrams.

## 0.1.0 – 2026-11-06 (definitions only, not yet evaluated)
- Agents: coordinator (new), discovery, architect, engineer, security,
  accessibility (new, split from engineer), verifier, lead-reviewer.
- Coordinator runs the runbook: pre-flight, isolated agent starts, gate checks
  after each agent, human checkpoints, circuit breakers, append-only run log.
- Model assignment per agent **pass** in `config/models.example.yaml`: several
  providers can review the same area; the verifier uses a different model
  family from the author; passes can be limited to profiles.
- Findings: required stable `Key` (CHECK-ID + file), so matching doesn't depend
  on title wording; provenance header records pass, provider, model family and harness.
- Skills: audit-findings, large-codebase-navigation, ai-generated-code-quality (anti-slop catalogue).
- Profiles: node-express (check catalogue, CommonJS notes), mssql (new; tagged
  template sharp edge), azure-architecture (build once, deploy many; AVM;
  platform build requirements), web-accessibility (new; WCAG 2.2 AA), and
  nsw-local-government and ai-governance (carried over).
- Agents never execute the target or install tools; scanners are run separately.
- Evaluation: seeded issues plus known real issues, three runs, scored by Key.

### Deferred
- Findings database (the auditdb design from the earlier 2.0.0 draft); outputs are Markdown for now.
- Installer script (needs to work with macOS bash 3.2 and Windows).
- Pinned scan script or container, and kit-owned ESLint, knip and tsc configs.
- Runner that reads `models.yaml` and starts passes in other harnesses.
- PR-review mode (partial-scope runs per pull request, non-blocking first).

## Earlier
- v1–v3: single-document council audit kit specification.
- 2.0.0 draft: added auditdb and an installer; its ideas are carried into 0.1.0, and its database is deferred.
