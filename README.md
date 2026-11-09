# agent-audit-kit

A reusable, harness- and model-independent kit for running an **independent,
evidence-based code audit with AI agents**, with humans making every decision.

> **Status: 0.1.0, definitions only.** Agents, skills, profiles, runbook and
> model configuration are written. The kit has **not yet passed its own
> evaluation** (`evals/`). Don't rely on its output until it has.

## How it works

```
 Stage 0  coordinator: pre-flight (approvals, clean disposable workspace, scans, evaluation)
 Stage 1  discovery                                   ◆ CHECKPOINT 1 (tech lead)
 Stage 2  architect | engineer | security | accessibility   parallel, isolated,
                                                      one or more model passes each
 Stage 3  verifier: fresh context, different model family from the author
 Stage 4  lead reviewer: report, briefing deck, ADRs, Boards backlog   ◆ CHECKPOINT 2 (tech lead)
```

- **You don't need to know the system to start.** The intake is six lines only a
  person can supply. `kit detect` (no AI) proposes profiles and exclusions from the
  files; discovery works blind and proposes what the system is; you confirm at
  Checkpoint 1. Team beliefs, if any, are tested only after the facts are saved.
- **The coordinator runs the process and decides nothing.** Only the tech lead
  passes checkpoints, changes scope or relaxes a rule.
- **Agents are read-only and never run the target.** Deterministic scanners
  (dependency audit, secrets, SAST, duplication, unused code, type check) are
  run separately by a human or pipeline; agents triage their output.
- **Every finding has a stable Key** (CHECK-ID + file), so passes by different
  models, and runs months apart, can be compared without relying on wording.
- **Each file review pass reads one prepared brief** (ADR 0007). `kit units`
  writes one brief per unit. `kit review` runs each pass as `claude -p` with no
  tools and that brief as its only input, checks the JSON it returns, and keeps
  the records of units that haven't changed. `kit store` puts every record in a
  DuckDB file that later agents read with `kit query`, and `kit cost` totals
  tokens, cost and time per stage and model.
- **Interruptions don't lose work.** Agents save after every small work item;
  a new session resumes from a short plan and capsule, not from scratch
  (`core/skills/checkpointing`). Cost and usage via OpenTelemetry: `docs/observability.md`.
- **Several models can review the same thing.** `config/models.example.yaml`
  assigns a provider, model and harness to each agent pass. The verifier
  checks each finding with a model family that didn't write it.

## Layout

```
AGENTS.md                 rules for every agent
THIRD_PARTY.md            pinned third-party skills, with review notes
VERSION, CHANGELOG.md
bin/kit, Makefile         thin wrappers for `uv run audit-kit <command>` (all logic is in Python)
bin/checkpoint            commits .audit/ only, on audit/* branches (resume points)
src/audit_kit/            Python package: every kit command (`bin/kit help` lists them)
tests/                    pytest unit and end-to-end tests
docs/architecture/        architecture record for the Python tooling
pyproject.toml, uv.lock   locked environment; `make check` runs every quality gate
config/models.example.yaml   which provider/model/harness runs each agent pass
config/models.schema.json    JSON Schema for models.yaml (editor validation; `audit-kit schema`)
core/
  runbook.md              stages, checkpoints, circuit breakers, multi-pass rules
  agents/                 coordinator, discovery, architect, engineer, security,
                          accessibility, verifier, lead-reviewer
  skills/                 audit-findings, large-codebase-navigation,
                          ai-generated-code-quality (anti-slop),
                          architecture-diagrams (rules for the pinned drawio-skill),
                          audit-publishing (Markdown → Marp slides, Pandoc Word/PowerPoint),
                          checkpointing (save after every item, LOCK, resume)
profiles/                 swappable knowledge, picked per project
  node-express/  mssql/  azure-architecture/  web-accessibility/
  nsw-local-government/  ai-governance/
templates/                project.md (+ example)
evals/                    finding evals (seeded + known issues) and output checks
adapters/
  claude-code/            subagent wrappers, /audit command, permission example
  generic/                how to run with any other agent tool
```

## Using it on a project
```zsh
make doctor && make tools && make tag        # once per machine / kit version
make project NAME=<system>                    # once per system: fill in the six-line intake
make workspace NAME=<system> SOURCE=<git url|path> REF=<commit> MODE=eval   # or MODE=real
make seed WS=<workspace>                      # eval only: plants issues, answer key outside
make ready WS=<workspace>                     # install + detect + data check + scans + validate (idempotent)
cd <workspace> && claude                      # /audit   (after a limit: /audit resume)
make diagrams publish verify WS=<workspace>
```
Every command is idempotent: re-running it does only what's missing. Run `make` for help.
On Windows, run the kit in WSL2 (or Git Bash): the Python CLI runs anywhere uv does, but
`make` and `bin/checkpoint` need a POSIX shell.

**Full guide: [`docs/how-to-run-an-audit.md`](docs/how-to-run-an-audit.md).** The steps behind the commands:

1. Make a disposable clone of the target, on branch `audit/<date>`.
2. Copy the kit in, and fill in `.audit/project.md` and `.audit/models.yaml`
   (see `adapters/claude-code/README.md` or `adapters/generic/README.md`).
3. Get the approvals `project.md` asks for: AI tool, each model provider,
   processing region.
4. Run the scans (`core/runbook.md` → Scans) into `.audit/scans/`.
5. Run the evaluation (`evals/README.md`) for this kit version and these models.
6. Run the audit: `/audit` in Claude Code, or follow `core/runbook.md` by hand.

## Extending
| Change | Put it in |
|---|---|
| A rule for every agent | `AGENTS.md` |
| How one role works | `core/agents/<role>.md` |
| Stack, cloud or regulator knowledge | a new `profiles/<name>/SKILL.md` with a check catalogue |
| One project's facts | that project's `.audit/project.md` (never in this repo) |
| Tool-specific settings | `adapters/` |

Every change: bump `VERSION`, add a `CHANGELOG.md` entry, and re-run the evaluation.

## Built on
- Your v1–v3 council audit kit specification
- addyosmani/agent-skills: skill anatomy, verification gates, rationalisation tables, doubt-driven review
- Anthropic skill-creator: progressive disclosure, descriptions as triggers
- GitHub ReviewBench and published review-agent evaluations: grounded recall/precision, repeated runs
- Azure Architecture Center, Well-Architected, Azure Verified Modules; WCAG 2.2;
  OWASP; NSW OLG Cyber Security Guidelines – Local Government; DTA AI Reference Architecture
