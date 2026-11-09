# NSW council digital services: obligations as checks

Load this when the system is a council's public website, forms, consultations,
meetings content, analytics or a staff-facing tool. It applies only because
`detected.md` lists this profile, which `kit detect` adds when the intake names
an NSW council. Use it with the `frontend-review` skill and the
`web-accessibility` profile. For an NSW council, the legal requirements here win
over their general rules; the council's own design system still wins on look.

> **Not legal advice.** These turn obligations into checks a code review can
> speak to. Interpretation belongs to the council's governance, right to
> information, privacy, records and legal officers. Every finding that rests on
> a legal reading says "not legal advice: confirm with the <role>".

## Where these claims come from, and what's checked
The obligations were researched for the tech lead's jsaudit rulebook
(`nsw-council-digital.md`, November 2026). For this kit (2026-11-08):
- The non-legislation sources below resolved: IPC, OLG, NSW State Archives and
  Records, the NSW Design System, Digital NSW, the Style Manual and Google's GA4
  documentation.
- **legislation.nsw.gov.au and humanrights.gov.au refuse automated reading**
  (HTTP 403), so no section number, fee, timeframe or date below has been checked
  against the current text by the kit. Before a finding cites one, open the
  current version and quote the section. Where you can't, write
  `Source: <act> (section not checked)` and lower the confidence.
- Several of the rulebook's references are law-firm, council or vendor pages.
  They're leads, not sources: cite the Act, the regulation or the regulator.

## The order of precedence
1. **Law and mandatory standards** come first: WCAG 2.2 AA, collection notices,
   statutory publishing and timeframes. They apply *to* the council's design
   system; they don't replace it.
2. **The council's design system, brand kit and content guide** for look,
   components, fonts, colours and voice.
3. **Gaps** (a multi-step form, an error summary, an exhibition page) borrow the
   *behaviour* from the NSW Design System, then GOV.UK, then the Agriculture
   Design System, rebuilt in the council's own tokens. Councils aren't NSW
   Government agencies: never recommend NSW Government branding or logos.
4. **Conflicts** between the brand and a standard get an accessible variant
   within the brand, with measured ratios, for the brand owner to sign off
   (`frontend-review` FE-BRAND-CONFLICT).

## Check catalogue
<!-- brief: markup, component, inline script -->
Kinds as in `frontend-review`: `static` (source), `runtime` (a rendered page),
`agent` (judgement on the source), `manual` (a person decides). Presence checks
can show a page or field exists; they can't show its content is complete, so they
say "present; content not verified".

| CHECK-ID | Obligation | What to look for | Kind | Severity guide | Owner for questions |
|---|---|---|---|---|---|
| NSW-A11Y-STANDARD | WCAG 2.2 AA as the minimum for public and staff services. For a council the obligation comes from the Disability Discrimination Act 1992 (Cth) and the Australian Human Rights Commission's 2025 guidelines (not checked by the kit); Digital NSW *recommends* the same minimum for NSW Government. Outsourcing doesn't transfer responsibility | The standard the code, tests and contracts aim at: WCAG 2.0 or 2.1 targets, or none | static, manual | Medium if the target is below 2.2 AA; findings themselves use `WCAG-*` IDs | Accessibility or digital lead |
| NSW-DESIGN-SYSTEM-BRAND | A council using NSW Design System code re-themes it with the council's own brand through the design system's CSS variables (colours, typography, radius, shadows, container width), and doesn't ship the NSW Government masthead ("A NSW Government website"), masterbrand or logos. Councils aren't NSW Government agencies | `@nswdigital` or NSW Design System packages; the masthead markup; whether the theme variables are overridden | static | Medium if council pages present as NSW Government | Communications lead |
| NSW-EASY-READ | Where the council publishes Easy Read content, it follows the NSW Design System Easy Read method: one idea per block, meaningful images with a single focal point and plain background, illustrations without border, shadow or scenery, text in images only where needed with the same text in HTML, and testing with the intended audience. Readability scores are a diagnostic only | Easy Read pages or templates | agent, manual | Low; Medium if Easy Read content is the only accessible version of a service | Communications lead |
| NSW-DOCS-ACCESSIBLE | Plans, papers and reports published as accessible HTML first; PDFs tagged or with an alternative | PDF-only publishing in templates or the CMS; generated PDFs without tags | static, manual | Medium | Digital lead |
| NSW-GIPA-OPEN-ACCESS | GIPA Act 2009 open access information free on the website: Agency Information Guide, policy documents, disclosure log, contracts register, and the council categories in Schedule 1 of the GIPA Regulation (business papers and minutes, returns of interests, registers, plans, development applications) | Routes, navigation or CMS content types for each category; stable URLs | static (presence), manual (complete) | High if a category has no page at all; otherwise `info` "present; content not verified" | Right to information officer |
| NSW-GIPA-APPLICATION | An online formal access application captures what makes it valid (made under the Act, the fee, enough detail, an Australian postal or email address) and the workflow supports the statutory acknowledgement and decision timeframes | The form's fields and the case workflow | static | Medium | Right to information officer |
| NSW-GIPA-REDACTION | Personal information in development application documents and submissions is redacted before publishing | A publish path from upload to public page with no redaction or review step | static, manual | High if personal information can be published unreviewed | Right to information officer, privacy officer |
| NSW-IPR-EXHIBITION | Draft IP&R plans on public exhibition for at least 28 days (Local Government Act 1993, ss 402 to 405) | An exhibition component that can be configured, or shown, with a period under 28 days; open and close times not handled in `Australia/Sydney` | static, runtime | High if a period under the minimum can be published | Governance officer |
| NSW-IPR-PUBLISH | Adopted plans and the annual report posted on the website within the statutory periods | A publishing workflow with no deadline or reminder (process evidence only) | manual | `info`, with a question | Governance officer |
| NSW-MEETING-RECORDINGS | Meetings livestreamed and recordings kept on, or linked from, the council website for the required period, with captions; a notice that meetings are recorded; written consent from public forum speakers | The recordings page; the request-to-speak form's consent field and disclaimer | static (presence), manual | Medium for a missing consent field or notice | Governance officer |
| NSW-RECORDS-CAPTURE | Web content, online form submissions, survey responses and exhibition comments are State records (State Records Act 1998; GA39) and must reach the corporate records system | A SaaS form or engagement platform as the only store of submissions; no export or integration; no version history of pages | static, manual | High if submissions exist only in a third-party platform | Records manager |
| NSW-PRIVACY-NOTICE | A collection notice at the point of collection on every form (PPIP Act 1998), stating purpose, recipients, whether supplying it is required, the consequences, access and correction, and the council as collector. A link to the privacy policy alone isn't enough | Each form's markup: a notice near the fields, not only a footer link | static, runtime | High on a form collecting personal information with no notice | Privacy officer |
| NSW-PRIVACY-MINIMISE | Collect only what's needed; no optional fields defaulted to share; no bundled consent | Optional personal fields, pre-ticked consent boxes, one checkbox for several purposes | static | Medium | Privacy officer |
| NSW-HEALTH-INFO | Health information (childcare, aged and community services, immunisation) falls under the HRIP Act 2002 | Forms or data stores that collect health information | static, manual | Medium; routes the privacy questions | Privacy officer |
| NSW-OFFSHORE-DATA | Personal information stored outside NSW or Australia (SaaS forms, analytics, session replay) needs the privacy officer's check of the transborder rules before use | Third-party hosts in `scans/sweep.json` and the integrations list | static, manual | Medium, with a question | Privacy officer |
| NSW-BREACH-READY | The Mandatory Notification of Data Breach scheme (PPIP Act Part 6A, since 28 November 2023): the system can answer who accessed what and when, and personal information isn't in analytics, logs or error reports | Audit logs of access to personal data; personal data in logs or client error reports | static | Medium to High. Related: NODE-LOGGING, FE-CLIENT-ERRORS | Privacy officer |
| NSW-ANALYTICS-PII | No personal information (emails, names, phone numbers, reference numbers, free-text search) in analytics events or beacon URLs | `dataLayer.push`, `gtag(` and tracking calls with form values; search terms sent unbucketed | static, runtime | High if personal information reaches a third party | Privacy officer |
| NSW-SESSION-REPLAY | No session recording or heatmaps (Hotjar, Microsoft Clarity and similar) on pages with forms, accounts, payments or health information | Recording scripts in `scans/sweep.json` or templates, and which pages load them | static, runtime | High on any form page | Privacy officer |
| NSW-ANALYTICS-EVENTS | Measurement designed with a tracking plan: step views, validation errors (never values), success only after the server confirms, and single-page apps not counting page views twice | A success event on button click before the response; both history-change and manual page views enabled | static, runtime | Medium for success fired before confirmation or double counting; Low otherwise | Digital lead |
| NSW-STAFF-SURVEILLANCE | Telemetry, activity logging or session replay that identifies staff is computer surveillance under the Workplace Surveillance Act 2005, lawful only under a notified policy | Staff-facing tools with identifying analytics or monitoring | static, manual | High until HR confirms a notified policy covers it | HR, privacy officer |
| NSW-PID-CONFIDENTIAL | A public interest disclosure reporting form or case system (Public Interest Disclosures Act 2022) has strict access control, no analytics or third-party scripts, minimal identifying logs and an access audit trail | The reporting form and its storage | static | High if a reporter's identity could leak | Governance officer |
| NSW-SYDNEY-TIME | Deadlines and meeting times stored in UTC and shown in `Australia/Sydney`, daylight saving aware | Date handling for exhibitions, applications and meetings. Related: JS-DATE-MATH | static | Medium; High where a statutory deadline is shown wrong | Digital lead |
| NSW-PLAIN-LANGUAGE | Content in the council's voice, checked against a Year 7 reading level in Australian English (Australian Government Style Manual), with interpreter details on contact pages | Reading level of key pages and error messages | agent, manual | Low | Communications lead |
| NSW-ACKNOWLEDGEMENT | Acknowledgement of Country in the footer and on key pages, following the council's protocol (practice, not statute) | Footer template | static | `info` | Communications lead |

## Vendors (SaaS, CMS, forms, engagement platforms)
When the code integrates a vendor platform, record what the contract should hold
as open questions for the procurement owner: WCAG 2.2 AA with AS EN 301 549
evidence and a remediation roadmap; stated data location and breach
notification fast enough for the 30-day assessment; full export into the records
system; Essential Eight-aligned controls with MFA and SSO; theming with council
tokens; and data portability with stable URLs on exit.

## Sources
Resolved on 2026-11-08 (the Digital NSW and NSW Design System pages were also
read for the points above):
- Digital NSW, accessibility basics (WCAG 2.2 AA recommended for NSW Government): https://digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/basics
- Digital NSW, colour contrast (and the NSW Colour Contrast Checker): https://digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/design/colour-contrast
- Digital NSW, graphics and images: https://digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/design/graphics-and-images
- NSW Design System, theming for developers: https://designsystem.nsw.gov.au/get-started/theming-for-developers.html
- NSW Design System, Easy Read: https://designsystem.nsw.gov.au/methods/easy-read.html
- IPC, Mandatory Notification of Data Breach scheme: https://www.ipc.nsw.gov.au/privacy/MNDB-scheme
- Office of Local Government: https://www.olg.nsw.gov.au/ (IP&R guidelines, meeting circulars, livestreaming guide)
- NSW State Archives and Records, "Managing council websites and web content": https://www.records.nsw.gov.au/recordkeeping/advice/managing-council-websites-and-web-content
- GA39, local government records: https://www.records.nsw.gov.au/recordkeeping/rules/authorities/ga39
- NSW Design System: https://designsystem.nsw.gov.au/
- Digital NSW, online forms: https://www.digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/design/online-forms
- Australian Government Style Manual: https://www.stylemanual.gov.au/
- Google, GA4 single-page applications: https://developers.google.com/analytics/devguides/collection/ga4/single-page-applications

Not readable by the kit (HTTP 403); open them yourself before citing a section:
- NSW legislation: https://legislation.nsw.gov.au/ (GIPA Act 2009 and GIPA Regulation 2018; Local Government Act 1993; PPIP Act 1998; HRIP Act 2002; State Records Act 1998; Workplace Surveillance Act 2005; Public Interest Disclosures Act 2022; Disability Inclusion Act 2014)
- Australian Human Rights Commission, digital access guidelines: https://humanrights.gov.au/
