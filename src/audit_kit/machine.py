"""Machine-level commands: doctor, tools, tag."""

from __future__ import annotations

import json
from pathlib import Path

from audit_kit.console import ok, say, skip, warn
from audit_kit.errors import AuditKitError
from audit_kit.runner import LONG, CommandError, git, have, run
from audit_kit.settings import DRAWIO_COMMIT, KitSettings

REQUIRED = ("git", "python3", "uv")
OPTIONAL = (
    "claude",
    "gitleaks",
    "cloc",
    "osv-scanner",
    "semgrep",
    "dot",
    "pandoc",
    "marp",
)
BREW_FORMULA = {"dot": "graphviz", "marp": "marp-cli"}
DRAWIO_APP = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")
DRAWIO_REPO = "https://github.com/Agents365-ai/drawio-skill.git"


def _drawio_app() -> bool:
    return have("drawio") or DRAWIO_APP.is_file()


def _tagged(s: KitSettings) -> bool:
    return (
        run(
            ["git", "rev-parse", "-q", "--verify", f"refs/tags/v{s.version}"],
            cwd=s.kit_home,
            check=False,
        ).code
        == 0
    )


def _clean(s: KitSettings) -> bool:
    return git("status", "--porcelain", cwd=s.kit_home) == ""


def doctor(s: KitSettings) -> None:
    """Report required and optional tools, the drawio-skill pin and the kit tag."""
    say(f"agent-audit-kit {s.version} ({s.kit_home})")
    for tool in REQUIRED:
        (ok if have(tool) else warn)(
            tool if have(tool) else f"{tool} missing (required)"
        )
    if (s.kit_home / ".venv").is_dir() and (s.kit_home / "uv.lock").is_file():
        ok("kit environment (uv.lock)")
    else:
        warn(f"kit environment not synced (cd {s.kit_home} && uv sync --frozen)")
    for tool in OPTIONAL:
        (ok if have(tool) else skip)(tool if have(tool) else f"{tool} not installed")
    for name, path in (("jscpd", s.jscpd), ("eslint", s.eslint), ("tsc", s.tsc)):
        (ok if have(path) else skip)(name if have(path) else f"{name} not at {path}")
    (ok if _drawio_app() else skip)(
        "draw.io" if _drawio_app() else "draw.io not installed"
    )
    if s.drawio_dir.is_dir():
        head = (
            run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=s.drawio_dir, check=False
            ).text
            or "?"
        )
        if head.startswith(DRAWIO_COMMIT):
            ok(f"drawio-skill @ {head}")
        else:
            warn(f"drawio-skill at {head}, expected {DRAWIO_COMMIT} (THIRD_PARTY.md)")
    else:
        skip(f"drawio-skill not at {s.drawio_dir} (THIRD_PARTY.md)")
    if _tagged(s):
        ok(f"kit tagged v{s.version}")
    else:
        warn(f"kit {s.version} not tagged (kit tag)")
    if _clean(s):
        ok("kit repo clean")
    else:
        warn("kit repo has uncommitted changes")
    say(
        "Install what is missing: make tools (preview: bin/kit tools --dry-run). "
        "On an organisation-managed machine, follow its software policy first."
    )


def tools(s: KitSettings, *, dry_run: bool) -> None:
    """Install what doctor reports missing: Homebrew formulae, draw.io, jscpd, ESLint, TypeScript, drawio-skill."""
    for tool in ("uv", *OPTIONAL[1:]):
        formula = BREW_FORMULA.get(tool, tool)
        if have(tool):
            skip(f"{tool} installed")
        elif not have("brew"):
            warn(f"{tool} missing and Homebrew not found (https://brew.sh)")
        elif dry_run:
            say(f"  would brew install {formula}")
        else:
            run(["brew", "install", formula], timeout=LONG)
            ok(tool)
    if _drawio_app():
        skip("draw.io installed")
    elif not have("brew"):
        warn("draw.io missing and Homebrew not found")
    elif dry_run:
        say("  would brew install --cask drawio")
    else:
        run(["brew", "install", "--cask", "drawio"], timeout=LONG)
        ok("draw.io")
    tools_dir = s.jscpd.parents[2]
    # The ESLint plugin is loaded by config/eslint.config.mjs from beside ESLint.
    wanted = [
        *([] if have(s.jscpd) else ["jscpd"]),
        *([] if have(s.eslint) else ["eslint", "eslint-plugin-regexp"]),
        # The type-check scan's tsconfig points typeRoots at these @types.
        *([] if have(s.tsc) else ["typescript", "@types/node"]),
    ]
    if not wanted:
        skip("jscpd, eslint and tsc installed")
    elif not have("npm"):
        warn(f"{', '.join(wanted)} need npm (install Node.js first)")
    elif dry_run:
        say(
            f"  would npm install --ignore-scripts --save-exact {' '.join(wanted)} into {tools_dir}"
        )
    else:
        tools_dir.mkdir(parents=True, exist_ok=True)
        if not (tools_dir / "package.json").is_file():
            run(["npm", "init", "-y"], cwd=tools_dir, timeout=LONG)
        run(
            ["npm", "install", "--ignore-scripts", "--save-exact", *wanted],
            cwd=tools_dir,
            timeout=LONG,
        )
        versions = json.loads(
            (tools_dir / "package.json").read_text(encoding="utf-8")
        ).get("dependencies", {})
        for name in wanted:
            ok(f"{name} {versions.get(name, '?')}")
    clone_root = s.drawio_dir.parents[1]
    if s.drawio_dir.is_dir():
        head = run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=s.drawio_dir, check=False
        ).text
        skip(f"drawio-skill present ({head})")
    elif dry_run:
        say(
            f"  would clone Agents365-ai/drawio-skill into {clone_root} at {DRAWIO_COMMIT}"
        )
    else:
        git("clone", "-q", DRAWIO_REPO, clone_root, timeout=LONG)
        git("checkout", "-q", "--detach", DRAWIO_COMMIT, cwd=clone_root)
        ok(f"drawio-skill @ {DRAWIO_COMMIT}")
    say("Dry run: nothing installed." if dry_run else "Done. Run: make doctor")


def tag(s: KitSettings) -> None:
    """Tag the kit's current version; skip if the tag exists."""
    if _tagged(s):
        skip(f"v{s.version} already tagged")
        return
    if not _clean(s):
        raise AuditKitError("kit repo has uncommitted changes; commit first")
    try:
        git("tag", f"v{s.version}", cwd=s.kit_home)
    except CommandError as exc:
        raise AuditKitError(f"could not tag: {exc}") from exc
    ok(f"tagged v{s.version}")
