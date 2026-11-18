---
name: ai-generated-code-quality
description: Use when reviewing code written wholly or partly by AI coding agents, or any codebase built quickly by one person. Gives the "anti-slop" check catalogue, evidence sources and red flags for defects AI-generated code characteristically has.
---

# AI-generated code quality ("anti-slop")

## Overview
AI coding agents produce code that *looks* finished: it compiles, reads
fluently and often passes its own tests. The defects are structural: copied
logic instead of reuse, error paths that hide failure, code nobody calls,
and tests that can't fail. This skill turns those into checks with evidence.

It is **not** a judgement on whether AI was used. Rate each finding on its
effect on a team that has to maintain the code, exactly as you would for
human-written code. Apply Chesterton's Fence: AI-generated code often
encodes real, undocumented lessons (workarounds for a firewall, a vendor
quirk). Find out why it exists before calling it slop.

## Why it matters (evidence, with caveats)
- Package hallucination: Spracklen et al., USENIX Security 2025
  (arXiv:2406.10279) found models suggesting non-existent packages in about
  20% of samples overall (lower for commercial models), and many hallucinated
  names recur, which makes them squattable.
- Duplication up, refactoring down since AI assistants spread: GitClear's
  code-quality reports (vendor-funded; treat the figures as indicative).
- DORA 2024/2025: AI adoption associates with lower delivery stability unless
  teams keep changes small and have strong version control (survey correlation).

## Sources for the checks
No standards body publishes an "anti-slop" standard (checked November 2026).
Each check below is tied to an official rule where one exists, so a finding
can cite a scan line instead of an opinion:
- OpenSSF Best Practices and AI/ML working groups, *Security-Focused Guide for
  AI Code Assistant Instructions* (2025-08-01):
  https://best.openssf.org/Security-Focused-Guide-for-AI-Code-Assistant-Instructions
  (non-existent or hallucinated packages, parameterised queries, no secrets in
  code, no internal detail in error messages, negative tests).
- ESLint core rules, run with the kit's config into `scans/lint.json`:
  https://eslint.org/docs/latest/rules/
- Node.js, *Don't Block the Event Loop (or the Worker Pool)*:
  https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop
- Community, reviewer judgement only: `miqdadbadjuber/anti-slop` (its
  `antislop-code` comment patterns, used in SLOP-COMMENT) and
  `dmmulroy/anti-slop` (its accumulator-copy rule, used in SLOP-QUADRATIC).
  Both are MIT and describe their rules as the author's taste; neither is
  installed or run by the kit. Their other rules are style, or need TypeScript.
- The severity guide's levels are reviewer judgement. Its form, yes-or-no
  questions that code must answer, follows AWS, *Configuring your AI
  vulnerability harness, part 2: the steering file*:
  https://aws.amazon.com/blogs/security/configuring-your-ai-vulnerability-harness-part-2-the-steering-file/
  The rule "if you can't state the damage, the answer is no" follows the
  severity anchors in Cloudflare's `security-audit-skill`:
  https://github.com/cloudflare/security-audit-skill

## Check catalogue
<!-- brief: script, component, inline script, sql, markup, stylesheet, inline style, python -->
Use these CHECK-IDs in finding Keys (`SLOP-DUP:lib/foo.js`). In the evidence
column, `lint:<rule>` means a `scans/lint.json` message with that `ruleId`.

| CHECK-ID | What to look for | Evidence source |
|---|---|---|
| SLOP-DUP | Near-identical blocks or functions with small differences (copy and adapt instead of a shared helper); several implementations of the same rule | `scans/duplication.json` (blocks of 50 tokens or more); `scans/similar.json` (small named functions that mostly match another, with where they differ: the difference is often the bug); grep for distinctive literals |
| SLOP-DEAD | Unused files, exports, routes, feature switches never read, functions never called | `scans/unused.json`; `lint:no-unused-vars`, `lint:no-unreachable`, `lint:no-useless-return`, `lint:no-unused-private-class-members`; grep callers. Chesterton's Fence first |
| SLOP-SWALLOW | `catch {}` or `catch (e) {}` with no action, `.catch(() => {})`, errors logged then success returned, fallbacks that hide outages, rejections or throws that aren't `Error` objects | `lint:no-empty`, `lint:no-useless-catch`, `lint:prefer-promise-reject-errors`, `lint:no-throw-literal`; grep `catch`, read each handler |
| SLOP-PHANTOM-DEP | Dependencies declared but unused, used but undeclared, names that look like typosquats, or packages that may not exist (OpenSSF guide: hallucinated packages) | `package.json` vs imports; `scans/unused.json`; `scans/deps-audit.json`; `scans/upstream-status.json` |
| SLOP-HALLUCINATED-API | Calls to methods or options that don't exist in the installed version of a library | compare with the library's docs for the locked version |
| SLOP-OVERENG | Abstractions with one caller, configuration for things that never vary, layers that only pass through, "might be useful later" | read call sites |
| SLOP-CONFIG-SPRAWL | Very many environment switches, undocumented defaults, behaviour that depends on combinations of flags | discovery "Configuration" count; docs vs code |
| SLOP-FAKE-TEST | Tests with no assertions, assertions that can't fail, tests that mock the unit under test, scripts that print PASS without checking, tests excluded from the default run | read tests; check how they're invoked |
| SLOP-COMMENT | Comments that **contradict the code** (the finding that matters: a reader, a reviewer or another AI will trust the comment); stale headers that list files, routes or behaviour that no longer match; comments that narrate a chat ("as requested", "now updated to"). Lower weight, usually one `low` or `info` finding per file: comments that restate the next line, "Step 1/2/3" narration, decorative banners or emoji, comments that only repeat a function's signature, vague TODOs, "end if" markers | compare each header and block comment with the code it describes (`AGENTS.md` rule 4); `lint:no-warning-comments` for TODOs |
| SLOP-ASYNC | `await` in loops where the calls are independent, `async` functions with no `await`, async Promise executors, `return` inside `finally` | `lint:no-await-in-loop`, `lint:require-await`, `lint:no-async-promise-executor`, `lint:no-promise-executor-return`, `lint:no-unsafe-finally` |
| SLOP-LOGIC | Conditions that are always true or false, duplicate `else if` branches, self-comparison, loop conditions never updated, functions that return a value on some paths only, loose equality | `lint:no-constant-condition`, `lint:no-constant-binary-expression`, `lint:no-dupe-else-if`, `lint:no-self-compare`, `lint:no-unmodified-loop-condition`, `lint:consistent-return`, `lint:eqeqeq` |
| SLOP-QUADRATIC | Work that grows faster than its input on a request path: spreading or copying a growing accumulator inside `reduce` or a loop, a search (`find`, `includes`, `indexOf`, `filter`) inside a loop over the same data, string building in a loop. Name `n` and who controls it | read the loop; `lint:max-depth`, `lint:complexity` point to candidates; the claim is a hypothesis until measured |
| SLOP-INCONSISTENT | Several ways to do the same job (HTTP clients, logging styles, error shapes, validation approaches) with no reason | grep for alternatives |
| SLOP-GOD | Very large files or functions mixing routing, validation, business rules, integration and presentation; dense one-liners | `scans/cloc.json`; `lint:complexity`, `lint:max-lines-per-function`, `lint:max-params`, `lint:max-nested-callbacks`; line lengths |
| SLOP-LEFTOVER | Debug output, commented-out blocks, AI instruction files, TODOs copied from prompts, scratch scripts presented as tests | `lint:no-warning-comments`; grep `console.log`, instruction files |
| SLOP-SILENT-DEGRADE | Features that quietly turn off or fall back when config is missing, so a misconfigured production deploy looks healthy | read config defaults and the startup path |

`lint.json` thresholds (complexity 10, depth 4, 80 lines per function, 4
parameters, 3 nested callbacks) are prompts to look, not defects. A rule hit is
a finding only when you can state its consequence. `lint.json` covers `.js`
files only; inline scripts in HTML are read by hand.

For a Python unit, `lint:<rule>` means a `scans/lint-python.json` row from Ruff
with the kit's config (ADR 0010). The equivalents: SLOP-DEAD `F401`, `F841`;
SLOP-SWALLOW `S110`, `S112`, `BLE001`, `SIM105`; SLOP-ASYNC `ASYNC*`; SLOP-LOGIC
`PLR0124`, `RET503`, `SIM*`; SLOP-GOD `C901` (complexity 10), `PLR0913`
(parameters); SLOP-LEFTOVER `T20`, `ERA001`, `FIX002`. There's no unused-code
scan for Python, so search for callers before calling code dead.

## Severity guide
<!-- brief: script, component, inline script, sql, markup, stylesheet, inline style, python -->
Each check has yes-or-no questions about the consequence. Ask the High question
first, then the Medium one. The first yes sets the level. If both are no, use
the last column.

- The guide sets the level and nothing else. A fault is still a finding when
  both answers are no: report it at the level in the last column.
- A yes needs a line in this unit that shows it. Name the question and the line
  in the finding's evidence ("Medium: line 42 returns `True` after the failed
  write").
- If you can't say what goes wrong and for whom, the answer is no.
- If only another file can answer a question, record the edge and treat the
  answer as yes for now. The cap for an open edge then holds the finding at
  Medium until a trace resolves it.
- The caps still apply. High needs a trigger and must be `verified`.
- You may rate one level above or below the guide when this system gives a
  reason. State the reason in the finding. Never move a level without one.
- A "none" means the check alone doesn't reach that level. If the fault does
  more harm than that, another catalogue has a check for it.

| CHECK-ID | High if | Medium if | Otherwise |
|---|---|---|---|
| SLOP-DUP | One copy lacks a security or data-integrity check that the other copy has | The copies hold a business rule (validation, a calculation, a permission) and already differ, so one of them is wrong | Low |
| SLOP-DEAD | A security or permission check is defined and nothing calls it, so the protection it names doesn't run | A validation, a control or a feature switch is never called or read, and a reader would believe it is active | Low |
| SLOP-SWALLOW | The hidden failure loses or corrupts stored data, or skips a security or permission check. This includes a failed undo, rollback or cleanup that nothing reports | The caller or the person is told the operation succeeded after it failed, or the code continues with a default as if it had succeeded | Low: only diagnostic detail is lost |
| SLOP-PHANTOM-DEP | Code imports or declares a name that `scans/upstream-status.json` shows doesn't exist, so anyone can register it | A package is used but not declared, or an unused one has install scripts or a known advisory | Low: declared and unused |
| SLOP-HALLUCINATED-API | The call or option that doesn't exist was meant to apply a protection (a timeout, a validation, an escape, a permission), so the protection is off | The call fails or the option is ignored on a path that normal use reaches | Low: only tests or unreachable code use it |
| SLOP-OVERENG | none | The layer hides where a security, validation or transaction decision is made | Low |
| SLOP-CONFIG-SPRAWL | A default or a combination of flags turns off a security control and nothing reports it | A default that isn't documented changes behaviour in production, or behaviour depends on a combination of flags | Low |
| SLOP-FAKE-TEST | none | It's the only test in this unit for a path that handles money, access, personal data or a stored write, or a script reports a pass without checking | Low |
| SLOP-COMMENT | none | The comment states a check, a validation or a guarantee that the code doesn't perform | Low for another contradiction or a stale header. One `low` or `info` finding per file for narration |
| SLOP-ASYNC | A `return` in `finally`, an async executor or a call that isn't awaited discards the failure of a stored write or a security check | An error is lost, or the caller continues before the work has finished | Low |
| SLOP-LOGIC | The condition or missing return turns off a security check or a validation, or picks the wrong branch for money or a stored write | A branch can never run, or a caller in this unit uses the missing return value | Low: the behaviour doesn't change |
| SLOP-QUADRATIC | none until an experiment measures it | The code runs on a request path, a caller controls `n`, and nothing caps it | Low: `n` is capped, or the code is off the request path |
| SLOP-INCONSISTENT | none | One of the ways lacks a protection that the others have (a timeout, a validation, error handling, escaping) | Low |
| SLOP-GOD | none | none | Low |
| SLOP-LEFTOVER | A debug route, a bypass or a test credential is reachable in the running system | Commented-out or debug code turns off a check | Low |
| SLOP-SILENT-DEGRADE | Missing config turns off a security control, or stored writes go nowhere, and nothing reports it | A feature turns off or falls back and nothing reports it | Low: the fallback is reported and the feature isn't essential |

## Dependency manifest
<!-- brief: manifest -->
A manifest is the only place a package that nothing uses shows up: no code
file mentions it. Read every declared package against the `unused` rows, which
list each one that no own file requires or imports and no script names.

| CHECK-ID | What to look for | Evidence source |
|---|---|---|
| SLOP-PHANTOM-DEP | Dependencies declared but unused, used but undeclared, names that look like typosquats of a well-known package, or packages that may not exist (OpenSSF guide: hallucinated packages). Each unused runtime dependency is still installed and shipped, so it widens the supply chain for nothing: Low, Medium if it has install scripts or a known advisory | `unused` rows; the declared names and ranges in this file |

## Process
<!-- brief: script, component, inline script, sql, markup, stylesheet, inline style, python -->
1. Start with the scans. Deterministic tools give numbers you can repeat.
2. For each check, find the strongest 1–5 examples and read them in context.
3. Write one finding per root cause, with Key `SLOP-...:<most affected file>`.
4. Severity is set by **consequence**, not by how ugly the code is. Answer the
   questions in the severity guide for the check. A swallowed error on the path
   that submits a citizen's report is High. Duplicated formatting helpers are
   Low.
5. Close with an `info` finding giving an overall view: the patterns that
   dominate, and the order to tackle them (tests before refactors).

## Rationalisations (and rebuttals)
<!-- brief: script, component, inline script, sql, markup, stylesheet, inline style, python -->
| Excuse | Rebuttal |
|---|---|
| "It works, so it's fine." | Working today isn't maintainable tomorrow. Rate the cost of the next change. |
| "Tests exist." | Do they assert anything? Can they fail? Do they run by default? |
| "Error handling removed for cleaner code." | Cleaner code that hides failure is worse. |
| "This abstraction might be useful later." | Only real callers count. |
| "Tests were modified to pass." | That's a red flag, not a fix. |
| "It's AI code, so rewrite it." | Rewrites lose embedded knowledge. Recommend incremental change behind tests. |

## Red flags
<!-- brief: script, component, inline script, sql, markup, stylesheet, inline style, python -->
- Calling code dead without searching for dynamic use (string-built requires, routes registered in loops)
- Slop findings with no example locations
- Treating style preferences as defects
