# Review your first file

> Status: Draft
> Created: 2026-11-18T13:13:29Z
> Last reviewed: 2026-11-18T13:13:29Z
> Next review: Not scheduled

In this tutorial you review one small Python file with the kit and read the
findings. It takes about 15 minutes after the tools are installed. In two test
runs the review cost USD 0.19 and USD 0.46 at API prices.

You will:

1. make a tiny sample repository with two faults in it
2. set up an audit workspace for it
3. run the file review on one file
4. read the findings and the cost

The tutorial doesn't run a full audit. For that, follow
[How to run an audit](../how-to-run-an-audit.md) afterwards.

## Before you start

You need macOS, or Linux with Homebrew, and these tools:

- git
- [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://claude.com/claude-code), signed in. Run `claude` once
  to check.

The commands were tested with zsh on macOS, with kit 0.26.1.

## 1. Get the kit and its tools

```zsh
git clone https://github.com/sophophilix/ai-code-audit.git ~/ai-code-audit
cd ~/ai-code-audit
make doctor
```

`make doctor` prints `ok` or `MISSING` for each tool. Install what is missing:

```zsh
make tools
```

`make tools` uses Homebrew and npm. To see what it would install first, run
`bin/kit tools --dry-run`.

`make doctor` also warns that the kit version isn't tagged. You can ignore
that for this tutorial.

## 2. Make a sample repository

The kit audits a git repository at a commit. Make one with a single file:

```zsh
mkdir ~/notes-demo && cd ~/notes-demo && git init -q
cat > notes.py <<'EOF'
"""A tiny notes store, written quickly."""

import sqlite3


def find(conn: sqlite3.Connection, text: str) -> list[tuple]:
    """Return the notes that contain the text."""
    return conn.execute(f"SELECT id, body FROM notes WHERE body LIKE '%{text}%'").fetchall()


def delete(conn: sqlite3.Connection, note_id: int) -> bool:
    """Delete a note and say whether it worked."""
    try:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
    except sqlite3.Error:
        pass
    return True
EOF
git add -A && git commit -qm "notes"
cd ~/ai-code-audit
```

The file has two faults. `find` builds SQL from its input, and `delete` says it
worked even when it failed.

## 3. Create the project and the workspace

A project holds what you know about one system. A workspace is a disposable
copy of its code that the audit works in. The kit never touches the original.

```zsh
make project NAME=notes-demo
make workspace NAME=notes-demo SOURCE=~/notes-demo REF=HEAD MODE=real WS_NAME=notes-demo
```

The project is in `~/audit-projects/notes-demo`. The workspace is in
`~/code/audits/notes-demo`.

## 4. Run the scans

```zsh
make ready WS=notes-demo
```

This step uses no AI. It copies the kit into the workspace, detects the stack,
runs the scanners and writes one brief for each file to review.

It ends with `Set up, but NOT ready` and a list of errors. That is expected:
the kit won't start any AI work until you say who approved it and which model
to use. You do that next.

## 5. Fill in the intake and choose the model

Open `~/code/audits/notes-demo/.audit/project.md`. Replace the six
placeholders under **Intake (required)**. For this sample, any honest values
work:

```markdown
## Intake (required)
- Organisation and jurisdiction: Personal project, Australia
- Repository and commit to audit: notes-demo @ HEAD
- Tech lead (passes checkpoints): <your name>
- Security owner (gets Critical findings the same day): <your name>
- AI use approved by (name, date, scope): <your name>, <today's date>, this sample only
- Where the AI provider processes data (region, confirmed by): United States, <your name>
```

On a real audit these six lines matter. The AI provider reads the code, so
someone with the authority to allow that must be named.

Then use the one-provider model file:

```zsh
cd ~/code/audits/notes-demo
cp .audit-kit/config/models.single-provider.example.yaml .audit/models.yaml
```

If your shell asks whether to overwrite `.audit/models.yaml`, answer `y`.

Open `.audit/models.yaml` and fill in the one empty value, `region`, with the
region you wrote in the intake:

```yaml
    region: "United States"
```

Check both files:

```zsh
cd ~/ai-code-audit
make validate WS=notes-demo
```

You see two warnings and then `pass: 0 error(s)`. One warning says the
verifier shares a model family with the other agents, which is what one
provider means. The other says the intake names no commit ID. Two notes
follow, because you edited the workspace's copies and not the project's. That
is fine here.

## 6. Review the file

The scans listed the review units in
`~/code/audits/notes-demo/.audit/work/files/units.tsv`. There is one, `u001`.
See what the review would run, without running it:

```zsh
bin/kit review notes-demo --units u001 --dry-run
```

Now run it:

```zsh
bin/kit review notes-demo --units u001
```

This takes one to two minutes. The kit sends the file's brief to the model,
which has no tools and sees nothing else. The kit then checks the answer. If
a quote doesn't match the file, or a rule isn't met, the kit sends the answer
back once or twice to be repaired. It writes a record only when the checks
pass.

The last line is `kept: 0, reused: 0, done: 1, ...`.

## 7. Read the findings

Put the record in the findings store and list what was found:

```zsh
make store WS=notes-demo
bin/kit query notes-demo "select id, severity, check_id, start_line, title from findings"
```

You see something like this. The wording, the number of findings and
sometimes a severity change from run to run. In one test run the SQL finding
was High, and in another it was Medium with a question about who calls `find`.

| id | severity | check_id | start_line | title |
|---|---|---|---|---|
| FILE-u001-001 | high | PY-SQL-STRING | 8 | SQL injection in find(): text interpolated into a LIKE query |
| FILE-u001-002 | medium | SLOP-SWALLOW | 16 | delete() swallows database errors and always returns True |
| FILE-u001-003 | medium | SLOP-COMMENT | 12 | Docstring on delete() claims it reports whether the delete worked |

Open the full record:

```zsh
open ~/code/audits/notes-demo/.audit/files/notes.py.md
```

For each finding, look at three lines:

- **Excerpt**: the code it quotes. The kit compared it with the file.
- **Evidence**: why it has this severity. For a `SLOP-` finding rated Medium
  or higher, it names the question from the severity guide and the line that
  answers it.
- **Sources**: the official documentation behind the recommendation.

The record also has a **Checks** table. It lists every check the reviewer
answered, including the ones it marked `not found`.

## 8. See what it cost

```zsh
make cost WS=notes-demo
```

The table gives passes, tokens, cost and seconds. More than one pass for one
unit means the kit asked for a repair.

## What you did

You ran the first stage of an audit on one file. The same steps work on a real
repository: point `SOURCE` at it, and review a few units before you review all
of them. `file_review.mode` in `models.yaml` controls that.

A full audit continues from here with discovery, four specialist reviews, an
independent verifier and a written report. See
[How to run an audit](../how-to-run-an-audit.md).

## Clean up

```zsh
rm -rf ~/notes-demo ~/code/audits/notes-demo ~/audit-projects/notes-demo
```
