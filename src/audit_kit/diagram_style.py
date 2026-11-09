"""The kit's house style for diagrams: grouped by trust boundary, soft and hand-drawn.

drawio-skill places the boxes; this module decides how they look. It runs
before the build (one group per trust boundary, card-sized nodes) and after it
(restyles every cell), so the pinned third-party code runs unchanged.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET  # nosec B405  parses only files the kit just built
from typing import Any

STYLES = ("handdrawn", "clean")
CARD_WIDTH, CARD_HEIGHT = 220, 72
ICON = 40

INK = "#1f2937"
EDGE_INK = "#4b5563"
CARD_STROKE = "#9ca3af"
FONT = "fontFamily=Helvetica;fontColor=" + INK
# rough.js settings draw.io uses for sketch=1; a solid fill keeps text readable.
SKETCH = "sketch=1;curveFitting=1;jiggle=1.5;fillStyle=solid"
# drawio-skill ranks the executive view with int(importance).
IMPORTANCE = {"low": 1, "medium": 2, "high": 3, "critical": 4}
# Shapes whose outline is the meaning (cylinder = data store); keep them.
KEEP_SHAPE = re.compile(r"\b(cylinder3?|hexagon|umlActor|rhombus|ellipse|cloud)\b")


def prepare(ir: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the IR ready for drawio-skill's build.

    Adds a group per trust boundary and card-sized nodes (a node's own `group`,
    `width` and `height` win), and turns a worded `importance` into the number
    drawio-skill sorts on (an unknown word is dropped, not guessed).
    """
    out = copy.deepcopy(ir)
    for node in out.get("nodes") or []:
        props = node.get("properties") or {}
        rank = str(props.get("importance", "")).strip().lower()
        if rank and not rank.isdigit():
            if rank in IMPORTANCE:
                props["importance"] = IMPORTANCE[rank]
            else:
                del props["importance"]
        boundary = props.get("trust_boundary")
        if boundary and not node.get("group"):
            node["group"] = _title(str(boundary))
        node.setdefault("width", CARD_WIDTH)
        node.setdefault("height", CARD_HEIGHT)
    return out


def restyle(xml: str, style: str = "handdrawn") -> str:
    """Return draw.io XML with the house style applied to every page.

    Geometry and edge waypoints are kept, so a later `sync` or a manual tidy in
    draw.io starts from the same layout.

    Raises:
        ValueError: If `style` isn't one of STYLES.
    """
    if style not in STYLES:
        raise ValueError(f"unknown diagram style {style!r}; use one of {STYLES}")
    sketch = style == "handdrawn"
    root = ET.fromstring(xml)  # noqa: S314  # nosec B314  the kit's own build output
    for model in root.iter("mxGraphModel"):
        model.set("background", "#ffffff")
        # A UserObject (a node with a link) wraps its mxCell; take each once.
        cells = [
            (holder, holder if holder.tag == "mxCell" else holder.find("mxCell"))
            for holder in model.find("root") or []
        ]
        parents = {c.get("parent") for _, c in cells if c is not None}
        for holder, cell in cells:
            if cell is None:
                continue
            old = cell.get("style") or ""
            if cell.get("edge") == "1":
                new = _edge(old, holder.get("data-kind") or cell.get("data-kind"))
            elif cell.get("vertex") != "1":
                continue
            elif (holder.get("id") or cell.get("id")) in parents:
                new = _container(old)
            elif "image=" in old:
                new = _card(old)
            else:
                new = _shape(old)
            cell.set("style", new + (";" + SKETCH if sketch else "") + ";")
    return ET.tostring(root, encoding="unicode")


def _title(boundary: str) -> str:
    words = re.split(r"[-_\s]+", boundary.strip())
    return " ".join(w if w.isupper() else w.capitalize() for w in words if w)


def _get(style: str, key: str) -> str | None:
    m = re.search(rf"(?:^|;){re.escape(key)}=([^;]*)", style)
    return m.group(1) if m else None


def _tint(color: str | None, keep: float) -> str:
    """Mix a #rrggbb colour with white, keeping `keep` of the colour."""
    if not color or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return "#f8fafc"
    rgb = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(255 - (255 - c) * keep):02x}" for c in rgb)


def _shade(color: str | None) -> str:
    """Darken a #rrggbb colour for text on its own tint."""
    if not color or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return INK
    return "#" + "".join(
        f"{int(color[i : i + 2], 16) * 6 // 10:02x}" for i in (1, 3, 5)
    )


def _container(old: str) -> str:
    stroke = _get(old, "strokeColor")
    stroke = stroke if stroke and stroke != "none" else CARD_STROKE
    return (
        "rounded=1;absoluteArcSize=1;arcSize=28;whiteSpace=wrap;html=1;container=1;"
        f"fillColor={_tint(stroke, 0.08)};strokeColor={stroke};strokeWidth=1.5;"
        f"fontFamily=Helvetica;fontColor={_shade(stroke)};fontSize=12;fontStyle=1;"
        # dot leaves 24px above the first child; the title fits in it.
        "verticalAlign=top;align=left;spacing=4;spacingLeft=14;spacingTop=0"
    )


def _card(old: str) -> str:
    """A rounded card with the official icon, unaltered, on the left."""
    image = _get(old, "image")
    return (
        "label;rounded=1;arcSize=14;whiteSpace=wrap;html=1;"
        f"image={image};imageWidth={ICON};imageHeight={ICON};"
        "imageAlign=left;imageVerticalAlign=middle;spacingLeft=58;spacingRight=8;"
        f"align=left;verticalAlign=middle;fillColor=#ffffff;strokeColor={CARD_STROKE};"
        f"strokeWidth=1.5;{FONT};fontSize=12;fontStyle=0"
    )


def _shape(old: str) -> str:
    shape = KEEP_SHAPE.search(old)
    fill = _get(old, "fillColor") or "#ffffff"
    stroke = _get(old, "strokeColor") or CARD_STROKE
    name = shape.group(0) if shape else ""
    base = (f"shape={name};" if name else "rounded=1;arcSize=14;") + (
        "whiteSpace=wrap;html=1;"
    )
    if name.startswith("cylinder"):
        base += "boundedLbl=1;size=10;"
    if name == "hexagon":
        base += "perimeter=hexagonPerimeter2;"
    if name == "umlActor":
        base += "verticalLabelPosition=bottom;verticalAlign=top;"
    dashed = "dashed=1;dashPattern=6 4;" if _get(old, "dashed") == "1" else ""
    return (
        f"{base}{dashed}fillColor={fill};strokeColor={stroke};strokeWidth=1.5;"
        f"{FONT};fontSize=12"
    )


def _edge(old: str, kind: str | None) -> str:
    dashed = "dashed=1;dashPattern=6 4;" if kind == "async" else ""
    return (
        "html=1;rounded=1;curved=1;endArrow=blockThin;endFill=1;endSize=8;"
        f"{dashed}strokeColor={EDGE_INK};strokeWidth=1.5;"
        f"fontFamily=Helvetica;fontColor={EDGE_INK};fontSize=10;"
        "labelBackgroundColor=#ffffff"
    )
