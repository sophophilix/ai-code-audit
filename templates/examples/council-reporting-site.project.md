# Audit intake: council-reporting-site (example)

## Intake (required)
- Organisation and jurisdiction: NSW local council
- Repository and commit to audit: <repo> @ <commit>
- Tech lead (passes checkpoints): <name>
- Security owner (gets Critical findings the same day): CISO or equivalent
- AI use approved by (name, date, scope): <ICT manager, date, exception for named ICT staff>
- Where the AI provider processes data (region, confirmed by): <region, name>

## Evaluation (pre-flight checks this)
| Date | Kit version | Harness | Models | Recall (seeded) | Recall (known issues) | FP rate | Interruption | Cost | Result |
|---|---|---|---|---|---|---|---|---|---|
| – | 0.7.0 | – | – | – | – | – | – | – | not yet run |

## Optional

### Profile overrides (only to correct `kit detect`; then re-run `make detect`)
- add:
- remove:

### Constraints that should shape recommendations
- Small team new to PR-based work; prefer incremental change over rewrite.
