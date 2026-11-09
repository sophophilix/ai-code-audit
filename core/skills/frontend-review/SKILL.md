---
name: frontend-review
description: Use when reviewing HTML, templates, CSS, design tokens, forms, page skeletons, browser security headers, caching or front-end performance. Gives the FE-* check catalogue, each marked static, runtime, agent or manual, with its evidence, severity guide and official source.
---

# Frontend review

## Overview
This skill is the rulebook for the parts of a web front end that aren't
JavaScript logic: markup, templates, stylesheets, design tokens, forms, the page
skeleton, what the server sends to the browser, and how the page loads. The
`file-reviewer` applies it to markup, stylesheet, JSX and inline-script units;
the accessibility, engineer and security agents use the sections in their lane.

The rules come from the bodies that define or measure the web platform: W3C WAI
(WCAG 2.2, ARIA), Chrome's web.dev, MDN, OWASP, WebAIM, the GOV.UK Design System,
and the React and Tailwind teams. They were collected in the tech lead's jsaudit
rulebook (`frontend-craft.md`, November 2026) and are restated here as checks.

Use it with:
- `javascript-review` for script behaviour (async, errors, DOM sinks);
- the `web-accessibility` profile, which owns WCAG success criteria. Where a
  check below maps to one, the Key uses the `WCAG-*` ID and this skill only adds
  how to find it;
- a jurisdiction profile when `detected.md` lists one (for an NSW council, the
  `nsw-local-government` profile's council digital checks). Its legal
  requirements win over the general rules here.

## Whose design is this?
<!-- brief: markup, component, stylesheet, inline style -->
Most councils and companies have their own design system: tokens, components,
fonts, brand colours, imagery and voice. **It takes precedence on look**, and the
audit evaluates it against these rules rather than replacing it. Where the brand
fails a standard (a brand colour below 4.5:1), the finding proposes an accessible
variant within the brand and the brand owner decides. Never recommend replacing
the brand or importing another design system's look.

**But the code isn't the approved design.** Tokens, fonts and components in the
repository or on the live site show what was *built*. They may have drifted from
the brand kit, used a stand-in font, hard-coded a near-miss colour, or predate a
rebrand. Only the brand owner can say what's approved. So:

1. Read `project.md` → "Design system and brand". It names the approved design
   system or brand kit, the brand owner and the approved fonts, or says `none`
   or `unknown`.
2. **Recorded:** treat that as the reference. Compare what's built with it
   (FE-DS-DRIFT) as well as with the rules. If you can't read the reference
   (a private Figma file, a PDF brand book), say so and ask for the token
   values.
3. **`unknown` or empty:** treat every token, font and component as **as-built,
   approval not confirmed**. Still rate them against the rules; that's most of
   the value. But don't call anything "off-brand", and write recommendations as
   "if this is the approved brand, …". Raise an open question for the brand
   owner (or the tech lead if no owner is named): "Is `<token file>` the
   approved brand, at which version? Are `<fonts>` the licensed brand fonts?"
4. **`none`:** the system has no design system. Rate what's built, and recommend
   setting one up from the tokens that exist (section 2) before any redesign.

## Rating against the rules
Alongside findings, give one rating per area, so the reader can see at a glance
how the site does. These are judgements with evidence, not scores; nothing is
added up.

| Rating | Meaning |
|---|---|
| Meets | Every applicable check passes, with evidence |
| Partly meets | Some checks fail, or they pass on some pages and not others |
| Doesn't meet | The checks that matter most in the area fail on main journeys |
| Not determinable | The evidence isn't available: a `runtime` check with no rendered page, or a `manual` one nobody has done |

The areas are this skill's sections: stack, design tokens and brand, page
skeleton, layout and CSS, accessibility patterns, forms, performance, browser
security, feedback and states, reuse and consistency. Each row gives the
rating, the two or three findings that decide it, and the one recommendation
that would move it up a level. The design system row says whether it was rated
as **approved** or **as built**.

Recommendations are written for the people who act on them: the designer
(tokens, components, patterns), the developer (code and headers), the content
designer (wording, reading level) and the service owner (journeys, policy). Say
which one each is for.

## What each kind means
<!-- brief: markup, component, stylesheet, inline style, inline script -->
Every check has a kind, which says what evidence can settle it.

| Kind | Evidence that settles it | If you can't get that evidence |
|---|---|---|
| `static` | The source: markup, CSS, tokens, server config in the repo | Not applicable |
| `runtime` | A rendered page: `scans/axe/`, or a browser run in the sandbox | Record what the source suggests at Medium confidence at most, and list the check under Limitations as "needs a rendered page" |
| `agent` | Your judgement on the source, with the excerpt | Not applicable |
| `manual` | A person: a screen reader, a brand owner, a content designer | Add it to the "still to check by hand" list in your output, with the page and what to do |

## Before you start
<!-- brief: markup, component, stylesheet, inline style, inline script -->
1. Read the unit in full. For an HTML file, script blocks are separate units:
   skip their lines, but note what they do to the markup (they may inject it).
2. Read this file's rows in `scans/lint.json`, `scans/sweep.json` (third-party
   tags, storage reads) and, if present, `scans/axe/`.
3. Read `scans/design-inventory.json` (or the `.md` beside it): every colour,
   token, font stack, `@font-face` rule and web-font link the stylesheets and
   markup declare, with contrast for each rule that sets both text and
   background colours. Start the tokens, contrast and font checks from it, and
   cite the file and line it gives. It doesn't see colours set by scripts,
   images or a CMS.
4. Find the design tokens, if any: CSS custom properties (`:root { --… }`), a
   Tailwind `@theme` or config, or a token JSON (W3C DTCG format). Note where
   they are; a raw value elsewhere is measured against them. Check
   `project.md` → "Design system and brand" for whether they're the approved
   design or only what was built ("Whose design is this?").
5. Note the stack: static HTML, server templates (EJS, Handlebars, Razor), or a
   framework (React, Vue). Section 1's checks depend on it.

## How to write a finding
<!-- brief: markup, component, stylesheet, inline style, inline script -->
Use the `audit-findings` format. Key `FE-<check>:<file>`, or `WCAG-<sc>:<file>`
where the check maps to a success criterion. Every finding has:
- the Location and a verbatim `Excerpt` (ADR 0004 D1);
- the **user impact**: who is stopped or slowed, and how;
- the **fix**, in the client's tokens and components;
- the kind, in the Evidence line (`static`, or `runtime: scans/axe/home.json`).

Critical or High needs a Trigger. For a front end that's the user and the step:
"a keyboard user on the report form can't reach the submit button".

## Check catalogue
<!-- brief: markup, component, stylesheet, inline style, inline script -->

In the evidence column, `grep` means a pattern to search the unit for, and
`axe:<rule>` means an axe result with that rule id.

### 1. Stack and HTML first
<!-- brief: markup, component -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-JS-PROPORTION | A content page (information, a brochure, a document list) built as a client-rendered app, or a whole page hydrated for one widget | agent | page has no server-rendered content; bundle entry per page | Low; Medium if content is missing without JS | Russell-2026, React-start |
| FE-NATIVE-FIRST | JavaScript reimplementing a native element: a modal without `<dialog>`, a disclosure without `<details>`, a custom select, hand-rolled validation | static | grep `role="dialog"`, `role="button"` on `div`/`span`, `onclick` on non-buttons | Low; Medium if keyboard or screen reader use breaks (WCAG-4.1.2) | ARIA-rules, MDN-invokers |
| FE-NO-JS-FORM | A transactional form that can't be submitted without JavaScript (no `action`, submit only through script) | static | `<form>` without `action` and a script `submit` handler | Low; Medium on a public service form | GOVUK-validation |

### 2. Design tokens and brand
<!-- brief: markup, component, stylesheet, inline style -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-TOKEN-RAW | Raw colours (`#3a7`, `rgb(`), pixel font sizes or arbitrary Tailwind values (`text-[#3a7]`, `p-[13px]`) in component code instead of tokens | static | grep `#[0-9a-fA-F]{3,8}\b`, `font-size:\s*\d+px`, `-\[` outside the token file | Low; Medium when widespread (a rebrand or dark mode can't be done in one place) | DTCG, Tailwind-theme |
| FE-TOKEN-PAIR | A text/background token pair below 4.5:1 (3:1 for large text, meaning 24px or about 18.5px bold, and for non-text) in **any** theme. Compute the ratio; never round (4.499 fails). A brand colour can pass on white and fail on dark | static | the two token values and the computed ratio | High on body text or controls; Medium otherwise. Maps to WCAG-1.4.3 / 1.4.11 | WCAG-contrast |
| FE-TOKEN-PRIMITIVE | Components using primitive tokens (`--blue-700`) instead of semantic ones (`--color-action`), so a theme or rebrand needs component edits | static | grep `var(--` names in component CSS | Low | DTCG |
| FE-DS-DRIFT | What's built differs from the approved design system: colours, fonts, spacing or components that don't match the recorded brand kit or its version. Only when `project.md` records an approved design system | agent | the approved value and the built one, with excerpts | Low to Medium; High if the drift fails a standard the approved value passes | intake |
| FE-DS-UNCONFIRMED | No approved design system recorded, but the code has tokens, a brand font or a component library. Not a defect: an open question for the brand owner, and every brand judgement stays conditional | manual | the token file and font declarations | `info`, plus an open question | intake |
| FE-BRAND-CONFLICT | A brand value that fails a standard. Report the measured ratio and the nearest same-hue shade that passes (compute in OKLCH); never propose dropping the brand | agent | the token, both ratios | As FE-TOKEN-PAIR | WCAG-contrast |
| FE-FLUID-TYPE | `clamp()` or `vw` font sizes without `rem` bounds, or a maximum more than 2.5 times the minimum, so text doesn't reach 200% at zoom | static | grep `clamp(`, `font-size:.*vw` | Medium (WCAG-1.4.4) | Smashing-fluid |
| FE-ICON-FONT | Icons from an icon font instead of SVG (layout shift, fallback glyphs, missing names) | static | `@font-face` for an icon set; `<i class="fa-` | Low | webdev-fonts |

### 3. Page skeleton
<!-- brief: markup, component -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-VIEWPORT-ZOOM | A viewport tag with `maximum-scale=1` or `user-scalable=no`, which blocks zoom | static | grep `user-scalable\s*=\s*no`, `maximum-scale\s*=\s*1\b` | High (WCAG-1.4.4) | WCAG22 |
| FE-HEAD | Missing `lang`, `<title>` or `charset`; the same `<title>` on every page; no `Error:` prefix on a page showing form errors | static (presence), runtime (uniqueness) | the `<html>` and `<head>` lines | Medium for `lang` and `<title>` (WCAG-3.1.1, 2.4.2); Low otherwise | WCAG22, GOVUK-validation |
| FE-LANDMARKS | No `<main>`, no skip link to it as the first focusable element, several `<h1>`, skipped heading levels, no `aria-current` on the current nav item | static | grep `<main`, `href="#main"`, `<h1` | Medium for the skip link and `<main>` (WCAG-2.4.1, 1.3.1); Low otherwise | WCAG22 |
| FE-STICKY-FOCUS | A sticky or fixed header or footer with no `scroll-padding` to match, so focused elements are hidden behind it | static (suggests), runtime (proves) | grep `position:\s*(sticky\|fixed)` and `scroll-padding` | Medium (WCAG-2.4.11) | WCAG22 |
| FE-TEXT-OVER-IMAGE | Text over a background image, gradient, video, `backdrop-filter: blur()` or a semi-transparent overlay (`rgba`, `opacity`, glass effects). Contrast is measured against the parts of the background most like the text and behind it, so the darkest or lightest point of the image, at every breakpoint, has to pass. A solid or opaque scrim behind the text settles it; anything see-through needs a rendered check | static (suggests), runtime (proves) | grep `background-image`, `backdrop-filter`, `linear-gradient`, `opacity:` on text containers | High on body text or a call to action; Medium otherwise (WCAG-1.4.3, failure F83) | WCAG-F83, Digital-NSW-contrast |
| FE-TEXT-SHADOW | `text-shadow` used as the only thing giving text contrast over an image. WCAG counts a narrow outline as part of the letter and a wide halo as background, so it can pass; heavy shadows still blur letter edges for some readers, and a solid box behind the text is the safer fix | static, runtime | grep `text-shadow` on text over images | Low (an advisory unless contrast fails). Source for the legibility point: reviewer judgement (Vision Australia) | WCAG-contrast |
| FE-HERO-LCP | The hero image (usually the largest element) lazy-loaded, set as a CSS background, missing `width`/`height` or `fetchpriority="high"`, or headline text baked into an image | static | the hero `<img>` line | Medium (slow first view; text in images also fails WCAG-1.4.5) | webdev-LCP |
| FE-AUTOPLAY | A carousel or animation that moves on its own with no pause, or ignores `prefers-reduced-motion` | static | grep `setInterval` near slides, `autoplay`, `@media (prefers-reduced-motion` | Medium (WCAG-2.2.2) | WCAG22 |

### 4. CSS architecture and layout
<!-- brief: markup, component, stylesheet, inline style -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-FOCUS-HIDDEN | `outline: none` or `outline: 0` with no `:focus-visible` replacement of at least 3:1; a focus ring drawn with `box-shadow` that a later rule (`box-shadow: none`, a component shadow) overrides | static | grep `outline:\s*(none\|0)`, `box-shadow:\s*none` in `:focus` rules | High on interactive controls (WCAG-2.4.7) | WCAG22 |
| FE-SPECIFICITY | `!important` or ID selectors outside the reset and token layers; no `@layer` order | static | grep `!important`, `^#[\w-]+\s*\{` | Low | MDN |
| FE-REFLOW | Fixed widths, `min-width` on the page or `overflow-x` that force horizontal scrolling at 320 CSS px | static (suggests), runtime (proves) | grep `width:\s*\d{4}px`, `min-width` on containers | Medium (WCAG-1.4.10) | WCAG22 |
| FE-TARGET-SIZE | Interactive targets under 24×24 CSS px without spacing | static (suggests), runtime (proves) | button and link sizes in CSS | Medium (WCAG-2.5.8) | WCAG22 |
| FE-USER-PREFS | No `prefers-reduced-motion` handling for animation, transitions or parallax; focus or borders hidden under `forced-colors`; no response to `prefers-contrast`; dark mode (`prefers-color-scheme`) without its own tested pairs | static | grep the media queries | Low; Medium if motion can't be stopped | WCAG22 |

### 5. Accessibility patterns
<!-- brief: markup, component -->

WCAG success criteria belong to the `web-accessibility` profile; use its IDs.
These checks are the patterns that most often fail them (the WebAIM Million 2026
found low-contrast text on 83.9% of home pages, missing alt text on 53.1%, missing
form labels on 51%, empty links on 46.3%, empty buttons on 30.6% and missing
`lang` on 13.5%).

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-EMPTY-CONTROL | Links and buttons with no accessible name: icon-only buttons without `aria-label`, links wrapping only an image with no `alt` | static | grep `<button[^>]*>\s*<(svg\|i\|img)` | High on a required step (WCAG-4.1.2, 2.4.4) | WebAIM-2026 |
| FE-ALT | Informative images with no `alt` or a filename as `alt`; decorative images without `alt=""`; functional images (in links and buttons) whose `alt` describes the picture instead of the action or destination; text in images without the same text in HTML | static (presence), agent (meaning) | grep `<img`, `<input type="image"` | Medium; High on a required step (WCAG-1.1.1, 1.4.5) | WCAG22, W3C-images, Digital-NSW-images |
| FE-COMPLEX-IMAGE | Charts, graphs, diagrams and maps with only a short `alt`: they need a short text alternative plus a long description or an HTML data table next to them | static (presence), agent (adequacy) | `<img>`, `<canvas>`, `<svg>` charts and map containers with no adjacent table or description | High when the information is only in the image (WCAG-1.1.1) | W3C-complex-images, Digital-NSW-images |
| FE-FLASH | Content that flashes or blinks more than three times a second | runtime, manual | grep `@keyframes` with short durations, `blink`, autoplaying video | High (WCAG-2.3.1: seizure risk) | WCAG22, Digital-NSW-basics |
| FE-READABLE-TEXT | Justified body text (`text-align: justify`); text spacing that breaks layout when users change line height or letter and word spacing; content whose reading order changes when styles are removed | static (justify), runtime (spacing), manual (order) | grep `text-align:\s*justify`, fixed heights on text containers | Low; Medium for spacing that hides text (WCAG-1.4.12, 1.3.2) | Digital-NSW-basics, WCAG22 |
| FE-ARIA-MISUSE | ARIA where a native element exists, `aria-hidden="true"` or `role="presentation"` on focusable elements, ARIA widgets without keyboard handling | static | grep `aria-hidden="true"` near `tabindex`, `role=` | Medium to High (WCAG-4.1.2) | ARIA-rules, ARIA-APG |

### 6. Forms
<!-- brief: markup, component -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-FORM-LABEL | An input with no visible `<label for>` (a placeholder isn't a label); radio or checkbox groups without `fieldset`/`legend` | static | each `<input>`, `<select>`, `<textarea>` | High on a required step (WCAG-1.3.1, 3.3.2) | GOVUK-validation |
| FE-AUTOCOMPLETE | Name, email, phone, address or password fields without `autocomplete`; `type="number"` used for identifiers | static | the field's `name`/`type` and attributes | Medium (WCAG-1.3.5) | webdev-forms |
| FE-PASTE-BLOCKED | `onpaste` returning false or `preventDefault()` on paste, especially on email or password fields | static | grep `onpaste`, `paste` listeners | Medium (WCAG-3.3.8) | webdev-forms |
| FE-ERROR-PATTERN | Errors not following the tested pattern: no error summary at the top that links to fields and takes focus; no inline message tied by `aria-describedby` with `aria-invalid`; values cleared on error; errors shown only as a toast or only by colour; validation while typing | static (code), runtime (behaviour) | the error-rendering code path | High when errors can't be found or fixed (WCAG-3.3.1, 3.3.3, 1.4.1) | GOVUK-validation, GOVUK-error-summary |
| FE-VALIDATION-MIX | Native browser validation and custom messages mixed in one product | static | `novalidate` on some forms, `required` messages on others | Low | GOVUK-validation, webdev-forms |
| FE-CSRF | A state-changing form or endpoint with no CSRF token or `Sec-Fetch-Site` check; session cookies without `SameSite`; GET requests that change state | static | form markup and the matching server route | High on authenticated state changes. Related: cross-ref security | OWASP-CSRF |
| FE-DOUBLE-SUBMIT | Nothing stops a second submission while the first is in flight | static | submit handler | Low; Medium where duplicates cost money or records | webdev-forms |

### 7. Performance and caching
<!-- brief: markup, component -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-IMG-DIMENSIONS | Images without `width` and `height` (or `aspect-ratio`), so the layout shifts; `loading="lazy"` on images above the fold | static | each `<img>` | Low; Medium on the hero | CWV, webdev-LCP |
| FE-FONTS | Non-WOFF2 fonts, many families or weights, no deliberate `font-display`, more than two preloads | static | `@font-face`, `<link rel="preload"` | Low | webdev-fonts |
| FE-CACHE | Hashed assets without `max-age=31536000, immutable`; HTML cached without revalidation; `no-store` on public pages (it also blocks back/forward cache); personal pages without `private` | static (server config), runtime (headers sent) | `Cache-Control` in server code or config | Low; Medium for personal data cached publicly | MDN-cache, webdev-bfcache |
| FE-BFCACHE | `unload` handlers, which block the back/forward cache | static | grep `unload` | Low | webdev-bfcache |
| FE-JS-BUDGET | Critical-path JavaScript far over about 0.3 MiB for a light page or 0.6 MiB for a heavy one (Russell's 2026 budget for a mid-range phone) | static (bundle sizes), runtime (measured) | built bundle sizes, if in the repo | Low; a performance hypothesis until measured | Russell-2026 |

### 8. Browser security
<!-- brief: markup, component, inline script -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-CSP | No Content Security Policy, an allowlist policy (bypassable in most configurations), `unsafe-inline` for scripts, or CSP only in a `<meta>` tag. A strict policy uses nonces or hashes with `strict-dynamic`, `object-src 'none'` and `base-uri 'none'` | static (server code), runtime (header sent) | the CSP string | Medium; High where untrusted HTML reaches the page. Related: EXP-SEC-HEADERS | webdev-CSP, OWASP-headers |
| FE-HEADERS | Missing or wrong HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, framing control; `X-Powered-By` or `Server` leaking; `X-XSS-Protection` set to anything but `0` | static, runtime | header setup in server code | Low to Medium. Related: EXP-SEC-HEADERS | OWASP-headers |
| FE-THIRD-PARTY | Third-party scripts without SRI (`integrity` and `crossorigin`) or a recorded owner and purpose; embeds without `sandbox`; tags that load before any consent | static | `scans/sweep.json` network rows; `<script src="https://` | Medium; High for session recording on pages with forms | OWASP-headers |
| FE-BUNDLE-SECRET | API keys, tokens or internal URLs shipped in front-end code or client-exposed environment variables | static | `scans/secrets.json`, grep `apiKey`, `NEXT_PUBLIC_`, `VITE_` | High if the key grants access | OWASP-headers |

`JS-DOM-XSS` in `javascript-review` covers untrusted data reaching
`innerHTML`, `dangerouslySetInnerHTML` and `v-html`.

### 9. Feedback, toasts and client errors
<!-- brief: markup, component, inline script -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-LIVE-REGION | Status messages through live regions that are injected on demand or hidden with `display:none` (often not announced); `role="alert"` for non-urgent messages | static | grep `aria-live`, `role="status"`, `role="alert"` and where they're created | Medium (WCAG-4.1.3) | Roselli-toast, WCAG22 |
| FE-TOAST | Toasts that hold buttons or links, take focus, carry form errors, or auto-dismiss errors and anything the user must act on | static (code), runtime (timing) | the notification code | Medium; High when an error disappears before it can be read (WCAG-2.2.1) | Roselli-toast |
| FE-NOTIFY-SERVICE | Each feature building its own toast or banner instead of one shared notification component | agent | several notification implementations | Low. Related: SLOP-DUP | Roselli-toast |
| FE-UI-STATES | Data components without designed loading, empty, error and offline states; error messages that show stack traces, IDs or internals | static | the component's render paths | Low; Medium if internals leak. Related: EXP-ERROR-LEAK | GOVUK-validation |
| FE-CLIENT-ERRORS | No global `error` and `unhandledrejection` handling; client error reports that include form values, tokens or emails | static | grep `addEventListener('error'`, `unhandledrejection`, `sendBeacon` | Low; Medium if personal data is sent | webdev-forms |

### 10. Reuse and consistency
<!-- brief: markup, component -->

| CHECK-ID | What to look for | Kind | Evidence | Severity guide | Source |
|---|---|---|---|---|---|
| FE-ONE-OFF | A component that duplicates an existing one in the catalogue (same role and structure, different markup or styles), or brand values changed inside a component | agent | both components, with excerpts | Low; Medium when it breaks consistency on a service path. Recommend reuse, then a variant, then a new component, in that order | Tailwind-reuse |
| FE-WORDING | The same action named differently across pages ("Sign in", "Log in", "Log on") | agent | the labels, with locations | Low | GOVUK-validation |
| FE-DRIFT-CONTROLS | No stylelint, html-validate or accessibility checks in CI to stop drift; no visual-regression or axe tests on key pages | static | pipeline files, `package.json` scripts | Low; an engineering-practice recommendation | stylelint, html-validate |

## Still to check by hand
<!-- brief: markup, component, stylesheet, inline style -->
Some things only a person can settle. For every page or journey you reviewed,
add the ones that apply to the "still to check by hand" list in your output,
with what to do:
- a screen reader pass (NVDA or VoiceOver) through each main journey;
- keyboard-only completion of each form, including the error path;
- 200% and 400% zoom, and 320 px width;
- whether alt text and link text make sense for their purpose;
- reading level against the client's content guide;
- the brand owner's sign-off for any FE-BRAND-CONFLICT variant.

## Tools for the manual checks
These are for the person doing the hand checks; agents compute contrast
themselves from the values in the code.
- NSW Colour Contrast Checker (https://contrast.design.nsw.gov.au/): built on the
  NSW Government palette, with a Check mode for any two colours. Digital NSW
  recommends starting there.
- WebAIM Contrast Checker and Link Contrast Checker; Contrast Grid and an
  accessible colour palette builder for checking a whole palette at once.
- Accessibility Insights for Web (headings and structure), axe, and the browser's
  own accessibility inspector.
- A screen reader (NVDA on Windows, VoiceOver on macOS and iOS), keyboard only,
  and 200% and 400% zoom.

## Rationalisations (and rebuttals)
<!-- brief: markup, component, stylesheet, inline style, inline script -->
| Excuse | Rebuttal |
|---|---|
| "axe passed, so it's accessible." | Automated tools find only part of the issues. List what still needs a person. |
| "The brand colour can't change." | It doesn't have to: propose a passing shade of the same hue, with the ratio, for the brand owner. |
| "It's only a hex value in one component." | One is a slip; many mean a rebrand or dark mode can't be done in one place. Count them. |
| "Contrast is 4.49, close enough." | Ratios aren't rounded. It fails. |
| "The toast says what went wrong." | Errors in a toast vanish and aren't tied to the field. Use the summary and inline pattern. |
| "The headers are set by the platform." | Then they aren't evidenced in the repo. Mark `runtime` and list it, don't assume. |

## Red flags
<!-- brief: markup, component, stylesheet, inline style, inline script -->
- A `runtime` check reported as confirmed from source alone
- A contrast finding without both colours and the computed ratio
- A recommendation to replace the client's brand or design system
- "Off-brand" when nobody has said what the approved brand is
- Copying another design system's look into the client's product
- A WCAG failure keyed `FE-*` instead of its `WCAG-*` ID

## Verification (before you finish the unit)
<!-- brief: markup, component, stylesheet, inline style, inline script -->
- [ ] Tokens located (or "no tokens" recorded), and raw values counted against them
- [ ] Every contrast finding has both values and the unrounded ratio
- [ ] Every finding names its kind; `runtime` ones are Medium confidence at most without a rendered page
- [ ] Manual checks added to the "still to check by hand" list
- [ ] No recommendation replaces the client's brand
- [ ] Tokens and fonts called "approved" only if `project.md` says so; otherwise "as built", with an open question for the brand owner

## Sources
<!-- brief: markup, component, stylesheet, inline style, inline script -->
Official:
- WCAG22: https://www.w3.org/TR/WCAG22/
- WCAG-contrast: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- ARIA-rules: https://www.w3.org/TR/using-aria/
- ARIA-APG: https://www.w3.org/WAI/ARIA/apg/
- CWV: https://web.dev/articles/vitals
- webdev-LCP: https://web.dev/articles/optimize-lcp
- webdev-fonts: https://web.dev/articles/font-best-practices
- webdev-forms: https://web.dev/articles/sign-in-form-best-practices
- webdev-CSP: https://web.dev/articles/strict-csp
- webdev-bfcache: https://web.dev/articles/bfcache
- Baseline: https://web.dev/baseline
- MDN-cache: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
- MDN-invokers: https://developer.mozilla.org/en-US/docs/Web/API/Invoker_Commands_API
- OWASP-headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP-CSRF: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- GOVUK-validation: https://design-system.service.gov.uk/patterns/validation/
- GOVUK-error-summary: https://design-system.service.gov.uk/components/error-summary/
- DTCG: https://www.w3.org/community/reports/design-tokens/CG-FINAL-format-20251028/
- React-start: https://react.dev/learn/creating-a-react-app
- Tailwind-reuse: https://tailwindcss.com/docs/reusing-styles
- Tailwind-theme: https://tailwindcss.com/docs/theme
- html-validate: https://html-validate.org/
- stylelint: https://stylelint.io/
- WCAG-F83 (text over background images): https://www.w3.org/WAI/WCAG22/Techniques/failures/F83
- WCAG-G18 (contrast and large text sizes): https://www.w3.org/WAI/WCAG22/Techniques/general/G18
- W3C-images: https://www.w3.org/WAI/tutorials/images/
- W3C-complex-images: https://www.w3.org/WAI/tutorials/images/complex/
- Digital-NSW-contrast: https://digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/design/colour-contrast
- Digital-NSW-images: https://digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/design/graphics-and-images
- Digital-NSW-basics: https://digital.nsw.gov.au/delivery/accessibility-and-inclusivity-toolkit/basics
- DTA inclusive design tips: https://www.digital.gov.au/policy/digital-experience/digital-inclusion-standard/inclusive-digital-design-tips

Research and practitioners, cited as reviewer judgement where no official
source says the same (`Source: none – reviewer judgement (<name>)`):
- WebAIM-2026: WebAIM, *The WebAIM Million*: https://webaim.org/projects/million/
- Roselli-toast: Adrian Roselli, "Defining 'Toast' Messages": https://adrianroselli.com/2020/01/defining-toast-messages.html
- Russell-2026: Alex Russell, "The Performance Inequality Gap, 2026": https://infrequently.org/2025/11/performance-inequality-gap-2026/
- Smashing-fluid: Smashing Magazine, "Addressing Accessibility Concerns With Using Fluid Type": https://www.smashingmagazine.com/2023/11/addressing-accessibility-concerns-fluid-type/
- Vision Australia, "Creating accessible digital colour palettes": https://www.visionaustralia.org/business-consulting/digital-access/Creating-accessible-digital-colour-palettes-60-30-10-design-rule (blur and shadow legibility)

All of these resolved (HTTP 200) on 2026-11-08. The rules restate the jsaudit
rulebook. The text-over-image, text-shadow, images, flashing and readable-text
checks were added the same day from the Digital NSW toolkit and WCAG F83, G18
and Understanding 1.4.3 (Note 5), each read for the point it supports. Read the
part of a page you rely on before citing it.
