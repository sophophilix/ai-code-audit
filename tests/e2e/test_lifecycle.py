"""End-to-end lifecycle: project → workspace → seed → ready → validate → verify.

Replaces the former bash end-to-end test (architecture exception E2). Commands run
in-process through cli.main with a PATH limited to basic tools, so no real scanner
runs; one test also drives bin/kit itself to prove the wrapper.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from audit_kit import cli

pytestmark = pytest.mark.e2e
KIT = Path(__file__).resolve().parents[2]
BASIC_TOOLS = ("git", "sh", "head", "cat", "uv")
MODELS = """version: 1
providers:
  anthropic: { family: claude, approved_in_project_md: true, region: "Australia East" }
harnesses:
  claude-code: { providers: [anthropic], invoke: "claude" }
agents:
  coordinator:   { model: { provider: anthropic, model: claude-opus-5-5, harness: claude-code } }
  discovery:     { passes: [ { label: a, provider: anthropic, model: claude-sonnet-5-5, harness: claude-code } ] }
  architect:     { passes: [ { label: a, provider: anthropic, model: claude-opus-5-5, harness: claude-code } ] }
  engineer:      { passes: [ { label: a, provider: anthropic, model: claude-sonnet-5-5, harness: claude-code } ] }
  security:      { passes: [ { label: a, provider: anthropic, model: claude-opus-5-5, harness: claude-code } ] }
  accessibility: { passes: [ { label: a, provider: anthropic, model: claude-sonnet-5-5, harness: claude-code } ] }
  verifier:      { passes: [ { label: a, provider: anthropic, model: claude-opus-5-5, harness: claude-code } ] }
  lead-reviewer: { passes: [ { label: a, provider: anthropic, model: claude-opus-5-5, harness: claude-code } ] }
"""
INTAKE = """- Organisation and jurisdiction: NSW local council
- Repository and commit to audit: demo @ main
- Tech lead (passes checkpoints): Tech Lead
- Security owner (gets Critical findings the same day): CISO
- AI use approved by (name, date, scope): ICT manager, 2026-11-01, named staff
- Where the AI provider processes data (region, confirmed by): Australia East, ICT
"""

Kit = Callable[..., tuple[int, str, str]]


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=60
    )
    return done.stdout.strip()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate projects, workspaces and git identity; limit PATH to basic tools."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in BASIC_TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    for key, value in {
        "AUDIT_PROJECTS_DIR": tmp_path / "projects",
        "AUDIT_WORKSPACES_DIR": tmp_path / "ws",
        "DRAWIO_SKILL_DIR": tmp_path / "none",
        "JSCPD_BIN": tmp_path / "none/jscpd",
        "ESLINT_BIN": tmp_path / "none/eslint",
        "TSC_BIN": tmp_path / "none/tsc",
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": bin_dir,
    }.items():
        monkeypatch.setenv(key, str(value))
    return tmp_path


@pytest.fixture
def kit(capsys: pytest.CaptureFixture[str]) -> Kit:
    def call(*argv: str | Path) -> tuple[int, str, str]:
        code = cli.main([str(a) for a in argv])
        out = capsys.readouterr()
        return code, out.out, out.err

    return call


@pytest.fixture
def source(env: Path, make_repo: Callable[..., Path]) -> Path:
    """A committed source repository with an answer sheet and an AI instruction file."""
    repo = make_repo()
    (repo / "HANDOFF.md").write_text("known issues\n")
    (repo / "CLAUDE.md").write_text("# ai rules\n")
    shutil.rmtree(repo / ".audit")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def commits(path: Path) -> int:
    return int(git(path, "rev-list", "--count", "HEAD"))


@pytest.fixture
def project(env: Path, kit: Kit) -> Path:
    assert kit("project", "demo")[0] == 0
    folder = env / "projects/demo"
    text = (folder / "project.md").read_text()
    (folder / "project.md").write_text(
        text.replace("<e.g. NSW local council>", "NSW local council")
    )
    (folder / "eval-remove.txt").write_text("HANDOFF.md\n")
    (folder / "beliefs.md").write_text("- no-ai: the site uses no AI\n")
    return folder


def test_project_command_never_overwrites(project: Path, kit: Kit) -> None:
    code, out, _ = kit("project", "demo")
    assert code == 0
    assert "skip  project.md exists" in out


def test_eval_lifecycle(env: Path, source: Path, project: Path, kit: Kit) -> None:
    ws = env / "ws/demo-eval-2026-01-01"
    args = (
        "workspace",
        "demo",
        "--source",
        source,
        "--ref",
        "main",
        "--mode",
        "eval",
        "--date",
        "2026-01-01",
    )
    assert kit(*args)[0] == 0
    assert not (ws / "HANDOFF.md").exists()
    assert commits(ws) == 1
    assert git(ws, "rev-parse", "--abbrev-ref", "HEAD") == "audit/eval-2026-01-01"
    assert "skip  workspace exists" in kit(*args)[1]

    code, _, err = kit("install", ws)
    assert code == 2
    assert "kit seed" in err

    assert kit("seed", ws)[0] == 0
    key = project / "keys/seeded-demo-eval-2026-01-01.md"
    assert "SQL-INJECTION:lib/wardLookup.js" in key.read_text()
    assert "skip  already seeded" in kit("seed", ws)[1]

    assert kit("install", ws)[0] == 0
    state = (ws / ".audit/.workspace").read_text()
    assert f"source_tree: {git(source, 'rev-parse', 'HEAD^{tree}')}" in state
    delta = (project / "keys/source-delta-demo-eval-2026-01-01.txt").read_text()
    assert "removed\tHANDOFF.md\n" in delta
    assert "seeded A\tlib/wardLookup.js\n" in delta
    assert f"source_delta: {len(delta.splitlines())}" in state
    assert "wardLookup" not in state
    git(ws, "cat-file", "-e", "HEAD~1:lib/wardLookup.js")
    assert int(git(ws, "rev-list", "--count", "HEAD~1")) == 1
    assert "lib/" not in git(ws, "show", "--name-only", "--format=", "HEAD")
    assert (ws / ".audit/quarantine/CLAUDE.md").is_file()
    assert not (ws / "CLAUDE.md").exists()
    assert os.access(ws / ".audit-kit/bin/checkpoint", os.X_OK)
    assert (ws / ".claude/skills/checkpointing/SKILL.md").is_file()
    assert (ws / ".audit/beliefs.md").is_file()
    before = commits(ws)
    assert kit("install", ws)[0] == 0
    assert commits(ws) == before

    assert kit("detect", ws)[0] == 0
    detected = (ws / ".audit/detected.md").read_text()
    assert (
        "node-express, mssql, azure-architecture, web-accessibility, nsw-local-government, ai-governance"
        in detected
    )
    kit("detect", ws)
    assert (ws / ".audit/detected.md").read_text() == detected

    assert kit("check-data", ws)[0] == 0
    (ws / ".env").write_text("SECRET=x\n")
    assert kit("check-data", ws)[0] == 1
    (ws / ".env").unlink()

    assert kit("scan", ws)[0] == 0
    assert (
        "secrets: gitleaks not installed"
        in (ws / ".audit/scans/MISSING.txt").read_text()
    )
    # ADR 0007: a brief per unit and the repository gate table, both stable.
    assert (ws / ".audit/work/files/u001/brief.md").is_file()
    assert "| eslint |" in (ws / ".audit/scans/gates.md").read_text()
    before = commits(ws)
    kit("scan", ws)
    assert commits(ws) == before

    code, out, _ = kit("status", ws)
    assert "mode: eval" in out
    assert "demo-eval-2026-01-01" in kit("list")[1]


def test_real_lifecycle_and_validation(
    env: Path, source: Path, project: Path, kit: Kit
) -> None:
    ws = env / "ws/demo-real-2026-01-02"
    assert (
        kit(
            "workspace",
            "demo",
            "--source",
            source,
            "--ref",
            "main",
            "--mode",
            "real",
            "--date",
            "2026-01-02",
        )[0]
        == 0
    )
    assert (ws / "HANDOFF.md").is_file()
    assert git(ws, "rev-parse", "--abbrev-ref", "HEAD") == "audit/2026-01-02"

    code, out, _ = kit("ready", ws)
    assert code == 0
    assert "NOT ready" in out
    assert "result: fail" in (ws / ".audit/validation.md").read_text()
    before = commits(ws)
    assert kit("ready", ws)[0] == 0
    assert commits(ws) == before
    assert kit("seed", ws)[0] == 2

    (ws / ".audit/models.yaml").write_text(MODELS)
    (ws / ".audit/project.md").write_text(INTAKE)
    code, out, _ = kit("validate", ws)
    assert code == 0
    assert "names no commit id" in out
    assert "result: pass" in (ws / ".audit/validation.md").read_text()

    (ws / ".audit/project.md").write_text(
        INTAKE.replace("demo @ main", "demo @ 1234abcd")
    )
    assert kit("validate", ws)[0] != 0
    assert "result: fail" in (ws / ".audit/validation.md").read_text()


def test_verify_through_the_cli(env: Path, source: Path, kit: Kit) -> None:
    audit = source / ".audit"
    audit.mkdir()
    header = "---\nagent: security\nmodel: m\ncommit: c\nstatus: complete\n---\n"
    block = "- Category: security\n- Severity: low\n- Confidence: high\n- Location: server.js:1\n- Evidence: e\n- Excerpt: `const express`\n"
    (audit / "04-security.md").write_text(
        header + "### SEC-001 T\n- Key: EXP-A:server.js\n" + block
    )
    assert kit("verify", source)[0] == 0
    (audit / "04-security.md").write_text(
        header
        + "### SEC-001 T\n- Key: EXP-A:server.js\n"
        + block
        + "### SEC-002 T\n- Key: EXP-A:server.js\n"
    )
    assert kit("verify", source)[0] == 1


def test_bin_kit_wrapper_runs_the_python_cli(env: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("needs uv")
    done = subprocess.run(
        ["/bin/bash", str(KIT / "bin/kit"), "help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "workspace" in done.stdout
    assert "ready" in done.stdout


def test_a_named_workspace_is_a_second_audit_on_the_same_day(
    env: Path, source: Path, project: Path, kit: Kit
) -> None:
    assert workspace(kit, source, "eval", "2026-01-03")[0] == 0
    code, _, _ = kit(
        "workspace", "demo", "--source", source, "--ref", "main",
        "--mode", "eval", "--date", "2026-01-03", "--name", "demo-eval-2026-01-03-v2",
    )  # fmt: skip
    assert code == 0
    assert (env / "ws/demo-eval-2026-01-03-v2/.audit/.workspace").is_file()


@pytest.mark.parametrize("name", ["../escape", "a/b", ".hidden", ""])
def test_a_workspace_name_that_is_not_one_folder_is_refused(
    env: Path, source: Path, project: Path, kit: Kit, name: str
) -> None:
    code, _, err = kit(
        "workspace", "demo", "--source", source, "--ref", "main",
        "--mode", "eval", "--date", "2026-01-04", "--name", name,
    )  # fmt: skip
    assert code == 2
    assert "--name" in err


def workspace(kit: Kit, source: Path, mode: str, date: str) -> tuple[int, str, str]:
    return kit(
        "workspace", "demo", "--source", source, "--ref", "main",
        "--mode", mode, "--date", date,
    )  # fmt: skip


def test_tracked_ignored_and_export_ignored_files_survive_the_eval_snapshot(
    env: Path, source: Path, project: Path, kit: Kit
) -> None:
    (source / ".gitignore").write_text("build/\n")
    (source / "build").mkdir()
    (source / "build/keep.js").write_text("tracked despite .gitignore\n")
    (source / ".gitattributes").write_text("sql/ export-ignore\n")
    git(source, "add", "-f", "-A")
    git(source, "commit", "-qm", "ignored and export-ignore paths")
    code, _, err = workspace(kit, source, "eval", "2026-02-01")
    ws = env / "ws/demo-eval-2026-02-01"
    assert code == 0
    assert "restored sql/t.sql" in err
    tracked = git(ws, "ls-files")
    assert "build/keep.js" in tracked
    assert "sql/t.sql" in tracked
    state = (ws / ".audit/.workspace").read_text()
    assert f"source_commit: {git(source, 'rev-parse', 'HEAD')}" in state
    assert "eval_removed: 1" in state


def test_a_plain_folder_is_a_source(
    env: Path, make_repo: Callable[..., Path], project: Path, kit: Kit
) -> None:
    folder = make_repo()
    shutil.rmtree(folder / ".audit")
    (folder / ".gitignore").write_text("dist/\n")
    (folder / "dist").mkdir()
    (folder / "dist/app.js").write_text("ignored, still audited\n")
    assert workspace(kit, folder, "real", "2026-02-02")[0] == 0
    ws = env / "ws/demo-real-2026-02-02"
    assert "dist/app.js" in git(ws, "ls-files")
    state = (ws / ".audit/.workspace").read_text()
    assert "source_kind: folder" in state
    assert "source_sha256: " in state

    assert kit("install", ws)[0] == 0
    assert kit("detect", ws)[0] == 0
    inventory = (ws / ".audit/inventory.json").read_text()
    assert '"path": "dist/app.js"' in inventory
    assert '"path": ".audit-kit/VERSION"' not in inventory
    assert "AI instruction files: none" in (ws / ".audit/detected.md").read_text()


def test_a_tar_archive_is_a_source(
    env: Path, make_repo: Callable[..., Path], project: Path, kit: Kit
) -> None:
    folder = make_repo()
    shutil.rmtree(folder / ".audit")
    archive = env / "drop.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(folder, arcname=".")
    assert workspace(kit, archive, "real", "2026-02-03")[0] == 0
    ws = env / "ws/demo-real-2026-02-03"
    assert "server.js" in git(ws, "ls-files")
    assert "archive_sha256: " in (ws / ".audit/.workspace").read_text()


def test_zip_and_kit_folder_clashes_are_refused(
    env: Path, make_repo: Callable[..., Path], project: Path, kit: Kit
) -> None:
    (env / "drop.zip").write_bytes(b"PK")
    code, _, err = workspace(kit, env / "drop.zip", "real", "2026-02-04")
    assert code == 2
    assert "zip" in err
    folder = make_repo()  # has its own .audit/
    code, _, err = workspace(kit, folder, "real", "2026-02-05")
    assert code == 2
    assert "has its own .audit" in err


def test_detect_stops_when_files_differ_from_the_snapshot(
    env: Path, source: Path, project: Path, kit: Kit
) -> None:
    assert workspace(kit, source, "real", "2026-02-06")[0] == 0
    ws = env / "ws/demo-real-2026-02-06"
    assert kit("install", ws)[0] == 0
    (ws / "server.js").write_text("changed after the snapshot\n")
    code, _, err = kit("detect", ws)
    assert code == 2
    assert "content differs from the snapshot commit: server.js" in err


def test_a_copy_that_differs_from_the_source_commit_is_refused(
    env: Path, source: Path, project: Path, kit: Kit
) -> None:
    # export-subst makes `git archive` rewrite the file, so the copy no longer matches.
    (source / "version.txt").write_text("$Format:%H$\n")
    (source / ".gitattributes").write_text("version.txt export-subst\n")
    git(source, "add", "-A")
    git(source, "commit", "-qm", "export-subst")
    code, _, err = workspace(kit, source, "eval", "2026-02-07")
    assert code == 2
    assert "doesn't match source commit" in err
    assert "content differs from the source commit: version.txt" in err
