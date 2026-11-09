"""The design inventory: colours, tokens and fonts as built, and contrast pairs."""

from __future__ import annotations

from pathlib import Path

import pytest

from audit_kit.design_inventory import (
    FONT_SHORTHAND,
    build,
    colour_key,
    contrast,
    hex_of,
    render_markdown,
)
from audit_kit.inventory import build as inventory
from audit_kit.workspace import Workspace


@pytest.mark.parametrize(
    ("colour", "ratio"),
    # Known answers from the jsaudit rulebook (frontend-craft) and WebAIM.
    [("#767676", 4.54), ("#1d4ed8", 6.70), ("#9ca3af", 2.54), ("#6b7280", 4.83)],
)
def test_contrast_on_white_matches_known_answers(colour: str, ratio: float) -> None:
    assert round(contrast(colour, "#ffffff"), 2) == ratio


def test_contrast_is_not_rounded_before_the_threshold() -> None:
    # #777777 on white is 4.478:1: it rounds to 4.5 but fails.
    assert round(contrast("#777777", "#ffffff"), 1) == 4.5
    assert contrast("#777777", "#ffffff") < 4.5


@pytest.mark.parametrize(
    ("written", "key"),
    [
        ("#FFF", "#ffffff"),
        ("#1b4081", "#1b4081"),
        ("rgb(27, 64, 129)", "#1b4081"),
        ("rgba(255,255,255,.5)", "#ffffff at 50%"),
        ("#ffffff80", "#ffffff at 50%"),
        ("hsl(0, 0%, 100%)", "#ffffff"),
        ("oklch(62% 0.2 250)", "oklch(62% 0.2 250)"),
    ],
)
def test_colours_are_normalised_and_translucent_uses_kept_apart(
    written: str, key: str
) -> None:
    assert colour_key(written) == key
    assert hex_of("not a colour") is None


@pytest.fixture
def site(tmp_path: Path) -> Workspace:
    root = tmp_path / "site"
    root.mkdir()
    (root / "tokens.css").write_text(
        ":root {\n  --brand: #60c3ad;\n  --ink: #0e2350;\n  --font: 'Brandsans', Arial, sans-serif;\n}\n"
        "@font-face {\n  font-family: 'Brandsans';\n  src: url(f.woff2) format('woff2');\n"
        "  font-weight: 400;\n  font-display: swap;\n}\n"
        ".hero {\n  color: #fff;\n  background: var(--brand);\n}\n"
        ".card {\n  color: var(--ink);\n  background-color: #ffffff;\n  font: 600 1rem/1.5 var(--font);\n}\n"
    )
    (root / "index.html").write_text(
        "<link href='https://fonts.googleapis.com/css2?family=Roboto' rel='stylesheet'>\n"
        "<style>\n.note { color: #767676; background: #fff; font-family: Roboto, sans-serif; }\n</style>\n"
        '<p style="color: rgba(0,0,0,.6)">x</p>\n'
    )
    return Workspace(root)


def test_the_inventory_lists_colours_tokens_fonts_and_pairs(site: Workspace) -> None:
    data = build(site, inventory(site), ())
    colours = {c["colour"]: c for c in data["colours"]}
    assert colours["#60c3ad"]["in_tokens"] and not colours["#767676"]["in_tokens"]
    assert colours["#000000 at 60%"]["on_white"] is None  # depends on what's behind
    assert colours["#000000 at 60%"]["where"] == ["index.html:5"]
    assert {t["name"]: t["uses"] for t in data["tokens"]} == {
        "--brand": 1,
        "--font": 1,
        "--ink": 1,
    }
    assert data["font_families"] == ["Arial", "Brandsans", "Roboto"]
    (face,) = data["font_faces"]
    assert (face["family"], face["formats"], face["display"]) == (
        "Brandsans",
        ["woff2"],
        "swap",
    )
    assert data["font_links"][0]["url"].startswith("https://fonts.googleapis.com/")
    pairs = {p["selector"]: p for p in data["contrast_pairs"]}
    assert (
        pairs[".hero"]["ratio"] == 2.12 and not pairs[".hero"]["passes_large_or_ui_3"]
    )
    assert pairs[".card"]["text"] == "#0e2350" and pairs[".card"]["passes_text_4_5"]
    assert pairs[".note"]["passes_text_4_5"]  # 4.54:1
    assert data["counts"]["contrast_pairs_failing_4_5"] == 1


def test_the_markdown_says_as_built_and_shows_failing_pairs(site: Workspace) -> None:
    md = render_markdown(build(site, inventory(site), ()))
    assert md.startswith("# Design inventory (as built)")
    assert "not what the brand owner approved" in md
    assert "| `.hero` | `#ffffff` | `#60c3ad` | 2.12:1 | fail | fail | no |" in md


@pytest.mark.parametrize(
    ("value", "families"),
    [
        ("600 1rem/1.5 var(--font)", "var(--font)"),
        ("italic bold 16px Arial, sans-serif", "Arial, sans-serif"),
        ("small-caps 12px/1 'Brandsans'", "'Brandsans'"),
        ("x-large Georgia", "Georgia"),
        ("inherit", None),
        ("700 normal", None),
    ],
)
def test_the_font_shorthand_gives_its_family_list(
    value: str, families: str | None
) -> None:
    m = FONT_SHORTHAND.search(value)
    assert (m.group(1) if m else None) == families


def site_with(tmp_path: Path, css: str) -> Workspace:
    root = tmp_path / "s"
    root.mkdir()
    (root / "a.css").write_text(css)
    return Workspace(root)


def test_a_background_with_an_image_or_gradient_is_not_measured(
    tmp_path: Path,
) -> None:
    # Review finding: the first colour of `#000 url(hero.jpg)` isn't what's behind the text.
    ws = site_with(
        tmp_path,
        ".a{color:#fff;background:#000 url(hero.jpg)}\n"
        ".b{color:#fff;background:linear-gradient(#ffffff,#000000)}\n"
        ".c{color:#000;background:#fff}\n",
    )
    data = build(ws, inventory(ws), ())
    assert [p["selector"] for p in data["contrast_pairs"]] == [".c"]
    assert [p["selector"] for p in data["unmeasured_pairs"]] == [".a", ".b"]
    assert "image or gradient" in data["unmeasured_pairs"][0]["why"]


def test_ids_in_url_are_not_colours(tmp_path: Path) -> None:
    ws = site_with(tmp_path, ".i{fill:url(#a1b2c3);stroke:#123456}\n")
    assert [c["colour"] for c in build(ws, inventory(ws), ())["colours"]] == ["#123456"]


def test_var_fallbacks_and_token_overrides_are_followed_and_flagged(
    tmp_path: Path,
) -> None:
    ws = site_with(
        tmp_path,
        ":root{--ink:#111111}\n[data-theme=dark]{--ink:#eeeeee}\n"
        ".a{color:var(--ink);background:#ffffff}\n"
        ".b{color:var(--gone, #222222);background:#ffffff}\n"
        ".c{color:light-dark(#111111, #eeeeee);background:#ffffff}\n",
    )
    data = build(ws, inventory(ws), ())
    pairs = {p["selector"]: p for p in data["contrast_pairs"]}
    assert pairs[".b"]["text"] == "#222222"
    assert pairs[".a"]["other_values"] and pairs[".c"]["other_values"]
    assert not pairs[".b"]["other_values"]
    (ink,) = [t for t in data["tokens"] if t["name"] == "--ink"]
    assert [v["where"] for v in ink["values"]] == ["a.css:1", "a.css:2"]


def test_pipes_in_selectors_and_values_keep_the_tables_intact(tmp_path: Path) -> None:
    ws = site_with(tmp_path, "[lang|=en]{color:#000;background:#fff}\n")
    md = render_markdown(build(ws, inventory(ws), ()))
    row = next(r for r in md.splitlines() if "lang" in r)
    assert row.count("|") - row.count("\\|") == 9  # eight columns
