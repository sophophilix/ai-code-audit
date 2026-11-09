# ADR 0001: A complete, checked inventory of the target

> Status: In review
> Created: 2026-11-06T12:47:48Z
> Last reviewed: 2026-11-06T12:47:48Z
> Next review: Not scheduled

## Review guide

Decision requested: replace heuristic detection with a deterministic inventory stage
that records every file of the target, accepts any source (git or not), and is the
single input that detection, scans and agents are checked against.

Check these points:

- [ ] The ingest rules (D1, D2): any source becomes a git snapshot, nothing is dropped by ignore rules, and the snapshot is proven equal to what was received.
- [ ] Building the walk in Python and taking Linguist's rule data, instead of adopting a Rust or Go tool (D3, D4).
- [ ] "Excluded" becoming a label on a recorded file, never a reason to leave a file out (D5).
- [ ] ScanCode and Syft as optional cross-check scans rather than dependencies (D8).
- [ ] The coverage check (D10) being deferred to the findings store.

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The kit's audit pipeline is only as complete as its first step, and that step is
weak. `detection.py` picks profiles from filename and regex hits and writes a summary.
It never records which files exist, which it read, or why it set any aside. Every
later stage (scans, the five specialist agents, the verifier) inherits those gaps
and can't detect them.

This record makes the first step an inventory: one sorted JSON record per file in
the target, with its class, the reason for that class, its hashes and whether it was
read. The inventory is built from the files on disk, then checked against the git
tree of the snapshot commit. Any difference stops the run. Detection, scans and the
agents' work plans read the inventory instead of walking the tree themselves.

Research found no existing tool that does this job end to end for an audit. Linguist,
go-enry, tokei and ripgrep's `ignore` crate all skip files by design. ScanCode is the
closest match but is a licence-compliance tool with a heavy runtime. The decision is
to build a small inventory in the kit's Python package, reuse Linguist's rule data,
and run ScanCode or Syft as optional cross-checks.

## Context

### What the first evaluation run showed

Evidence from the pilot eval workspace (
kit 0.9.1, snapshot `92a3e9d`), checked on 2026-11-06:

1. Excluded files are invisible to every layer. `public/vendor` (face-api.js,
   libheif.js, heic2any.min.js, qrcode.js, face models) is excluded by folder name in
   `detection.py` (`GENERATED_DIRS`). `scans.py` passes the same exclusions to Semgrep
   and jscpd, and agents are told not to review it. The only remaining coverage is one
   sentence in `detected.md` asking agents to "inventory these". No code does. The
   archived upstream of face-api.js was never flagged.
2. Silent skips. `workspace.py` `SKIP_DIRS` drops `.git`, `.audit`, `.audit-kit`,
   `.claude` and `node_modules` without reporting them. Files whose extension is not
   in `TEXT_EXT` (`.bin`, `.wasm`, fonts, `.ico`) are never read and never listed.
3. A false governance signal. `detected.md` reports "AI instruction files: .claude".
   The source repository at `a1b2c3d` contains no `.claude`. `kit ready` runs install
   before detect, so detect found the kit's own adapter.
4. Stale stamps. `detected.md` says `kit_version: 0.9.0`; the workspace has 0.9.1
   installed. Nothing records which inputs produced a derived file.
5. An unchecked equality claim. The coordinator wrote that the snapshot equals the
   source. It differs by 2 removed paths (`eval-remove.txt`) and 8 seeded files, and
   the claim had to be corrected in commit `7b5c985`. No code computes this diff.
6. Overfitting to one target. `TEST_PATH` treats `-check.js` as a test, which is
   the pilot app's naming convention. Profiles exist only for Node, Express, MSSQL and
   Azure. A Python or .NET repository would load only `ai-governance`, with no warning.

### Non-git sources

The kit can't audit a code drop that isn't a git repository. Real mode runs
`git clone`. Eval mode runs `git archive`, falling back to `git clone`, so a plain
folder or an archive fails.

Both git paths can also lose files silently:

- `git archive` leaves out paths with the `export-ignore` attribute: "Files and
  directories with the attribute export-ignore won't be added to archive files"
  ([git-archive](https://git-scm.com/docs/git-archive), [gitattributes](https://git-scm.com/docs/gitattributes)).
- Eval mode commits the extracted snapshot with `git add -A`. Git "will not add
  ignored files by default ... Otherwise it will silently ignore the file"
  ([git-add](https://git-scm.com/docs/git-add)). A tracked file that matches the
  target's own `.gitignore`, or any ignored file in a plain folder, would vanish from
  the snapshot. This did not happen on the pilot app (207 source files, minus 2 removed,
  plus 8 seeded, equals the 213 in the snapshot), but nothing guards against it.

## Research

Sources were accessed on 2026-11-06. Statements marked "reviewer judgement" are not
taken from a source.

### Classifying files: Linguist and its ports

- **GitHub Linguist** (MIT, [LICENSE](https://raw.githubusercontent.com/github-linguist/linguist/main/LICENSE))
  classifies paths with three rule sets: `vendor.yml` (about 200 path regexes, such as
  `(^|/)vendors?/`, `(^|/)node_modules/`, `(\.|-)min\.(js|css)$` and
  `(^|/)jquery([^.]*)\.js$`), `documentation.yml` (18 regexes) and `generated.rb`
  (code). Repositories override these with the `.gitattributes` attributes
  `linguist-vendored`, `linguist-generated` and `linguist-documentation`
  ([overrides](https://github.com/github-linguist/linguist/blob/main/docs/overrides.md),
  [vendor.yml](https://raw.githubusercontent.com/github-linguist/linguist/main/lib/linguist/vendor.yml),
  [documentation.yml](https://raw.githubusercontent.com/github-linguist/linguist/main/lib/linguist/documentation.yml)).
  Linguist's purpose is to keep vendored code out of language statistics, so a
  vendored file is removed from its counts.
- **go-enry** (Apache-2.0) is a Go port built on Linguist v9.5.0 data, with
  `IsVendor`, `IsGenerated`, `IsDocumentation`, `IsTest`, `IsConfiguration`,
  `IsBinary` and `IsDotFile`. Python bindings exist on PyPI as `enry`, built on a C
  shared library through cffi ([go-enry](https://github.com/go-enry/go-enry)). Its
  README notes a divergence from Linguist on `bootstrap.css`.
- **hyperpolyglot** is a Rust port of Linguist's language detection. Its README says
  it does not exclude generated or binary files from breakdowns
  ([docs.rs](https://docs.rs/crate/hyperpolyglot/latest)).

Lesson: Linguist's rule data is mature, permissively licensed, and has a standard
override mechanism through `.gitattributes`. Its behaviour (dropping matched files)
is the wrong default for an audit.

### Walking the tree: ripgrep's `ignore` crate and tokei

- The Rust `ignore` crate (the walker behind ripgrep) skips hidden files and honours
  `.gitignore`, `.ignore`, `.git/info/exclude` and the global gitignore, all
  "enabled by default". `standard_filters(false)` turns them off as a group
  ([WalkBuilder](https://docs.rs/ignore/latest/ignore/struct.WalkBuilder.html)).
- **tokei** (Rust, MIT or Apache-2.0) counts files, code, comments and blank lines
  per language, "respects `.gitignore` and `.ignore` files by default", and skips
  hidden files unless given `--hidden` ([tokei](https://github.com/XAMPPRocky/tokei)).

Lesson: the established walkers are built for search and statistics, where skipping
is helpful. For an audit, every one of those defaults hides evidence. Nothing in the
walk itself is hard; the kit's existing `os.walk` with symlink refusal already does
it. The value is in the policy: skip nothing, record everything.

### Inventory and provenance: ScanCode, Syft and Software Heritage

- **ScanCode Toolkit** (Apache-2.0; CC-BY-4.0 for reference data; Python) is the
  closest prior art. Its pipeline "first collects an inventory of the code files and
  classifies the code using file types", then detects packages, licences and
  copyrights ([GitHub](https://github.com/aboutcode-org/scancode-toolkit),
  [docs](https://scancode-toolkit.readthedocs.io/en/latest/reference/scancode-cli/index.html)).
  `--info` adds size, type, language, sha1 and md5, and binary, text, source and script
  flags. `--classify` adds `is_key_file`, `is_legal`, `is_manifest`, `is_readme` and
  `is_top_level`. `--generated` flags generated code. `--facet` tags paths as core,
  dev, tests, docs, data or examples. Output is JSON, YAML, HTML, SPDX or CycloneDX.
- **Syft** (Apache-2.0) builds SBOMs from directories. By default it records file
  digests only for files owned by a detected package; `file.metadata.selection: all`
  with `file.metadata.digests: [sha256]` records every file
  ([File Selection](https://github.com/anchore/syft/wiki/File-Selection),
  [configuration](https://oss.anchore.com/docs/reference/syft/configuration/)).
  Its default, again, leaves out exactly the unmanifested vendored files an audit
  needs.
- **Software Heritage identifiers (SWHID)** are ISO/IEC 18670:2025. Content and
  directory identifiers "are, at present, compatible with the Git way of computing
  identifiers" ([Wikipedia](https://en.wikipedia.org/wiki/SoftWare_Hash_IDentifier)).
  The archive's `POST /api/1/known/` endpoint takes up to 1,000 SWHIDs and returns
  whether each is known ([API](https://docs.softwareheritage.org/devel/swh-web/uri-scheme-api-swhids.html)).
  Recording each file's git blob id therefore makes a later, approved provenance
  lookup possible without re-reading the target.

Lesson: ScanCode proves the shape (inventory, then classify, then identify) and is a
good independent cross-check. Recording git blob ids costs nothing and keeps the
door open to hash-based identification of vendored files.

### File-type detection

- Git treats a path as text if its contents "look like text"; the page doesn't
  define the test ([gitattributes](https://git-scm.com/docs/gitattributes)). The
  commonly cited rule, a NUL byte in the first 8,000 bytes, comes from git's source,
  not its documentation. Source: none, reviewer judgement.
- **Magika** (Apache-2.0, Python and Rust) detects over 200 content types with a deep
  learning model ([Magika](https://github.com/google/magika)).

## Decision

### D1. Ingest any source into a git snapshot

`kit workspace` accepts a git URL, a local git repository, a plain folder or a tar or
zip archive.

| Source | How it is ingested | Source fingerprint |
|---|---|---|
| Git URL or repository | Real mode: clone and check out `REF`. Eval mode: `git archive REF`, extracted with the tar `data` filter. | Commit SHA |
| Plain folder | Copied without following symlinks; symlinks recorded. | sha256 manifest of every file |
| Archive | Extracted with the tar `data` filter (zip with an equivalent path check). | sha256 of the archive and the per-file manifest |

Snapshots are committed with `git add -A --force`, so the target's ignore rules
can't drop a file. For a git source, the kit reads `.gitattributes` and records every
path with `export-ignore` that `git archive` left out. Real mode records untracked
and ignored files in the source checkout as "present in source, not committed".

### D2. Build the inventory before the kit is installed

The inventory is built from the freshly ingested snapshot, before `install` copies
`.audit-kit/` and `.claude/` into it. The kit can therefore never mistake its own
files for the target's. Target AI instruction files are recorded with class
`ai-instructions` before quarantine moves them.

The walk skips nothing except the workspace's own `.git` directory, which is
recorded as a single entry. It does not follow symlinks; each symlink is a record
with its target text. After the walk, the kit compares the inventory paths and
blob ids with `git ls-tree -r` of the snapshot commit. Any difference stops the run
with the list of differing paths.

### D3. Build the walk in the kit's Python package

The kit keeps its own walk in `audit_kit.workspace` instead of adopting the Rust
`ignore` crate, tokei or go-enry.

- The walk is about 30 lines and already enforces the confinement rule (C2).
- Every established walker's defaults are wrong for an audit (see Research), so
  adopting one means overriding all of its filters anyway.
- A Rust or Go dependency adds a second toolchain or native wheel to a Python CLI
  run by a small team. Reviewer judgement.

### D4. Take Linguist's rule data, pinned, with target overrides

The kit vendors `vendor.yml` and `documentation.yml` from a pinned Linguist release,
records them in `THIRD_PARTY.md` (MIT), and ports the path rules from
`generated.rb`. A refresh is a deliberate kit change with a test diff. The target's
`.gitattributes` `linguist-vendored`, `linguist-generated` and
`linguist-documentation` attributes override the defaults; the kit reads that file
as data and never runs anything from it (C3).

This replaces `GENERATED_DIRS`, the `-check.js` test rule and the licence-file
heuristic, which were tuned to the pilot app.

### D5. Excluded is a label, not an absence

Every file gets one record, whatever its class:

```json
{
  "path": "public/vendor/face-api.js",
  "kind": "file",
  "size": 1333943,
  "sha256": "…",
  "git_blob": "…",
  "class": "vendored",
  "reason": "linguist vendor.yml: (^|/)vendors?/",
  "language": "JavaScript",
  "binary": false,
  "lines": 0,
  "read": "skipped: class vendored",
  "banner": "face-api.js v…"
}
```

Classes: `own`, `vendored`, `generated`, `documentation`, `test`, `binary`,
`ai-instructions`, `data-candidate`, `symlink`, `seeded` (eval key only, never
written to the workspace) and `unknown`. `reason` names the rule that matched.
`read` says whether the kit read the file and, if not, why (too large, binary,
class, decode error).

Scans and agents may still leave a class out of review. They can't leave it out of
the record, and every report states how many files of each class it did not review.

### D6. Identify vendored files one by one

For each `vendored` or unmanifested third-party file, the inventory records:

- the version banner or `version` constant found in the first 64 KB (a regex, no
  code execution);
- a licence file in the same folder, if any;
- the package name from a banner or licence, if found.

These records are the input to the supply-chain stage: retire.js run offline against
a pinned database, then archived and deprecated lookups. That stage, and any
hash-based lookup (deps.dev, Software Heritage), needs network access and council
approval. It gets its own ADR.

### D7. Fail loudly

The run stops, or lists the item under "Needs a person" in `detected.md`, when:

- own files in a language no profile covers make up more than 5% of own lines
  (threshold reviewer judgement, adjustable in the intake);
- any file couldn't be read;
- the inventory and the snapshot tree differ (always a stop);
- an `unknown` class holds any file.

### D8. ScanCode and Syft as optional cross-checks

`kit scan` runs ScanCode (`--info --classify --generated --json`) and Syft (with
`file.metadata.selection: all`) when installed, writing to `.audit/scans/`. A check
compares their file lists and hashes with the inventory and reports differences.
Neither tool is a dependency: both bring their own large runtime, and the kit must
keep working when they are absent (the MISSING.txt rule).

### D9. Stamp derived outputs with their inputs

`inventory.json` records the source fingerprint, the snapshot commit and the kit
version, and contains no timestamp (so C4 holds). Every derived file (`detected.md`,
scan outputs, agent outputs) records the sha256 of the inventory it used. `kit
status` and pre-flight report any output whose stamp doesn't match the current
inventory or kit version.

### D10. Coverage check (deferred)

Agents' work plans will list the inventory paths they cover, and `kit verify` will
report own files no agent touched. This depends on typed findings and plans, so it
follows the findings store named as the next boundary in
[ARCHITECTURE.md](../architecture/ARCHITECTURE.md).

## Implementation status (0.10.0)

| Decision | Status | Notes |
|---|---|---|
| D1 Ingest any source | Done | Git, folder, `.tar`/`.tar.gz`/`.tgz`. Zip refused. A folder or archive in real mode becomes a snapshot. `export-ignore` paths are restored from git objects instead of stopping the run. |
| D2 Inventory and cross-check | Done | The walk handles the kit's own folders by rule, so it works before and after install; quarantined files are recorded at their original paths. Blob ids are compared, so line-ending normalisation in a target's `.gitattributes` shows up as "content differs". |
| D3 Python walk | Done | |
| D4 Linguist data | Done | v9.7.0 pinned. The real data vendors `.github/`, `Jenkinsfile`, `.gitignore` and `env/`, so the kit adds an `UNVENDOR` rule. `generated.rb` is not ported; a kit rule covers build-output folders. |
| D5 Records for every path | Done | `read` status is not a field yet; detection lists unreadable files under "Needs a person". |
| D6 Vendored identification | Done (0.11.0) | Version banners were rare in the pilot app's vendored files, so each record carries `upstream` (a repository URL in the header) and `version` (the first version marker) as leads. `kit lookup` checks npm deprecation, GitHub archived status and Node.js end of life, when `.audit/policy.yaml` allows. The council's decision became a per-engagement setting, not a design limit. A live run on a synthetic workspace reported `vladmandic/face-api` archived. |
| D7 Fail loudly | Done (0.11.0) | Cross-check stops the run; symlinks, submodules and data candidates are listed; a language over 5% of reviewed code lines that no profile covers goes under "Needs a person". |
| D8 ScanCode, Syft | Done, not verified against real tools (0.11.0) | Optional scans with an inventory cross-check, tested with recording fakes. Neither tool was installed, so the command lines follow the documentation and need one real run. |
| D9 Stamps | Partly | `detected.md` records the snapshot commit and inventory sha256; reinstall re-runs detection. Agent outputs don't record the stamp yet. |
| D10 Coverage | Not started | Waits for the findings store. |

On a copy of the pilot eval workspace, the inventory recorded 213 paths that match
snapshot `92a3e9d`, reported no AI instruction files (0.9.1 wrongly reported `.claude`),
and named `https://github.com/vladmandic/face-api` as face-api.js's upstream.

## Consequences

- Detection becomes a reader of `inventory.json`. It no longer walks the tree.
- `workspace.SKIP_DIRS` goes, along with `TEXT_EXT`, `GENERATED_DIRS` and `TEST_PATH`.
- `scans.py` takes its exclusions from inventory classes, not folder names.
- Non-git code drops can be audited. They have no history, so history-dependent
  checks (secrets in past commits, blame, churn) are recorded as limitations.
- The architecture record gains an `inventory` boundary owned by a new module, with
  `detection` depending on it.
- Constraints C2 (confinement), C3 (never execute the target), C4 (deterministic
  output) and C5 (no network) are unchanged.

## Rejected options

| Option | Reason |
|---|---|
| Adopt ripgrep's `ignore` crate or tokei for the walk | Built to skip files; adds a Rust toolchain for code the kit already has. |
| Use go-enry through its Python bindings | Native library for rules that are plain regex data; Linguist's data alone is enough. |
| Make ScanCode the inventory | Closest prior art, but a licence-compliance tool with its own large runtime; the kit would depend on its output format. Kept as a cross-check. |
| Syft with default settings | Records digests only for package-owned files, missing unmanifested vendored code. |
| Magika for file types | An ML model is more than the binary versus text decision needs; reconsider if `unknown` files are common. |
| Keep `git ls-tree` as the only source | Can't see files the ingest dropped, and needs git; used as the cross-check instead. |

## Risks and open items

- Linguist's rules target GitHub repositories. Council code may vendor libraries in
  folders the rules miss (for example `public/lib/`). Those files land in `own` and
  get reviewed, which is the safe failure, but they also miss the supply-chain stage.
  D6's banner detection runs on `own` JavaScript files too, to catch this.
- Very large repositories: hashing every file costs I/O. Not measured.
- The 5% uncovered-language threshold in D7 is a guess and needs tuning on a second
  target.
- Whether hash-only lookups count as "code stays local" is for the council to decide
  (D6).
- Zip extraction needs a path-safety check equivalent to the tar `data` filter; the
  standard library's `zipfile` has none built in. Not yet designed.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-06T13:31:37Z | Updated | D6, D7 and D8 implemented in 0.11.0; lookups gated by the engagement policy. |
| 2026-11-06T13:19:04Z | Updated | D1 to D5 implemented in 0.10.0; findings from the real Linguist data and the pilot app recorded under Implementation status. |
| 2026-11-06T12:47:48Z | Drafted | Initial version, from the pilot eval run and research into Linguist, go-enry, tokei, the `ignore` crate, ScanCode, Syft, Software Heritage and Magika. |
