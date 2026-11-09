"""The house style: grouping before the build and restyling after it."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pytest

from audit_kit.diagram_style import CARD_HEIGHT, CARD_WIDTH, prepare, restyle

ICON = "img/lib/azure2/app_services/App_Services.svg"
BUILT = f"""<mxfile><diagram id="system" name="System"><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="group_0" value="Azure" vertex="1" parent="1"
  style="rounded=0;fillColor=none;strokeColor=#82b366;dashed=1;fontStyle=2;"/>
<mxCell id="app" value="App" vertex="1" parent="group_0"
  style="image;aspect=fixed;html=1;image={ICON};"><mxGeometry x="24" y="24" width="220" height="72" as="geometry"/></mxCell>
<mxCell id="db" value="DB" vertex="1" parent="group_0"
  style="shape=cylinder3;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;"/>
<UserObject id="crm" label="CRM" link="data:page/id,security"><mxCell vertex="1" parent="1"
  style="rounded=1;dashed=1;fillColor=#f5f5f5;strokeColor=#666666;"/></UserObject>
<mxCell id="e0" edge="1" parent="1" source="app" target="db" data-kind="sync" style="endArrow=classic;rounded=0;">
  <mxGeometry relative="1" as="geometry"><Array as="points"><mxPoint x="10" y="20"/></Array></mxGeometry></mxCell>
<mxCell id="e1" edge="1" parent="1" source="app" target="crm" data-kind="async" style="endArrow=classic;"/>
</root></mxGraphModel></diagram></mxfile>"""


def styles(xml: str) -> dict[str, str]:
    root = ET.fromstring(xml)  # noqa: S314  a fixture written above
    out = {}
    for holder in root.iter():
        cell = holder if holder.tag == "mxCell" else holder.find("mxCell")
        if holder.tag in ("mxCell", "UserObject") and cell is not None:
            out[holder.get("id") or cell.get("id") or ""] = cell.get("style") or ""
    return out


def test_prepare_groups_by_trust_boundary_without_changing_the_input() -> None:
    ir: dict[str, Any] = {
        "nodes": [
            {"id": "a", "properties": {"trust_boundary": "council-network"}},
            {"id": "b", "group": "Azure/Data", "width": 90},
            {"id": "c"},
        ]
    }
    a, b, c = prepare(ir)["nodes"]
    assert a["group"] == "Council Network"
    assert (b["group"], b["width"], b["height"]) == ("Azure/Data", 90, CARD_HEIGHT)
    assert "group" not in c and c["width"] == CARD_WIDTH
    assert "group" not in ir["nodes"][0]


def test_prepare_turns_worded_importance_into_numbers() -> None:
    ir = {
        "nodes": [
            {"id": n, "properties": {"importance": v}}
            for n, v in (("a", "High"), ("b", 2), ("c", "vital"))
        ]
    }
    a, b, c = (n["properties"] for n in prepare(ir)["nodes"])
    assert (a["importance"], b["importance"]) == (3, 2)
    assert "importance" not in c


def test_containers_become_rounded_tinted_zones() -> None:
    zone = styles(restyle(BUILT))["group_0"]
    assert "rounded=1" in zone and "dashed" not in zone
    assert "fillColor=#f5f9f3" in zone and "strokeColor=#82b366" in zone


def test_azure_icons_become_cards_with_the_same_unaltered_image() -> None:
    card = styles(restyle(BUILT))["app"]
    assert card.startswith("label;") and f"image={ICON};" in card
    assert "imageWidth=40;imageHeight=40" in card


def test_meaningful_shapes_and_dashes_are_kept() -> None:
    out = styles(restyle(BUILT))
    assert out["db"].startswith("shape=cylinder3;") and "fillColor=#d5e8d4" in out["db"]
    assert "dashed=1" in out["crm"]  # the UserObject's own mxCell, styled once
    assert out["crm"].count("sketch=1") == 1


def test_edges_are_curved_and_async_ones_dashed() -> None:
    out = styles(restyle(BUILT))
    assert "curved=1" in out["e0"] and "dashed" not in out["e0"]
    assert "dashed=1" in out["e1"]


def test_handdrawn_sketches_everything_and_clean_nothing() -> None:
    assert all(
        "sketch=1" in s
        for k, s in styles(restyle(BUILT)).items()
        if k not in ("0", "1")
    )
    assert not any("sketch" in s for s in styles(restyle(BUILT, "clean")).values())


def test_layout_is_kept() -> None:
    out = restyle(BUILT)
    assert '<mxPoint x="10" y="20"' in out
    assert 'x="24" y="24" width="220" height="72"' in out


def test_unknown_style_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown diagram style"):
        restyle(BUILT, "neon")
