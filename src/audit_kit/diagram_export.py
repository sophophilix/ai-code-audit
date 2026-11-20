"""Export diagram pages to SVG and PNG with the draw.io desktop command line.

ADR 0014. A person runs this from the kit folder, never an agent (AGENTS.md
rule 2). A missing draw.io skips the export with a message: the `.drawio`
files are the primary output, so the build never fails for want of images.
"""

from __future__ import annotations

import html
import os
import platform
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from audit_kit.console import ok, skip, warn
from audit_kit.errors import AuditKitError, WorkspaceError
from audit_kit.runner import CommandError, run
from audit_kit.workspace import Workspace

FOLDER = ".audit/diagrams"
MACOS_APP = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")
# The Windows app as WSL2 sees it: machine-wide, then per-user installs.
WSL_APP = Path("/mnt/c/Program Files/draw.io/draw.io.exe")
WSL_USER_APPS = "/mnt/c/Users/*/AppData/Local/Programs/draw.io/draw.io.exe"
# Seconds per page and format. draw.io takes about 3 on a laptop; a hung
# Electron start shouldn't hold the run for the kit's LONG limit.
TIMEOUT = 300.0
PAGE = re.compile(r"<diagram\b([^>]*)>")
NAME = re.compile(r'\bname="([^"]*)"')
FORMATS = {"svg": ("--embed-svg-images",), "png": ("-s", "2")}
MANUAL = "open each .drawio file in draw.io and use File > Export as"


class ExportUnavailableError(AuditKitError):
    """draw.io, or the display it needs, isn't available on this machine."""


@dataclass(frozen=True)
class Exporter:
    """How to start the draw.io command line on this machine.

    Attributes:
        prefix: The program to run, with any wrapper such as `xvfb-run -a`.
        suffix: Switches that go after the input file.
        windows: Paths must be converted with `wslpath -w` (Windows app on WSL2).
    """

    prefix: tuple[str, ...]
    suffix: tuple[str, ...] = ()
    windows: bool = False


def _linux() -> bool:
    return platform.system() == "Linux"


def _wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def windows_drawio() -> Path | None:
    """Return the Windows draw.io app as WSL2 sees it, or None."""
    if not _wsl():
        return None
    if WSL_APP.is_file():
        return WSL_APP
    users = sorted(Path("/").glob(WSL_USER_APPS.lstrip("/")))
    return users[0] if users else None


def find_exporter(env: Mapping[str, str] | None = None) -> Exporter:
    """Resolve the draw.io command line once, in the order ADR 0014 D3 sets.

    Args:
        env: Environment to read `DISPLAY` and `WAYLAND_DISPLAY` from.

    Returns:
        How to start draw.io.

    Raises:
        ExportUnavailableError: If draw.io, or on Linux a display, can't be found.
    """
    env = os.environ if env is None else env
    found = shutil.which("drawio")
    if found is None and MACOS_APP.is_file():
        found = str(MACOS_APP)
    if found is None:
        app = windows_drawio()
        if app is not None:
            return Exporter((str(app),), windows=True)
        raise ExportUnavailableError("draw.io not installed (make doctor)")
    if not _linux() or env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        return Exporter((found,))
    xvfb = shutil.which("xvfb-run")
    if xvfb is None:
        raise ExportUnavailableError(
            "no display for draw.io; install xvfb (sudo apt install xvfb)"
        )
    return Exporter((xvfb, "-a", found), ("--disable-gpu",))


def pages(xml: str) -> list[str]:
    """Return a file name part for each page in a draw.io file, in order.

    A page's name is lower-cased, with runs of other characters turned into
    one hyphen. A page with no usable name is numbered from 1. A file with no
    `<diagram>` element (a bare `<mxGraphModel>`) is one page to draw.io.
    """
    out = []
    for n, attrs in enumerate(PAGE.findall(xml), start=1):
        m = NAME.search(attrs)
        name = html.unescape(m.group(1)) if m else ""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        out.append(slug or f"page-{n}")
    return out or ["page-1"]


def outputs(rel: str, names: list[str]) -> list[tuple[int, str]]:
    """Return (page number, output path without extension) for each page.

    `target.drawio` with one page gives `target`. `target.views.drawio` gives
    `target-executive`, `target-deployment` and so on (ADR 0014 D2).
    """
    stem = rel.removesuffix(".drawio").removesuffix(".views")
    if len(names) == 1:
        return [(1, stem)]
    return [(n, f"{stem}-{name}") for n, name in enumerate(names, start=1)]


def _arg(exp: Exporter, path: Path) -> str:
    if not exp.windows:
        return str(path)
    return run(["wslpath", "-w", path]).text


def _export_page(
    exp: Exporter, ws: Workspace, source: Path, page: int, out: str, fmt: str
) -> bool:
    try:
        target = ws.path(f"{out}.{fmt}")  # refuses a symlinked target
        ws.remove(f"{out}.{fmt}")  # so a stale image never passes for a new one
        args = [*exp.prefix, "-x", "-f", fmt, "-p", str(page), *FORMATS[fmt]]
        args += ["-o", _arg(exp, target), _arg(exp, source), *exp.suffix]
        result = run(args, cwd=ws.root, timeout=TIMEOUT, check=False)
    except (CommandError, WorkspaceError) as exc:
        warn(f"{out}.{fmt}: {exc}")
        return False
    if result.code or not target.is_file():
        warn(f"{out}.{fmt}: draw.io exit {result.code}, no image written")
        return False
    return True


def export(ws: Workspace) -> None:
    """Export every page of every `.drawio` file in `.audit/diagrams/`."""
    folder = ws.root / FOLDER
    files = sorted(folder.glob("*.drawio")) if folder.is_dir() else []
    if not files:
        skip("no .audit/diagrams/*.drawio to export")
        return
    try:
        exp = find_exporter()
    except ExportUnavailableError as exc:
        skip(f"diagrams have no images: {exc}; or {MANUAL}")
        return
    done = total = 0
    for file in files:
        rel = file.relative_to(ws.root).as_posix()
        source = ws.path(rel)  # refuses a symlinked source
        for page, out in outputs(rel, pages(ws.read_text(rel))):
            for fmt in FORMATS:
                total += 1
                done += _export_page(exp, ws, source, page, out, fmt)
    (ok if done == total else warn)(f"exported {done} of {total} images")
