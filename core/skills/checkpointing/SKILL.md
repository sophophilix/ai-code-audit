---
name: checkpointing
description: Use in every audit agent session, from the first action. Defines how work is split into small items, saved after each one, locked against concurrent sessions, and resumed by a new session after an API limit, crash or context limit, with minimal re-reading and no renumbering.
---

# Checkpointing and resume

## Overview
Sessions end without warning: API rate limits, usage caps, network drops,
context limits. Nothing an agent has learned may live only in its context.
After every small unit of work, the result is on disk in a form the next
session can pick up by reading a few short files, not by redoing the analysis.

A file-reviewer unit pass is the exception (ADR 0007 D4). It's one short call
that returns one JSON object or fails, and `kit review` runs a failed pass again
and keeps the units already done, so it has no LOCK, plan or capsule. Every
other agent, the tracer included, follows this skill.

## Your files
For output `.audit/<NN>-<agent>[.<pass>].md` the work folder is
`.audit/work/<NN>-<agent>[.<pass>]/`:

| File | Purpose | Size |
|---|---|---|
| `LOCK` | Who is working on this pass right now | 6 lines |
| `plan.md` | Numbered work items and their status | one line per item |
| `capsule.md` | Everything a new session needs that isn't in the output yet | **≤ 60 lines** |
| the output file | Built **incrementally**: header with `status: in-progress`, findings appended as you go | grows |

### LOCK
```
holder: <harness> / <model> / pass <label>
started_utc: 2026-11-06T02:10Z
heartbeat_utc: 2026-11-06T02:41Z
state: active            # active | released
item: 7
```

### plan.md
```
# Plan – security, pass a (derived from: 01-discovery.md routes, integrations; profile checks)
1. [x] Threat model (info finding)
2. [x] Secrets: scans/secrets.json
3. [~] Injection: routes in server.js:600-900        ← in progress when the session ended
4. [ ] Injection: routes in admin/server.js
5. [ ] Uploads
...
```
Status marks: `[ ]` to do, `[~]` started, `[x]` done, `[!]` blocked (reason after it).

### capsule.md
```
next_id: SEC-a-009
last_item_done: 2
decisions:
  - Treat APP_MODE=admin as a separate trust boundary (see SEC-a-001)
assumptions_to_check:
  - Rate-limit state is per instance (needs discovery State section)
open_threads:
  - server.js:640 reportsGate: confirm order vs body parser (item 3)
read_on_resume:
  - 01-discovery.md sections 3, 5 (routes, data flows) only
```

## Process
1. **Start: check for a lock.** If `LOCK` says `state: active` and its
   heartbeat is newer than `lock_stale_minutes` (from `.audit/models.yaml`,
   default 30), **stop**: another session may be working. Report this and do
   nothing else. Otherwise write your own `LOCK`.
2. **Resume or plan.**
   - `plan.md` exists → **resume**: read `capsule.md`, `plan.md`, and only the
     ID and Key lines of your output (`grep -nE '^### |^- Key:'`). Read only the
     inputs named under `read_on_resume`. Redo any `[~]` item from the start.
     Don't re-read finished work.
   - No plan → **plan**: turn your agent definition's numbered steps into
     items. Split any step that covers many files or routes into one item per
     file or group. Derive items from the inputs (discovery's lists, profile
     check catalogues), so a different session would produce the same plan.
     Write `plan.md`, an empty `capsule.md`, and the output file with its
     provenance header and `status: in-progress`.
3. **Work one item at a time.** Mark it `[~]` before starting.
4. **Checkpoint after every item, in this order:**
   1. append the item's findings to the output (check its Keys aren't already there first)
   2. mark the item `[x]` in `plan.md`
   3. update `capsule.md` (`next_id`, decisions, open threads, what the remaining items need to read)
   4. update `heartbeat_utc` and `item` in `LOCK`

   If the session dies between steps, the worst case is redoing one item,
   and the Key check stops it creating duplicates.
5. **Hand over early.** If your context is getting long, or the harness warns
   of limits, finish the current item, checkpoint, set `LOCK` to
   `state: released`, and end with "handover: N items left". A fresh session
   costs less than a bloated one and drifts less.
6. **Finish:** set the output header to `status: complete` with
   `finished_utc` and `sessions: <n>`, and set `LOCK` to `state: released`.

## Rules for low drift
- **Times come from the clock.** Every `*_utc` value is the output of
  `date -u +%Y-%m-%dT%H:%MZ` run at that moment. Never estimate a time, and never
  use local time or the date in your context.
- **No scratch files from the shell.** `rm` and `mv` are denied, so a temporary
  file made with `>` can't be cleaned up. Keep working notes in `capsule.md`, and
  write files with your edit tool.
- **Never renumber** finding IDs. Continue from `next_id`.
- **Never rewrite earlier findings** in a resumed session. Add a new finding,
  or note a correction in `capsule.md` for the lead reviewer.
- Decisions that affect later items go in `capsule.md` → `decisions`, so the next
  session applies the same judgement.
- Keep `capsule.md` under 60 lines. Move settled points into findings.
- Use the same model as `.audit/models.yaml` assigns. A resume on a different
  model is logged by the coordinator as a substitution.

## Red flags
- An output file that only appears at the end of a session
- `capsule.md` growing into a second report
- Re-reading whole input files on resume "to be safe"
- Two sessions writing the same pass (no LOCK check)
