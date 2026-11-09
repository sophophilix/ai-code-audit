"""Every colour, design token and font the front end declares (no AI, no execution).

Reads own stylesheets, inline `<style>` blocks and `style=""` attributes as text,
and lists what they use: colours (with counts, properties and locations),
CSS custom properties (the tokens, with their uses), font stacks, `@font-face`
rules and web-font links. Where one rule sets both a text and a background
colour, it computes the WCAG contrast ratio, unrounded.

This is the design *as built*. Whether it's the approved brand is a question for
the brand owner (`project.md` → "Design system and brand").

Not seen, so a rendered page is needed for them: colours set by scripts, images
or a CMS at run time, and JSX style objects (`style={{ color: ... }}`). A
`url()` with semicolons (a data URI) can cut a declaration short. A background
that mixes a colour with an image or gradient isn't measured: what's behind the
text is the image (WCAG failure F83).
"""

from __future__ import annotations

import colorsys
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from audit_kit.errors import WorkspaceError
from audit_kit.inventory import Inventory
from audit_kit.workspace import Workspace

JSON_OUT = ".audit/scans/design-inventory.json"
MD_OUT = ".audit/scans/design-inventory.md"
STYLESHEETS = (".css", ".scss", ".sass", ".less")
MARKUP = (
    ".html", ".htm", ".ejs", ".hbs", ".handlebars", ".njk", ".pug",
    ".vue", ".svelte", ".cshtml", ".razor", ".jsx", ".tsx",
)  # fmt: skip
SHOWN = 5
MAX_BYTES = 16_000_000

COLOUR = re.compile(
    # Not `url(#id)`, which names an SVG element.
    r"(?<!url\()#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b"
    r"|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\([^)]*\)",
    re.I,
)
DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;{}]+)")
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
FONT_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.I)
STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.I | re.S)
STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*(["'])(.*?)\1""", re.I | re.S)
FONT_LINK = re.compile(
    r"https?://(?:fonts\.googleapis\.com|fonts\.gstatic\.com|use\.typekit\.net"
    r"|fonts\.bunny\.net|fast\.fonts\.net|use\.fontawesome\.com)[^\s\"'<>)]*",
    re.I,
)
STYLE_ATTR_RULE = "(style attribute)"
# The family list at the end of the `font` shorthand: what follows the size (which
# has a unit or is a keyword, unlike a bare weight such as 600) and line height.
FONT_SHORTHAND = re.compile(
    r"(?:^|\s)(?:[\d.]+(?:px|r?em|%|pt|vw|vh|vmin|vmax|ch|ex|cap|lh)"
    r"|(?:xx?-)?(?:small|large)|medium|smaller|larger)"
    r"(?:\s*/\s*[\w.%]+)?\s+(.+)$",
    re.I,
)
VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)")
# A background that is, or includes, an image: its colour isn't what's behind the text.
IMAGE_BACKGROUND = re.compile(r"\burl\(|gradient\(|image-set\(", re.I)
COMMENT = re.compile(r"/\*.*?\*/", re.S)
TEXT_PROPS = frozenset({"color"})
BACKGROUND_PROPS = frozenset({"background-color", "background"})
GENERIC_FONTS = frozenset(
    {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
     "ui-sans-serif", "ui-serif", "ui-monospace", "inherit", "initial", "unset"}
)  # fmt: skip


def hex_of(value: str) -> str | None:
    """Normalise a hex, rgb() or hsl() colour to `#rrggbb` (alpha dropped), else None.

    Colours with transparency are returned too; their contrast depends on what's
    behind them, so callers mark it.
    """
    v = value.strip().lower()
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        return f"#{h[:6]}" if len(h) >= 6 else None
    nums = [float(n) for n in re.findall(r"-?\d*\.?\d+", v)]
    if v.startswith("rgb") and len(nums) >= 3:
        if "%" in v:
            nums[:3] = [n * 2.55 for n in nums[:3]]
        r, g, b = (max(0, min(255, round(n))) for n in nums[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    if v.startswith("hsl") and len(nums) >= 3:
        rgb = colorsys.hls_to_rgb(nums[0] / 360 % 1, nums[2] / 100, nums[1] / 100)
        return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
    return None


def alpha(value: str) -> float:
    """The colour's opacity from 0 to 1 (8- or 4-digit hex, rgba(), `/ a`); 1 if none."""
    v = value.strip().lower()
    if v.startswith("#"):
        h = v[1:]
        digits = h[6:8] if len(h) == 8 else h[3] * 2 if len(h) == 4 else "ff"
        return int(digits, 16) / 255
    parts = re.split(r"[,/]", v[v.find("(") + 1 : v.rfind(")")])
    if len(parts) < 4:
        return 1.0
    a = parts[3].strip()
    try:
        return float(a[:-1]) / 100 if a.endswith("%") else float(a)
    except ValueError:
        return 1.0


def translucent(value: str) -> bool:
    """True when the colour lets what's behind it show through."""
    return alpha(value) < 1


def colour_key(value: str) -> str:
    """`#rrggbb`, or `#rrggbb at 50%` for a translucent use, or the value as written."""
    hexed = hex_of(value)
    if hexed is None:
        return value.strip().lower()
    a = alpha(value)
    return hexed if a >= 1 else f"{hexed} at {round(a * 100)}%"


def luminance(hex_colour: str) -> float:
    """WCAG 2 relative luminance of `#rrggbb`."""

    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two `#rrggbb` colours, unrounded."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@dataclass
class _Found:
    colours: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Every definition of each token, in file order: a theme or a media query
    # can redefine one, and a pair is only right for the definition it used.
    tokens: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    token_uses: dict[str, int] = field(default_factory=dict)
    stacks: dict[str, dict[str, Any]] = field(default_factory=dict)
    faces: list[dict[str, Any]] = field(default_factory=list)
    links: dict[str, list[str]] = field(default_factory=dict)
    rules: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)


def _css_chunks(path: str, text: str) -> Iterator[tuple[str, int]]:
    """(css, first line) for a stylesheet, each <style> block and each style=""."""
    if path.endswith(STYLESHEETS):
        yield text, 1
        return
    for m in STYLE_BLOCK.finditer(text):
        yield m.group(1), text.count("\n", 0, m.start(1)) + 1
    for m in STYLE_ATTR.finditer(text):
        yield (
            STYLE_ATTR_RULE + "{" + m.group(2) + "}",
            text.count("\n", 0, m.start(2)) + 1,
        )


def _record(found: _Found, path: str, css: str, first: int) -> None:
    css = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), css)
    for m in FONT_FACE.finditer(css):
        body = {k.lower(): v.strip() for k, v in DECLARATION.findall(m.group(1))}
        src = body.get("src", "")
        found.faces.append(
            {
                "family": body.get("font-family", "").strip("'\" "),
                "weight": body.get("font-weight", ""),
                "style": body.get("font-style", ""),
                "display": body.get("font-display", ""),
                "formats": sorted(set(re.findall(r"format\(\s*['\"]?([\w-]+)", src))),
                "where": f"{path}:{first + css.count(chr(10), 0, m.start())}",
            }
        )
    for rule in RULE.finditer(css):
        selector = " ".join(rule.group(1).split())[-80:]
        line = first + css.count("\n", 0, rule.start(2))
        where = f"{path}:{line}"
        decls: dict[str, str] = {}
        for prop, value in DECLARATION.findall(rule.group(2)):
            prop, value = prop.lower(), value.strip()
            decls[prop] = value
            if prop.startswith("--"):
                found.tokens.setdefault(prop, []).append(
                    {"value": value, "where": where, "selector": selector}
                )
            for name, _fallback in VAR.findall(value):
                found.token_uses[name] = found.token_uses.get(name, 0) + 1
            for c in COLOUR.findall(value):
                _colour(found, c, prop, where)
            if prop == "font-family":
                _stack(found, value, where)
            elif prop == "font" and (shorthand := FONT_SHORTHAND.search(value)):
                _stack(found, shorthand.group(1), where)
        found.rules.append((selector, where, decls))


def _colour(found: _Found, raw: str, prop: str, where: str) -> None:
    key = colour_key(raw)
    entry = found.colours.setdefault(
        key,
        {"count": 0, "as_written": set(), "properties": set(), "where": [],
         "in_tokens": False, "translucent": False},
    )  # fmt: skip
    entry["count"] += 1
    entry["as_written"].add(raw)
    entry["properties"].add(prop)
    entry["in_tokens"] = entry["in_tokens"] or prop.startswith("--")
    entry["translucent"] = entry["translucent"] or translucent(raw)
    if len(entry["where"]) < SHOWN:
        entry["where"].append(where)


def _opaque(key: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-f]{6}", key))


Tokens = dict[str, list[dict[str, str]]]


def _first(tokens: Tokens, name: str, fallback: str | None) -> str | None:
    """A token's first definition, or the var() fallback when it isn't defined."""
    defined = tokens.get(name)
    return defined[0]["value"] if defined else fallback


def _expand(value: str, tokens: Tokens, depth: int = 0) -> str:
    """Replace var(--x) with the token's value, so `var(--font)` lists real families."""
    if depth >= 5 or "var(" not in value:
        return value
    expanded = VAR.sub(lambda m: _first(tokens, m.group(1), m.group(2)) or "", value)
    return _expand(expanded, tokens, depth + 1)


def _themed(value: str, tokens: Tokens, depth: int = 0) -> bool:
    """True when the value can change with a theme: light-dark() or a redefined token."""
    if "light-dark(" in value.lower():
        return True
    if depth >= 5:
        return False
    for name, _fallback in VAR.findall(value):
        defined = tokens.get(name, [])
        if len({d["value"] for d in defined}) > 1:
            return True
        if defined and _themed(defined[0]["value"], tokens, depth + 1):
            return True
    return False


def _stack(found: _Found, value: str, where: str) -> None:
    stack = ", ".join(f.strip().strip("'\"") for f in value.split(",") if f.strip())
    entry = found.stacks.setdefault(stack, {"count": 0, "where": []})
    entry["count"] += 1
    if len(entry["where"]) < SHOWN:
        entry["where"].append(where)


def _resolve(value: str, tokens: Tokens, depth: int = 0) -> str | None:
    """A colour value as `#rrggbb`, following var() and its fallback (5 levels).

    For `light-dark()` and redefined tokens this is the first value; `_themed`
    says when other values exist.
    """
    m = VAR.search(value)
    if m and depth < 5:
        target = _first(tokens, m.group(1), m.group(2))
        return _resolve(target, tokens, depth + 1) if target else None
    colour = COLOUR.search(value)
    if colour and not translucent(colour.group(0)):
        return hex_of(colour.group(0))
    return None


def _pairs(found: _Found) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Rules that set both text and background colour: measured, and not measurable."""
    pairs: list[dict[str, Any]] = []
    unmeasured: list[dict[str, str]] = []
    for selector, where, decls in found.rules:
        text = next((decls[p] for p in TEXT_PROPS if p in decls), None)
        back = next((decls[p] for p in BACKGROUND_PROPS if p in decls), None)
        if text is None or back is None:
            continue
        if IMAGE_BACKGROUND.search(_expand(back, found.tokens)):
            unmeasured.append(
                {
                    "selector": selector,
                    "where": where,
                    "why": "the background includes an image or gradient: measure the "
                    "darkest and lightest parts behind the text on a rendered page",
                }
            )
            continue
        fg, bg = _resolve(text, found.tokens), _resolve(back, found.tokens)
        if fg is None or bg is None:
            continue
        ratio = contrast(fg, bg)
        pairs.append(
            {
                "selector": selector,
                "where": where,
                "text": fg,
                "background": bg,
                "ratio": round(ratio, 2),
                "passes_text_4_5": ratio >= 4.5,
                "passes_large_or_ui_3": ratio >= 3.0,
                "other_values": _themed(text, found.tokens)
                or _themed(back, found.tokens),
            }
        )
    pairs.sort(key=lambda p: (p["ratio"], p["where"]))
    return pairs, unmeasured


def build(ws: Workspace, inv: Inventory, excluded: tuple[str, ...]) -> dict[str, Any]:
    """Collect the design inventory from own stylesheets and markup."""

    def kept(path: str) -> bool:
        return not any(
            path == e or path.startswith(e.rstrip("/") + "/") for e in excluded
        )

    found = _Found()
    problems: list[str] = []
    files = sorted(
        e.path
        for e in inv.of("own")
        if e.kind == "file"
        and e.path.endswith((*STYLESHEETS, *MARKUP))
        and kept(e.path)
    )
    for path in files:
        try:
            text = ws.read_text(path, limit=MAX_BYTES)
        except WorkspaceError as exc:
            problems.append(f"not read: {exc}")
            continue
        for css, first in _css_chunks(path, text):
            _record(found, path, css, first)
        for url in FONT_LINK.findall(text):
            found.links.setdefault(url, []).append(path)
    colours = [
        {
            "colour": key,
            "count": e["count"],
            "as_written": sorted(e["as_written"])[:SHOWN],
            "properties": sorted(e["properties"]),
            "in_tokens": e["in_tokens"],
            "translucent": e["translucent"],
            # A translucent colour's contrast depends on what's behind it.
            "on_white": round(contrast(key, "#ffffff"), 2) if _opaque(key) else None,
            "on_black": round(contrast(key, "#000000"), 2) if _opaque(key) else None,
            "where": e["where"],
        }
        for key, e in found.colours.items()
    ]
    colours.sort(key=lambda c: (-c["count"], c["colour"]))
    pairs, unmeasured = _pairs(found)
    families = sorted(
        {
            f.strip().strip("'\"")
            for stack in found.stacks
            for f in _expand(stack, found.tokens).split(",")
            if f.strip() and f.strip().lower() not in GENERIC_FONTS
        }
    )
    return {
        "generated_by": "kit scan: design inventory (deterministic, no execution)",
        "meaning": (
            "The design as built: colours, tokens and fonts the stylesheets and markup "
            "declare. Not proof of the approved brand; colours set at run time aren't seen."
        ),
        "files": len(files),
        "counts": {
            "colours": len(colours),
            "raw_colours_outside_tokens": sum(not c["in_tokens"] for c in colours),
            "tokens": len(found.tokens),
            "font_families": len(families),
            "font_faces": len(found.faces),
            "contrast_pairs_failing_4_5": sum(not p["passes_text_4_5"] for p in pairs),
        },
        "problems": problems,
        "colours": colours,
        "tokens": [
            {
                "name": n,
                "value": d[0]["value"],
                "where": d[0]["where"],
                "values": d,
                "uses": found.token_uses.get(n, 0),
            }
            for n, d in sorted(found.tokens.items())
        ],
        "font_families": families,
        "font_stacks": [
            {"stack": s, **e}
            for s, e in sorted(found.stacks.items(), key=lambda kv: -kv[1]["count"])
        ],
        "font_faces": found.faces,
        "font_links": [
            {"url": u, "in": sorted(set(p))} for u, p in sorted(found.links.items())
        ],
        "contrast_pairs": pairs,
        "unmeasured_pairs": unmeasured,
    }


def render_markdown(data: dict[str, Any]) -> str:
    """A page to hand a designer: the palette, tokens, fonts and failing pairs."""
    c = data["counts"]
    out = [
        "# Design inventory (as built)",
        "",
        "Generated by `kit scan` from the stylesheets and markup, without running the",
        "site. It shows what the code declares, not what the brand owner approved:",
        "compare it with the approved brand kit. Colours set by scripts, images or a",
        "CMS at run time aren't included.",
        "",
        f"{data['files']} files: {c['colours']} colours ({c['raw_colours_outside_tokens']} "
        f"written outside tokens), {c['tokens']} tokens, {c['font_families']} font "
        f"families, {c['font_faces']} `@font-face` rules, "
        f"{c['contrast_pairs_failing_4_5']} text/background pairs below 4.5:1.",
        "",
        "## Colours",
        "",
        "| Colour | Uses | In tokens | On white | On black | Used for | First seen |",
        "|---|---|---|---|---|---|---|",
    ]
    for col in data["colours"]:
        note = ""
        white = f"{col['on_white']}:1" if col["on_white"] else "n/a"
        black = f"{col['on_black']}:1" if col["on_black"] else "n/a"
        out.append(
            f"| `{col['colour']}`{note} | {col['count']} | {'yes' if col['in_tokens'] else 'no'} "
            f"| {white} | {black} | {', '.join(col['properties'][:4])} | `{col['where'][0]}` |"
        )
    out += ["", "## Tokens (CSS custom properties)", ""]
    if data["tokens"]:
        out += ["| Token | Value | Uses | Defined at |", "|---|---|---|---|"]
        out += [
            f"| `{t['name']}` | `{_cell(t['value'][:60])}` | {t['uses']} "
            f"| `{t['where']}`{_more(len(t['values']) - 1)} |"
            for t in data["tokens"]
        ]
    else:
        out.append("None: every colour and size is written where it's used.")
    out += ["", "## Fonts", ""]
    out.append(
        "Families: "
        + (", ".join(data["font_families"]) or "none named (system defaults)")
    )
    out += ["", "| Font stack | Uses | First seen |", "|---|---|---|"]
    out += [
        f"| {_cell(s['stack'])} | {s['count']} | `{s['where'][0]}` |"
        for s in data["font_stacks"]
    ]
    if data["font_faces"]:
        out += [
            "",
            "| `@font-face` family | Weight | Style | Formats | font-display | At |",
            "|---|---|---|---|---|---|",
        ]
        out += [
            f"| {f['family']} | {f['weight'] or '-'} | {f['style'] or '-'} | "
            f"{', '.join(f['formats']) or '-'} | {f['display'] or 'not set'} | `{f['where']}` |"
            for f in data["font_faces"]
        ]
    if data["font_links"]:
        out += ["", "Web fonts loaded from:", ""]
        out += [
            f"- {link['url']} (in {', '.join(link['in'][:3])})"
            for link in data["font_links"]
        ]
    out += ["", "## Text and background pairs", ""]
    if data["contrast_pairs"]:
        out += [
            "Rules that set both colours. Ratios are WCAG 2 contrast, rounded only for",
            "display; pass or fail uses the exact value.",
            "",
            '"Other values" means a theme, a media query or `light-dark()` gives',
            "another value too: check that pair as well.",
            "",
            "| Selector | Text | Background | Ratio | 4.5:1 text | 3:1 large or UI "
            "| Other values | At |",
            "|---|---|---|---|---|---|---|---|",
        ]
        out += [
            f"| `{_cell(p['selector'])}` | `{p['text']}` | `{p['background']}` "
            f"| {p['ratio']}:1 | {'pass' if p['passes_text_4_5'] else 'fail'} "
            f"| {'pass' if p['passes_large_or_ui_3'] else 'fail'} "
            f"| {'yes' if p['other_values'] else 'no'} | `{p['where']}` |"
            for p in data["contrast_pairs"]
        ]
    else:
        out.append(
            "No rule sets both a text and a background colour that can be resolved."
        )
    if data["unmeasured_pairs"]:
        out += [
            "",
            "Not measured, because the background includes an image or gradient. Check",
            "the darkest and lightest parts behind the text on a rendered page:",
            "",
        ]
        out += [
            f"- `{_cell(u['selector'])}` at `{u['where']}`"
            for u in data["unmeasured_pairs"]
        ]
    return "\n".join(out) + "\n"


def _more(extra: int) -> str:
    """` (and 2 more)` for a token defined again elsewhere, such as a dark theme."""
    return f" (and {extra} more)" if extra else ""


def _cell(text: str) -> str:
    """Escape `|` so selectors like `[lang|=en]` don't split a table row."""
    return text.replace("|", "\\|")


def write(ws: Workspace, inv: Inventory, excluded: tuple[str, ...]) -> dict[str, int]:
    """Write design-inventory.json and .md; returns the headline counts."""
    data = build(ws, inv, excluded)
    ws.write_text(JSON_OUT, json.dumps(data, indent=1) + "\n")
    ws.write_text(MD_OUT, render_markdown(data))
    return dict(data["counts"])
