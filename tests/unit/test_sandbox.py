"""The Docker sandbox (ADR 0005), with Docker replaced by a recording fake.

These prove the kit asks Docker for the right isolation; they don't prove Docker
enforces it, which needs a real run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from audit_kit import sandbox as sb
from audit_kit.errors import AuditKitError
from audit_kit.runner import CommandError, Result
from audit_kit.workspace import Workspace


@pytest.fixture(autouse=True)
def copy_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sb, "COPY_PARENT", tmp_path / "copies")


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    (root / ".audit/work/files/u042").mkdir(parents=True)
    (root / ".audit-kit").mkdir()
    (root / "lib").mkdir()
    (root / "package.json").write_text('{"engines": {"node": ">=22.18"}}')
    (root / "package-lock.json").write_text("{}")
    (root / "lib/a.js").write_text("module.exports = 1;\n")
    (root / ".audit-kit/VERSION").write_text("0.15.0\n")
    (root / ".audit/work/files/u042/prove.test.js").write_text("test();\n")
    (root / ".audit/work/files/u042/try-nan.js").write_text(
        "console.log(isNaN('x'));\n"
    )
    return Workspace(root)


def test_every_container_is_locked_down_and_only_install_has_a_network(
    ws: Workspace, tmp_path: Path
) -> None:
    jobs = sb.plan("structure", ws, None)
    assert [j.name for j in jobs] == ["install", "knip", "depcruise"]
    for job in jobs:
        args = sb.docker_args("img", job, tmp_path / "copy", "audit-kit-t")
        for flag in ("--read-only", "--cap-drop", "no-new-privileges", "--pids-limit"):
            assert flag in args
        user = args[args.index("--user") + 1]
        assert user.split(":")[0] != "0"  # never root, even when the kit is
        assert args[args.index("--network") + 1] == (
            "bridge" if job.name == "install" else "none"
        )
        mount = args[args.index("--mount") + 1]
        # Docker accepts `readonly`, not `ro` or `rw`.
        assert mount.endswith(",readonly") != (job.name == "install")
        assert "-e" not in args and "--env" not in args
        assert not any(str(Path.home()) in a for a in args)


def test_try_mounts_only_the_snippet(ws: Workspace) -> None:
    (job,) = sb.plan("try", ws, ".audit/work/files/u042/try-nan.js")
    args = sb.docker_args("img", job, Path("/copy"), "audit-kit-t")
    assert "/copy" not in " ".join(args)
    assert args[-5:] == [
        "timeout",
        "--signal=KILL",
        "1500",
        "node",
        "/snippet/try-nan.js",
    ]


def test_agent_files_must_be_under_the_work_folder_and_small(ws: Workspace) -> None:
    with pytest.raises(AuditKitError, match=r"under \.audit/work/"):
        sb.plan("prove", ws, "lib/a.js")
    with pytest.raises(AuditKitError, match=r"under \.audit/work/"):
        sb.plan("try", ws, ".audit/work/../../lib/a.js")
    (ws.root / ".audit/work/files/u042/try-long.js").write_text("x();\n" * 21)
    with pytest.raises(AuditKitError, match="at most 20"):
        sb.plan("try", ws, ".audit/work/files/u042/try-long.js")
    prove = sb.plan("prove", ws, ".audit/work/files/u042/prove.test.js")
    assert prove[-1].output == "prove-u042.txt"


def test_no_lockfile_means_no_install(ws: Workspace) -> None:
    (ws.root / "package-lock.json").unlink()
    assert [j.name for j in sb.plan("tests", ws, None)] == ["tests"]


def test_node_version_comes_from_the_target(ws: Workspace) -> None:
    assert sb.node_major(ws) == "22"
    (ws.root / ".nvmrc").write_text("v24.11.0\n")
    assert sb.node_major(ws) == "24"


def test_the_copy_leaves_out_kit_folders_and_dependencies(
    ws: Workspace, tmp_path: Path
) -> None:
    (ws.root / "node_modules/x").mkdir(parents=True)
    (ws.root / "node_modules/x/i.js").write_text("evil();\n")
    dest = tmp_path / "copy"
    assert sb.copy_target(ws, dest) == 3
    assert not (dest / ".audit").exists() and not (dest / "node_modules").exists()


def test_a_name_with_mount_option_characters_is_refused(ws: Workspace) -> None:
    # Review finding F1: Docker's --mount is comma-separated key=value pairs.
    evil = ".audit/work/files/u042/a,bind-propagation=shared.js"
    (ws.root / evil).write_text("x();\n")
    with pytest.raises(AuditKitError, match="use only letters"):
        sb.plan("try", ws, evil)
    job = sb.Job("j", ("node",), "j.txt", extra_mounts=((Path("/a,b=c.js"), "/s.js"),))
    with pytest.raises(AuditKitError, match="refused mount path"):
        sb.docker_args("img", job, None, "audit-kit-t")


def fake_docker(calls: list[list[str]], *, hang: bool = False) -> Any:
    def fake_run(args: list[Any], **_: Any) -> Result:
        argv = [str(a) for a in args]
        calls.append(argv)
        if argv[:3] == ["docker", "image", "inspect"]:
            return Result(0, b"sha256:abc\n", b"")
        if hang and argv[:2] == ["docker", "run"]:
            raise CommandError("docker timed out after 1800s")
        return Result(1 if "test" in argv else 0, b"1 failing\n", b"")

    return fake_run


def test_a_denied_policy_runs_nothing(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(sb, "run", fake_docker(calls))
    with pytest.raises(AuditKitError, match="sandbox denied"):
        sb.run_jobs(ws, "0.15.0", Path("/kit"), "tests")
    assert calls == []


def test_an_allowed_job_writes_its_output_and_log(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws.write_text(".audit/policy.yaml", "version: 1\nsandbox: allow\n")
    calls: list[list[str]] = []
    monkeypatch.setattr(sb, "run", fake_docker(calls))
    sb.run_jobs(ws, "0.15.0", Path("/kit"), "tests")
    assert calls[0][:3] == ["docker", "build", "--quiet"]
    assert "NODE_MAJOR=22" in calls[0]
    out = ws.read_text(".audit/scans/dynamic/tests.txt")
    assert out.startswith("exit: 1") and "1 failing" in out
    log = ws.read_text(".audit/scans/dynamic/jobs.log").splitlines()
    assert [line.split("\t")[2:] for line in log] == [
        ["install", "sha256:abc", "exit 0"],
        ["tests", "sha256:abc", "exit 1"],
    ]


def test_a_timed_out_container_is_removed_by_name(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding F2: killing the client leaves the container running.
    ws.write_text(".audit/policy.yaml", "version: 1\nsandbox: allow\n")
    (ws.root / "package-lock.json").unlink()
    calls: list[list[str]] = []
    monkeypatch.setattr(sb, "run", fake_docker(calls, hang=True))
    sb.run_jobs(ws, "0.15.0", Path("/kit"), "tests")
    started = next(c for c in calls if c[:2] == ["docker", "run"])
    name = started[started.index("--name") + 1]
    assert ["docker", "rm", "--force", name] in calls
    assert ws.read_text(".audit/scans/dynamic/tests.txt").startswith("not run:")


def test_tests_get_a_writable_copy_and_structure_a_read_only_one(ws: Workspace) -> None:
    # Test runners write caches next to the code; the copy is thrown away.
    (tests,) = sb.plan("tests", ws, None)[1:]
    assert tests.target_writable
    assert not any(j.target_writable for j in sb.plan("structure", ws, None)[1:])


def test_the_container_runs_as_the_host_user_or_a_non_root_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "getuid", lambda: 501)
    monkeypatch.setattr(os, "getgid", lambda: 20)
    assert sb._user() == "501:20"
    monkeypatch.setattr(os, "getuid", lambda: 0)
    assert sb._user() == sb.FALLBACK_USER


def test_a_job_killed_by_its_own_timeout_says_so(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws.write_text(".audit/policy.yaml", "version: 1\nsandbox: allow\n")
    (ws.root / "package-lock.json").unlink()

    def fake_run(args: list[Any], **_: Any) -> Result:
        if [str(a) for a in args][:3] == ["docker", "image", "inspect"]:
            return Result(0, b"sha256:abc\n", b"")
        return Result(137, b"", b"Killed")

    monkeypatch.setattr(sb, "run", fake_run)
    sb.run_jobs(ws, "0.15.0", Path("/kit"), "tests")
    assert "(timed out: stopped after 1500 s)" in ws.read_text(
        ".audit/scans/dynamic/tests.txt"
    )


def test_agent_files_are_mounted_from_the_copy_folder_not_the_workspace(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Found on a real colima run: the VM can't see a workspace outside home.
    ws.write_text(".audit/policy.yaml", "version: 1\nsandbox: allow\n")
    calls: list[list[str]] = []
    monkeypatch.setattr(sb, "run", fake_docker(calls))
    sb.run_jobs(ws, "0.15.0", Path("/kit"), "try", ".audit/work/files/u042/try-nan.js")
    started = next(c for c in calls if c[:2] == ["docker", "run"])
    mounts = [started[i + 1] for i, a in enumerate(started) if a == "--mount"]
    assert all(str(tmp_path / "copies") in m for m in mounts)
    assert not any(str(ws.root) in m for m in mounts)
