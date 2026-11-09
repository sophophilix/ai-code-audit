"""ADR 0007 D6, D8: the findings store, read-only queries, and cost."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from audit_kit import brief, ledger, review, store
from audit_kit.errors import AuditKitError
from audit_kit.headless import Reply
from audit_kit.settings import KitSettings
from audit_kit.units import Unit
from audit_kit.workspace import Workspace

TRACE = (
    "---\nagent: tracer\n---\n"
    "## Edges resolved\n- EDGE-u001-001: nothing validates folder\n"
    "## Findings\n### TRACE-t01-001 Middleware order\n"
    "- Key: X-order:lib/export.js\n- Severity: Medium\n- Confidence: high\n"
    "- Location: lib/export.js:4\n"
)


@pytest.fixture
def stored(
    ws: Workspace,
    settings: KitSettings,
    ready: Callable[..., list[Unit]],
    make_output: Callable[..., dict[str, Any]],
    make_reply: Callable[..., Reply],
    fake_runner: Any,
) -> dict[str, int]:
    """Provide a workspace with one reviewed unit and one trace, stored."""
    u = ready()[0]
    meta = brief.read_meta(ws, u.id)
    assert meta is not None
    runner = fake_runner(make_reply(json.dumps(make_output(u, meta.check_ids))))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    ws.write_text(".audit/traces/get-export.md", TRACE)
    return store.build(ws)


@pytest.mark.parametrize(
    ("table", "count"),
    [
        ("findings", 2),
        ("edges", 1),
        ("facts", 1),
        ("flows", 1),
        ("gates", 6),
        ("passes", 1),
    ],
)
def test_the_store_has_a_row_per_item(
    stored: dict[str, int], table: str, count: int
) -> None:
    assert stored[table] == count


def test_a_query_returns_typed_columns(ws: Workspace, stored: dict[str, int]) -> None:
    result = store.query(ws, "SELECT id, severity, edges FROM findings ORDER BY id")
    assert result.rows[0] == ("FILE-u001-001", "medium", ["EDGE-u001-001"])


def test_an_edge_records_the_trace_that_resolved_it(
    ws: Workspace, stored: dict[str, int]
) -> None:
    assert store.query(ws, "SELECT resolved_by FROM edges").rows == [("get-export",)]


def test_results_render_as_csv(ws: Workspace, stored: dict[str, int]) -> None:
    text = store.render(store.query(ws, "SELECT id FROM edges"), "csv")
    assert text.splitlines() == ["id", "EDGE-u001-001"]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO units (unit) VALUES ('x')",
        "COPY findings TO 'out.csv'",
        "SELECT * FROM read_csv('/etc/hosts')",
        "SET enable_external_access = true",
        "ATTACH 'other.duckdb'",
        "INSTALL httpfs",
    ],
)
def test_a_query_can_only_read_the_store(
    ws: Workspace, stored: dict[str, int], sql: str
) -> None:
    with pytest.raises(AuditKitError, match="refused or failed"):
        store.query(ws, sql)


def test_a_query_without_a_store_is_refused(ws: Workspace) -> None:
    with pytest.raises(AuditKitError, match="run kit store"):
        store.query(ws, "SELECT 1")


def test_the_store_is_kept_out_of_checkpoints(
    ws: Workspace, settings: KitSettings, ready: Callable[..., list[Unit]]
) -> None:
    ready()
    store.store(settings, str(ws.root))
    assert "findings.duckdb" in ws.read_text(store.IGNORE).splitlines()


def test_cost_totals_by_stage_and_model(ws: Workspace, stored: dict[str, int]) -> None:
    table = store.cost_table(ledger.read(ws))
    assert (
        "| 1a | claude-sonnet-5-5 | 1 | 1 | 1 | 10 | 20 | 1,000 | 0 | 0.05 | 12 |"
        in table
    )


def test_cost_counts_a_unit_once_and_not_a_refused_pass(
    ws: Workspace, stored: dict[str, int]
) -> None:
    row = ledger.read(ws)[0]
    refused = row.model_copy(
        update={
            "unit": "u999",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
    )
    assert "for 1 units" in store.cost_table([row, row, refused])


def test_an_unpriced_pass_is_counted_as_unpriced(
    ws: Workspace, stored: dict[str, int]
) -> None:
    row = ledger.read(ws)[0].model_copy(update={"cost_usd": None})
    assert "0.00 (1 unpriced)" in store.cost_table([row])


def test_cost_with_no_passes_is_refused(
    ws: Workspace,
    settings: KitSettings,
    ready: Callable[..., list[Unit]],
) -> None:
    ready()
    with pytest.raises(AuditKitError, match="no passes"):
        store.cost(settings, str(ws.root))


def test_units_carry_their_summary(ws: Workspace, stored: dict[str, int]) -> None:
    got = store.query(
        ws, "SELECT medium, unverified, open_edges FROM units WHERE unit = 'u001'"
    )
    assert got.rows == [(1, 1, 1)]


def test_findings_carry_their_verification(
    ws: Workspace, stored: dict[str, int]
) -> None:
    got = store.query(ws, "SELECT id, verification FROM findings ORDER BY id")
    assert got.rows == [("FILE-u001-001", "unverified"), ("TRACE-t01-001", None)]


def test_checks_are_stored_per_unit(ws: Workspace, stored: dict[str, int]) -> None:
    got = store.query(
        ws, "SELECT result, count(*) FROM checks WHERE unit = 'u001' GROUP BY result"
    )
    results = {str(row[0]): int(str(row[1])) for row in got.rows}
    assert results.get("found") == 1 and results.get("not found", 0) > 10
