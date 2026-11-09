"""After a run: build diagrams with drawio-skill and publish Office and PDF copies."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from audit_kit import diagram_style
from audit_kit.console import ok, skip, warn
from audit_kit.errors import AuditKitError
from audit_kit.runner import LONG, have, run
from audit_kit.settings import KitSettings
from audit_kit.workspace import Workspace
from audit_kit.workspaces import locate

VIEWS = "executive,deployment,dataflow,security"


def diagrams(s: KitSettings, given: str, style: str = "handdrawn") -> None:
    """Build, project, style and validate every .audit/diagrams/*.ir.json.

    The IR is grouped by trust boundary and laid out left to right before the
    build; the kit's house style (`diagram_style`) is applied after it.
    """
    loc = locate(s, given)
    root = loc.ws.root
    if not s.drawio_dir.is_dir():
        raise AuditKitError(
            f"drawio-skill not installed at {s.drawio_dir} (THIRD_PARTY.md)"
        )
    ctl = s.drawio_dir / "scripts/diagramctl.py"
    folder = root / ".audit/diagrams"
    irs = sorted(folder.glob("*.ir.json")) if folder.is_dir() else []
    for ir in irs:
        stem = ir.name.removesuffix(".ir.json")
        out = folder / f"{stem}.drawio"
        views = folder / f"{stem}.views.drawio"
        for target in (out, views):  # refuse symlinked targets
            loc.ws.path(target.relative_to(root).as_posix())
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.loads(loc.ws.read_text(ir.relative_to(root).as_posix()))
            ws = Workspace(Path(tmp))  # the prepared IR, outside the target
            ws.write_text(ir.name, json.dumps(diagram_style.prepare(raw)))
            prepared = ws.path(ir.name)
            # Left to right reads as internet -> Azure -> services it calls.
            steps: tuple[list[str | Path], ...] = (
                ["build", prepared, "--from", "ir", "-o", out],
                ["views", prepared, "--views", VIEWS, "-o", views],
            )
            for args in steps:
                run(
                    ["python3", ctl, *args, "--direction", "LR"],
                    cwd=root,
                    timeout=LONG,
                )
        for built in (out, views):
            rel = built.relative_to(root).as_posix()
            loc.ws.write_text(rel, diagram_style.restyle(loc.ws.read_text(rel), style))
        score = run(
            ["python3", s.drawio_dir / "scripts/validate.py", out, "--score"],
            cwd=root,
            timeout=LONG,
            check=False,
        )
        last = score.text.splitlines()[-1:] or [""]
        ok(f"{stem}: {last[0]}")
    policy, target = folder / "policy.yml", folder / "target.drawio"
    if policy.is_file() and target.is_file():
        result = run(
            ["python3", ctl, "test", target, "--rules", policy],
            cwd=root,
            timeout=LONG,
            check=False,
        )
        loc.ws.write_text(
            ".audit/diagrams/policy-results.json",
            result.stdout.decode("utf-8", errors="replace"),
        )
        if result.code:
            warn("architecture contracts failed (policy-results.json)")
    if irs:
        ok(f"built {len(irs)} diagram(s); open them in draw.io to tidy")
    else:
        skip("no .audit/diagrams/*.ir.json yet")


def publish(s: KitSettings, given: str) -> None:
    """Generate Word, PowerPoint and PDF copies from the Markdown outputs."""
    loc = locate(s, given)
    root = loc.ws.root
    templates = loc.project / "templates"

    def pandoc(source: str, output: str, template: str) -> None:
        args = ["pandoc", source, "-o", output]
        if (templates / template).is_file():
            args.append(f"--reference-doc={templates / template}")
        run(args, cwd=root, timeout=LONG)

    if not loc.ws.is_file(".audit/07-final-report.md"):
        skip("no 07-final-report.md yet")
    elif not have("pandoc"):
        skip("pandoc not installed")
    else:
        pandoc(
            ".audit/07-final-report.md", ".audit/07-final-report.docx", "report.docx"
        )
        ok("07-final-report.docx")
    if not loc.ws.is_file(".audit/09-briefing.slides.md"):
        skip("no 09-briefing.slides.md yet")
        return
    if have("pandoc"):
        pandoc(".audit/09-briefing.slides.md", ".audit/09-briefing.pptx", "deck.pptx")
        ok("09-briefing.pptx (editable)")
    if have("marp"):
        run(
            [
                "marp",
                "--quiet",
                ".audit/09-briefing.slides.md",
                "--pdf",
                "-o",
                ".audit/09-briefing.pdf",
            ],
            cwd=root,
            timeout=LONG,
        )
        ok("09-briefing.pdf")
    else:
        skip("marp not installed")
