# Third-party skills and tools

Every third-party skill the kit relies on is **pinned to a reviewed commit**
and installed from that commit, never with `npx skills add` or a moving
branch. Updating means a new review of what changed, a new row here, and a
re-run of the evaluation.

## Linguist rule data

| Field | Value |
|---|---|
| Repository | https://github.com/github-linguist/linguist |
| Files | `lib/linguist/vendor.yml`, `lib/linguist/documentation.yml`, `LICENSE` |
| Pinned release | v9.7.0 (commit `e0c78d6`, published 2026-08-26) |
| Licence | MIT (copied to `src/audit_kit/rules/linguist/LICENSE`) |
| Used by | `src/audit_kit/inventory.py` (file classes) |
| Reviewed | 2026-11-06 |

**Review.** Data only: 168 and 18 path regexes, loaded with `yaml.safe_load`; all compile
under Python `re`. Nothing is executed. Linguist built them for language statistics, so
some match files an audit must review (`.github/`, `Jenkinsfile`, `.gitignore`, `env/`);
the kit's `UNVENDOR` rule overrides those. Updating means copying the files from a new
release, re-running the tests, and a new row here.

## DuckDB (Python package)

| Field | Value |
|---|---|
| Repository | https://github.com/duckdb/duckdb-python |
| Pinned release | `duckdb==1.5.6` (published 2026-09-28; 2.0.0, published 2026-10-21, is a new major version and wasn't taken) |
| Licence | MIT (PyPI classifier) |
| Used by | `src/audit_kit/store.py`: `kit store` writes `.audit/findings.duckdb`, `kit query` reads it (ADR 0007 D6) |
| Reviewed | 2026-11-08 |

**Review.** A local, in-process database; nothing is installed or downloaded at
run time. `kit query` opens the store read-only with `enable_external_access`
off, extension autoloading and autoinstall off, and the configuration locked.
Tested in `tests/unit/file_review/test_store.py`: `INSERT`, `COPY ... TO`,
`read_csv` of a host file, `SET enable_external_access`, `ATTACH` and
`INSTALL` are all refused. Updating means a new pin at least two weeks old,
re-running those tests, and a new row here.

## Node.js Best Practices (cited, not installed)

| Field | Value |
|---|---|
| Repository | https://github.com/goldbergyoni/nodebestpractices |
| Pinned commit | `dc3d60c` (master, read 2026-11-07; README says "2026 edition") |
| Licence | CC BY-SA 4.0 |
| Used by | `profiles/node-express` (check sources by item number) and its `references/service-structure.md` and `references/error-handling.md` |
| Reviewed | 2026-11-07 |

**Use.** Cited by item number; no text is copied. ShareAlike would require any
adapted text to carry CC BY-SA, so the profile is written in the kit's own words.
A community guide (README by Yoni Goldberg), not a Node.js project document:
cite an official source instead where one says the same thing. Known gaps at this
commit: the English page on separating the Express app from the server was removed
(translations remain); no item gives shutdown code; item 2.6 registers an
`uncaughtException` handler, which the Express performance page advises against.
The profile's `NODE-UNHANDLED` reconciles them (never resume).

## Practica.js (cited, not installed)

| Field | Value |
|---|---|
| Repository | https://github.com/practicajs/practica |
| Pinned commit | `9d0cfc8` (main, read 2026-11-07) |
| Licence | MIT (from the repository sidebar; LICENSE file not opened) |
| Used by | `profiles/node-express/references/service-structure.md` (layout and start/stop shape) |
| Reviewed | 2026-11-07, `start.ts` and `entry-points-fastify/api/server.ts` only |

**Use.** Shape only, no code copied. Its `stopWebServer` awaits the callback-style
`server.close()`, and neither file handles SIGTERM, so the reference's shutdown code
is the kit's own.

## drawio-skill

| Field | Value |
|---|---|
| Repository | https://github.com/Agents365-ai/drawio-skill |
| Path | `skills/drawio-skill` |
| Pinned commit | `053600a` (skill version 3.4.4) |
| Licence | MIT |
| Used by | `core/skills/architecture-diagrams` |
| Reviewed | 2026-11-06, targeted review (below) |

**Review scope.** We reviewed the code paths the kit allows, not all
~11,700 lines: `diagramctl.py` (build, views, doctor, transform, publish),
`diagram_ir.py`, `validate.py`, `autolayout.py`, `drawio_cli.py`,
`shapesearch.py`, and `references/security.md`.

**Findings.**
- No network access in those files (`urllib.parse` only, for decoding).
- Subprocesses use argument lists without a shell: the skill's own scripts via
  `sys.executable`, Graphviz `dot`, and the draw.io CLI (`--version` only
  with `doctor --probe`).
- Writes only to the output paths given.
- `aiicons.py` and `dbxicons.py` fetch from `unpkg.com` and `cdn.simpleicons.org`
  (host allow-listed in code). They're excluded by the kit's rules.
- The shape index (`data/shape-index.json.gz`) has 645 `img/lib/azure2/`
  entries (draw.io's copy of the Microsoft Azure icons) and 109 legacy
  `mxgraph.azure.*` shapes. The kit allows only the former.
- The SKILL.md sets `disable-model-invocation: true`, so a person starts it.
- The publisher's identity isn't stated beyond the GitHub account.
  The repo is popular (about 10.6k stars) and actively maintained (about 50
  commits from July to November 2026), so expect frequent updates. Pin, don't follow.

**Smoke test (2026-11-06).** On a sample IR with `img/lib/azure2/` styles: `build --from ir`,
`views`, `validate.py --score` (0 errors, 0 crossings), `whatif` and `story` all ran offline and
kept the official icon styles. The scripts import their sibling modules, so don't run them with `python3 -I`.

**Install (pinned).**
```zsh
DEST=~/.local/share/agent-skills/drawio-skill-053600a
git clone https://github.com/Agents365-ai/drawio-skill.git "$DEST"
git -C "$DEST" checkout --detach 053600a
# Claude Code (user-level): link only the skill folder
ln -s "$DEST/skills/drawio-skill" ~/.claude/skills/drawio-skill
# Local tools it calls (optional): draw.io for export, Graphviz for layout
brew install --cask drawio && brew install graphviz
```
Software installs on council machines need ICT approval.

## technical-writing and humanizer (writing skills)

| Field | Value |
|---|---|
| Repository | https://github.com/sophophilix/agent-skills |
| Paths | `plugins/writing/skills/technical-writing` (version 1.1.0), `plugins/writing/skills/humanizer` (version 3.0.0) |
| Pinned commit | `c33d852` (main, 2026-11-09) |
| Licence | MIT (repository `LICENSE`). `humanizer` is a modified copy of blader/humanizer 3.0.0, MIT, with its own `LICENSE`. `scripts/ste-lint.py` is a byte-for-byte copy of danyuchn/asd-ste100-skill at `d48bfca`, MIT, with `LICENSE-ste-lint`. The repository's own `THIRD_PARTY.md` records both. |
| Used by | `core/agents/lead-reviewer.md` and `core/skills/audit-publishing` (the report, the briefing and the ADRs) |
| Reviewed | 2026-11-10 |

**Review.** Both skills are instructions only, except `ste-lint.py`. The
linter imports the standard library only, reads the files named on its
command line, and makes no network or subprocess calls (checked 2026-11-10 by
reading its imports and searching for `subprocess`, `socket`, `urllib`,
`os.system`, `exec(` and `eval(`; 2,388 lines, the rest not read). Agents
never run it (AGENTS.md rule 2). A person runs it with `python3 -I` at
publishing, and its output is advisory.

`technical-writing` defaults to `docs/`, its own document-control block and a
review-guide format. `audit-publishing` ("Where the kit's rules win") replaces
those for audit outputs, so the skills run unchanged.

**Install (pinned).**
```zsh
DEST=~/.local/share/agent-skills/agent-skills-c33d852
git clone https://github.com/sophophilix/agent-skills.git "$DEST"
git -C "$DEST" checkout --detach c33d852
# Claude Code (user-level): link only the two skill folders
ln -s "$DEST/plugins/writing/skills/technical-writing" ~/.claude/skills/technical-writing
ln -s "$DEST/plugins/writing/skills/humanizer" ~/.claude/skills/humanizer
```
A link to a working checkout of the repository follows its branch, not the
pin. Point the links at the pinned folder before an audit.

## knip and dependency-cruiser (sandbox image only)

| Field | Value |
|---|---|
| Packages | `knip@6.42.1` (ISC), `dependency-cruiser@18.7.0` (MIT), both published 2026-10-19 |
| Installed | Only inside the sandbox image, `config/sandbox/Dockerfile`, with `--ignore-scripts` |
| Used by | `kit sandbox structure` (ADR 0005); never on the host, because knip's plugins load the target's config files |
| Reviewed | 2026-11-07: versions and licences from the npm registry. 2026-11-08: both ran in the sandbox and wrote JSON (`knip --reporter json`, `depcruise --output-type json`) |
