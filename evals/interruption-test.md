# Interruption test

Proves that a run survives API limits, crashes and lock conflicts without
losing work, duplicating findings, drifting, or spending far more tokens.
Run it with the first finding evaluation, and again whenever the kit's
`checkpointing` skill, the coordinator, a model or the harness changes.

## Setup
- Use the **eval clone** with seeded issues (`README.md`), on its own
  `audit/eval-<date>` branch, with `.audit-kit/bin/checkpoint` executable.
- Pick one agent with many work items. **Security pass a** is a good choice.
- **Baseline (A):** one uninterrupted run of that pass. The three finding-eval
  runs can serve as baselines. Record its total tokens (harness report or
  `claude_code.token.usage` filtered by `agent.name`) and its Keys.
- Turn on telemetry if you can (`docs/observability.md`); it makes T4 and T5 exact.

## Scenarios (interrupted run B)

| # | Scenario | How to cause it | Expected behaviour |
|---|---|---|---|
| S1 | Session killed mid-item | When `plan.md` shows ≥ 30% `[x]` and one `[~]`, close the terminal or press Ctrl+C twice | New session + `/audit resume`: the pass resumes at the `[~]` item, earlier items untouched |
| S2 | Crash between "append finding" and "mark done" | After a checkpoint commit, take the next item: append one of its findings to the output by hand (copy a real one), leave the item `[~]`, then start a resume | The item is redone; the Key check stops a duplicate; one copy remains |
| S3 | Second session while one is active | While B is running, start another session on the same pass | It reads the fresh `LOCK`, refuses, and changes nothing |
| S4 | Stale lock | Kill a session, edit `LOCK` `heartbeat_utc` to older than `lock_stale_minutes`, resume | The coordinator marks the pass `interrupted`, takes over, and logs the takeover |
| S5 | Coordinator killed | Kill the main session during stage 2, after one pass is `done` | `/audit resume` rebuilds from `run-state.md`, doesn't rerun the `done` pass, and resumes the rest |
| S6 | Agent hands over early | Tell the agent at start: "hand over after 3 items" | It checkpoints, releases `LOCK`, reports "handover: N items left"; the next session continues |
| S7 | Rate limit (when it happens naturally, or with a very small plan quota) | — | The coordinator stops (no retry loop), checkpoints, marks `interrupted`, and tells you how to resume. `api_error` with status 429 appears in telemetry |

S1–S6 are required. S7 is recorded whenever it occurs in any run.

## Measures and thresholds (starting points)

| ID | Measure | How to check | Pass |
|---|---|---|---|
| T1 | Completeness | Output `status: complete`; `command grep -c '\[ \]\|\[~\]' plan.md` = 0; `LOCK` `state: released` | all |
| T2 | No lost or rewritten findings | `git diff --unified=0 <checkpoint-before-interrupt> HEAD -- <output>` shows no removed finding lines (ignore header `status:`, `sessions:`, `finished_utc:`) | no removals |
| T3 | No duplicates | `command grep -h '^- Key:' <output> \| sort \| uniq -d` is empty | empty |
| T4 | IDs continue | IDs are sequential with no reuse; the first ID after resume = capsule `next_id` | exact |
| T5 | Recall parity | Seeded and known issues found in B vs A, by Key | no Critical/High lost; overall within 1 item |
| T6 | Resume overhead | Tokens of B ÷ tokens of A | ≤ 1.25 |
| T7 | Lean resume | The resumed session's first reads are AGENTS.md, its agent file, the skill, `capsule.md`, `plan.md`, and ID/Key lines, plus only the `read_on_resume` inputs (transcript or `tool_result` events) | no full re-read of finished work |
| T8 | Capsule discipline | `wc -l capsule.md` | ≤ 60 |
| T9 | Locks | S3 refused with no writes; S4 takeover logged in `run-log.md` | both |
| T10 | Coordinator resume | S5: the `done` pass not rerun; `run-state.md` correct afterwards | both |
| T11 | Drift | Severity of findings created after the resume vs the same Keys in A | ≤ 1 level apart; differences explained by the verifier |

## Recording
Add a row to the project's `project.md` → Evaluation table (column
"Interruption") and to `run-log.md`:
`INTERRUPTION TEST: S1–S6 <pass/fail each>, T1–T11 <failed IDs or none>, overhead <ratio>, <model>, <harness>, kit <version>`.

Any failure in T1–T4 or T9 means the kit isn't safe to run on real work:
fix the `checkpointing` skill or coordinator, bump the patch version, and re-run.
