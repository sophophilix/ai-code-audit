# ADR 0008: Cross-file evidence for the file review, and checks the harness enforces

> Status: Approved (D1 and D2); D3 to D7 deferred
> Created: 2026-11-08T22:46:00Z
> Last reviewed: 2026-11-09T11:57:43Z
> Next review: Not scheduled

## Outcome

The tech lead approved D1 and D2, which were built in 0.18.0. D3 to D7 are
deferred: they stay below as proposals, not decisions, and are taken up only
when an audit shows the need. For example, D5 if the file review's findings
prove noisy, or D3 if an agent skips its final checks.

## Review guide

Decision requested: keep the file-review pass without tools (ADR 0007 D1) and
give it what one file can't show as precomputed, deterministic facts (D1, built
in 0.18.0). Then, in order: enforce the agents' rules and their final checks
with Claude Code hooks (D3), add a caller and dependency graph to each brief
(D4), score each finding independently before stage 2 reads it (D5), carry the
tech lead's Checkpoint decisions into the next run (D6), and measure every
change on a held-out eval that counts false positives (D7).

Check these points:

- [ ] Facts computed by the kit, not tools or retrieval in the pass, are the
      right way to give a unit pass cross-file context (D1, D2).
- [ ] Hooks are worth one more harness-specific file per adapter (D3).
- [ ] An independent score per finding (D5) is worth its cost before stage 2.
- [ ] Learnings from Checkpoint decisions (D6) can't hide a real issue.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The tuned 0.17.0 seeded pilot found 15 of the 17 seeded issues in the files it
reviewed. Two it could never find, whatever the brief said:

| Seeded issue | Why one file can't show it |
|---|---|
| S13, a copied helper with a one-token change | The other copy is in another file, and it is below jscpd's default minimum (50 tokens, 5 lines), which `kit scan` uses. |
| S15, a declared dependency nothing imports | Only the absence of an import shows it; no code file mentions the package. `unused.json` listed it, but the scan reader dropped the row and `package.json` was never a unit. |

That's a harness gap, not a wording gap. This ADR records how other review
tools close it, what the kit adopted in 0.18.0, and what comes next.

The tech lead asked that tuning not fit the 19 seeded issues. Every decision
here is a general capability, tested on the real code as well as on the seeded
copy.

## Evidence: how other tools give a reviewer cross-file context

Sources were read on 2026-11-08 between 22:00Z and 22:45Z. Vendor pages describe
their own products, and the benchmarks aren't comparable with each other.

| Tool or study | What it does | Source |
|---|---|---|
| CodeRabbit | Clones the repository into a sandbox for each review and builds a code graph of dependencies each time. Runs 40+ linters and SAST tools (its architecture page says 50+). Aims for "a 1:1 ratio of code-to-context" in its prompts. Generates verification scripts in the sandbox, and "any low value feedback is automatically filtered out". Specialised agents run in parallel, one of them for verification. | [Context engineering for AI code reviews](https://coderabbit.ai/blog/context-engineering-ai-code-reviews); [Architecture](https://docs.coderabbit.ai/overview/architecture) |
| Greptile | Parses every file into a graph of directories, files, functions, classes and variables, with calls, imports and variable use as edges. When a file is reviewed it queries the graph for a changed function's dependencies, its callers, and similar functions, and flags code that differs from its siblings (string-built SQL where the others use parameters). | [Graph-based codebase context](https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context) |
| Claude Code `/code-review` plugin | Specialised agents with confidence-based filtering. The listing says each finding is scored 0 to 100 and only findings at 80 or above are posted. Third-party write-ups say separate agents do the scoring; that isn't in the official docs. | [Code Review plugin](https://claude.com/plugins/code-review); [third-party write-up](https://instagit.com/anthropics/claude-code/code-review-confidence-scoring-claude-code) |
| AACR-Bench (arXiv 2601.19494) | Tested models with no context, BM25, embedding retrieval and an agent. Retrieved context didn't uniformly help: for Claude Sonnet 4.5, BM25 or embedding context lowered F1 from about 14.5% to about 10%, which the authors put down to noise. | [AACR-Bench](https://arxiv.org/html/2601.19494) |
| CR-Bench (arXiv 2603.11078) | Pressing an agent to find more bugs raised noise; a relaxed single pass missed some bugs. | [CR-Bench](https://arxiv.org/html/2603.11078v1) |
| Vendor benchmarks | Qodo reports 52% recall for Claude Code Review against 60% to 71% for its own configurations, on defects it injected. Augment reports that tools with stronger retrieval recall more. Both are vendors measuring themselves. | [Qodo](https://www.qodo.ai/blog/qodo-outperforms-claude-in-code-review-benchmark); [Augment](https://www.augmentcode.com/blog/we-benchmarked-7-ai-code-review-tools-on-real-world-prs-here-are-the-results) |
| Atlas meta-review (2026) | Different definitions of "caught", LLM-seeded bug sets, and almost no reporting of false positives make published numbers incomparable. | [Atlas](https://laoujin.github.io/Atlas/research/2026-06-09-ai-assisted-code-review-in-2026-landscape-tools-evidence-and-limits/) |

Three patterns recur:

1. **Compute context before the model sees the code.** A code graph, static
   analysers and similar-function lookup (CodeRabbit, Greptile).
2. **Verify each finding separately from the pass that wrote it.** Scripts, a
   verification agent, or an independent confidence score (CodeRabbit,
   `/code-review`).
3. **Learn from the reviewer's decisions** (CodeRabbit's learnings from chat and
   feedback).

The studies add a warning: more context, or more pressure to find things, isn't
free. Precision has to be measured alongside recall.

## Decision

### D1. What one file can't show reaches its brief as a fact (built in 0.18.0)

The kit computes cross-file facts once, deterministically, and puts them in the
brief as scan rows. The pass still reads only its brief (ADR 0007 D1).

- **Dependency manifests are units.** Each own `package.json` is a unit of kind
  `manifest`. Its brief has the file's `unused` rows and sections tagged
  `manifest`: `SLOP-PHANTOM-DEP` and the node-express checks a manifest can show.
- **Unused dependencies reach the manifest's brief**, with a line.
- **Near-duplicate functions** (`scans/similar.json`): named functions of 12 to
  400 tokens whose tokens match at least 85% in order, with where they differ.
  Both briefs get a row naming the other copy. On the pilot app's real code it finds
  212 pairs, including copy-and-adapt clusters jscpd misses
  (two queue modules, two PDF builders, a health check and a status page,
  three Azure client wrappers).

### D2. No tools or retrieval in the unit pass

A unit pass gets no search tools, no embeddings and no other files. AACR-Bench's
results suggest retrieved context can cost a model accuracy, and tools would
undo ADR 0007's cost and isolation. Questions only another file can answer stay
open edges, and the trace stage (1b), which has read-only tools, answers them.

### D3. Hooks enforce what the prompt only asks (deferred)

Workspaces already get Claude Code permissions from
`adapters/claude-code/settings.audit.example.json`: an allow list of read-only
commands and a deny list (`npm`, `npx`, `node`, `curl`, `rm`, and others).
Permissions match command prefixes, so they can't express "finish only when
the output passes its checks", and they miss forms they don't name: `make`,
`bash`, `sh` and `bun` aren't denied, and AGENTS.md rule 2 names `Makefile` as
code. Add to the adapter:

- **A Stop and SubagentStop hook** that runs `kit verify` on the stage's output
  file and blocks the agent from finishing, with the failures as feedback, until
  it passes. This moves AGENTS.md rules 13 and 14 and the verification checklist
  from the prompt to the harness.
- **A PreToolUse hook** for Bash, Write and Edit that refuses anything that
  executes, installs or reaches the network, and any write outside `.audit/`,
  by parsing the whole command rather than its prefix. Defence in depth behind
  the permissions, not a replacement.

The `generic` adapter documents the same checks for harnesses without hooks.

### D4. A caller and dependency graph in each brief (deferred)

`unused.py` already builds the require graph. Each brief gets rows saying which
own files require this file and which it requires, and, for each exported
function, the files that name it. This is Greptile's pattern without the index,
and it helps flows that cross files (a route in one file, a SQL sink in another).

### D5. An independent score for each finding before stage 2 (deferred)

A short pass with no tools reads one finding, its excerpt and the unit's code,
and scores it 0 to 100 against a rubric. It doesn't see the reasoning of the
pass that wrote the finding. The score goes in the findings store. Stage 2 reads
findings at or above a threshold the tech lead sets, and the rest are listed as
low-confidence, not dropped. This targets precision now that recall is up.

### D6. Learnings from Checkpoint decisions (deferred)

When the tech lead accepts, rejects or re-rates a finding at a Checkpoint, the
kit records the decision against its Key in the store. The next audit's brief
for that file shows earlier rejections with their reasons, as context, never as
an instruction to stay silent. A rejected Key that reappears is reported with
the earlier decision beside it.

### D7. A held-out eval that counts false positives (deferred)

Tuning against one seeded set fits that set. Every change to briefs, rules or
the pass is measured on a second seeded set with different plants, and on real
findings the tech lead confirmed, reporting false positives alongside recall.

## Consequences

- The file review can now find issues whose evidence is in another file, at no
  model cost: `similar.json` takes under a second on the pilot app.
- Briefs with `similar` rows grow by a few lines; a manifest brief is small.
- D3 makes the agents' final checks impossible to skip, at the cost of a hook
  file per adapter.
- D5 adds a pass per finding. Its cost is measured before it becomes a default.

## Rejected options

| Option | Why not |
|---|---|
| Search tools in the unit pass | Breaks ADR 0007's cost and isolation; CR-Bench and AACR-Bench report more noise from agents pushed to find more and from retrieved context. |
| An embedding index of the repository | Needs an embedding model from a third party (ADR 0007, rejected options) and answers "probably related". The token comparison in D1 is exact and repeatable. |
| A lower jscpd token minimum | Floods the duplication report with matching boilerplate (imports, `module.exports`) and still misses copies that differ by one token in the middle. |
| Rules that name the seeded issues | Fits the answer key, not the code. |

## Risks and open items

- **`similar` pairs are leads, not verdicts.** Small functions can match by
  coincidence, and a copy can be deliberate. The rules keep Chesterton's Fence
  and rate duplicated helpers Low unless the difference is a defect.
- **The 0.18.0 seeded eval hasn't run yet.** Recall on the seeded set and the
  severity mix are measured after the real pilot audit.
- **Hooks are Claude Code-specific.** Other harnesses rely on permissions and
  the prompt until they have an equivalent.
- **Learnings could suppress a real issue.** D6 shows earlier decisions as
  context only, and a reappearing rejected Key is reported, not hidden.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-08T22:46:00Z | Drafted | D1 and D2 built in 0.18.0 (`d157452`). D3 to D7 proposed, from research on CodeRabbit, Greptile, Claude Code's `/code-review` plugin and three benchmark studies. |
| 2026-11-09T11:57:43Z | Approved in part | Tech lead: D1 and D2 approved as built. D3 to D7 deferred as "over engineering too soon"; revisit when an audit shows the need. |
