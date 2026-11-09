---
name: javascript-review
description: Use when reviewing a JavaScript file (.js, .cjs, .mjs) or an inline <script> block, one file per pass. Gives the JS-* check catalogue for language, async, error, Node, data, security, UI framework and test mistakes, each with its evidence source, severity guide and official source.
---

# JavaScript review

## Overview
This skill is the rulebook for reviewing one JavaScript unit at a time: an own
`.js`, `.cjs`, `.mjs`, `.jsx` or TypeScript file, a section of a large one, or one
inline `<script>` block in HTML (ADR 0002 file review, ADR 0004 D10). The
`file-reviewer` agent applies it to every such unit in `units.tsv`; the `tracer`
applies it across files. When the file review is off, the engineer agent applies
it to the ten files at the top of `scans/hotspots.json` and to files over 300 lines.

The rules come from the people who maintain JavaScript and its platforms: TC39 and
MDN for the language, V8, Node.js core, the React, Vue, Svelte and Angular teams,
and OWASP. They were collected in the tech lead's jsaudit rulebook
(`javascript-craft.md`) and are restated here as checks with evidence. Concepts
from Kyle Simpson's *You Don't Know JS Yet* are restated, not quoted (the book is
CC BY-NC-ND).

You never run code to prove how the language behaves (`AGENTS.md` rule 2). Cite the
documentation instead.

## Before you start
<!-- brief: script, component, inline script -->
1. Read the whole file, or the whole `<script>` block. For an inline script, every
   line number you cite is the line in the HTML file, not in the block.
2. Read the scan rows for this file only:
   - `scans/lint.json`: messages whose `filePath` is this file
   - `scans/suppressions.json`: directives in this file (ADR 0004 D4)
   - `scans/blindspots.json` and `scans/sweep.json`: entries for this file
   - `scans/typecheck.txt`: diagnostics for this file
3. Note which frameworks the file uses (imports, globals, `detected.md`). Apply the
   UI section only for a framework the file uses.
4. List the comments that make a claim about behaviour: "already validated",
   "sanitised", "never null", "safe", "handled", "can't happen", "only called
   from". Check each one against the code below it (rule 4). A claim the code
   contradicts is a finding with Key `JS-COMMENT-CLAIM:<file>`. A claim the file
   can't settle is an open edge (ADR 0002 D3).

## How to write a finding
<!-- brief: script, component, inline script -->
Use the `audit-findings` format. For every finding:

- **Rule**: the CHECK-ID, in the Key (`JS-OR-DEFAULT:lib/upload.js`).
- **Line and excerpt**: Location plus `- Excerpt:` copied verbatim from those
  lines (ADR 0004 D1).
- **Consequence**: what goes wrong for this system, in one or two sentences. "Bad
  practice" isn't a consequence.
- **Fix**: the smallest change, as a short code sketch where it helps.
- **Severity**: from the guide in the catalogue, then these caps:
  - Critical or High needs `- Trigger:`: a concrete input or call sequence and
    what happens (ADR 0004 D7). Without one, Medium at most.
  - A finding that depends on another file (is this input validated upstream?) is
    Medium at most until a trace resolves the open edge (ADR 0002 D3).
- **Sources**: the source key from the catalogue, expanded from the list at the end.

Don't restate a lint message as a finding. Use it as the lead, read the code, and
rate the consequence. Many lint hits in one file with one cause are one finding.

When a check also exists in another catalogue, use that ID: node-express (`NODE-*`,
`EXP-*`) for server concerns and `ai-generated-code-quality` (`SLOP-*`) for dead
code, duplication and swallowed errors. The "See" column shows where.

## Check catalogue
<!-- brief: script, component, inline script -->

In the evidence column, `lint:<rule>` means a `scans/lint.json` message with that
`ruleId`, and `grep` means a pattern to search this file for.

### Language
<!-- brief: script, component, inline script -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| JS-VAR | `var`, assignments to undeclared names (implicit globals), or variables declared far wider than they're used | grep `\bvar\b`; `typecheck.txt` "Cannot find name" | Low; Medium if an implicit global holds request data in server code | MDN-var, Google-style |
| JS-LOOP-CLOSURE | A `var` loop variable captured by a callback that runs later (timer, promise, listener), so every callback sees the last value | read loops that create functions | Medium | MDN-closures |
| JS-THIS-LOST | A method passed as a callback (`setTimeout(obj.m)`, `arr.map(this.f)`, `el.addEventListener('x', this.h)`) that uses `this` | read callbacks that reference methods | Medium | MDN-this |
| JS-LOOSE-EQ | `==` or `!=` with booleans, `''`, `0`, arrays or objects. `x == null` is accepted | `lint:eqeqeq` | Low; Medium if it guards access or money | MDN-equality |
| JS-OR-DEFAULT | `a || fallback` where `0`, `''` or `false` is a valid value: a limit of 0, an empty search, a port, a flag | grep `\|\|` in assignments and parameters | Medium where it changes behaviour | MDN-nullish |
| JS-COERCION | Global `isNaN`; `parseInt` without a radix; `typeof x === 'object'` without a null check; `===` on floats; money held as a float | grep `isNaN(`, `parseInt(`, `typeof .* 'object'` | Low; Medium for money or IDs | MDN-isNaN, MDN-parseInt |

### Async and the event loop
<!-- brief: script, component, inline script -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| JS-FLOATING | A promise neither awaited, returned, nor given a `.catch`: the work may not finish and its error goes nowhere | read calls to `async` functions and promise APIs | Medium; High on payment, submission or data-writing paths | Node-errors, Collina | NODE-UNHANDLED |
| JS-ASYNC-FOREACH | `forEach(async ...)`, or an `async` callback to `map` without `Promise.all`: nothing waits and errors are unhandled | grep `forEach\(\s*async` | Medium–High | MDN-forEach | |
| JS-SERIAL-AWAIT | Independent `await`s in a row, or `await` in a loop over independent items | `lint:no-await-in-loop` | Low; a performance hypothesis with a named n (ADR 0002 D5) | V8-async | |
| JS-FANOUT | `Promise.all` over a list whose size users control, with no concurrency limit | read `Promise.all(` arguments | Medium | Node-eventloop | |
| JS-ABORT | Browser or Node network calls with no `AbortSignal` or timeout; `AbortError` and `TimeoutError` treated the same | grep `fetch(` without `signal` | Low in browser code | MDN-abort | NODE-OUTBOUND-TIMEOUT for server code |
| JS-LONG-TASK | Browser code doing long synchronous work on the main thread (large loops, parsing, sorting big lists) with no yield | read event handlers and load code | Low; a hypothesis until measured | web.dev-longtasks | NODE-BLOCKING-SYNC, NODE-REDOS for server code |
| JS-ZALGO | A function that calls its callback synchronously on some paths and asynchronously on others (often a cache hit) | read functions taking callbacks | Medium | Node-eventloop | |
| JS-PROMISE-WRAP | `new Promise` wrapped around something that already returns a promise; an `async` executor | `lint:no-async-promise-executor`, `lint:no-promise-executor-return` | Low; Medium if a rejection is lost | MDN-promise | |

### Errors
<!-- brief: script, component, inline script -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| JS-CAUSE-DROPPED | A rethrow or wrapped error that drops the original (`throw new Error('failed')` inside `catch (e)` without `{ cause: e }`) | read `catch` blocks | Low; Medium on integration clients | MDN-cause | |
| JS-ERROR-LOGGED-EMPTY | `JSON.stringify(err)` or spreading an error into a log object: `message` and `stack` aren't enumerable, so the log shows `{}` | grep `stringify\(\s*(e\|err\|error)\b` | Medium (failures can't be diagnosed) | MDN-error | NODE-LOGGING |
| JS-PROGRAMMER-SWALLOWED | A `catch` around code whose only possible errors are bugs (`undefined is not a function`), which logs and carries on | read broad `try` blocks | Medium | Node-errors | SLOP-SWALLOW for empty catches and thrown strings |

### Node.js
<!-- brief: script -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| JS-BACKPRESSURE | `stream.write()` in a loop with its `false` return ignored, no wait for `'drain'` | grep `\.write\(` in loops | Medium for large or user-sized output | Node-streams | NODE-EMITTER-ERROR for `.pipe()` |
| JS-SERVER-TIMEOUTS | An HTTP server with `headersTimeout`, `requestTimeout` or `keepAliveTimeout` changed to unsafe values, or set to 0 | grep `Timeout\s*=` near `createServer`, `listen` | Medium | Node-http | |
| JS-PASSWORD-HASH | Passwords hashed with a fast hash (`md5`, `sha1`, `sha256`) instead of `scrypt`, `argon2` or `bcrypt` | grep `createHash\(` near `password` | High | OWASP-passwords, Node-crypto | |
| JS-INSPECT | `--inspect` or `--inspect-brk` in a production start command or host config | grep `--inspect` | High if reachable off the host | Node-security | |

### Data
<!-- brief: script, component, inline script -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| JS-MUTATE-INPUT | A function that changes an argument, a shared module object, props or state it doesn't own; `sort`, `reverse` or `splice` on a caller's array | read functions that assign to parameter properties | Medium | TC39-ES2023 |
| JS-SORT-NUMERIC | `sort()` with no comparator on numbers or dates: it sorts as strings | grep `\.sort\(\s*\)` | Medium (wrong order shown or used) | MDN-sort |
| JS-SHALLOW-COPY | A spread, `Object.assign` or `Object.freeze` treated as a deep copy or deep freeze | read the copies and later writes | Medium | MDN-structuredClone |
| JS-DATE-MATH | Date arithmetic by hand (adding milliseconds for days, `getHours` maths), local time used where the business rule is in a named time zone, dates parsed from non-ISO strings. Daylight saving changes break these | grep `new Date\(`, `setDate\(`, `86400000`, `getTimezoneOffset` | Medium; High for deadlines, fees or legal dates | MDN-Temporal, MDN-date |

### Security
<!-- brief: script, component, inline script -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| JS-DOM-XSS | Untrusted data (URL, `location`, `postMessage`, storage, API responses with user content) written to `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `on*` attributes, or a framework escape hatch (`dangerouslySetInnerHTML`, `v-html`, `{@html}`, `[innerHTML]`) without DOMPurify or encoding | grep the sinks; trace each to its source | High; Critical if stored and shown to staff | OWASP-XSS, OWASP-DOM | NODE-DANGEROUS-SINK for `eval` |
| JS-URL-SINK | Untrusted data assigned to `location`, `href`, `src` or `window.open` without checking the scheme, so `javascript:` URLs run | grep `location\s*=`, `\.href\s*=`, `\.src\s*=` | High if the source is user-controlled | OWASP-DOM | |
| JS-PROTO-POLLUTION | User-supplied keys used on a plain `{}` (`obj[key] = value`), or untrusted JSON deep-merged or cloned by hand, so `__proto__` or `constructor` keys change every object | grep `\[[a-zA-Z_.]+\]\s*=`, `merge(`, `extend(` | High if reachable from input | OWASP-proto | |

`NODE-INSTALL-SCRIPTS`, `NODE-LOCKFILE`, `NODE-TIMING-COMPARE`, `NODE-SSRF` and
`NODE-PATH-TRAVERSAL` cover the rest of the source's security section.

### UI frameworks (only for a framework the file uses)
<!-- brief: script, component, inline script -->

All five major frameworks say the same thing: derive values, don't sync them, and
use effects only to talk to systems outside the framework.

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| JS-UI-EFFECT-DERIVE | An effect or watcher (`useEffect`, `watch`, `$effect`, `effect()`, `createEffect`) that computes a value from props or state, or copies one piece of state into another | read every effect | Low; Medium if it loops or shows stale data | React-effects, Vue-style, Svelte-effect, Angular-effect |
| JS-UI-EFFECT-EVENT | Logic for a user action placed in an effect instead of the event handler | read effects that check a flag set by a handler | Low–Medium | React-effects |
| JS-UI-EFFECT-CLEANUP | An effect that starts a fetch, listener, timer or subscription with no cleanup, or omits values it reads from its dependencies | `react-hooks/exhaustive-deps` if the target's lint ran; otherwise read | Medium (races, leaks) | React-effects |
| JS-UI-PROPS | Props mutated, or copied into state so later changes are ignored (unless named `initialX`) | read assignments to props | Medium | Vue-props, React-rules |
| JS-UI-KEY | The array index used as the key for a list that reorders, filters or inserts; Vue `v-if` on the same element as `v-for` | grep `key=\{(i\|index\|idx)\}`, `:key="index"` | Low–Medium | React-rules, Vue-style |
| JS-UI-IMPURE-RENDER | Side effects, `Date.now()`, `Math.random()` or mutation during render | read render bodies | Medium | React-rules |

### Tests (for test files)
<!-- brief: script, component -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| JS-TEST-INTERNALS | Tests that assert on private functions, internal state, CSS classes or component instance names instead of behaviour | read assertions | Low | reviewer judgement (Dodds) |
| JS-TEST-OVERMOCK | Tests that mock the module under test or its own collaborators, instead of the network boundary, so they pass whatever the code does | read `jest.mock`, `sinon.stub`, `vi.mock` targets | Medium | reviewer judgement (Dodds) |

A test that can't fail belongs to the engineer agent's test review.

### Engine performance
<!-- brief: script, component, inline script -->

V8's advice on object shapes, holey arrays and `delete` is real, but static review
can't show that it matters. Record it only as a performance hypothesis on a hot path
with a named n (ADR 0002 D5), never as a finding on its own. Source: V8-shapes,
V8-elements.

## Suppressions
<!-- brief: script, component, inline script -->
For each entry in `scans/suppressions.json` for this file:

- With a reason that the code bears out: nothing to report.
- No reason, over a correctness rule (`no-floating-promises`, `eqeqeq`,
  `no-unused-vars`, a type error): read the line it hides. If the hidden problem is
  real, report it under its own check and mention the directive. If not, report
  `JS-SUPPRESSED-NO-REASON` at Low, once per file.
- `@ts-nocheck` or a file-wide `eslint-disable`: always say what it hides, in
  Limitations if you can't tell.

## Rationalisations (and rebuttals)
<!-- brief: script, component, inline script -->
| Excuse | Rebuttal |
|---|---|
| "Everyone writes `||` for defaults." | It's only a finding where `0`, `''` or `false` can arrive. Show the value, or leave it out. |
| "The lint rule fired, so it's a finding." | Lint is the lead. The consequence comes from reading the code. |
| "This is slow." | Name n, who controls it, and the lines. Without a measurement it's a hypothesis. |
| "The comment says it's validated." | A comment is a claim. Find the validation, or record an open edge. |
| "XSS, obviously." | Show the source and the sink, each with an excerpt. Encoding in between kills the finding. |
| "Modern code should use `const`." | Style isn't a finding. `var` matters only where its scope causes a bug. |

## Red flags
<!-- brief: script, component, inline script -->
- A finding with no consequence for this system
- High or Critical without a Trigger
- A check from the UI section on a file that doesn't use that framework
- An excerpt you didn't copy from the file
- A performance claim with no n

## Verification (before you finish the file)
<!-- brief: script, component, inline script -->
- [ ] Every claim-making comment checked, and contradictions recorded
- [ ] Every lint, sweep and blind-spot row for this file read and either used or dismissed
- [ ] Every suppression in this file handled
- [ ] Every finding has an Excerpt, Consequence and Fix; every High has a Trigger
- [ ] Questions about other files recorded as open edges, not answered by guessing

## Sources
<!-- brief: script, component, inline script -->
Official:
- MDN-var: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/var
- MDN-closures: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Closures
- MDN-this: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/this
- MDN-equality: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Equality_comparisons_and_sameness
- MDN-nullish: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Nullish_coalescing
- MDN-isNaN: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/isNaN
- MDN-parseInt: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/parseInt
- MDN-forEach: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/forEach
- MDN-promise: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise
- MDN-abort: https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static
- MDN-cause: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error/cause
- MDN-error: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error
- MDN-sort: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/sort
- MDN-structuredClone: https://developer.mozilla.org/en-US/docs/Web/API/Window/structuredClone
- MDN-date: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Date
- MDN-Temporal: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal
- TC39-ES2023 (change array by copy): https://github.com/tc39/proposal-change-array-by-copy
- V8-async: https://v8.dev/blog/fast-async
- V8-shapes: https://mathiasbynens.be/notes/shapes-ics (by V8 team members)
- V8-elements: https://v8.dev/blog/elements-kinds
- web.dev-longtasks: https://web.dev/articles/optimize-long-tasks
- Node-eventloop: https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop
- Node-streams: https://nodejs.org/en/learn/modules/backpressuring-in-streams
- Node-errors: https://nodejs.org/api/errors.html
- Node-http: https://nodejs.org/api/http.html#serverrequesttimeout
- Node-crypto: https://nodejs.org/api/crypto.html#cryptoscryptpassword-salt-keylen-options-callback
- Node-security: https://nodejs.org/en/learn/getting-started/security-best-practices
- OWASP-XSS: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP-DOM: https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html
- OWASP-proto: https://cheatsheetseries.owasp.org/cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.html
- OWASP-passwords: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- React-effects: https://react.dev/learn/you-might-not-need-an-effect
- React-rules: https://react.dev/reference/rules
- Vue-style: https://vuejs.org/style-guide/
- Vue-props: https://vuejs.org/guide/components/props.html#one-way-data-flow
- Svelte-effect: https://svelte.dev/docs/svelte/$effect
- Angular-effect: https://angular.dev/guide/signals/effect
- Google-style: https://google.github.io/styleguide/jsguide.html
- ESLint rules: https://eslint.org/docs/latest/rules/

Community, reviewer judgement only (cite as `Source: none – reviewer judgement
(<name>)`):
- Kyle Simpson, *You Don't Know JS Yet*: https://github.com/getify/You-Dont-Know-JS
- Matteo Collina (Node.js TSC), make-promises-safe: https://github.com/mcollina/make-promises-safe
- Kent C. Dodds, "Testing Implementation Details" and "The Testing Trophy": https://kentcdodds.com/blog
- Dan Abramov, "Writing Resilient Components": https://overreacted.io/writing-resilient-components/

These URLs come from the jsaudit rulebook. All of them resolved (HTTP 200) on
2026-11-07; the rules restate that rulebook and weren't each re-read against
their page, so cite the page only after reading the part you rely on.
