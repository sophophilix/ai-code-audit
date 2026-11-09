# Audit intake: <system name>

<!-- Only what the code can't tell us. Everything else (what the system does,
     its stack, profiles, exclusions, data handled) is detected by `kit detect`
     and discovered by the discovery agent, then confirmed by you at Checkpoint 1.
     You don't need to know the system to fill this in.
     Keep secrets, personal data and known-vulnerability details out. -->

## Intake (required)
- Organisation and jurisdiction: <e.g. NSW local council>
- Repository and commit to audit: <url or name @ commit>
- Tech lead (passes checkpoints): <name>
- Security owner (gets Critical findings the same day): <name or role>
- AI use approved by (name, date, scope): <name, date, scope>
- Where the AI provider processes data (region, confirmed by): <region, name>

## Evaluation (pre-flight checks this)
| Date | Kit version | Harness | Models | Recall (seeded) | Recall (known issues) | FP rate | Interruption | Cost | Result |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

## Optional

### Profile overrides (only to correct `kit detect`; then re-run `make detect`)
- add:
- remove:

### Design system and brand (for a website or app with a user interface)
<!-- The code and the live site show what was built, not what the brand owner
     approved. Say where the approved design is, or write none or unknown. -->
- Approved design system or brand kit (location, version): <link or path, version; or none / unknown>
- Brand owner (approves brand and design changes): <name or role>
- Approved fonts and licences: <families and licence; or unknown>

### Other owners (for open questions; default: the tech lead)
- privacy-owner:
- platform/cloud admin:
- application owner:

### Constraints that should shape recommendations
-

### Sources allowed (documentation domains agents may read)
- learn.microsoft.com, azure.github.io, expressjs.com, nodejs.org,
  cheatsheetseries.owasp.org, owasp.org, www.w3.org, playwright.dev,
  cyber.gov.au, olg.nsw.gov.au, digital.gov.au, eslint.org,
  best.openssf.org, ota-meshi.github.io

## Checkpoint 1 corrections
Filled in by the tech lead at Checkpoint 1. Every agent after discovery reads
this section. Correct discovery's project description here (especially lines
marked `(comment only)` or `(doc only)`), and answer its open questions by ID.
- (none yet)
