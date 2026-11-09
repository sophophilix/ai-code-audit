---
name: audit-publishing
description: Use when writing an audit report, briefing deck or other document people will edit and share. Markdown is the single source; Marp turns it into slides and PDF, Pandoc turns it into editable Word and PowerPoint using the organisation's templates.
---

# Publishing audit outputs (Markdown first)

## Overview
Everything is written in **Markdown**: readable in the repo and the Azure
DevOps wiki, reviewable in a pull request, and easy for an agent to write.
People who need Office files get them **generated** from that source, so
there's never a second copy to keep in sync.

| Output | Source | Tool (run by a person, not an agent) | Result |
|---|---|---|---|
| Report | `07-final-report.md` | Pandoc + the organisation's Word template | editable `.docx` |
| Briefing deck | `09-briefing.slides.md` | Marp | PDF for sending; preview in VS Code |
| Editable deck | the same `09-briefing.slides.md` | Pandoc + the organisation's PowerPoint template | editable `.pptx` (real text boxes) |
| Diagrams | drawio-skill (`architecture-diagrams`) | draw.io export | SVG for Markdown and Marp; PNG at 2× for Word and PowerPoint |

Marp's own PowerPoint export renders slides as images. Use Pandoc when
someone needs to edit the deck in PowerPoint.

## One slide source for Marp and Pandoc
Write the deck so both tools read it the same way:
```markdown
---
marp: true
paginate: true
title: <Audit name> – briefing
---

# <Audit name>
Independent code audit · <date>

---

## Overall risk: <rating>
- Top issue 1 (SEC-001)
- Top issue 2 (ARC-003)

---

## Target architecture
![Target architecture: residents reach the site through Front Door with WAF; the app runs in App Service with private access to its data](diagrams/target.png)
```
- `---` separates slides in both Marp and Pandoc.
- One `##` heading per slide, with no more than about six bullets.
- Marp-only directives go in HTML comments (`<!-- _class: lead -->`). Pandoc ignores them.
- Every image has **alt text that states what the picture shows**, not "diagram".
- Every claim on a slide carries its finding ID, so it can be traced.

## Briefing deck contents (about 8–12 slides)
1. Title, date, scope, kit version
2. Overall risk and the headline recommendation
3. What the system actually is (one diagram)
4. Top five issues, with IDs and plain-English impact
5. What must happen before go-live
6. Hosting and technology direction (ADR links, all *Proposed*)
7. What the platform team must build
8. Roadmap phases 0–3
9. Decisions needed and open questions, by owner
10. Method: AI agents, models, what humans checked

## Writing rules
- Plain English for non-technical readers. Explain terms the first time they appear.
- Numbers come from the findings files. Never round "7 High" into "several".
- No secrets, no personal data, no exploit detail. Describe impact, not technique.
- Headings in sentence case; one idea per paragraph.

## Conversion commands (for the person publishing)
```zsh
brew install pandoc marp-cli            # once; needs ICT approval on council machines
pandoc .audit/07-final-report.md -o .audit/07-final-report.docx --reference-doc=<org-template.docx>
pandoc .audit/09-briefing.slides.md -o .audit/09-briefing.pptx --reference-doc=<org-template.pptx>
marp .audit/09-briefing.slides.md --pdf -o .audit/09-briefing.pdf
```
Then check the output-eval items in `evals/output-checks.md`.

## Red flags
- Editing the Word or PowerPoint copy instead of the Markdown source
- Slides with claims and no finding IDs
- Images without meaningful alt text
- Counts in the summary that don't match the findings files
