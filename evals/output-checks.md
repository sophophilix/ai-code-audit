# Output checks (every audit output gets evaluated)

The findings evaluation (`README.md`) shows the agents can *find* issues.
These checks show that what they *produced* is consistent, traceable and
safe to share. Order of trust: **automated checks first, a person second, an
AI judge last** (from a different model family, with a person reviewing a sample).

`Auto` = a script can decide it. These are listed here as requirements;
the scripts are deferred (see CHANGELOG). Until then a person ticks them at Checkpoint 2.

## Findings files (`01`–`05`)
| ID | Check | Auto |
|---|---|---|
| OUT-F1 | Every finding has Key, Severity, Confidence, Location and Evidence | yes |
| OUT-F2 | Keys use a CHECK-ID from a profile catalogue, or `X-` | yes |
| OUT-F3 | No duplicate Keys within a file | yes |
| OUT-F4 | Every cited `file:line` exists at the audited commit | yes |
| OUT-F5 | Provenance header complete and matches `run-log.md` (commit, model, pass) | yes |
| OUT-F6 | Every Critical/High has an Impact scenario and a Recommendation with a source | yes (presence) / person (quality) |
| OUT-F7 | Every finding with a line has an Excerpt that appears, ignoring whitespace, in the cited lines | yes |
| OUT-F8 | Every `- Searched:` line, re-run over the target, matches nothing | yes |
| OUT-F9 | Every Critical/High has a Trigger | yes (presence) / person (quality) |
| OUT-F10 | Every Excerpt cell in `01-discovery.md`'s tables appears in the row's `file:line` | yes |

## File records (`files/`, ADR 0002 and 0007)
`kit review` runs OUT-F1 to F4, F7 to F9, U2 and U4 on a pass's JSON before it
writes the record, and sends a failure back once. `kit verify` runs them again on
every record, so a record reused from an earlier audit is checked against this one.

| ID | Check | Auto |
|---|---|---|
| OUT-U1 | Every record has its sections: Summary, Facts, Comments versus code, Sources and sinks, Functions, Gates, Findings, Open edges, Checks, Limitations | yes |
| OUT-U2 | Every location in a record is in its unit's file and lines | yes |
| OUT-U3 | Every unit (or every pilot unit) has a record | yes |
| OUT-U4 | No Critical or High finding depends on an open edge or is `unverified`, and no finding with an open edge is `verified` | yes |
| OUT-U5 | The brief shows every scan row its table counts, and the record's counts match the brief's | yes |
| OUT-U6 | Every check ID in the brief is answered once (`found`, `not found` or `not applicable`), and a check is `found` exactly when a finding's Key uses it. Run by `kit review` | yes |

## Verification (`06`)
| ID | Check | Auto |
|---|---|---|
| OUT-V1 | Every Critical/High has exactly one verdict | yes |
| OUT-V2 | The Medium sample matches the offset recorded in `run-log.md` | yes |
| OUT-V3 | Each verdict came from a different model family than the finding's author, when `models.yaml` requires it | yes |

## Report and briefing (`07`, `09`, and the generated `.docx` / `.pptx`)
| ID | Check | Auto |
|---|---|---|
| OUT-R1 | Every finding ID mentioned exists, with the same severity as after verification | yes |
| OUT-R2 | Every confirmed Critical/High appears in the report | yes |
| OUT-R3 | Counts in the executive summary equal the counts in the findings files | yes |
| OUT-R4 | Rejected findings appear only in the appendix | yes |
| OUT-R5 | Links resolve; Markdown passes `markdownlint` | yes |
| OUT-R6 | Every image has meaningful alt text (not empty, not "diagram") | yes (presence) / person (meaning) |
| OUT-R7 | Secret scan of all outputs is clean (gitleaks on `.audit/`, excluding `scans/`) | yes |
| OUT-R8 | No exploit detail beyond a scenario in words | person |
| OUT-R9 | A non-technical reader can follow the executive summary | person |
| OUT-R14 | Part A (executive summary, decisions needed, top five issues, roadmap) stands on its own: a manager who reads only Part A knows the risk, the decisions and the next step | person |
| OUT-R15 | `ste-lint.py` from the pinned `technical-writing` skill was run on the report and its warnings were read (advisory; doesn't block release) | person |
| OUT-R10 | The method section states which findings a person checked | yes (presence) |
| OUT-R13 | When the target has a user interface, the report has a "Still to check by hand" section listing the manual checks | yes (presence) / person (complete) |
| OUT-R12 | Every package named in a finding's `Packages` field was looked up, and none is missing from npm or deprecated (skipped, with a note, when lookups are denied) | yes |
| OUT-R11 | The report has a "Not examined" section built from `scans/coverage.json` and `blindspots.json` | yes (presence) / person (complete) |

## Backlog (`08-backlog.csv`)
| ID | Check | Auto |
|---|---|---|
| OUT-B1 | Parses as CSV with the required columns, in order | yes |
| OUT-B2 | One row per confirmed or unverified finding above info; none for rejected | yes |
| OUT-B3 | Every row has testable acceptance criteria | yes (presence) / person (testable) |
| OUT-B4 | Imports into a test Azure Boards project without errors | person |

## Diagrams (`diagrams/`)
| ID | Check | Auto |
|---|---|---|
| OUT-D1 | `validate.py --score`: 0 errors; overlaps and crossings reported | yes |
| OUT-D2 | Architecture contracts (`policy.yml`) pass for the target design | yes |
| OUT-D3 | Every node and edge has provenance | yes |
| OUT-D4 | Every Azure icon style is `img/lib/azure2/…` from the shape index; no `mxgraph.azure.` | yes |
| OUT-D5 | The as-is diagram agrees with discovery's facts (components, integrations) | person |

## The run (`run-log.md`)
| ID | Check | Auto |
|---|---|---|
| OUT-P1 | Every stage and pass has started and finished rows | yes |
| OUT-P2 | Both checkpoints signed by the tech lead, with names and times | yes |
| OUT-P3 | `git status` shows no changes outside `.audit/` | yes |
| OUT-P4 | Pre-flight data check passed, or exceptions were recorded and approved | yes |
| OUT-P5 | Every output is `status: complete`, and no `LOCK` is left `state: active` | yes |
| OUT-P6 | Usage recorded for every pass (tokens, or `not reported`), with sessions and resumes | yes |
| OUT-P7 | Resumed passes: no duplicate Keys and no renumbered IDs (compare with checkpoint commits) | yes |

## Recording results
Add a line to `run-log.md`:
`OUTPUT CHECKS: <n> passed, <n> failed (<IDs>), checked by <name>, <UTC time>`.
Any failure in R1–R3, R7, B1 or P2 blocks release of the report.
