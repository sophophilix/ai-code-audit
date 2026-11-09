# Architecture of the kit's Python tooling

> Status: Approved
> Created: 2026-11-06T08:12:03Z
> Last reviewed: 2026-11-06T15:36:40Z
> Next review: Not scheduled

## Review guide

Decision requested: accept the 0.9.0 update (bin/kit ported to Python; exceptions E1
and E2 removed) and the proposed next boundary, the findings database (removes E3).

- [ ] The new boundaries (settings, console, runner, state, projects, workspaces, scans, outputs, machine).
- [ ] Two Semgrep rules that enforce the architecture: writes only through `Workspace`, programs only through `runner`.
- [ ] The findings database as the next boundary.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The kit has three Python tools: detection, seeding and output verification.
`bin/kit` (bash) calls them. The python-review at commit `6374dc7` rejected them.
There was no locked environment, writes could escape the workspace, input
validation was missing at the `package.json` boundary, and types were missing.

This record moves the tools into one typed package, `audit_kit`, run through uv.
The untrusted target repository is reached only through one confined workspace
adapter. Each operation has one command handler.

## Evidence

- System shape: a command-line tool. `bin/kit` and the Makefile call it; a person runs those. Audit agents never run it (`core/runbook.md`, "Scans").
- Operations finish in seconds on a repository the size of the pilot app: about 23,000 text lines and 200 files.
- Trust boundaries:
  - The target repository is untrusted data. The review reproduced writes outside the workspace through `package.json` `main` and through a symlink (finding F2).
  - Agent outputs in `.audit/` are produced by AI and also untrusted. `location_ok()` followed `../` paths (F8).
  - Project files in `~/audit-projects/<name>/` are written by the tech lead and trusted.
- The tools read local files only. The one exception is `kit lookup` (C5), which a
  person runs and the engagement policy must allow.
- No service, scale or latency targets exist. None are invented here.

## Decision

The decision record follows.

```yaml
architecture:
  schema_version: 2
  project: agent-audit-kit (Python tooling)
  recorded_at: "2026-11-06T08:12:03Z"
  last_reviewed_at: "2026-11-06T09:01:03Z"
  record_path: docs/architecture/ARCHITECTURE.md
  mode: legacy_refactor
  system_shape: cli

  problem: >-
    The detect, seed and verify tools support a tech lead who runs AI code audits.
    They must read an untrusted repository and AI-written outputs safely,
    deterministically and with typed contracts. The 0.7.0 scripts failed review
    (rejected at 6374dc7).
  consumers:
    - bin/kit (bash), called by the Makefile and by the tech lead
  entry_points:
    - "bin/kit <command> (wrapper for `uv run audit-kit <command>`)"
    - "audit-kit doctor | tools | tag | project | workspace | seed | install | detect | check-data | scan | units | ready | diagrams | publish | status | list | selftest"
    - "audit-kit review <workspace> [--units IDS] [--reuse-from WORKSPACE] [--dry-run]"
    - "audit-kit store <workspace> | cost <workspace>"
    - "audit-kit query <workspace> <SQL> [--format table|csv|json]"
    - "audit-kit detect <workspace> [--commit SHA] [--kit-version V]"
    - "audit-kit seed <workspace> <key-file>"
    - "audit-kit verify <workspace>"
    - "audit-kit validate <workspace> [--profiles-dir DIR]"
    - "audit-kit schema"
  operation_duration: seconds

  constraints:
    - id: C1
      statement: Python 3.11 or newer; environment, lock and command execution through uv.
      source: python-standards (Runtime and layout; Supported toolchain)
    - id: C2
      statement: No read or write may resolve outside the workspace root, and symlinks are not followed.
      source: python-review 6374dc7 findings F2 and F8; AGENTS.md rule 1
    - id: C3
      statement: Never execute anything from the target repository.
      source: AGENTS.md rule 2
    - id: C4
      statement: The same commit and inputs give byte-identical detect output, so `make ready` stays idempotent.
      source: tests/e2e (ready re-run makes no new commit); CHANGELOG 0.6.0
    - id: C5
      statement: >-
        No network access at run time, except `kit lookup`: run by a person, only when
        .audit/policy.yaml sets network.metadata_lookups to allow, https to the hosts in
        lookups.HOSTS only, sending package and repository names and versions, never
        code, file contents or hashes.
      source: AGENTS.md rule 3 (agents never connect); tech lead decision 2026-11-06 (fixed safety rules in the kit, client rules in policy.yaml)
    - id: C9
      statement: >-
        `kit review`, run by a person, sends each unit's brief (its code and scan
        rows) to the model provider through the Claude Code CLI, with no tools, no
        customisations (`--safe-mode`) and no session kept, from an empty working
        folder. It's the same
        provider the intake approves for every agent; the kit itself opens no
        connection (C5 is unchanged for the kit's own code).
      source: ADR 0007 D1, D3 and D8
    - id: C10
      statement: >-
        `kit query` reads the findings store read-only with external access off and
        the configuration locked, so a query can't write, read files, attach
        databases or load extensions.
      source: ADR 0007 D6; AGENTS.md rule 2
    - id: C6
      statement: Seeding either applies every plant or leaves the workspace unchanged.
      source: python-review 6374dc7 finding F6
    - id: C7
      statement: Every program the kit starts is started by audit_kit.runner with an argument list and an explicit timeout.
      source: python-style-guide (proportional reliability controls, subprocess boundaries); enforced by .semgrep.yml subprocess-only-in-runner
    - id: C8
      statement: bin/kit and bin/checkpoint stay thin shell entry points; bin/checkpoint must run without the kit's Python environment because agents call it.
      source: tech lead decision 2026-11-06 (port of bin/kit); core/skills/checkpointing

  principles:
    - dependencies point toward policy
    - side effects stay visible
    - variable dependencies are explicit
    - one entry point per operation
    - configuration is loaded once

  patterns:
    - name: CLI command handler plus adapters
      used: true
      reason: Three operations, each with one handler in cli.py; file access goes through one adapter.
    - name: Confined workspace adapter
      used: true
      reason: One place enforces C2 for every read and write, instead of path checks in each tool.
    - name: Pydantic boundary model for package.json
      used: true
      reason: package.json is external JSON; a list-shaped dependencies field crashed detection (F3).
    - name: Immutable value objects (frozen dataclasses)
      used: true
      reason: Detection, Plant and Finding replace loose dicts (F10) so mypy strict can check them.
    - name: Plan then apply (staged writes with rollback)
      used: true
      reason: Seeding computes every plant before writing and restores originals on failure (C6).
    - name: Pydantic models for models.yaml, exporting JSON Schema
      used: true
      reason: Unknown keys are errors (a typo can't be silently ignored), and the committed schema lets editors and non-Python tools validate the same file.
    - name: Repository or unit of work
      used: false
      reason: There is no persistent store; outputs are files.

  boundaries:
    - name: cli
      path: src/audit_kit/cli.py
      owns: argument parsing, calling one handler, mapping errors to exit codes, stdout and stderr
      may_depend_on:
        - detection
        - seeding
        - verification
        - validation
        - workspace
        - errors
    - name: workspace
      path: src/audit_kit/workspace.py
      owns: confined path resolution, the full file walk, streaming digests, size-limited reads, staged writes
      may_depend_on:
        - errors
    - name: inventory
      path: src/audit_kit/inventory.py
      owns: one record per target path, file classes from the pinned Linguist data and kit rules, scan exclusions (ADR 0001)
      may_depend_on:
        - workspace
        - errors
    - name: manifest
      path: src/audit_kit/manifest.py
      owns: parsing and validating package.json into a typed model
      may_depend_on:
        - errors
    - name: detection
      path: src/audit_kit/detection.py
      owns: profile rules, facts, rendering detected.md and writing inventory.json
      may_depend_on:
        - inventory
        - workspace
        - manifest
        - intake
    - name: seeding
      path: src/audit_kit/seeding.py
      owns: choosing plant locations (pure), the plant catalogue, applying a plan, rendering the key
      may_depend_on:
        - detection
        - manifest
        - workspace
        - errors
    - name: verification
      path: src/audit_kit/verification.py
      owns: parsing audit outputs and running the automated output checks
      may_depend_on:
        - workspace
    - name: intake
      path: src/audit_kit/intake.py
      owns: parsing the six required intake fields and profile overrides from project.md
      may_depend_on: []
    - name: policy
      path: src/audit_kit/policy.py
      owns: the typed .audit/policy.yaml model (per-client rules; every default denies)
      may_depend_on:
        - workspace
        - errors
    - name: lookups
      path: src/audit_kit/lookups.py
      owns: the only network boundary (allow-listed https GETs with a timeout) and reading npm, GitHub and endoflife.date answers
      may_depend_on:
        - inventory
        - manifest
        - workspace
        - errors
    - name: models_config
      path: src/audit_kit/models_config.py
      owns: the typed models.yaml model and cross-reference checks
      may_depend_on: []
    - name: validation
      path: src/audit_kit/validation.py
      owns: reading models.yaml and project.md, rendering validation.md, exporting the schema
      may_depend_on:
        - intake
        - models_config
        - workspace
        - errors
    - name: settings
      path: src/audit_kit/settings.py
      owns: kit, project, workspace and tool locations, loaded once in cli.main
      may_depend_on:
        - errors
    - name: runner
      path: src/audit_kit/runner.py
      owns: starting programs (argument lists, timeouts, error mapping); the only subprocess boundary
      may_depend_on:
        - errors
    - name: console
      path: src/audit_kit/console.py
      owns: the ok, skip and warn output format
      may_depend_on: []
    - name: lifecycle
      path: src/audit_kit/{projects,workspaces,scans,outputs,machine,state}.py
      owns: project folders, workspace create from git, folder or tar sources, seal, install and status, the snapshot cross-check, data check and scanners, diagrams and publishing, doctor, tools and tag
      may_depend_on:
        - inventory
        - lookups
        - policy
        - workspace
        - runner
        - console
        - settings
        - detection
        - seeding
        - validation
        - file_review
        - errors
    - name: file_review
      path: src/audit_kit/{units,skill_sections,scan_rows,brief,gates,file_record,headless,ledger,review,store}.py
      owns: >-
        units; skill sections by tag; scan rows by file, parsed through
        Pydantic boundary models; briefs; gate tables; the pass output schema,
        record checks and stored records; the claude -p adapter (headless);
        the pass ledger and unit status; review orchestration and reuse by
        hash; and the DuckDB findings store
      may_depend_on:
        - inventory
        - detection
        - verification
        - models_config
        - validation
        - lifecycle
        - workspace
        - runner
        - console
        - settings
        - errors
    - name: errors
      path: src/audit_kit/errors.py
      owns: the AuditKitError hierarchy
      may_depend_on: []

  process_wide_facilities: []

  current_exceptions:
    - id: E3
      applies_to: src/audit_kit/verification.py
      reason: Findings live in Markdown and are parsed with regular expressions.
      risk: Format drift in agent output can hide or create check failures.
      removal_condition: >-
        The findings database stores typed findings and verification reads from it.
        Since 0.17.0 file records are typed JSON (ADR 0007 D3) and the store is
        built from them; stage 1 to 5 outputs are still parsed from Markdown.

  rejected:
    - pattern: structlog and OpenTelemetry in the tools
      reason: Short local CLI runs; stdout for the summary and stderr for diagnostics is proportional (python-style-guide, small local CLIs).
    - pattern: Plugin system for seed catalogues
      reason: Only the Node and Express catalogue exists; a typed list is enough until a second stack arrives.
    - pattern: Async I/O
      reason: No concurrent I/O; reads are local and fast.
    - pattern: One interface per library
      reason: Only the file-system boundary needs a seam; pydantic and the standard library are used directly.

  trade_offs:
    - PyYAML becomes a second runtime dependency, loaded only with yaml.safe_load, so models.yaml can be validated without an AI reading it.
    - Pydantic becomes the first runtime dependency, so running the tools needs a uv-synced environment, in exchange for validated input at the package.json boundary.
    - Refusing symlinks may skip a legitimately linked file in a target repository; detect lists skipped symlinks so a person sees them.
    - The Makefile and bin/checkpoint still need a POSIX shell, so Windows users run the kit in WSL2 or Git Bash; the Python CLI itself runs anywhere uv does.
    - DuckDB becomes the third runtime dependency (pinned, ADR 0007), so agents can query every record instead of reading it; the store is rebuilt from the JSON records, which stay the source of truth.
    - lifecycle and file_review depend on each other: `kit scan` writes the briefs (scans calls review.prepare), and review resolves workspaces through lifecycle (workspaces.locate). There's no import cycle: scans imports review, review imports workspaces, and workspaces imports neither. Moving locate out of lifecycle would remove the two-way dependency.
    - DuckDB writes its own file, at a path from Workspace.path (C2), then Workspace.move puts it in place; that write isn't through Workspace.write_text.
    - Semgrep's write rule relies on the naming convention `ws` / `<object>.ws` for Workspace objects, because Semgrep rejected the typed form for Python.

  next_boundary:
    target: >-
      A findings store: agents' findings recorded as typed records (the deferred auditdb
      design) rather than parsed from Markdown, with verify and the lead reviewer reading
      from it. Removes E3.
    completion_signal: >-
      Verification reads typed findings, Markdown reports are generated from the store,
      and findings round-trip through a committed findings.jsonl.
```

## Error and exit contract

| Exit | Meaning | Stream |
|---|---|---|
| 0 | Success | Summary on stdout |
| 1 | `verify` found failed checks, `validate` found errors, or the data check found files | Results on stdout |
| 2 | Invalid input or refused operation (`AuditKitError`), such as a path outside the workspace, a non-eval workspace for seeding, or an existing key file | Message on stderr |
| 3 | Unexpected internal error, caught only at the CLI boundary | Exception type and message on stderr |

## Test layout

- `tests/unit/`: pytest functions with `tmp_path` fixtures, one module per boundary, including the regression tests for review findings F2, F3, F5, F6 and F8.
- `tests/e2e/`: pytest end-to-end tests of the whole lifecycle through `cli.main`, plus one test that drives `bin/kit` itself.
- Branch coverage of at least 80% for the `audit_kit` package, enforced in `pyproject.toml`.

## Risks and open items

- Pydantic needs network access once for `uv sync`; after that, runs are offline.
- E3 depends on the deferred findings database.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-06T08:12:03Z | Drafted | Initial version, from python-review at `6374dc7`. |
| 2026-11-06T08:31:29Z | Approved | Approved by the tech lead after the 0.7.1 implementation passed python-review at `1319fe8`. |
| 2026-11-06T08:34:36Z | Updated for 0.8.0 | Added validate and schema, removed E4, and proposed porting bin/kit to Python as the next boundary. |
| 2026-11-06T08:50:38Z | Approved | Approved by the tech lead, including the port of bin/kit to Python (0.9.0), after weighing Windows use (WSL2) against keeping bash. |
| 2026-11-06T08:58:08Z | Updated for 0.9.0 | bin/kit ported to Python behind a thin wrapper; E1 and E2 removed; constraints C7 and C8; runner and write rules enforced by Semgrep; findings store proposed as the next boundary. |
| 2026-11-06T09:01:03Z | Approved | Approved by the tech lead: 0.9.0 boundaries, the Semgrep architecture rules, and the findings store as the next boundary. |
| 2026-11-06T13:31:37Z | Updated for 0.11.0 | C5 now allows `kit lookup` when the engagement policy allows it; new `policy` and `lookups` boundaries. Awaiting review. |
| 2026-11-06T13:19:04Z | Updated for 0.10.0 | New `inventory` boundary (ADR 0001); `workspace` walks every file and hashes it; lifecycle ingests folders and tar archives and cross-checks the inventory against the snapshot commit. `Workspace.write_bytes` added to the Semgrep write rule. Awaiting review. |
| 2026-11-06T15:36:40Z | Approved | Approved by the tech lead (typed "approve"): the 0.10.0 and 0.11.0 updates. The 0.12.x changes (`unused` boundary, eval delta list written to the project's `keys/`) aren't described here yet. |
| 2026-11-08T03:22:57Z | Updated for 0.17.0 | ADR 0007: new `file_review` boundary (briefs, gates, typed file records, `kit review`, the DuckDB store, `kit query` and `kit cost`); constraints C9 and C10; DuckDB dependency; E3 narrowed. Awaiting review. |
| 2026-11-08T08:17:07Z | Updated for 0.17.0 | After the python-standards, python-style-guide and python-testing pass: `file_review` split into `skill_sections`, `scan_rows`, `brief`, `headless`, `ledger`, `review` and `store`, with Pydantic boundary models for scan files, the Claude Code envelope, briefs, records and the ledger. Recorded the two-way dependency with `lifecycle`; C9 now says `--safe-mode` (customisations off), not "no settings". Awaiting review. |
