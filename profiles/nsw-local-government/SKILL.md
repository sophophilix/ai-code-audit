---
name: nsw-local-government
description: Use only when detected.md lists this profile (kit detect adds it when the intake names an NSW local council). Maps findings to the NSW Cyber Security Guidelines – Local Government, the ACSC Essential Eight and NSW privacy and records law, and gives council digital-service checks (GIPA, IP&R, meetings, records, collection notices, analytics, staff surveillance).
---

# NSW local government compliance profile

## Overview
The NSW Office of Local Government *Cyber Security Guidelines – Local Government*
(issued January 2025, based on the NSW Cyber Security Policy) set Foundational
Requirements in three groups: Govern and identify (1.x), Detect, respond and
recover (2.x), Protect (3.x). Essential Eight Maturity Level 1 is the minimum
baseline (requirements 3.3–3.10). Compliance is voluntary but strongly
encouraged, and cyber risk is reported to the council's Audit, Risk and
Improvement Committee (ARIC).
Source: https://www.olg.nsw.gov.au/sites/default/files/2026-02/cyber-security-guidelines-local-government.pdf

The full requirement list is in `references/foundational-requirements.md`.
Load it only when filling the compliance table.

## When this profile applies
Only when `.audit/detected.md` lists it. `kit detect` adds it when the intake's
jurisdiction names NSW and a council or local government; the tech lead can add
or remove it in the intake. A non-council NSW system, or any other jurisdiction,
doesn't get these checks.

## Council digital services
`references/council-digital.md` turns council obligations into `NSW-*` checks
for websites, forms, consultations, meeting content, analytics and staff tools:
GIPA open access pages and applications, IP&R exhibition periods, meeting
recordings and speaker consent, records capture of submissions, PPIP collection
notices and minimisation, health information, offshore data, breach readiness,
personal information in analytics, session replay on form pages, staff
surveillance, PID confidentiality and Sydney time. Load it when the system has a
public or staff user interface (`detected.md` also lists `web-accessibility`).
The kit hasn't checked the legislation's current text (the site refuses
automated reading): open the section before citing it.

## Requirements that code and deployment evidence can speak to
<!-- brief: script, component, inline script, markup -->
| Ref | Requirement | What to check |
|---|---|---|
| 1.6 | Asset inventory and dependencies | Dependency list / SBOM; every external service |
| 1.7 | Crown Jewels and classification | Is the data classified? Is the system rated? (question for owner) |
| 1.8 | Data retention and secure disposal | Temp files, logs, local copies of uploads, retention rules |
| 1.10 | Third-party provider risk | Each integration's vendor; hosting location; contract clauses (question) |
| 1.11 | Vulnerability management | Audit tools in CI; outdated runtime/framework; Cyber Security NSW alerts process |
| 1.12 | Security in change management | Branch policies, PR review, pipeline gates, post-change testing |
| 2.1 | Logging and monitoring | Security events logged; no personal data in logs; alerting |
| 2.2 | Incident response | Can a submission be traced? Correlation IDs; incident register (question) |
| 2.3 | Report incidents to Cyber Security NSW | Process exists (question) |
| 3.2 | Access control | Who can deploy / access cloud and repo; access reviews |
| 3.3 | Patch applications (E8 ML1) | Online services: daily vulnerability scan; critical patches within 48 hours, others within two weeks; unsupported services removed |
| 3.4 | Patch operating systems (E8 ML1) | Internet-facing OS: critical within 48 hours; unsupported OS replaced (PaaS reduces this) |
| 3.5 | MFA (E8 ML1) | MFA on cloud portal, DevOps, CRM/SharePoint admin; on customer services holding sensitive data (3.5.6) |
| 3.6 | Restrict admin privileges (E8 ML1) | Least privilege for app identities and API scopes; separate privileged accounts |
| 3.10 | Backups (E8 ML1) | Any local state, config and IaC backed up and restore-tested |
| 3.11 | Secure configuration | Defaults removed; hardening; no default credentials |
| 3.12 | Data security | 3.12.1 scan imported data (uploads) for malicious content; 3.12.2 encryption |
| 3.15 | Network security | Segmentation, private endpoints, WAF |

## Legislation for personal information
<!-- brief: script, component, inline script, markup -->
- Privacy and Personal Information Protection Act 1998 (NSW) – collection, use, disclosure, security, retention
- Health Records and Information Privacy Act 2002 (NSW) – if any health information can be submitted
- State Records Act 1998 (NSW) – records created by the system (including audit outputs)
- IPC NSW data breach guidance; Mandatory Notification of Data Breach scheme applies to councils

## Roles to route questions to
General Manager, CIO/COO, CISO (or equivalent), Privacy Officer, Information
Management Officer, Internal Audit, ARIC. Use these as owners for open questions.

## Process
1. Add the NSW ref to `frameworks` on every security/privacy finding (e.g. "NSW 3.12.1").
2. In the compliance table (security agent, section 11), one row per requirement above:
   `NSW 3.12.1 | Not met | SEC-004`.
3. Anything the code can't show → `not determinable`, plus a question for the right owner.

## Red flags
- Treating "voluntary" as "optional": ARIC will still ask.
- Marking a requirement met on assumptions about cloud config that isn't in the repo.
