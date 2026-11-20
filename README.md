# ai-code-audit

> **TL;DR:** AI agents audit a codebase you didn't write, without running or
> changing it. You get a report, architecture diagrams, ranked findings and a
> backlog. Every finding cites a line you can open, and a person approves the
> result. It's for tech leads and architects who must decide about a system.
> It doesn't fix code. [Try it on one file in 15 minutes](docs/tutorials/review-your-first-file.md).

Point it at a repository and get a code audit you can check. AI agents read
every file, and every finding they report cites a line you can open. A person
makes every decision.

It audits JavaScript, TypeScript and Python. It works with code written by
people, by AI coding agents, or both.

## Who it's for

It's for the person who has to decide about code they didn't write: a tech
lead, architect or reviewer. You might be taking a system over, approving it
for production, assessing a vendor's delivery, or checking what AI agents
built. You need a view of it you can defend to a governance board.

## What it solves

A review you can't check is an opinion. This kit gives you one you can check:

- Every finding quotes the lines it is about, and the kit re-reads them.
- The kit never runs, builds or changes the code it reviews.
- An independent agent tries to disprove each serious finding.
- A person approves the result at two checkpoints.

You get a current-state architecture with diagrams, findings ranked by
severity, proposed decision records, and a backlog you can import.

## What it isn't

- **Not a fixer.** It reports problems and recommends fixes. It never changes
  your code. To fix the findings, export them (`kit query`) and give them to
  your own coding agent in a separate session.
- **Not a CI gate.** A full audit takes hours and costs money. Run your
  linters and scanners in CI, and run this audit when you have a decision to make.
- **Not a penetration test.** It reads the code. It doesn't attack a running
  system, so it can't prove that a flaw can be exploited.
- **Not a replacement for people.** It's a careful second reader. A security
  review by people is still needed where the risk calls for one.

## What you get

Here is the kit's file review on an 18-line Python file with two obvious
faults. It took about 90 seconds and cost USD 0.46 at API prices. A second
run took 46 seconds and USD 0.19, and rated the first finding Medium.

| ID | Severity | Check | Line | Finding |
|---|---|---|---|---|
| FILE-u001-001 | high | PY-SQL-STRING | 8 | SQL injection in `find()`: text interpolated into a LIKE query |
| FILE-u001-002 | medium | SLOP-SWALLOW | 16 | `delete()` swallows database errors and always returns True |
| FILE-u001-003 | medium | SLOP-COMMENT | 12 | Docstring on `delete()` claims it reports whether the delete worked |
| FILE-u001-004 | low | PY-SQLITE-TX | 14 | No rollback after a failed write in `delete()` |
| FILE-u001-005 | low | SLOP-INCONSISTENT | 8 | Two query styles in one file |

Each finding comes with the lines it quotes, what goes wrong, a fix, an
official source and the reason for its severity. For the second one:

> Medium question answered yes: "The caller or the person is told the operation
> succeeded after it failed". Line 18 (`return True`) runs after the handler at
> lines 16-17 passes on `sqlite3.Error`.

### What a full audit produces

All outputs go in the workspace's `.audit/` folder.

| File | What it holds | Who reads it |
|---|---|---|
| `01-discovery.md` | What the system does, its parts, entry points and data | You, at checkpoint 1 |
| `02-architecture.md` | Current state, risks, a target architecture and a phased path | Architects |
| `03-engineering.md` | Code quality, tests, dependencies, AI-generated code faults | Developers |
| `04-security.md` | Security findings, each with evidence and a fix | Security owner |
| `05-accessibility.md` | Accessibility findings for web front ends | Product owner |
| `06-verification.md` | Which serious findings survived an independent attempt to disprove them | You |
| `07-final-report.md` | Part A for decision-makers (about two pages), Part B with the detail | Management, governance boards |
| `08-backlog.csv` | One work item per finding, ready to import into Azure DevOps Boards | Delivery team |
| `09-briefing.slides.md` | A short slide deck (Marp) for the briefing | Stakeholders |
| `adr/` | Proposed architecture decision records. Only a person accepts them. | Architects |

### Diagrams

The architect agent draws two pictures of the system:

- **As-is:** the system as the code shows it today.
- **Target:** where it should go, matched to the phased path in the report.

Each picture is context level: at most 15 boxes, grouped by trust zone, with
official Azure icons where they apply. Every box and arrow points to the
`file:line` that shows it exists. `make diagrams` builds each one as an
editable draw.io file, plus a second file with four views of it:

| View | Shows |
|---|---|
| Executive | Only the most important parts, for a non-technical reader |
| Deployment | Where each part runs: environment and region |
| Data flow | Where data goes, and how sensitive it is |
| Security | Trust boundaries, and the paths that cross them |

The architect can add smaller diagrams that each answer one question, and
architecture rules for the target, such as "no direct path from the internet
to a data store". `make diagrams` checks the target against them.

When [draw.io](https://www.drawio.com) is installed, `make diagrams` also
exports every page as SVG (for Markdown and slides) and PNG (for Word and
PowerPoint), such as `target.png` and `target-security.png`. Without draw.io
you get the `.drawio` files only, and the command says so.

To tidy a diagram, open its `.drawio` file in draw.io. Then run
`make export-diagrams WS=<workspace>` to export your tidied version.
Don't run `make diagrams` again after tidying: it rebuilds the files and
overwrites your changes. Sequence, entity-relationship, data-flow and
lifecycle diagrams are approved but not built yet
([ADR 0009](docs/decisions/0009-more-diagram-types-on-drawio.md)).

## Quick guide

You work with two folders. Keep them apart:

- **The kit**: this repository. Clone it once and run every `make` command
  from inside it.
- **A workspace**: a disposable copy of the code you audit, which the kit
  creates for you. The agents work there. Your original repository is never
  touched.

To try it first, follow the tutorial. It reviews the 18-line file above:
**[Review your first file](docs/tutorials/review-your-first-file.md)**.

To audit a real system:

1. Clone the kit and check your tools:

   ```zsh
   git clone https://github.com/sophophilix/ai-code-audit.git && cd ai-code-audit
   make doctor                          # lists the tools you have and the ones you need
   make tools                           # installs the missing ones
   ```

2. Create a project for the system, then fill in its six-line intake:

   ```zsh
   make project NAME=my-app             # creates ~/audit-projects/my-app
   ```

3. Create the workspace from the code you want to audit:

   ```zsh
   make workspace NAME=my-app SOURCE=<git url or path> REF=<commit> MODE=real
   ```

   The workspace is `~/code/audits/my-app-real-<date>`. Add `WS_NAME=my-app`
   to choose the folder name.

4. Run the scans and checks. This step uses no AI:

   ```zsh
   make ready WS=<workspace>
   ```

5. Open Claude Code in the workspace and start the audit:

   ```zsh
   cd <workspace> && claude             # then type: /audit   (after a limit: /audit resume)
   ```

6. Go back to the kit folder. Build the diagrams, make Word, PowerPoint and
   PDF copies of the report, and check the outputs:

   ```zsh
   make diagrams publish verify WS=<workspace>
   ```

Every command is safe to run again: it does only what is missing.

## What you need

- macOS, or Linux. On Windows, use Ubuntu in WSL2.
- [git](https://git-scm.com) and [uv](https://docs.astral.sh/uv/).
- [Claude Code](https://claude.com/claude-code) and an account that can run it.
  The file review runs through it. Other agent tools can run the later stages
  (`adapters/generic/README.md`).
- `make tools` installs the scanners: gitleaks, cloc, osv-scanner, Ruff,
  Semgrep, jscpd, ESLint and TypeScript, plus Pandoc, Marp and draw.io for the
  report. It uses [Homebrew](https://brew.sh) where it can.

### On Linux and WSL2

Without Homebrew, `make tools` doesn't install the system tools. It prints the
command for each missing one instead, because most of them need `sudo`. For
example:

```text
  warn  cloc missing; install it with: sudo apt install cloc
  warn  draw.io missing; install it with: sudo snap install drawio, or the .deb from https://github.com/jgraph/drawio-desktop/releases
```

Run the commands you're happy with, then run `make doctor` again. It still
installs jscpd, ESLint, TypeScript and drawio-skill itself, which need Node.js
and git.

draw.io is only needed for the diagram images and for tidying. The audit
runs without it. With no desktop, draw.io needs a virtual display to export:
install `xvfb` (`sudo apt install xvfb`), and the kit uses it. In WSL2 you can
instead install draw.io on Windows. The kit finds it there and uses it.

## Why it's built this way

- **Evidence or it isn't a finding.** Every finding quotes the code. The kit
  re-reads the cited lines and refuses a record whose quote doesn't match.
- **It never runs your code.** Agents are read-only. They don't install,
  build or test the target, and they don't touch your services.
- **Scanners first, then agents.** Linters, secret scans and dependency audits
  give facts that repeat. Agents read those facts with the code and judge what
  matters.
- **You stay in charge.** The audit stops at two checkpoints for a person to
  read and approve. Agents never approve their own work.
- **Your repository is data, not instructions.** Agents are told to report
  text addressed to an AI, in comments or AI config files, as a finding and
  not to follow it.
- **Findings keep the same Key between runs.** You can compare two models, or
  the same code six months apart, without matching on wording.
- **You see the cost.** `kit cost` totals tokens, money and time per stage.

## Run a full audit

```
 Stage 0  pre-flight: approvals, a disposable workspace, scans
 Stage 1  file review and discovery                   ◆ Checkpoint 1 (you)
 Stage 2  architect | engineer | security | accessibility, in parallel
 Stage 3  verifier: a fresh context tries to disprove the serious findings
 Stage 4  lead reviewer: report, briefing, decisions, backlog   ◆ Checkpoint 2 (you)
```

The [quick guide](#quick-guide) has the commands.
**The full guide is [How to run an audit](docs/how-to-run-an-audit.md).**

To set your expectations: one full audit of a Python application, split into
215 review units, took about two hours of machine time and USD 89 at API
prices. Plan a day or two of your own time to read and check the results.

You don't need to know the system to start. The intake is six lines that only
a person can supply, such as who approved the use of AI. The kit detects the
stack, and the discovery agent proposes what the system does for you to
confirm.

## Where it stands

This is an early release (see `VERSION`), built and used by one person so far.
It is useful today as a careful second reader. It isn't a replacement for a
security review by people.

What has been measured, on one application with 19 faults planted by hand:

- The file review found all 18 planted faults it could see. The other one was
  in a CI workflow, which two specialist agents found.
- 15 of the 19 reached the body of the final report. All 19 were in the report
  or its register of findings.
- Severity matched the answer key exactly for 10 of 18, and within one level
  for 17.
- False alarms haven't been measured yet. Check a finding's evidence before
  you act on it. The kit is designed for that.

What to know before you rely on it:

- A full audit has been run with Claude Code on macOS only. The kit's own
  tests run on macOS and Ubuntu. One tester has started it on Ubuntu in WSL2.
- Some rules for the agents are enforced by the kit and some only by
  instruction. `CHANGELOG.md` says which, release by release, and records what
  each change did in a live run, including the results that were disappointing.
- About 700 automated tests cover the kit's own code. `make check` runs them with
  the linters, type checker and dependency audit.

## How the pieces fit

- **`kit detect`** reads the files, with no AI, and proposes the knowledge
  packs and exclusions.
- **`kit units`** splits the code into review units and writes one brief for
  each. **`kit review`** runs one pass per brief with no tools, checks the JSON
  that comes back and stores a record (ADR 0007).
- **`kit store`** puts every record in a DuckDB file. Later agents read it
  with **`kit query`**.
- **`kit register`** lists every file-review finding beside the specialist
  finding that reports it. **`kit verify`** fails if a Medium or higher is
  missing from both the report and the backlog.
- **Work survives interruptions.** Agents save after each small item and
  resume from a short plan (`core/skills/checkpointing`).
- **Several models can review the same code.** `config/models.example.yaml`
  assigns a provider and model to each agent pass.
  `config/models.single-provider.example.yaml` is the simple form.

## What's in the repository

```
AGENTS.md                 rules for every agent
core/
  runbook.md              stages, checkpoints and stop conditions
  agents/                 coordinator, discovery, file-reviewer, tracer, architect,
                          engineer, security, accessibility, verifier, lead-reviewer
  skills/                 finding format, check catalogues for JavaScript, front ends
                          and AI-generated code, diagrams, publishing, checkpointing
profiles/                 knowledge packs, picked per project (ADR 0012):
                          node-express, python, mssql, azure-architecture,
                          web-accessibility, nsw-local-government, ai-governance
config/                   example model assignments, scanner configs, schemas
src/audit_kit/            the `kit` commands, in Python (`bin/kit help` lists them)
tests/                    unit and end-to-end tests
adapters/                 Claude Code wrappers, and notes for other agent tools
evals/                    how the kit is evaluated, and the checks on its outputs
docs/                     tutorial, how-to guide, architecture record, decisions (ADRs)
templates/                the intake, with an example
```

## Make it yours

| To change | Edit |
|---|---|
| A rule for every agent | `AGENTS.md` |
| How one role works | `core/agents/<role>.md` |
| Knowledge of a stack, cloud or regulator | a new pack in `profiles/<name>/` (ADR 0012) |
| Your own practice and sector knowledge | a private pack folder outside this repository, named in `AUDIT_KIT_PACKS` |
| One project's facts | that project's `.audit/project.md`, never this repository |
| Settings for one agent tool | `adapters/` |

## Contributing

Issues and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md)
explains the checks to run and how to keep client details out of a public
repository.

## Licence

[MIT](LICENSE). Third-party rules and skills the kit uses keep their own
licences, listed in `THIRD_PARTY.md`.

## Built on

- The author's earlier audit kit specifications, versions 1 to 3
- addyosmani/agent-skills: skill anatomy, verification gates, rationalisation tables, doubt-driven review
- Anthropic skill-creator: progressive disclosure, descriptions as triggers
- GitHub ReviewBench and published review-agent evaluations: grounded recall and precision, repeated runs
- AWS, *Configuring your AI vulnerability harness, part 2*, and Cloudflare's `security-audit-skill`: severity from yes-or-no questions
- Azure Architecture Center, Well-Architected, Azure Verified Modules; WCAG 2.2;
  OWASP; NSW OLG Cyber Security Guidelines – Local Government; DTA AI Reference Architecture
