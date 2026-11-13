# ADR 0010: Audit Python targets

> Status: Proposed
> Created: 2026-11-13T21:10:00Z
> Last reviewed: 2026-11-13T21:10:00Z
> Next review: after the first Python audit's Checkpoint 2

## Review guide

Decision requested: let the kit audit a Python repository with the same depth it
gives a JavaScript one. That means detecting each ecosystem from the files (D1),
reading `pyproject.toml` and Python lockfiles (D2), running Python scanners that
never execute the target (D3), cutting Python files into units (D4), judging those
units with Python gates (D5), and giving reviewers a Python rulebook (D6). Two
detection faults found on the same run are fixed with it (D7, D8).

Check these points:

- [ ] Running Ruff with the kit's config (`--config`, `--ignore-noqa`) is safe
      under `AGENTS.md` rule 2: Ruff parses files and never imports them.
- [ ] Not type-checking Python (D3) is an acceptable limitation, rather than
      installing the target's dependencies.
- [ ] A folder whose licence file matches the root licence byte for byte is
      first-party code (D7).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The first audit of a Python application (a local-first CLI of about 30,000
lines) produced 0 file-review units. `kit detect` found no dependencies, no
lockfile, no AI signals and no profile for 100% of the code. The scans ran
ESLint, tsc and Semgrep's JavaScript rules, so they reported nothing. Two
first-party plugins were excluded as vendored code because each folder holds a
LICENSE file. The kit was built against Node.js apps and assumed that stack in
seven modules.

## Evidence

| Observation | Where |
|---|---|
| Unit extensions list JavaScript, TypeScript and SQL only | `src/audit_kit/units.py` `CODE` |
| Manifest is `package.json` only | `src/audit_kit/manifest.py` |
| Lockfiles are npm, Yarn and pnpm only | `src/audit_kit/detection.py` `LOCKFILES` |
| Dependency audit runs only with `package-lock.json` | `src/audit_kit/scans.py` `scan()` |
| Semgrep rulesets are `p/javascript`, `p/expressjs` and `p/owasp-top-ten` | `src/audit_kit/scans.py` `semgrep()` |
| Gates treat any non-JavaScript unit as not applicable | `src/audit_kit/gates.py` `_UnitView.cannot_judge` |
| A licence file marks its folder as vendored | `src/audit_kit/inventory.py` `build()`, `classify()` |
| Line counts read a PNG under `docs/` as text | `src/audit_kit/detection.py` `detect()` (only `binary` and `data-candidate` classes skipped) |

## Decision

**D1. Ecosystems come from the inventory.** `audit_kit.ecosystems` returns the
ecosystems a workspace holds: `javascript` (a `package.json` or a JavaScript or
TypeScript file) and `python` (a `pyproject.toml`, `setup.py`, `setup.cfg` or
`requirements*.txt`, or a `.py` file). Scanners, unit boundaries and manifests
are chosen by ecosystem. A repository can hold both.

**D2. Python manifests.** `pyproject.toml` is parsed with `tomllib` and checked
against a Pydantic model: `[project].dependencies`,
`[project].optional-dependencies` and `[dependency-groups]`. Recognised Python
lockfiles are `uv.lock`, `poetry.lock`, `pdm.lock` and `Pipfile.lock`.
`pyproject.toml` is a manifest unit, like `package.json`.

**D3. Python scanners never import the target.**

- Dependency audit: `osv-scanner scan source -L <lockfile>`, once per
  recognised lockfile in either ecosystem.
- SAST: Semgrep's `p/python` ruleset is added when `python` is present.
- Lint: Ruff with the kit's `config/ruff.audit.toml`, passed by `--config` so
  the target's settings never apply, and `--ignore-noqa` so the target's
  suppressions can't hide anything. That matches `--no-inline-config` for
  ESLint. The files Ruff examined come from `--show-files`. The output is
  `scans/lint-python.json`.
- Type checking is **not run** for Python. mypy and pyright need the target's
  dependencies installed, and the kit never installs them. This is written to
  `MISSING.txt`.
- Unused-code analysis stays JavaScript-only. This is written to `MISSING.txt`.

**D4. Python units.** `.py` and `.pyi` files are units. A file over 1,000 lines
is cut at a top-level `def`, `async def`, `class` or decorator. Their skill
sections are chosen by the new kind `python`.

**D5. Python gates.** A `ruff` gate joins the unit gates. For a Python unit:
`ruff` and `semgrep` apply, `complexity` reads Ruff's `C901` rows (limit 10, as
with ESLint), and `eslint`, `tsc` and `knip` are not applicable. For a
JavaScript unit, `ruff` is not applicable.

**D6. Python rules.** `core/skills/python-review` holds the `PY-*` check
catalogue for briefs and the engineer, tagged for `python` units. The
`python` profile holds the stack checks (packaging, configuration, SQLite,
subprocess, local model clients) for the stage agents, and covers the Python
language in detection.

**D7. Same-licence folders are first-party.** A folder's licence file marks it
as vendored only when its content differs from the repository's root licence.
A monorepo's first-party packages often carry a copy of the root licence.

**D8. Binary files never count as text.** Detection skips every inventory entry
marked binary when it counts lines and searches for signals.

## Consequences

- A Python audit gets units, briefs, gates, a dependency audit, SAST and lint.
- `gates.json` gains a seventh gate, so records written by 0.18.0 have six. The
  store reads gates by name, so old records still load.
- Ruff becomes a scan tool that `kit doctor` checks and `kit tools` installs.
- Python type errors remain unchecked. Reviewers see that as a limitation, not
  as a clean result.

## Rejected

- **Installing the target's dependencies to run mypy.** That breaks rule 2,
  because installing runs build backends that the target controls.
- **Running the target's own Ruff config.** The target's config can switch rules
  off. The kit's baseline must be the same for every target.
- **Bandit as a separate scanner.** Ruff's `S` rules are Bandit's checks, and
  Semgrep's `p/python` covers the rest. A third tool adds output without new
  evidence.

## Review history

| Date (UTC) | Reviewer | Outcome |
|---|---|---|
| 2026-11-13 | Claude (author) | Proposed |
