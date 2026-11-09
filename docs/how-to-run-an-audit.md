# How to run an audit with the kit

A step-by-step guide for a tech lead auditing one repository. Allow about
half a day for setup and evaluation the first time, then one to two days
for the audit itself, mostly spent reviewing.

Commands are for macOS with zsh. Replace `<…>` placeholders.

> **Shortcut:** the kit's `Makefile` / `bin/kit` does steps 1–6 and 9–10 for you,
> idempotently (see the README). This guide explains what those commands do,
> and how to do it by hand if you need to.

---

## 0. Before you touch anything: approvals

You need these in writing, because the AI provider will read the
organisation's source code:

- [ ] The AI tool and each model provider you'll use, approved by the
      CISO / Privacy Officer (or equivalent)
- [ ] Where each provider **processes** data (region), confirmed
- [ ] Who gets a Critical finding the same day (security owner)

No approval, no audit. Pre-flight checks this.

---

## 1. Pin the kit version

```zsh
cd ~/code/github.com/sophophilix/agent-audit-kit
git status                       # must be clean
git tag v$(cat VERSION)          # once per release; skip if already tagged
KIT=$PWD
KIT_VERSION=$(cat VERSION)
```

Every output records this version, so results can be compared later.

---

## 2. Make a disposable workspace

Never audit your working copy. Clone fresh into a separate folder:

```zsh
AUDIT_DATE=$(date -u +%Y-%m-%d)
WS=~/code/audits/<repo-name>-$AUDIT_DATE
git clone <repo-url> "$WS"
cd "$WS"
git branch -a                    # find where the code actually is
git checkout <branch-with-the-code>
git checkout -b audit/$AUDIT_DATE
git rev-parse HEAD               # note this SHA: it's what you're auditing
```

> **Check which branch holds the code.** After an import, `main` may hold only
> a README while the code sits on a feature branch. Audit the branch that will
> go to production, and write its SHA in `project.md`.

**Data check.** Run the "Data check" commands in `.audit-kit/core/runbook.md`
(after step 3 has copied the kit in). Data files, credentials or dumps in the
tree or history stop the audit until they're removed from the workspace, or an
exception is approved and recorded.

**AI instruction files in the target** (`CLAUDE.md`, `AGENTS.md`, `.claude/`,
`.cursorrules`, `.github/copilot-instructions.md`): Claude Code and other tools
load these automatically. Move them aside on the audit branch:

```zsh
mkdir -p .audit/quarantine
for f in CLAUDE.md AGENTS.md .claude .cursorrules .github/copilot-instructions.md; do
  [ -e "$f" ] && git mv "$f" .audit/quarantine/ && echo "quarantined $f"
done
```

---

## 3. Install the kit into the workspace

```zsh
mkdir -p .audit-kit .audit/scans .audit/adr .claude/agents .claude/commands .claude/skills
cp -R "$KIT"/{AGENTS.md,VERSION,core,profiles,evals,templates,config} .audit-kit/
cp "$KIT"/adapters/claude-code/agents/*.md   .claude/agents/
cp "$KIT"/adapters/claude-code/commands/*.md .claude/commands/
cp -R "$KIT"/core/skills/* "$KIT"/profiles/* .claude/skills/
cp "$KIT"/templates/project.md       .audit/project.md
cp "$KIT"/config/models.example.yaml .audit/models.yaml
cp "$KIT"/adapters/claude-code/settings.audit.example.json .claude/settings.json
```

The workspace is disposable, so writing `.claude/settings.json` here is safe.

---

## 4. Fill in the intake (`project.md`)

> Since 0.7.0 you only fill in the six-line **Intake**: what the code can't tell
> us. `kit detect` proposes the profiles, exclusions and facts; discovery
> proposes what the system is; you confirm both at Checkpoint 1. The guidance
> below on profiles and assumptions now applies to the optional sections
> (Profile overrides, and team beliefs in `beliefs.md`).

Start from `templates/examples/council-reporting-site.project.md`. Most important:

- **Approvals**: from step 0.
- **Profiles**: only those that apply. For a Node/Express app on SQL Server
  in Azure: `node-express, mssql, azure-architecture, web-accessibility`,
  plus your compliance and governance profiles.
- **Assumptions to test**: what the team *believes* the system does. Include
  the uncomfortable ones ("no AI", "nothing stored locally"). Discovery
  confirms or contradicts each.
- **Scope**: branch and SHA from step 2.
- **People**: real names or roles for the owners of questions.

Keep it short, factual, and free of secrets and known-vulnerability details.

---

## 5. Choose models in `.audit/models.yaml`

Start simple: **one approved provider**. Use a mid-tier model for discovery,
engineer and accessibility, and a top-tier model for architect, security,
verifier and lead reviewer. Until a second provider is approved, give the
verifier a different model from the authors.

When a second provider is approved, add a second pass to `security` (and
optionally `verifier`) with that provider. See the comments in the file.

---

## 6. Run the scans (you run these, not the agents)

Install pinned tools **outside** the workspace once:

```zsh
brew install gitleaks cloc osv-scanner semgrep
mkdir -p ~/audit-tools && cd ~/audit-tools
npm init -y >/dev/null && npm install --ignore-scripts jscpd@<pinned-version>
cd "$WS"
```

Then, in the workspace:

```zsh
cloc --exclude-dir=node_modules,.audit,.audit-kit,.claude --json . > .audit/scans/cloc.json
gitleaks git --redact --report-format json --report-path .audit/scans/secrets.json .
osv-scanner scan source --format json -L package-lock.json > .audit/scans/deps-audit.json
semgrep scan --config p/javascript --config p/expressjs --config p/owasp-top-ten \
  --exclude .audit --exclude .audit-kit --sarif -o .audit/scans/sast.sarif .
~/audit-tools/node_modules/.bin/jscpd --reporters json --output .audit/scans/jscpd \
  --ignore "**/node_modules/**,**/.audit/**,**/.audit-kit/**" .
cp .audit/scans/jscpd/jscpd-report.json .audit/scans/duplication.json
```

**Azure shape index for diagrams.** Install drawio-skill at its pinned commit
(`THIRD_PARTY.md`), then:

```zsh
DRAWIO=~/.local/share/agent-skills/drawio-skill-053600a/skills/drawio-skill
python3 "$DRAWIO/scripts/shapesearch.py" azure --limit 5000 --json > .audit/scans/drawio-azure-shapes.json
```

Never run `npm install`, `npm test` or any of the target's own scripts on your
machine. `kit scan` writes `lint.json`, `typecheck.txt` and `unused.json` with the
kit's own configs (`make tools` installs ESLint and TypeScript), and, with no tools
needed, `sweep.json`, `suppressions.json`, `blindspots.json`, `coverage.json`,
`hotspots.json` (real clones only), `gates.md` (which checks the target runs in
its own CI), and the file review's units in `.audit/work/files/units.tsv`, each
with a brief in `.audit/work/files/<unit>/brief.md` (`kit units` writes them
again without re-running the scanners). To run the tools by hand, use the
commands in the `node-express` profile.

**The sandbox (optional, ADR 0005).** Some evidence needs code to run: knip and
dependency-cruiser, the target's own tests, and failing tests that prove a
Critical or High. Only if you allow it for this engagement:

```zsh
colima start                      # or Docker Desktop: the daemon must be running
echo "sandbox: allow" >> .audit/policy.yaml
kit sandbox "$WS" structure       # knip.json, depcruise.json
kit sandbox "$WS" tests           # tests.txt: pass, fail, or failed to run
kit sandbox "$WS" prove .audit/work/files/u042/prove.test.js
kit sandbox "$WS" try .audit/work/files/u042/try-nan.js
```

Each job copies the snapshot (never the workspace), installs with
`npm ci --ignore-scripts` where a lockfile exists, then runs with `--network none`,
a read-only root, no capabilities and no host files. Outputs go to
`.audit/scans/dynamic/`, and `jobs.log` records the image id of every run.

Check the CLI flags against your installed versions (`<tool> --help`); they change.

---

## 7. Evaluate first (the first time, and after any kit or model change)

Do this in a **second** disposable clone (`…-eval`), set up the same way.

1. **Known issues.** Handover notes, earlier reviews and bug lists already
   name real problems. Write them up as expected findings (CHECK-ID, file,
   severity) in a file **outside** both workspaces.
   > If those notes are *in* the repo (e.g. `HANDOFF.md`, `docs/`), delete
   > them in the eval clone. Otherwise the agents can read the answers, and
   > the test measures reading, not reviewing.
2. **Seeded issues.** Plant the issues from `evals/seeded-issues.template.md`
   (adapted to the code), commit them on the eval branch, and record exactly
   where they went, outside the workspace.
3. Run stages 1–3 **three times**. Score by Key, using `evals/README.md`.
4. Run the **interruption test** (`evals/interruption-test.md`) on the same eval
   clone: scenarios S1–S6, measured against an uninterrupted run.
5. Record the results in the real workspace's `project.md` → Evaluation.
   Below threshold? Fix the kit, bump its version, and repeat.

---

## 8. Run the audit

First make sure `make validate WS=<workspace>` passes (`make ready` runs it). It
checks `models.yaml` and the intake, and pre-flight won't start without a pass.


```zsh
cd "$WS"
git add -A && git commit -qm "audit setup: kit $KIT_VERSION"   # local only; never pushed
chmod +x .audit-kit/bin/checkpoint
# optional: cost and usage telemetry (docs/observability.md)
# export CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_METRICS_EXPORTER=otlp OTEL_LOGS_EXPORTER=otlp ...
claude
```
Then, in Claude Code:
```
/audit
```

What happens:

| Stage | You do |
|---|---|
| 0 Pre-flight | Fix whatever it reports as failed |
| 1a File review (if `file_review.mode` isn't `off`) | For a pilot, pick about ten units across the size bands in `.audit/work/files/units.tsv` and list them in `models.yaml` → `file_review.pilot_units` first. When the coordinator asks, run `kit review "$WS"` in another terminal (`--dry-run` first lists each unit's pass and model), then `kit cost "$WS"` for turns, tokens, cost and time. Re-running `kit review` keeps every unit already done; after a usage limit, run it again later. On a re-audit, `kit review "$WS" --reuse-from <last workspace>` keeps the records of units that haven't changed |
| 1b Traces | Run `kit store "$WS"` when asked, before and after the traces |
| 1 Discovery | Wait |
| ◆ Checkpoint 1 | Read `.audit/01-discovery.md`. Answer the open questions in `project.md`, fix wrong assumptions, then tell the coordinator: "Checkpoint 1 passed – <your name>" |
| 2 Specialists | Run any passes it hands you for other tools (Codex, Gemini CLI) in a new terminal, then say "pass <label> finished" |
| Critical alert | Tell the security owner **today** |
| 3 Verifier | Wait (or run the other-provider verifier pass it hands you) |
| 4 Lead reviewer | Wait |
| ◆ Checkpoint 2 | Open the evidence for **every** Critical and High yourself, plus at least three Mediums. Then: "Checkpoint 2 passed – <name>, checked: SEC-001, …" |

If anything stops with a circuit breaker, read the reason in
`.audit/run-log.md`. Usually the fix is in the kit or the setup, not the target.

---

## 9. Build the diagrams

The architect writes Diagram IR, not pictures. `kit diagrams <workspace>` builds,
projects, styles and checks them with drawio-skill (offline features only; see
`core/skills/architecture-diagrams`). It groups nodes by trust zone, lays them out
left to right and applies the kit's house style: rounded zones, icon cards,
curved edges and a hand-drawn stroke. Add `--style clean` for a formal look.

The same steps by hand, without the house style:

```zsh
for ir in .audit/diagrams/*.ir.json; do
  out=".audit/diagrams/$(basename "${ir%.ir.json}")"
  python3 "$DRAWIO/scripts/diagramctl.py" build "$ir" --from ir -o "$out.drawio" \
    --direction LR
  python3 "$DRAWIO/scripts/diagramctl.py" views "$ir" --direction LR \
    --views executive,deployment,dataflow,security -o "$out.views.drawio"
  python3 "$DRAWIO/scripts/validate.py" "$out.drawio" --score
done
# architecture contracts, if the architect wrote any
[ -f .audit/diagrams/policy.yml ] && python3 "$DRAWIO/scripts/diagramctl.py" test \
  .audit/diagrams/target.drawio --rules .audit/diagrams/policy.yml
```

Open the results in draw.io and tidy them. Export SVG for Markdown and slides,
and PNG at 2× for Word and PowerPoint (File → Export as). Export VSDX for Visio users.

---

## 10. Publish the report and briefing

Markdown is the source; Office files are generated (skill `audit-publishing`):

```zsh
brew install pandoc marp-cli     # once
pandoc .audit/07-final-report.md -o .audit/07-final-report.docx --reference-doc=<council-template.docx>
pandoc .audit/09-briefing.slides.md -o .audit/09-briefing.pptx --reference-doc=<council-template.pptx>
marp .audit/09-briefing.slides.md --pdf -o .audit/09-briefing.pdf
```
Edit the Markdown and regenerate; don't edit the Word or PowerPoint copies.

Then run the **output checks** (`evals/output-checks.md`) and record the
`OUTPUT CHECKS:` line in `run-log.md`. A failure in R1–R3, R7, B1 or P2 blocks release.

---

## 11. After the audit

- **Outputs are organisation records.** Copy `.audit/` (minus `scans/`
  that contain secrets output, even if redacted) to the organisation's
  records location or an access-controlled audit repository. **Never** put
  them in a personal repo.
- Import `.audit/08-backlog.csv` into Azure DevOps Boards (Boards → Work items
  → Import work items). Review it before importing.
- ADRs are `Proposed`. Take them to whoever accepts architecture decisions.
- Delete the workspace when the records are safely stored.
- Re-run after fixes, with the same kit version, to confirm what's closed.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Hit an API rate limit or usage cap | Expected. The coordinator stops and checkpoints. Later: `cd "$WS" && claude`, then `/audit resume`. Don't reopen the old conversation; a new session is cheaper |
| "LOCK is active" on resume | Another session may still be running that pass. If you're sure it isn't, wait for `lock_stale_minutes`, or tell the coordinator to take it over (it logs this) |
| A command hangs with no output | A shell alias prompting for input (e.g. `rm -i`). Run it with `command rm` or answer the prompt |
| An agent asks to run `npm` or `npx` | Correct behaviour is to refuse. Deny it, and check the agent cited a scan instead |
| Findings with no Key or evidence | The coordinator should send them back. If it keeps happening, the evaluation will catch it; fix the prompt |
| The target's own `CLAUDE.md` changed agent behaviour | Step 2 quarantine was skipped |
