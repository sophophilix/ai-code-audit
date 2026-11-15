# ADR 0012: The pack contract

> Status: Approved
> Created: 2026-11-14T15:03:02Z
> Last reviewed: 2026-11-15T05:51:26Z
> Next review: after the first private pack is used on an audit

## Review guide

Decision requested: adopt the pack contract. It gives every pack one checked
shape (D1 to D3) and defines a pattern entry for practice knowledge (D4). It
loads private packs from outside the repository (D5). It makes the Python pack
the reference by moving its language rules out of the core (D6).

Check these points:

- [ ] The pattern entry in D4 is something you would fill in at the end of a
      working day.
- [ ] Copying a private pack into a workspace only when the intake adds it (D5)
      is the right default.
- [ ] Python file-review records from 0.19.0 being reviewed again (Consequences)
      is acceptable.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

A profile was a folder with a free-form `SKILL.md`. Nothing checked it, the
languages it covered were a table in `detection.py`, and it had to live in this
public repository. ADR 0011 makes packs the home of all stack, platform, concern
and sector knowledge, so a pack needs a contract the kit can check.

The folder stays `profiles/`, and `detected.md` still says "Profiles to load".
A pack is a profile that meets this contract.

## Decision

**D1. Every pack has a manifest.** `pack.toml` sits in the pack folder:

```toml
name = "python"
type = "stack"
version = "1.0.0"
summary = "Python applications, libraries and command-line tools."
languages = ["Python"]
check_prefixes = ["PY", "PYAPP"]
borrows = ["SLOP"]
```

| Field | Rule |
|---|---|
| `name` | Lowercase letters, digits and hyphens. Matches the folder name. |
| `type` | `stack`, `platform`, `concern` or `sector` (ADR 0011 D3). |
| `version` | Three numbers, such as `1.0.0`. |
| `summary` | One line. |
| `languages` | Optional. Languages as `kit detect` names them. A language that a loaded pack names is covered. |
| `check_prefixes` | Optional. CHECK-ID prefixes this pack owns. |
| `borrows` | Optional. Prefixes this pack uses and another pack or core skill owns. |

An unknown field is an error. `detection.py` no longer holds a table of
languages for each profile.

**D2. Layout.**

```text
<name>/
  pack.toml
  SKILL.md                   what the stage agents load
  references/*.md            optional, loaded on demand
  skills/<skill>/SKILL.md    optional skills that travel with the pack
  patterns/<id>.md           optional pattern entries (D4)
```

A brief draws tagged sections from `SKILL.md`, then `references/*.md`, then
`skills/*/SKILL.md`, in that order. `kit install` copies each skill under
`skills/` into the workspace by its own name, so an agent loads `python-review`
exactly as it did before.

**D3. `kit pack-check` checks the contract.** With no arguments it checks every
installed pack. A pack fails when:

- `pack.toml` is missing, isn't TOML, or breaks a rule in D1
- `SKILL.md` is missing, or its front matter has no description or a different
  name
- a `<!-- brief: ... -->` tag names a kind the kit doesn't know
- a catalogue row's CHECK-ID has a prefix the manifest neither owns nor borrows
- the manifest owns a prefix that no check uses
- no file in the pack cites a source (an `https` URL), which `AGENTS.md` rule 8
  requires
- a pattern entry breaks D4

The kit's own tests run the same checks on every pack in `profiles/`.

**D4. A pattern entry records one lesson.** A pattern is a principle the author
has met in practice. It is the unit a private pack grows by. Each is one file,
`patterns/<id in lowercase>.md`:

```markdown
---
id: AZ-STATE-OUTSIDE
title: Keep state outside the process
status: accepted
applies_to: [hosting, containers]
sources:
  - title: The Twelve-Factor App, VI. Processes
    url: https://12factor.net/processes
seen:
  - date: 2025-03-01
    context: a bank's customer portal
check: AZ-SCALE-OUT
post: https://example.org/blog/state-outside-the-process
recall: An app keeps sessions in memory behind a load balancer. What breaks?
---

## Principle
## How to check
## Good
## Bad
```

| Field | Rule |
|---|---|
| `id` | A CHECK-ID style name with a prefix the pack owns. |
| `status` | `draft` or `accepted`. |
| `applies_to` | At least one tag. |
| `sources` | Published sources, each with a title and an `https` URL. |
| `seen` | Dated sightings. `context` describes the setting without naming the client ("a bank's customer portal"). |
| `check` | Optional. The catalogue check this pattern supports. |
| `post` | Optional. A published article that tells the longer story. |
| `recall` | Optional. A scenario question for spaced recall. |

An entry needs at least one source or one sighting. The four headings are
required. Each new sighting of an existing pattern is added to `seen`, so the
list shows how often a pattern recurs.

**D5. Private packs load from outside the repository.** `AUDIT_KIT_PACKS` names
one or more folders of packs, separated like `PATH`. The kit's own packs come
first. Two packs with one name are an error.

- A private pack is chosen for an audit by the intake's `add` line in
  `project.md`. Detection rules stay in the kit, so they never propose a private
  pack.
- `kit install` copies a private pack into a workspace only when that
  workspace's intake adds it. Setup is committed to the workspace's audit
  branch, and one client's workspace shouldn't hold another sector's pack.
- `kit detect` reports an added pack that isn't installed.
- A brief labels a private pack's sections `profiles/<name>/...`, the same as
  the kit's own. The folder's location on the machine never reaches a brief.

**D6. The Python pack is the reference.** The `python-review` skill, which holds
the `PY-*` language checks, moves from `core/skills/` to
`profiles/python/skills/python-review/`. The core no longer names Python in its
list of skills. The other six packs get a manifest and are otherwise unchanged.

## Consequences

- A Python unit's brief lists its rules in a different order, and the
  `python-review` rules now carry the source
  `profiles/python/skills/python-review/SKILL.md`. A Python file-review record
  written by 0.19.0 no longer matches its brief, so `kit review` reviews that
  unit again.
- The `PY-*` rules reach a brief only when the `python` pack is loaded. Removing
  the pack in the intake now removes its language rules too.
- An audit branch that adds a private pack holds a copy of it. The kit never
  pushes, and the tech lead must not push that branch to a client's remote.
- Installing by hand needs one more path. The adapter guides show it.
- Pattern entries are checked but don't reach a brief or an agent yet.

## Not in this decision

- A skill that captures a note and writes a pattern entry.
- Loading pattern entries into briefs.
- A `supported` or `experimental` status for a pack (ADR 0011 D6).
- Moving `javascript-review` and `frontend-review` into the Node.js and
  accessibility packs.
- Detection rules, unit kinds, gates and scanners declared by a pack rather
  than written in the core (ADR 0011, Consequences).

## Rejected

- **Renaming `profiles/` to `packs/`.** Agent definitions, `detected.md`, the
  runbook and past audits all say "profile". The rename changes many files and
  no behaviour.
- **YAML for the manifest.** `tomllib` is in the standard library and the kit
  already reads `pyproject.toml` with it.
- **Copying every private pack into every workspace.** It is simpler, and it
  leaves one sector's knowledge in another client's audit branch.
- **Leaving `python-review` in the core and listing it in the manifest.** The
  core would still name a language, which ADR 0011 D2 rules out.

## Review history

| Date (UTC) | Reviewer | Outcome |
|---|---|---|
| 2026-11-14 | Claude (author) | Proposed. Built in 0.20.0 with tests, not yet committed. |
| 2026-11-15 | Tech lead | `approve` |
