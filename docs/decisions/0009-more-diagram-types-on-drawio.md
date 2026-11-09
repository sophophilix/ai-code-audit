# ADR 0009: More diagram types on the pinned draw.io route

> Status: Approved
> Created: 2026-11-09T11:29:04Z
> Last reviewed: 2026-11-09T11:57:43Z
> Next review: Not scheduled

## Review guide

Decision requested: add sequence, entity-relationship (ERD), data-flow and
lifecycle diagrams to the kit by extending the pinned drawio-skill route, and
don't adopt Archify as a second renderer (D1). Then: limit the first increment
to the types an audit can support with evidence (D2), give each type a
kit-owned schema with provenance on every element (D3), name where each type's
data comes from (D4), gate every build on that provenance (D5), and extend the
drawio-skill review to the two scripts the new types use (D6).

Check these points:

- [ ] Editable `.drawio` output and one pinned renderer are worth more than
      Archify's interactive HTML (D1).
- [ ] The four types in D2 are the right first increment, and timeline and
      waterfall are rightly out of scope for a read-only audit.
- [ ] A tracer sidecar file is an acceptable extra output for stage 1b (D4).
- [ ] Refusing to build a diagram whose provenance doesn't resolve (D5) won't
      block an audit in practice.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The kit draws one kind of picture today: architecture diagrams. The architect
writes Diagram IR (`.audit/diagrams/*.ir.json`), and `kit diagrams` builds
editable `.drawio` files with the pinned drawio-skill and the kit's house
style. Reviewers also need to see how a request moves through the code, what
the database looks like, where data goes, and which states a record passes
through.

Archify, an open-source agent skill, draws ten diagram types as interactive
HTML. We studied how it models diagrams. We will take its ideas (a schema per
type, source evidence pinned to a commit, a delivery gate) and build the types
on the draw.io route we already pin and review. drawio-skill already lays out
sequence diagrams and ERDs, so most of the work is schemas, data sources and
checks, not drawing code.

This lands after the pilot audit. The kit version stays fixed during an
audit (runbook, "Interruptions and resume").

## Evidence

Sources were read on 2026-11-09 between 11:00Z and 11:29Z, from local copies.

### Archify

Local copy of `tt-a1i/archify` at `11b0d603`, skill version 3.2.0, Apache-2.0.

| What we looked at | What it shows | Where |
|---|---|---|
| Output | One standalone HTML page per diagram, with themes, motion and image export. Not an editable diagram file. | `archify/SKILL.md`, description |
| Diagram types | architecture, workflow, sequence, dataflow, lifecycle, erd, class, tree, timeline, waterfall | `archify/SKILL.md`, "Type router" |
| A schema per type | Each type has its own JSON Schema. Sequence has `participants`, `segments`, `messages`, `activations`, `cards`; ERD has `entities` and `relationships`; lifecycle has `mainPath`, `states`, `transitions`. | `archify/schemas/*.schema.json` |
| Source evidence | `meta.repository` pins a URL and a 40-character revision. Elements carry `sourceReferences`: 1 to 3 items of `path`, `line`, `end_line`, `label`. Evidence is checked "against committed bytes at the pinned revision, not working-tree edits". | `archify/schemas/common.schema.json` (`repository`, `sourceReferences`); `archify/references/repository-authoring.md` |
| Delivery gate | `finalize` runs schema validation, delivery, a strict check and a real-browser check. "A non-zero exit is never success." | `archify/SKILL.md`, steps 4 and 5 |
| Runtime needs | Node 18 or later. The browser check finds and drives a local Chrome. | `archify/package.json`; `archify/bin/finalize.mjs` (`findChrome`) |
| Network | Each `finalize` and `deliver` includes an update check in its receipt. We didn't find an option that turns it off. | `archify/references/update-awareness.md`; `archify/bin/delivery-update.mjs` |

### drawio-skill at the kit's pin

`Agents365-ai/drawio-skill` at `053600a`, skill version 3.4.4, MIT
(`THIRD_PARTY.md`).

| What we looked at | What it shows | Where |
|---|---|---|
| Type presets | Styles for ERD, UML class, sequence, C4, architecture, BPMN, network topology, swimlane and flowchart | `references/diagram-types.md` |
| Sequence layout | `seqlayout.py` computes lifelines, activation bars and arrows from a `participants` and `messages` JSON. Sync, async, return, self messages and notes. "Fragments (alt/loop/opt frames) are out of scope." 222 lines. | `scripts/seqlayout.py`, docstring |
| ERD from SQL | `sqlerd.py` parses `CREATE TABLE` with regular expressions into one node per table, with primary and foreign key markers and crow's-foot edges, as input for `autolayout.py`. It normalises bracket-quoted identifiers (`[t]`). 167 lines. | `scripts/sqlerd.py`, docstring |
| Imports and I/O of those two scripts | Standard library only (`argparse`, `json`, `sys`, `glob`, `os`, `re`, `xml.sax.saxutils`). They open their input and output files and nothing else. No network or subprocess calls. | `scripts/seqlayout.py:39-42,209,213`; `scripts/sqlerd.py:23-28,131,158` |
| Current review scope | `seqlayout.py` and `sqlerd.py` weren't in the 2026-11-06 review. | `THIRD_PARTY.md`, "drawio-skill" |

### The kit today

- The architect writes IR only. Agents can't run scripts. The tech lead runs
  `kit diagrams`, which builds, makes views, restyles and validates
  (`core/skills/architecture-diagrams/SKILL.md`, "In an audit";
  `src/audit_kit/outputs.py`).
- The tracer writes `traces/<entry>.md` with `## Entry` and an ordered
  `## Call chain`: each step's function, `file:line`, an Excerpt, and what it
  does with the data (`core/agents/tracer.md`). That is a sequence diagram
  written as prose.
- The findings store holds facts of kinds `route`, `timer`, `outbound`,
  `state` and others. On the pilot app it holds 1,004 facts and 106 flows
  (`kit store`, 2026-11-09).

## Decision

### D1. One renderer: drawio-skill. Archify isn't adopted.

Every diagram the kit makes is an editable `.drawio` file built by the pinned
drawio-skill and restyled by `kit diagrams`. Archify isn't installed, pinned or
called. We borrow three ideas from it, described in D3 and D5, and copy no
code or schema text.

Reasons:

- Council staff edit diagrams after the audit. Archify's output is HTML.
- The kit's icon rules allow only Microsoft's Azure icon set in draw.io's
  bundled copy (`architecture-diagrams`, "Icon rules").
- Archify needs Node and Chrome, and its update check breaks AGENTS.md rule 3
  (no network).
- One pinned renderer is one review. A second renderer that changes quickly
  would need its own.

### D2. First increment: sequence, ERD, data flow and lifecycle

| Type | In the first increment | Why |
|---|---|---|
| Sequence | Yes | Stage 1b already produces the call chain. |
| ERD | Yes | The schema is in the target's SQL files and needs no model. |
| Data flow | Yes | The existing IR has a `dataflow` view; it needs flows from the store, not new drawing. |
| Lifecycle (states) | Yes | Report status and outbox retry states are common review questions. |
| Class | Later | Rare in the JavaScript codebases audited so far. |
| Workflow | Later | Runbooks and CI. The pilot app has neither. |
| Tree | No | `inventory.json` already lists the files. |
| Timeline, waterfall | No | They need timings or event history from a running system. A read-only audit doesn't have them. |

### D3. A kit-owned schema per type, with provenance on every element

Each type gets a JSON Schema under `core/schemas/diagrams/`:
`sequence.schema.json`, `erd.schema.json`, `lifecycle.schema.json`. Data flow
keeps the Diagram IR. Agents write JSON that matches a schema, never `.drawio`
XML. `kit diagrams` converts each file into drawio-skill's input.

Every participant, message, entity, state and transition has a `provenance`
list of `path` and `line`, like the IR's provenance today. The file names the
audit's source commit once, from `.audit/.workspace` (`source_commit`). This
is Archify's `repository` and `sourceReferences` idea in the kit's own terms.

An element with no code behind it isn't drawn. It goes to the output's open
questions instead (AGENTS.md rule 4).

### D4. Where each type's data comes from

| Type | Written by | File | Built with |
|---|---|---|---|
| Sequence | Tracer, one per trace | `.audit/traces/<entry>.seq.json` beside `<entry>.md` | `seqlayout.py` |
| ERD | `kit scan`, no model | `.audit/diagrams/erd.json` from the target's `*.sql` files | `sqlerd.py`, then `autolayout.py` |
| Data flow | Architect | `.audit/diagrams/as-is-data.ir.json`, from `flows` and `outbound` facts | `diagramctl.py build --from ir`, `views --views dataflow` |
| Lifecycle | Engineer | `.audit/diagrams/lifecycle-<entity>.json` | `autolayout.py` with a state preset |

`sqlerd.py` reads SQL as text and runs nothing, so it stays within AGENTS.md
rule 2. Sequence participants come from the call chain's files and outbound
targets. Each message is one call-chain step, and its provenance is that
step's `file:line`.

### D5. A build gate on schema and provenance

`kit diagrams` refuses to build a diagram when:

- the file fails its schema, or
- any `provenance` item doesn't resolve to an existing line in the audit
  snapshot at `source_commit`.

It then runs `validate.py --score` on the built file, as it does for
architecture diagrams. A refused diagram is listed with its reasons and the
others still build. This is Archify's "a non-zero exit is never success" rule
applied to evidence.

### D6. Extend the drawio-skill review, keeping the same pin

Review `seqlayout.py` and `sqlerd.py` in full at `053600a` and add them to the
allowed list in `THIRD_PARTY.md` and in `architecture-diagrams`. A first read
for this ADR found standard-library imports and file I/O only (Evidence). The
pin stays `053600a`. Moving it is a separate decision.

## Consequences

- Each trace gets a picture of its call chain that a reviewer can edit, for
  the cost of one extra JSON file from the tracer.
- The ERD costs no model tokens.
- The kit owns three more schemas and their converters, with tests.
- `seqlayout.py` can't draw `alt`, `loop` or `opt` frames. A branch shows as
  a note, or as a second sequence for that path.
- A diagram whose evidence doesn't resolve isn't drawn. That can leave a gap,
  but never a picture that claims more than the code shows.

## Rejected options

| Option | Why not |
|---|---|
| Adopt Archify as a second renderer | HTML output isn't editable; needs Node and Chrome; its update check reaches the network; a second fast-moving dependency to pin and review. |
| All ten Archify types | Timeline and waterfall need runtime data the audit doesn't have; tree duplicates `inventory.json`; class and workflow have no current use. |
| Agents write `.drawio` XML directly | Geometry by hand is error-prone (the `seqlayout.py` docstring says so of sequences), and XML can't be schema-checked for provenance. |
| Derive sequence diagrams from `traces/<entry>.md` with a parser | Prose structure drifts between passes. A sidecar JSON can be schema-checked. |

## Risks and open items

- **`sqlerd.py` is regular-expression based.** Its docstring says
  dialect-specific clauses are ignored, and the worst case is a skipped column
  line. The pilot app's SQL (`sql/create_tables.sql`,
  `sql/migrate_multiple_photos.sql`) should be tried before relying on it.
- **Traces may grow too large to read.** Set a participant and message limit
  per sequence, as `architecture-diagrams` limits context diagrams to 15 nodes
  and 20 edges, and split longer chains.
- **The tracer's prompt gets longer.** Measure the extra tokens per trace on an
  eval workspace before making the sidecar a default.
- **Lifecycle layout is untested.** `autolayout.py` has been used for
  architecture and ERD graphs. A state preset needs a spike.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-09T11:29:04Z | Drafted | From a study of Archify 3.2.0 (`11b0d603`) and drawio-skill at the kit's pin (`053600a`), at the tech lead's request. |
| 2026-11-09T11:57:43Z | Approved | Tech lead approved. Work starts after the pilot audit, on a new kit version. |
