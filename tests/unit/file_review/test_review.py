"""ADR 0007 D3, D4, D7: kit review runs, repairs, stops, keeps and reuses."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audit_kit import brief, file_record, ledger, review
from audit_kit.errors import AuditKitError
from audit_kit.headless import Reply
from audit_kit.settings import KitSettings
from audit_kit.units import Unit
from audit_kit.verification import Status, check
from audit_kit.workspace import Workspace

Ready = Callable[..., list[Unit]]
Output = Callable[..., dict[str, Any]]
MakeReply = Callable[..., Reply]


def good(u: Unit, make_output: Output, make_reply: MakeReply, ws: Workspace) -> Reply:
    """Return a reply that passes every check, answering the brief's check list."""
    meta = brief.read_meta(ws, u.id)
    assert meta is not None
    return make_reply(json.dumps(make_output(u, meta.check_ids)))


def test_a_good_reply_writes_the_record(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    left = review.review(
        settings,
        str(ws.root),
        only=[u.id],
        runner=fake_runner(good(u, make_output, make_reply, ws)),
    )
    assert left == 0
    assert ws.is_file(u.record) and ws.is_file(u.record.removesuffix(".md") + ".json")


def test_the_pass_gets_the_file_reviewer_as_its_system_prompt(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    runner = fake_runner(good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    assert runner.systems[0].startswith("You are one pass of an independent code audit")
    assert "name: file-reviewer" not in runner.systems[0]


def test_a_failed_check_goes_back_once_after_the_brief(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    bad = make_reply(json.dumps(make_output(u, excerpt="exec(folder)")))
    runner = fake_runner(bad, good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    assert runner.prompts[1].startswith(runner.prompts[0])
    assert "OUT-F7" in runner.prompts[1].removeprefix(runner.prompts[0])


def test_every_attempt_is_in_the_ledger(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    bad = make_reply(json.dumps(make_output(u, excerpt="exec(folder)")))
    review.review(
        settings,
        str(ws.root),
        only=[u.id],
        runner=fake_runner(bad, good(u, make_output, make_reply, ws)),
    )
    assert [(r.attempt, r.outcome) for r in ledger.read(ws)] == [
        (1, "checks failed"),
        (2, "ok"),
    ]


def test_three_failures_leave_no_record_and_keep_the_problems(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    runner = fake_runner(
        make_reply("not json"), make_reply("still not json"), make_reply("{}")
    )
    assert review.review(settings, str(ws.root), only=[u.id], runner=runner) == 1
    assert not ws.is_file(u.record)
    assert ledger.read_status(ws)[u.id].status == "gate-failed"
    assert "schema" in ws.read_text(f".audit/work/files/{u.id}/problems.txt")


def test_a_crashed_pass_is_run_again_with_the_same_brief(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    crash = make_reply("", ok=False, error="exit 1: boom")
    runner = fake_runner(crash, good(u, make_output, make_reply, ws))
    left = review.review(
        settings, str(ws.root), only=[u.id], runner=runner, pause=lambda _: None
    )
    assert left == 0
    assert runner.prompts[0] == runner.prompts[1]


def test_a_usage_limit_stops_the_run_and_marks_the_unit_interrupted(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    found = ready()
    limit = make_reply("", ok=False, error="Claude usage limit reached; resets 5pm")
    left = review.review(
        settings,
        str(ws.root),
        only=[found[0].id, found[1].id],
        runner=fake_runner(limit),
    )
    status = ledger.read_status(ws)
    assert left == 2
    assert (status[found[0].id].status, status[found[1].id].status) == (
        "interrupted",
        "pending",
    )


def test_after_a_limit_a_new_login_carries_on_from_the_unit_that_stopped(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    found = ready()
    u = next(x for x in found if x.path == "lib/export.js")
    other = next(x for x in found if x.path != "lib/export.js")
    limit = make_reply("", ok=False, error="You've hit your session limit")
    given = str(ws.root)
    assert review.review(settings, given, only=[u.id], runner=fake_runner(limit)) == 1
    assert ledger.read_status(ws)[u.id].status == "interrupted"
    # The next account's run reviews the unit that stopped.
    login = fake_runner(good(u, make_output, make_reply, ws))
    assert review.review(settings, given, only=[u.id], runner=login) == 0
    # And a later limit costs only the unit it stopped: the finished one is kept.
    again = fake_runner(limit)
    assert review.review(settings, given, only=[u.id, other.id], runner=again) == 1
    assert len(again.prompts) == 1 and other.id in again.prompts[0]
    assert ledger.read_status(ws)[other.id].status == "interrupted"


def test_an_unchanged_unit_keeps_its_record_without_a_pass(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    review.review(
        settings,
        str(ws.root),
        only=[u.id],
        runner=fake_runner(good(u, make_output, make_reply, ws)),
    )
    runner = fake_runner()
    assert review.review(settings, str(ws.root), only=[u.id], runner=runner) == 0
    assert runner.prompts == []


def test_the_pilot_reviews_only_its_units(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready(mode="pilot")[0]
    runner = fake_runner(good(u, make_output, make_reply, ws))
    assert review.review(settings, str(ws.root), runner=runner) == 0
    assert ws.read_text(".audit/work/files/pilot.txt") == "u001\n"
    assert runner.models == ["claude-sonnet-5-5"]


def test_a_brief_for_changed_code_is_refused(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    code = (ws.root / "lib/export.js").read_text()
    (ws.root / "lib/export.js").write_text(code.replace('"ok"', '"done"'))
    with pytest.raises(AuditKitError, match="out of date"):
        review.review(settings, str(ws.root), only=[u.id], runner=fake_runner())


def test_an_unvalidated_config_is_refused(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    fake_runner: Any,
) -> None:
    ready()
    ws.write_text(".audit/validation.md", "result: fail\n")
    with pytest.raises(AuditKitError, match="kit validate"):
        review.review(settings, str(ws.root), runner=fake_runner())


def test_file_review_off_needs_named_units(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    fake_runner: Any,
) -> None:
    ready(mode="off")
    with pytest.raises(AuditKitError, match="mode is off"):
        review.review(settings, str(ws.root), runner=fake_runner())


def later_audit(ws: Workspace, tmp_path: Path) -> Path:
    later = tmp_path / "later"
    shutil.copytree(ws.root, later)
    shutil.rmtree(later / ".audit/files")
    for name in ("passes.jsonl", "status.tsv"):
        (later / ".audit/work/files" / name).unlink()
    (later / ".audit/.workspace").write_text(
        "project: demo\nmode: eval\nsnapshot: def456\n"
    )
    return later


def test_an_unchanged_unit_reuses_the_last_audits_record(
    ws: Workspace,
    tmp_path: Path,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    review.review(
        settings,
        str(ws.root),
        only=[u.id],
        runner=fake_runner(good(u, make_output, make_reply, ws)),
    )
    later = later_audit(ws, tmp_path)
    left = review.review(
        settings, str(later), only=[u.id], reuse_from=str(ws.root), runner=fake_runner()
    )
    md = (later / u.record).read_text()
    assert left == 0
    assert "commit: def456" in md and "reused_from: abc123 (ws)" in md


def test_a_kit_written_record_passes_kit_verify(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    review.review(
        settings,
        str(ws.root),
        only=[u.id],
        runner=fake_runner(good(u, make_output, make_reply, ws)),
    )
    failed = [
        r
        for r in check(ws).results
        if r.status is Status.FAIL
        and r.check.startswith(("OUT-F", "OUT-U1", "OUT-U2", "OUT-U4", "OUT-U5"))
    ]
    assert failed == []


def test_a_brief_that_drops_a_counted_row_fails_u5(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    review.review(
        settings,
        str(ws.root),
        only=[u.id],
        runner=fake_runner(good(u, make_output, make_reply, ws)),
    )
    rel = f".audit/work/files/{u.id}/brief.md"
    ws.write_text(rel, ws.read_text(rel).replace("- 6: no-undef", "dropped", 1))
    assert any(
        r.check == "OUT-U5" and r.status is Status.FAIL for r in check(ws).results
    )


def test_parallel_passes_finish_every_unit_and_keep_the_ledger_whole(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
) -> None:
    found = ready(parallel=2)
    by_id = {u.id: u for u in found}

    def runner(claude: Path, model: str, system: str, prompt: str) -> Reply:
        unit = by_id[prompt.split("- Unit: ", 1)[1].split("\n", 1)[0]]
        if unit.path == "lib/export.js":
            return good(unit, make_output, make_reply, ws)
        meta = brief.read_meta(ws, unit.id)
        assert meta is not None
        empty: dict[str, list[object]] = {
            key: [] for key in ("facts", "comments", "flows", "functions")
        }
        checks = [{"check": c, "result": "not found"} for c in meta.check_ids]
        body = {
            "unit": unit.id,
            "checks": checks,
            **empty,
            "findings": [],
            "edges": [],
            "limitations": [],
        }
        return make_reply(json.dumps(body))

    assert review.review(settings, str(ws.root), runner=runner) == 0
    assert {r.unit for r in ledger.read(ws)} == set(by_id)
    assert {s.status for s in ledger.read_status(ws).values()} == {"done"}


def test_new_scan_rows_mean_a_fresh_pass(
    ws: Workspace,
    kit_home: Path,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    first = fake_runner(good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=first)
    ws.write_text(
        ".audit/scans/duplication.json",
        '{"duplicates": [{"lines": 2, '
        '"firstFile": {"name": "lib/export.js", "start": 4, "end": 5}, '
        '"secondFile": {"name": "lib/other.js", "start": 1, "end": 1}}]}',
    )
    review.prepare(ws, [u], kit_home, settings.version)
    again = fake_runner(good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=again)
    assert len(again.prompts) == 1


def test_a_reused_record_takes_this_audits_gates(
    ws: Workspace,
    tmp_path: Path,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    runner = fake_runner(good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    later = later_audit(ws, tmp_path)
    review.review(
        settings, str(later), only=[u.id], reuse_from=str(ws.root), runner=fake_runner()
    )
    record = file_record.read(Workspace(later), u)
    meta = brief.read_meta(Workspace(later), u.id)
    assert record is not None and meta is not None
    assert (record.gates, record.scan_rows) == (meta.gates, meta.scan_rows)


def test_a_reuse_whose_excerpts_fail_falls_back_to_a_pass(
    ws: Workspace,
    tmp_path: Path,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    runner = fake_runner(good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    js = ws.root / file_record.record_paths(u)[1]
    js.write_text(js.read_text().replace("const folder = req.query.folder;", "made up"))
    later = later_audit(ws, tmp_path)
    fresh = fake_runner(good(u, make_output, make_reply, ws))
    review.review(
        settings, str(later), only=[u.id], reuse_from=str(ws.root), runner=fresh
    )
    assert len(fresh.prompts) == 1


def test_an_unreadable_record_is_reviewed_again(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    ws.write_text(file_record.record_paths(u)[1], "{not json")
    runner = fake_runner(good(u, make_output, make_reply, ws))
    assert review.review(settings, str(ws.root), only=[u.id], runner=runner) == 0
    assert len(runner.prompts) == 1


def test_a_failed_pass_waits_before_it_runs_again(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    crash = make_reply("", ok=False, error="exit 1: boom")
    waits: list[float] = []
    runner = fake_runner(crash, good(u, make_output, make_reply, ws))
    review.review(
        settings, str(ws.root), only=[u.id], runner=runner, pause=waits.append
    )
    assert len(waits) == 1
    assert review.RETRY_SECONDS * 0.5 <= waits[0] <= review.RETRY_SECONDS * 1.5


def test_kit_verify_catches_a_high_finding_marked_unverified(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    runner = fake_runner(good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    md = ws.read_text(u.record).replace("- Severity: medium", "- Severity: high")
    ws.write_text(u.record, md)
    assert any(
        r.check == "OUT-U4" and r.status is Status.FAIL and "unverified" in r.detail
        for r in check(ws).results
    )


def test_a_repair_shows_the_lines_the_excerpt_should_copy(
    ws: Workspace,
    settings: KitSettings,
    ready: Ready,
    make_output: Output,
    make_reply: MakeReply,
    fake_runner: Any,
) -> None:
    u = ready()[0]
    bad = make_reply(json.dumps(make_output(u, excerpt="exec(folder)")))
    runner = fake_runner(bad, good(u, make_output, make_reply, ws))
    review.review(settings, str(ws.root), only=[u.id], runner=runner)
    repair = runner.prompts[1].removeprefix(runner.prompts[0])
    assert "lines 6-6 read exactly: '  exec(`zip -r out.zip ${folder}`);'" in repair
