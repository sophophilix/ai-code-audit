from __future__ import annotations

from pathlib import Path

import pytest

from audit_kit import cli


def test_detect_succeeds_and_writes_outputs(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["detect", str(repo), "--commit", "abc"]) == cli.EXIT_OK
    assert "profiles: node-express" in capsys.readouterr().out
    assert (repo / ".audit/detected.md").is_file()


def test_detect_warns_about_unusable_input_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "package.json").write_text("{bad")
    assert cli.main(["detect", str(tmp_path)]) == cli.EXIT_OK
    assert "warning: package.json: invalid JSON" in capsys.readouterr().err


def test_refused_operations_exit_2_with_a_message(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["seed", str(repo), str(repo / "key.md")]) == cli.EXIT_INVALID
    assert (
        "error: the key file must be outside the workspace" in capsys.readouterr().err
    )


def test_a_missing_workspace_exits_2(tmp_path: Path) -> None:
    assert cli.main(["verify", str(tmp_path / "missing")]) == cli.EXIT_INVALID


def test_verify_exits_1_when_checks_fail(tmp_path: Path) -> None:
    assert cli.main(["verify", str(tmp_path)]) == cli.EXIT_CHECKS_FAILED


def test_unexpected_errors_exit_3(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(cli, "detect", boom)
    assert cli.main(["detect", str(repo)]) == cli.EXIT_INTERNAL
    assert "internal error: RuntimeError: unexpected" in capsys.readouterr().err


def test_seed_reports_the_key_path(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["seed", str(repo), str(tmp_path / "k.md")]) == cli.EXIT_OK
    assert "planted 19 issues" in capsys.readouterr().out
