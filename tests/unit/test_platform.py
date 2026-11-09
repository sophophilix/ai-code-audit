"""Runner, settings, state, projects, archive extraction and machine commands."""

from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import pytest

from audit_kit import machine
from audit_kit.errors import AuditKitError
from audit_kit.projects import create_project, list_lines, project_dir
from audit_kit.runner import CommandError, have, run
from audit_kit.settings import KitSettings
from audit_kit.state import State
from audit_kit.workspace import Workspace
from audit_kit.workspaces import extract_archive

KIT = Path(__file__).resolve().parents[2]


def test_run_captures_output() -> None:
    assert run([sys.executable, "-c", "print('hi')"]).text == "hi"


def test_run_raises_on_failure_with_the_last_error_line() -> None:
    with pytest.raises(CommandError, match=r"failed \(exit 3\) boom"):
        run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])


def test_run_can_return_a_failure_without_raising() -> None:
    assert run([sys.executable, "-c", "raise SystemExit(4)"], check=False).code == 4


def test_run_reports_a_missing_program() -> None:
    with pytest.raises(CommandError, match="not found"):
        run(["definitely-not-a-real-program-xyz"])


def test_run_stops_a_program_that_exceeds_its_timeout() -> None:
    with pytest.raises(CommandError, match="timed out"):
        run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)


def test_have_checks_absolute_paths_for_the_execute_bit(tmp_path: Path) -> None:
    script = tmp_path / "tool"
    script.write_text("#!/bin/sh\n")
    assert not have(script)
    script.chmod(0o755)
    assert have(script)


def test_settings_follow_the_environment(tmp_path: Path) -> None:
    s = KitSettings.load(
        {
            "AUDIT_PROJECTS_DIR": str(tmp_path / "p"),
            "AUDIT_WORKSPACES_DIR": str(tmp_path / "w"),
        }
    )
    assert s.kit_home == KIT
    assert s.version == (KIT / "VERSION").read_text().strip()
    assert s.projects_dir == tmp_path / "p"
    assert s.workspaces_dir == tmp_path / "w"


def test_settings_need_a_kit_folder(tmp_path: Path) -> None:
    with pytest.raises(AuditKitError, match="kit folder not found"):
        KitSettings.load({"AUDIT_KIT_HOME": str(tmp_path)})


def test_state_keeps_order_and_persists(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    state = State(ws)
    state.set("project", "demo")
    state.set("mode", "eval")
    state.set("project", "other")
    assert (
        tmp_path / ".audit/.workspace"
    ).read_text() == "project: other\nmode: eval\n"
    assert State(ws).get("mode") == "eval"


def test_project_names_must_be_one_safe_segment(tmp_path: Path) -> None:
    with pytest.raises(AuditKitError, match="invalid project name"):
        project_dir(tmp_path, "../escape")


def test_project_creation_is_idempotent_and_private(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = create_project(KIT, tmp_path / "projects", "demo")
    (folder / "project.md").write_text("mine\n")
    create_project(KIT, tmp_path / "projects", "demo")
    assert (folder / "project.md").read_text() == "mine\n"
    assert "skip  project.md exists" in capsys.readouterr().out
    assert (folder / "keys").stat().st_mode & 0o777 == 0o700


def test_list_lines_skips_comments_and_blanks(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("# comment\n\nHANDOFF.md\n  docs/x.md  \n")
    assert list_lines(f) == ["HANDOFF.md", "docs/x.md"]
    assert list_lines(tmp_path / "missing.txt") == []


def _tar(name: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        data = b"x"
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_archive_entries_cannot_escape_the_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "ws"
    dest.mkdir()
    with pytest.raises(AuditKitError, match="unsafe entry"):
        extract_archive(_tar("../evil.txt"), dest)
    assert not (tmp_path / "evil.txt").exists()
    extract_archive(_tar("ok/file.txt"), dest)
    assert (dest / "ok/file.txt").read_bytes() == b"x"


def test_tools_dry_run_without_homebrew_or_npm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(machine, "have", lambda _tool: False)
    s = KitSettings.load(
        {
            "DRAWIO_SKILL_DIR": str(tmp_path / "none"),
            "JSCPD_BIN": str(tmp_path / "none/a/b/jscpd"),
            "ESLINT_BIN": str(tmp_path / "none/a/b/eslint"),
            "TSC_BIN": str(tmp_path / "none/a/b/tsc"),
        }
    )
    machine.tools(s, dry_run=True)
    captured = capsys.readouterr()
    assert "Homebrew not found" in captured.err
    assert (
        "jscpd, eslint, eslint-plugin-regexp, typescript, @types/node need npm"
        in captured.err
    )
    assert "Dry run: nothing installed." in captured.out


def test_doctor_reports_without_failing(capsys: pytest.CaptureFixture[str]) -> None:
    machine.doctor(KitSettings.load({}))
    assert "agent-audit-kit" in capsys.readouterr().out
