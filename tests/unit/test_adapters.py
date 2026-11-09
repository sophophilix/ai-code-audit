"""Orchestration of external tools, with each tool replaced by a recording fake.

These prove the command lines the kit sends and how it handles the results; they
don't prove the real tools work (python-testing, optional adapters).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from audit_kit import cli, lookups, machine, outputs, scans
from audit_kit.errors import AuditKitError
from audit_kit.settings import KitSettings
from audit_kit.workspace import Workspace

KIT = Path(__file__).resolve().parents[2]
FAKE = f"""#!{sys.executable}
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + "\\n")
args = sys.argv[1:]
for flag in ("-r", "-o", "--output", "--sarif-output", "--json-pp"):
    if flag in args:
        target = args[args.index(flag) + 1].split("=", 1)[-1]
        if name == "jscpd":
            os.makedirs(target, exist_ok=True)
            target = os.path.join(target, "jscpd-report.json")
        if not target.startswith("-"):
            with open(target, "w") as fh:
                fh.write("{{}}")
if name == "npm" and args[:1] == ["install"]:
    with open("package.json", "w") as fh:
        json.dump({{"dependencies": {{"jscpd": "4.0.5"}}}}, fh)
print("{{}}")
"""


def fake_tools(bin_dir: Path, names: tuple[str, ...]) -> None:
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        script = bin_dir / name
        script.write_text(FAKE)
        script.chmod(0o755)


def calls(log: Path) -> list[list[str]]:
    return (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.is_file()
        else []
    )


@pytest.fixture
def world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_repo: Callable[..., Path]
) -> dict[str, Path]:
    """An installed eval workspace, fake tools on PATH, and a fake drawio-skill."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("git", "sh", "head", "cat"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    drawio = tmp_path / "drawio/skills/drawio-skill"
    (drawio / "scripts").mkdir(parents=True)
    for script in ("diagramctl.py", "validate.py", "shapesearch.py"):
        (drawio / "scripts" / script).write_text(
            "import sys, json\nargs = sys.argv[1:]\n"
            "if '-o' in args:\n    open(args[args.index('-o') + 1], 'w').write('<mxfile/>')\n"
            "print(json.dumps({'ok': True}) if 'shapesearch' in sys.argv[0] else 'score: 0')\n"
        )
    log = tmp_path / "calls.log"
    env = {
        "AUDIT_PROJECTS_DIR": tmp_path / "projects",
        "AUDIT_WORKSPACES_DIR": tmp_path / "ws",
        "DRAWIO_SKILL_DIR": drawio,
        "JSCPD_BIN": bin_dir / "jscpd",
        "ESLINT_BIN": bin_dir / "eslint",
        "TSC_BIN": bin_dir / "tsc",
        "FAKE_LOG": log,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": bin_dir,
    }
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    (bin_dir / "python3").symlink_to(sys.executable)
    source = make_repo()
    shutil.rmtree(source / ".audit")
    (source / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-qm", "init"],
    ):
        subprocess.run(
            ["git", *args], cwd=source, check=True, capture_output=True, timeout=60
        )
    assert cli.main(["project", "demo"]) == 0
    assert (
        cli.main(
            [
                "workspace",
                "demo",
                "--source",
                str(source),
                "--ref",
                "main",
                "--date",
                "2026-01-01",
            ]
        )
        == 0
    )
    ws = tmp_path / "ws/demo-eval-2026-01-01"
    assert cli.main(["install", str(ws), "--no-seed"]) == 0
    assert cli.main(["detect", str(ws)]) == 0
    return {
        "ws": ws,
        "bin": bin_dir,
        "log": log,
        "drawio": drawio,
        "projects": tmp_path / "projects",
    }


def test_scan_sends_expected_commands_and_records_outputs(
    world: dict[str, Path],
) -> None:
    fake_tools(
        world["bin"],
        (
            "cloc", "gitleaks", "osv-scanner", "semgrep", "jscpd", "eslint",
            "tsc", "scancode", "syft",
        ),
    )  # fmt: skip
    s = KitSettings.load()
    scans.scan(s, str(world["ws"]))
    used = {c[0]: c for c in calls(world["log"])}
    assert used["gitleaks"][1] == "dir"  # eval snapshots have no history to scan
    assert "--exclude" in used["semgrep"]
    assert "public/vendor" in used["semgrep"]
    assert any(a.startswith("--exclude-dir=") and "vendor" in a for a in used["cloc"])
    eslint = used["eslint"]
    assert eslint[eslint.index("--config") + 1] == str(
        s.kit_home / "config/eslint.config.mjs"
    )
    assert "--no-inline-config" in eslint
    assert "public/vendor/**" in eslint
    scans_dir = world["ws"] / ".audit/scans"
    tsc = used["tsc"]
    assert tsc[1:3] == ["-p", str(scans_dir / "tsconfig.audit.json")]
    config = json.loads((scans_dir / "tsconfig.audit.json").read_text())
    assert config["compilerOptions"]["checkJs"] is True
    assert config["compilerOptions"]["noEmit"] is True
    assert "../../public/vendor/**" in config["exclude"]
    assert "../../.audit-kit/**" in config["exclude"]
    unused = json.loads((scans_dir / "unused.json").read_text())
    assert "no execution" in unused["generated_by"]
    for name in (
        "cloc.json",
        "secrets.json",
        "deps-audit.json",
        "sast.sarif",
        "duplication.json",
        "lint.json",
        "typecheck.txt",
        "unused.json",
        "drawio-azure-shapes.json",
    ):
        assert (scans_dir / name).stat().st_size > 0, name
    missing = (scans_dir / "MISSING.txt").read_text()
    assert "not installed" not in missing
    before = len(calls(world["log"]))
    scans.scan(s, str(world["ws"]))
    assert len(calls(world["log"])) == before  # outputs kept unless --force
    scans.scan(s, str(world["ws"]), force=True)
    assert len(calls(world["log"])) > before


def test_a_failing_scanner_is_recorded_not_fatal(world: dict[str, Path]) -> None:
    (world["bin"] / "cloc").write_text("#!/bin/sh\necho broken >&2\nexit 9\n")
    (world["bin"] / "cloc").chmod(0o755)
    scans.scan(KitSettings.load(), str(world["ws"]))
    assert (
        "cloc: failed (cloc failed (exit 9) broken)"
        in (world["ws"] / ".audit/scans/MISSING.txt").read_text()
    )


def test_diagrams_build_views_and_contracts(world: dict[str, Path]) -> None:
    diagrams = world["ws"] / ".audit/diagrams"
    (diagrams / "target.ir.json").write_text('{"nodes": []}')
    (diagrams / "policy.yml").write_text("rules: []\n")
    outputs.diagrams(KitSettings.load(), str(world["ws"]))
    assert (diagrams / "target.drawio").is_file()
    assert (diagrams / "policy-results.json").is_file()


def test_diagrams_need_drawio_skill(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DRAWIO_SKILL_DIR", str(world["ws"] / "missing"))
    with pytest.raises(AuditKitError, match="drawio-skill not installed"):
        outputs.diagrams(KitSettings.load(), str(world["ws"]))


def test_publish_uses_templates_and_skips_missing_tools(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    s = KitSettings.load()
    outputs.publish(s, str(world["ws"]))
    assert "no 07-final-report.md yet" in capsys.readouterr().out
    (world["ws"] / ".audit/07-final-report.md").write_text("# Report\n")
    (world["ws"] / ".audit/09-briefing.slides.md").write_text("# Deck\n")
    (world["projects"] / "demo/templates/report.docx").write_bytes(b"docx")
    outputs.publish(s, str(world["ws"]))
    assert "pandoc not installed" in capsys.readouterr().out
    fake_tools(world["bin"], ("pandoc", "marp"))
    outputs.publish(s, str(world["ws"]))
    pandoc = [c for c in calls(world["log"]) if c[0] == "pandoc"]
    assert any(
        a.startswith("--reference-doc=") and a.endswith("report.docx")
        for a in pandoc[0]
    )
    assert not any(
        a.startswith("--reference-doc") for a in pandoc[1]
    )  # no deck template
    assert any(c[0] == "marp" for c in calls(world["log"]))


def test_tools_installs_only_what_is_missing(
    world: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_tools(world["bin"], ("brew", "npm"))
    monkeypatch.setattr(machine, "DRAWIO_APP", tmp_path / "no-app")
    s = KitSettings.load(
        {**os.environ, "JSCPD_BIN": str(tmp_path / "tools/node_modules/.bin/jscpd")}
    )
    machine.tools(s, dry_run=False)
    installed = [c for c in calls(world["log"]) if c[0] == "brew"]
    assert ["brew", "install", "graphviz"] in installed
    assert ["brew", "install", "--cask", "drawio"] in installed
    assert any(
        c[:2] == ["npm", "install"]
        and "--ignore-scripts" in c
        and {"jscpd", "eslint", "eslint-plugin-regexp"} <= set(c)
        for c in calls(world["log"])
    )
    out = capsys.readouterr().out
    assert "jscpd 4.0.5" in out
    assert "drawio-skill present" in out


def test_tag_skips_when_tagged_and_refuses_a_dirty_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "kit"
    home.mkdir()
    (home / "VERSION").write_text("9.9.9\n")
    for key, value in {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x.invalid",
    }.items():
        monkeypatch.setenv(key, value)
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "v"]):
        subprocess.run(
            ["git", *args], cwd=home, check=True, capture_output=True, timeout=60
        )
    s = KitSettings.load({"AUDIT_KIT_HOME": str(home)})
    machine.tag(s)
    tags = subprocess.run(
        ["git", "tag"], cwd=home, capture_output=True, text=True, check=True, timeout=60
    ).stdout
    assert "v9.9.9" in tags
    machine.tag(s)  # already tagged: skipped
    (home / "VERSION").write_text("9.9.10\n")
    with pytest.raises(AuditKitError, match="uncommitted changes"):
        machine.tag(KitSettings.load({"AUDIT_KIT_HOME": str(home)}))


def test_scancode_and_syft_run_offline_and_are_cross_checked(
    world: dict[str, Path],
) -> None:
    fake_tools(world["bin"], ("scancode", "syft"))
    scans.scan(KitSettings.load(), str(world["ws"]))
    used = {c[0]: c for c in calls(world["log"])}
    assert {"--info", "--classify", "--generated", "--strip-root"} <= set(
        used["scancode"]
    )
    assert used["syft"][1:3] == ["scan", "dir:."]
    config = (world["ws"] / ".audit/scans/syft-config.yaml").read_text()
    assert "selection: all" in config
    assert "check-for-app-update: false" in config

    scans_dir = world["ws"] / ".audit/scans"
    (scans_dir / "scancode.json").write_text(
        json.dumps(
            {
                "files": [
                    {"path": "server.js", "type": "file"},
                    {"path": "ghost.js", "type": "file"},
                    {"path": "lib", "type": "directory"},
                ]
            }
        )
    )
    (scans_dir / "syft.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "location": {"path": "/server.js"},
                        "digests": [{"algorithm": "sha256", "value": "0" * 64}],
                    }
                ]
            }
        )
    )
    differences = scans.cross_check_tools(Workspace(world["ws"]))
    assert "scancode saw, inventory lacks: ghost.js" in differences
    assert "inventory has, scancode didn't see: lib/a.js" in differences
    assert "sha256 differs (syft): server.js" in differences
    assert (scans_dir / "inventory-crosscheck.txt").is_file()


def test_lookups_follow_the_engagement_policy(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def fetch(url: str) -> object:
        asked.append(url)
        raise lookups.FetchError("HTTP 404")

    monkeypatch.setattr(lookups, "https_fetch", fetch)
    status = world["ws"] / ".audit/scans/upstream-status.json"
    scans.lookup(KitSettings.load(), str(world["ws"]))
    assert asked == []
    assert json.loads(status.read_text())["policy"] == "deny"

    (world["ws"] / ".audit/policy.yaml").write_text(
        "version: 1\nnetwork: {metadata_lookups: allow}\n"
    )
    inventory = world["ws"] / ".audit/inventory.json"
    doc = json.loads(inventory.read_text())
    doc["entries"].append(
        {
            "path": "public/vendor/x.js",
            "cls": "vendored",
            "upstream": "https://github.com/o/r",
        }
    )
    inventory.write_text(json.dumps(doc))
    scans.lookup(KitSettings.load(), str(world["ws"]))
    assert asked == ["https://api.github.com/repos/o/r"]
    assert json.loads(status.read_text())["policy"] == "allow"
