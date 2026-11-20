# ADR 0014: Export diagram images with the draw.io command line

> Status: Approved
> Created: 2026-11-20T13:32:00Z
> Last reviewed: 2026-11-20T14:30:02Z
> Next review: after the first export on Linux and on WSL2

## Review guide

Decision requested: make `kit diagrams` export SVG and PNG images of every
diagram page when the draw.io desktop app is installed, and add a command that
exports again after a person tidies the diagrams.

Check these points:

- [ ] Skipping the export with a message, instead of failing, is right when
      draw.io is missing (D1).
- [ ] Running draw.io under a virtual display on Linux (D3) is an acceptable
      extra dependency.
- [ ] A separate export command (D5) is the right way to keep a person's
      tidying.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

`kit diagrams` writes editable `.drawio` files and no images. A person must
open each file in draw.io and export every page by hand. The report template
expects `diagrams/target.png`, so `kit publish` has no picture to embed until
someone does that.

The first outside tester ran the kit on Ubuntu in WSL2 and saw no images. They
thought the images "are generated later". That is true, but nothing told them so.

draw.io's desktop app has a command line that exports a page to SVG or PNG
with no window. The kit already detects the app in `kit doctor`. This record
uses that command line to export every page, so a run ends with images.

## Evidence

| Observation | Where |
|---|---|
| `kit diagrams` builds `.drawio` and `.views.drawio` files and validates them. It writes no images. | `src/audit_kit/outputs.py`, `diagrams()` |
| The views file holds four pages: Executive, Deployment, Dataflow, Security. | `outputs.py` (`VIEWS`); page names read from a built `target.views.drawio` |
| The publishing skill expects SVG for Markdown and Marp, and PNG at 2× for Word and PowerPoint. Its example embeds `diagrams/target.png`. | `core/skills/audit-publishing/SKILL.md`, lines 20 and 46 |
| draw.io 32.7.4 exports with `-x`. `-p` picks one page, counted from 1. Without it, an image export takes the first page only. `--all-pages` covers PDF, HTML and SVG only. | `draw.io --help`, run on macOS on 2026-11-20 |
| An export of page 2 of a built views file took about 3 seconds offline on macOS. The PNG at `-s 2` was 4482 × 1277 pixels, with the house style and icons intact. | Local test, 2026-11-20 |
| On Linux, the command line needs a display. drawio-skill advises `xvfb-run -a` for headless use, and `--disable-gpu` when graphics drivers fail. | drawio-skill at `053600a`, `references/troubleshooting.md` |
| On WSL2, draw.io is often installed on Windows. Its command line is `draw.io.exe` under `/mnt/c`, and it needs Windows paths (`wslpath -w`). | drawio-skill at `053600a`, `references/troubleshooting.md`, "WSL2 / Windows specifics" |
| A PNG exported with `-e` (diagram embedded) is truncated and needs `repair_png.py`. | drawio-skill at `053600a`, `SKILL.md`, "Export invariants" |
| The kit looks for draw.io as `drawio` on the PATH or as the macOS app. | `src/audit_kit/machine.py`, `_drawio_app()` |

## Decision

**D1. Export when draw.io is there, and say so when it isn't.** After it builds
and validates the diagrams, `kit diagrams` exports images if it finds the
draw.io command line. If it doesn't, it prints one line saying the diagrams
were built without images, and how to install draw.io or export by hand. A
missing draw.io never fails the command, because the `.drawio` files are the
primary output.

**D2. One image per page.**

| File | Pages | Output |
|---|---|---|
| `<name>.drawio` | 1 | `<name>.svg`, `<name>.png` |
| `<name>.views.drawio` | 4 | `<name>-executive.svg`, `<name>-executive.png`, and the same for each view |

Images go next to their source in `.audit/diagrams/`. Page names come from the
`<diagram name="...">` elements, in lower case. SVG uses
`--embed-svg-images`, so it shows the icons with no network. PNG uses `-s 2`
and no `-e`, which avoids the truncation bug. The kit refuses to write through
a symlink, as it does for the `.drawio` files.

**D3. Find the command line once, per platform.** The kit resolves an
absolute path in this order:

1. `drawio` on the PATH (Homebrew, Linux packages, snap)
2. the macOS app: `/Applications/draw.io.app/Contents/MacOS/draw.io`
3. on WSL2 only, the Windows app under `/mnt/c/Program Files/draw.io/` or the
   user's `AppData/Local/Programs/draw.io/`. Paths are converted with
   `wslpath -w`.

On Linux with no `DISPLAY` or `WAYLAND_DISPLAY`, the kit runs the export under
`xvfb-run -a` and adds `--disable-gpu`. If `xvfb-run` is missing, it skips the
export as in D1 and names the package to install. `kit doctor` and
`kit tools` report both draw.io and, on Linux, `xvfb-run`.

The kit never adds `--no-sandbox`. If draw.io's sandbox fails on a machine,
the export fails and the person decides what to do.

**D4. Each export is bounded.** Each call has a five-minute timeout
(`TIMEOUT` in `diagram_export.py`). A failed page is reported and the rest continue. The command
ends with a count, such as `exported 10 of 10 images`.

**D5. Export again after tidying.** `kit diagrams` rebuilds the `.drawio`
files from the IR, so it overwrites a person's tidying. A new command,
`kit export-diagrams <workspace>` (`make export-diagrams WS=`), exports the
current `.drawio` files without rebuilding them. The run order becomes: build,
tidy in draw.io, export, publish.

**D6. A person runs it.** The export starts draw.io, a program the kit
doesn't control. Like `kit diagrams` today, a person runs it from the kit
folder. Agents never do (AGENTS.md rule 2). The diagram files come from the
architect's IR, which quotes the target's names, so draw.io renders text that
the target influenced. The export runs offline, as `kit diagrams` does.

## Consequences

- A run that has draw.io ends with images, and `kit publish` can embed them.
- Linux setups need one more package (`xvfb`) for images. The audit runs
  without it.
- Re-running `kit diagrams` still overwrites tidied `.drawio` files. D5 makes
  that easier to work around, not impossible to do.
- The kit's tests can't run draw.io. They check the commands the kit would
  run, with draw.io replaced by a fake program.

## Not in this decision

- Exporting PDF or VSDX. A person can still do that in draw.io.
- Keeping a person's tidying when `kit diagrams` runs again.
- The local HTML report. It would show these images, but it needs its own
  record.

## Rejected

- **Rendering with drawio-skill's viewer route** (`viewer.diagrams.net` in a
  headless browser). It loads the diagram from the internet, which breaks the
  kit's offline rule.
- **Exporting from the Python code without draw.io.** No library renders the
  draw.io format, the house style or the Azure icons faithfully.
- **Failing `kit diagrams` when draw.io is missing.** The editable files are
  the main output. A missing viewer shouldn't block the audit.
- **Adding `--no-sandbox` on Linux by default.** It removes a protection
  against the text the target influenced.

## Risks and open items

- **Nobody has exported on Linux or WSL2 yet.** The flags come from
  drawio-skill's notes and draw.io's help. The first runs there may need
  changes. The next review waits for them.
- **draw.io's command line changes between versions.** The kit doesn't pin
  draw.io. A changed flag breaks the export, but not the build (D1).
- **Large diagrams make large images.** A wide diagram at `-s 2` can exceed
  the size a vision model accepts. The images are for people, not agents.
- **Text from the target appears in the images.** The architect writes node
  labels from what the code shows. A label that holds a secret would be
  exported too. `kit verify` checks outputs for secrets. Nobody has checked
  whether it reads the exported SVG and PNG files.

## Review history

| Date (UTC) | Reviewer | Outcome |
|---|---|---|
| 2026-11-20 | Claude (author) | Drafted after the first outside trial (feedback F4) |
| 2026-11-20 | Tech lead | `approve` |
| 2026-11-20 | Claude (author) | Built in 0.27.0. D4's timeout changed from `LONG` (30 minutes) to five minutes, because a hung draw.io start would otherwise hold the run. D2 gained one case: a file with no `<diagram>` element is one page. A real export on macOS wrote 20 of 20 images in 49 seconds. |
