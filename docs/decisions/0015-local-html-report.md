# ADR 0015: One local HTML file to read the whole audit

> Status: In review
> Created: 2026-11-20T20:42:54Z
> Last reviewed: 2026-11-20T20:42:54Z
> Next review: after the first audit that ships the page

## Review guide

Decision requested: add `kit report-html`, which writes the whole audit as one
self-contained HTML file that opens offline from disk, with a findings
explorer that guides the reader from the report to the code each finding
quotes.

Check these points:

- [ ] Showing only the excerpts the findings already quote, not a viewer for
      the whole source (D3), is enough for a reader to follow a finding.
- [ ] The page's content security policy (D5) is strict enough for a file
      that holds text the target influenced.
- [ ] A person, not an agent, runs it, and it stays separate from `kit publish`
      (D7).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

A full audit ends with about ten Markdown files, a findings store, a backlog
CSV, diagrams and Office copies, all in `.audit/`. A tech lead can read them.
A stakeholder, or anyone less technical, sees a folder of files.

The first outside tester asked for "a single HTML file so the user can see all
the various reports in one place". They also asked for a page they can "click
and get guided on where what is happening". The user agreed that a local,
offline page fits the kit.

This record adds one command that writes `.audit/report.html`. It holds the
report, the specialist reviews, the diagrams and every finding. The findings
explorer starts with what matters most and leads, finding by finding, to the
lines of code each one quotes. The file needs no server, no network and no
installed software beyond a browser.

## Evidence

| Observation | Where |
|---|---|
| The outputs are separate files: discovery, architecture, engineering, security, accessibility, verification, final report, backlog CSV and briefing. | `core/runbook.md`; a past audit's `.audit/` folder |
| In one past audit the Markdown outputs total about 350 KB. | `du` over `01-*.md` to `09-*.md`, 2026-11-20 |
| The findings store holds every file-record and trace finding with its path, lines, quoted excerpt, severity, verification, evidence, recommendation and sources. A past audit held 561, all with an excerpt. | `src/audit_kit/store.py`, `TABLES["findings"]`; query on a past store, 2026-11-20 |
| The specialist findings (`SEC-`, `ARC-` and so on) are parsed from the stage outputs. The register links each file finding to the specialist finding that reports it. | `src/audit_kit/register.py`, `stage_findings()` and `register()` |
| The kit checks that a quoted excerpt matches the cited lines before it accepts a record. | `README.md`, "Why it's built this way"; ADR 0004 |
| `kit verify` (OUT-R7) searches every text output under `.audit/`, including `.html` and `.svg`, for values the secret scan found. | `src/audit_kit/verification.py`, `_check_secret_values()`; `src/audit_kit/leaks.py`, `TEXT` |
| `kit diagrams` exports SVG images of every diagram page when draw.io is installed. | ADR 0014; `src/audit_kit/diagram_export.py` |
| `kit publish` already runs Pandoc from the kit folder, when it is installed. | `src/audit_kit/outputs.py`, `publish()` |
| With Pandoc 3.11, the `gfm`, `commonmark` and `commonmark_x` readers ignore `-raw_html`: a `<script>` element passes through to the HTML. Pandoc's own `markdown` reader with `-raw_html-raw_attribute` turns raw HTML into text. No reader removes a `javascript:` link. | Local test, 2026-11-20: one input with a `<script>` element, a `javascript:` link and `<b>`, through each reader |
| A content security policy in a `<meta http-equiv>` element applies to a page opened from disk. A `script-src` with a hash and without `'unsafe-inline'` blocks injected scripts and `javascript:` URLs. | W3C, Content Security Policy Level 3; MDN, `Content-Security-Policy`. Not yet checked by opening a page (see Risks) |

## Decision

**D1. One command, one file.** `kit report-html <workspace>` (`make report-html
WS=`) writes `.audit/report.html`. It runs again safely and overwrites the
file. The page opens from disk with a double click. It needs no server and
loads nothing from the network.

**D2. What the page holds.**

| Section | Content |
|---|---|
| Start | The audit's name, commit, kit version and dates. Part A of the final report. Counts of findings by severity and by verification. A plain notice when the final report or checkpoint 2 isn't done yet. |
| Where to start | The findings to read first, in order: verified critical and high, then unverified high, then medium. Each line links to the finding. |
| Findings | Every finding from the store and the stage outputs, in one table. Filters for severity, verification, agent, check and file, and a text search. |
| Finding | Title, severity and the reason for it, the file and lines, the quoted excerpt, what goes wrong, the recommendation and its sources, and links to related findings: the specialist finding that reports it, and other findings in the same file. |
| Files | The audited files that have findings, with counts. A file opens its findings in line order. |
| Reports | Each Markdown output, rendered: discovery, architecture, engineering, security, accessibility, verification, final report. |
| Diagrams | The exported SVGs, with the four views on tabs. A note when there are none. |
| Backlog | The backlog CSV as a table. |

**D3. Code comes only from the findings.** The page shows the excerpts the
findings already quote. The kit checked each one against the cited lines
when it accepted the record. The page doesn't read the target's files, and
it has no viewer for the whole source. Paths are shown as text relative to
the target, not as `file://` links, because the reader's copy of the code may
be elsewhere or absent.

**D4. Built with what the kit already has.** Python's standard library writes
the page. Every piece of text from the outputs goes through `html.escape`.
Markdown is rendered by Pandoc with `-f markdown-raw_html-raw_attribute`,
so raw HTML in an output becomes text. The GitHub reader (`gfm`) can't be used
here, because it passes raw HTML through even with `-raw_html` (Evidence). The
kit treats Pandoc's output as untrusted anyway: D5 and D6 apply to it. Without
Pandoc, each report shows as preformatted text,
and the command says so. Findings go into the page as JSON inside
`<script type="application/json">`, with `<` escaped. One small inline
script, written for the kit with no framework, adds filters, search and
navigation. Without JavaScript, the reports and the findings table still
read in order. No new Python dependency.

**D5. The page can't reach the network or run injected code.** The page sets
this policy in a `<meta>` element:

```text
default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-<hash of the kit's script>'
```

Images are inlined as `data:` URIs. The kit keeps a link only if it starts
with `#` or `https://`. It turns every other link into plain text. That keeps
the official sources in recommendations clickable (AGENTS.md rule 8), and
removes `javascript:`, `file:` and `data:` links.

**D6. The checks.** `kit verify` already searches `report.html` for secret
values (OUT-R7). A new check, OUT-R18, fails when `report.html` exists and:

- it has no content security policy, or a different one from D5
- an `src` or `href` points anywhere other than `#`, `data:` or `https://`
- it holds a `<script>` element other than the kit's own script and the JSON
  data element

**D7. A person runs it, separately from `kit publish`.** Like `kit publish`, a
person runs it from the kit folder. Agents never do (AGENTS.md rule 2). It's
a separate command so a failure in one doesn't block the other. `kit publish`
ends with a line that suggests it.

**D8. The page says what it is.** A banner at the top of every section says
the page holds code excerpts and findings from the audited system, and that
it should be handled like the source code and the report. A finding the
verifier hasn't confirmed is labelled `unverified` wherever it appears.

## Consequences

- One file holds the whole audit. It is easy to read and easy to send, so
  D8's banner matters.
- The tester's guided view exists without a server, and without changing what
  the agents write.
- A new output means another check (OUT-R18) and a test fixture for it.
- Pandoc becomes more useful, but stays optional.

## Not in this decision

- Hosting the page, sharing it or serving it on a network.
- Editing on the page: accepting a risk, commenting or changing a status.
  Feedback F8 (accepted risks) needs its own record.
- A full source viewer, or links into a code host.
- Changing what the agents write. The page reads the outputs as they are.
- PDF output of the page.

## Rejected

- **Pandoc's `--embed-resources` on the Markdown alone.** It makes one file,
  but it has no findings explorer and no guided order.
- **A static site generator** (MkDocs, Docusaurus and similar). It adds a
  dependency and writes a folder of files, not one.
- **A JavaScript framework from a CDN.** It needs the network, and loads code
  the kit doesn't control.
- **A local web server.** It adds a process to start and stop, and a port.
  A file opened from disk does the job.
- **Embedding the audited source files.** It would send the whole codebase
  with every copy of the report. OUT-R7 can only check values the secret scan
  found.

## Risks and open items

- **Size.** About 600 findings, ten reports and ten SVGs fit in a few
  megabytes. A much larger audit may make the page slow to open. The first
  real page will show this.
- **Browsers differ in how they treat files opened from disk.** The policy in
  D5 is standard, but nobody has opened such a page in each main browser yet.
- **Pandoc versions differ.** An older Pandoc may render some Markdown
  differently, and Pandoc's `markdown` reader differs from GitHub's in small
  ways. The reports remain readable. A Pandoc that passes raw HTML through
  would still be caught by D5 and D6, which is why they don't rely on it.
- **The page can be mistaken for an approved report.** D2's start section
  says when the final report or checkpoint 2 isn't done. The kit reads that
  from the outputs as written, so it is a claim, not proof of approval.
- **Text from the target appears on the page.** Escaping (D4) and the policy
  (D5) stop it from acting as code. It can still mislead a reader, as it can
  in the Markdown today.

## Review history

| Date (UTC) | Reviewer | Outcome |
|---|---|---|
| 2026-11-20 | Claude (author) | Drafted after the first outside trial (feedback F3) |
