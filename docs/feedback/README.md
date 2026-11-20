# User feedback

> Status: Approved
> Created: 2026-11-20T12:07:07Z
> Last reviewed: 2026-11-20T12:07:07Z
> Next review: Not scheduled

This folder holds feedback from people who have used the kit. Each session
gets one file. A session is a demo, a trial run, a chat or a written review.

Feedback is a claim about the kit, not a decision. A record says what the
person asked for and what the kit does today. A change to the kit still goes
through an issue, a pull request or a decision record in `docs/decisions/`.

## Record a session

1. Copy the template below into `docs/feedback/<topic>-<YYYYMMDDTHHMMSSZ>.md`.
2. Use the UTC time you write the record for the timestamp.
3. Name the person by role only, such as "tester, non-technical, Claude Code on Ubuntu".
4. Write each point as one item. Quote short phrases only.
5. Check each point against the kit, and record what the kit does today.
6. Give each point a status and a next step.
7. Add a row to the index in this file.

This repository is public. Don't record a person's name, phone number or
employer without their permission. Don't record a client's name or code.
`CONTRIBUTING.md` explains the client-terms hook.

## Status values

| Status | Meaning |
|---|---|
| `new` | Recorded, not yet checked against the kit. |
| `checked` | Compared with the kit. The record says what the kit does today. |
| `planned` | Has an issue, a pull request or a decision record. Link it. |
| `done` | Shipped. Give the kit version. |
| `declined` | Won't be built. Give the reason. |
| `user error` | The kit already does it. The docs may need a change. |

## Template

```markdown
# <Short title of the session>

> Status: Draft
> Created: <UTC timestamp>
> Last reviewed: <UTC timestamp>
> Next review: Not scheduled

## Session

- Date: <YYYY-MM-DD>
- Who: <role, technical level>
- Setup: <OS, AI tool, kit version>
- Format: <demo, chat, trial run, written review>

## Points raised

### F1. <One-line summary>

- What they said: <paraphrase, or a short quote>
- What the kit does today: <checked fact, with a file reference>
- Status: <status>
- Next step: <action, or "none">

## Follow-up

- [ ] <action>
```

## Index

| Date | Record | Who | Points | Open |
|---|---|---|---|---|
| 2026-11-20 | [First outside trial](first-outside-trial-20261120T120707Z.md) | Tester, less technical, Claude on Ubuntu (WSL) | 10 | 6 |
