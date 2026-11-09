---
name: web-accessibility
description: Use when reviewing user-facing web pages and forms for accessibility against WCAG 2.2 Level AA. Gives the success-criterion check catalogue, what static review can and can't establish, and how to use axe results.
---

# Web accessibility profile (WCAG 2.2 AA)

## Sources
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Understanding WCAG 2.2: https://www.w3.org/WAI/WCAG22/Understanding/
- What's new in WCAG 2.2: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- axe-core with Playwright (free, open source): https://playwright.dev/docs/accessibility-testing

Deque's official axe MCP server and Claude plugin need a paid licence (checked
November 2026). The free route is `@axe-core/playwright` with the tags
`wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` in end-to-end tests. Its JSON
output goes in `.audit/scans/axe/`.

## Static review: what it can and can't show
<!-- brief: markup, component -->
| Can establish from source | Needs a rendered page or a person |
|---|---|
| Labels are associated, names exist, `lang` is set, live regions are coded, focus is managed in script, error text exists | Actual contrast, real focus order, reflow at 320 px, screen reader announcements, whether a custom widget really works |

## Check catalogue
<!-- brief: markup, component, inline script -->
Key format: `WCAG-<sc>:<file>`, for example `WCAG-3.3.1:public/index.html`.

| CHECK-ID | SC (level) | What to check |
|---|---|---|
| WCAG-1.1.1 | Non-text content (A) | Images, icons and icon buttons have text alternatives; decorative ones are hidden |
| WCAG-1.3.1 | Info and relationships (A) | Labels tied to inputs; fieldset/legend for groups; headings and lists marked up |
| WCAG-1.3.5 | Identify input purpose (AA) | `autocomplete` on personal-data fields (name, email, tel, address) |
| WCAG-1.4.3 | Contrast, minimum (AA) | Text colours from the stylesheet/tokens, checked against backgrounds |
| WCAG-1.4.10 | Reflow (AA) | No fixed widths forcing horizontal scroll at 320 px |
| WCAG-1.4.11 | Non-text contrast (AA) | Input borders, focus indicators, map pins, icons |
| WCAG-1.4.13 | Content on hover or focus (AA) | Tooltips and pop-ups can be dismissed and hovered |
| WCAG-2.1.1 | Keyboard (A) | Every control reachable and operable by keyboard, including the map and custom widgets |
| WCAG-2.1.2 | No keyboard trap (A) | Modals and maps release focus |
| WCAG-2.2.1 | Timing adjustable (A) | Session or draft timeouts, minimum-time checks: warning and extension |
| WCAG-2.4.3 | Focus order (A) | Focus moves logically between steps, into errors and dialogs |
| WCAG-2.4.6 | Headings and labels (AA) | Descriptive headings and labels |
| WCAG-2.4.7 | Focus visible (AA) | No `outline: none` without a replacement |
| WCAG-2.4.11 | Focus not obscured, minimum (AA) *new in 2.2* | Pinned bars or footers don't hide the focused element |
| WCAG-2.5.7 | Dragging movements (AA) *new in 2.2* | Dragging a map pin or slider has a single-pointer alternative (tap to place, address search) |
| WCAG-2.5.8 | Target size, minimum (AA) *new in 2.2* | Targets at least 24×24 CSS px or properly spaced |
| WCAG-3.1.1 / 3.1.2 | Language of page / parts (A / AA) | `lang` on `<html>`; `lang` on translated passages |
| WCAG-3.2.2 | On input (A) | Changing a field doesn't unexpectedly submit or navigate |
| WCAG-3.2.6 | Consistent help (A) *new in 2.2* | Help or contact appears in the same place across steps |
| WCAG-3.3.1 | Error identification (A) | Errors described in text and tied to the field (`aria-describedby`, `aria-invalid`) |
| WCAG-3.3.2 | Labels or instructions (A) | Required fields and formats explained before input |
| WCAG-3.3.3 | Error suggestion (AA) | Errors say how to fix them |
| WCAG-3.3.4 | Error prevention, legal/financial/data (AA) | Review step before submitting, or the ability to correct |
| WCAG-3.3.7 | Redundant entry (A) *new in 2.2* | Information already given isn't asked for again in the same process |
| WCAG-3.3.8 | Accessible authentication, minimum (AA) *new in 2.2* | Sign-in doesn't rely on a cognitive test; paste allowed; passkeys or email links OK; CAPTCHA alternatives |
| WCAG-4.1.2 | Name, role, value (A) | Custom controls expose role and state |
| WCAG-4.1.3 | Status messages (AA) | Progress, "saved", "sent" and error summaries announced through live regions |

## Process
<!-- brief: markup, component, inline script -->
1. Use discovery's routes and data flows to find every page and step.
2. Walk each journey in code order. Check each relevant SC.
3. For maps and other visual-only features, make sure an equivalent non-visual
   path exists (search by address, a text list of nearby items).
4. Merge in the axe results, if provided, by rule and page.

## Red flags
<!-- brief: markup, component, inline script -->
- "Passes axe" presented as "accessible"
- Visual-only confirmation of location (map) with no text equivalent
- Errors shown only by colour or only at the top of a long form
