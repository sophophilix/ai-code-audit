"""Exporting diagram pages with the draw.io command line (ADR 0014)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from audit_kit import diagram_export
from audit_kit.diagram_export import Exporter, ExportUnavailableError
from audit_kit.workspace import Workspace

VIEWS = (
    '<mxfile><diagram id="a" name="Executive"/><diagram id="b" name="Deployment"/>'
    '<diagram id="c" name="Data &amp; flow"/><diagram id="d" name="Security"/></mxfile>'
)
ONE = '<mxfile><diagram id="a" name="Page-1"/></mxfile>'
# Logs its arguments, writes the -o file, and fails on page 2 if asked to.
FAKE = f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps([os.path.basename(sys.argv[0]), *args]) + "\\n")
if os.environ.get("FAIL_PAGE") == args[args.index("-p") + 1]:
    sys.exit(1)
open(args[args.index("-o") + 1], "w").write("image")
"""


@pytest.fixture
def no_drawio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An empty PATH, no macOS app, not Linux and not WSL2."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setattr(diagram_export, "MACOS_APP", tmp_path / "none/draw.io")
    monkeypatch.setattr(diagram_export, "_linux", lambda: False)
    monkeypatch.setattr(diagram_export, "_wsl", lambda: False)
    return bin_dir


def _tool(bin_dir: Path, name: str, body: str = FAKE) -> Path:
    path = bin_dir / name
    path.write_text(body)
    path.chmod(0o755)
    return path


def _ws(tmp_path: Path, **files: str) -> Workspace:
    folder = tmp_path / "ws/.audit/diagrams"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name.replace("_", ".")).write_text(text)
    return Workspace(tmp_path / "ws")


def _calls(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_pages_are_named_from_the_file_in_order() -> None:
    assert diagram_export.pages(VIEWS) == [
        "executive",
        "deployment",
        "data-flow",
        "security",
    ]


def test_a_page_without_a_name_is_numbered() -> None:
    assert diagram_export.pages('<diagram id="x"/><diagram name="  "/>') == [
        "page-1",
        "page-2",
    ]


def test_a_file_without_page_elements_is_one_page() -> None:
    assert diagram_export.pages("<mxGraphModel><root/></mxGraphModel>") == ["page-1"]


def test_one_page_keeps_the_file_name_and_views_add_the_page() -> None:
    assert diagram_export.outputs("d/target.drawio", ["page-1"]) == [(1, "d/target")]
    assert diagram_export.outputs(
        "d/target.views.drawio", ["executive", "security"]
    ) == [
        (1, "d/target-executive"),
        (2, "d/target-security"),
    ]


def test_drawio_on_the_path_runs_directly(no_drawio: Path) -> None:
    drawio = _tool(no_drawio, "drawio")
    assert diagram_export.find_exporter({}) == Exporter((str(drawio),))


def test_the_macos_app_is_found_when_not_on_the_path(
    no_drawio: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _tool(tmp_path, "draw.io")
    monkeypatch.setattr(diagram_export, "MACOS_APP", app)
    assert diagram_export.find_exporter({}) == Exporter((str(app),))


def test_linux_with_a_display_needs_no_wrapper(
    no_drawio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawio = _tool(no_drawio, "drawio")
    monkeypatch.setattr(diagram_export, "_linux", lambda: True)
    assert diagram_export.find_exporter({"WAYLAND_DISPLAY": "wayland-0"}) == Exporter(
        (str(drawio),)
    )


def test_headless_linux_runs_under_xvfb_without_gpu(
    no_drawio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawio = _tool(no_drawio, "drawio")
    xvfb = _tool(no_drawio, "xvfb-run")
    monkeypatch.setattr(diagram_export, "_linux", lambda: True)
    exp = diagram_export.find_exporter({})
    assert exp == Exporter((str(xvfb), "-a", str(drawio)), ("--disable-gpu",))
    assert "--no-sandbox" not in exp.prefix + exp.suffix


def test_headless_linux_without_xvfb_says_what_to_install(
    no_drawio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tool(no_drawio, "drawio")
    monkeypatch.setattr(diagram_export, "_linux", lambda: True)
    with pytest.raises(ExportUnavailableError, match="sudo apt install xvfb"):
        diagram_export.find_exporter({})


def test_wsl_uses_the_windows_app_with_windows_paths(
    no_drawio: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _tool(tmp_path, "draw.io.exe")
    monkeypatch.setattr(diagram_export, "_wsl", lambda: True)
    monkeypatch.setattr(diagram_export, "WSL_APP", app)
    assert diagram_export.find_exporter({}) == Exporter((str(app),), windows=True)


def test_no_drawio_anywhere_is_reported(no_drawio: Path) -> None:
    with pytest.raises(ExportUnavailableError, match=r"draw\.io not installed"):
        diagram_export.find_exporter({})


def test_export_writes_svg_and_png_for_every_page(
    no_drawio: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _tool(no_drawio, "drawio")
    ws = _ws(tmp_path, target_drawio=ONE, target_views_drawio=VIEWS)
    diagram_export.export(ws)
    folder = ws.root / ".audit/diagrams"
    for name in ("target", "target-executive", "target-data-flow", "target-security"):
        assert (folder / f"{name}.svg").is_file()
        assert (folder / f"{name}.png").is_file()
    calls = _calls(tmp_path)
    png = next(c for c in calls if c[c.index("-f") + 1] == "png")
    svg = next(c for c in calls if c[c.index("-f") + 1] == "svg")
    assert png[png.index("-s") + 1] == "2" and "-e" not in png
    assert "--embed-svg-images" in svg
    assert "exported 10 of 10 images" in capsys.readouterr().out


def test_a_failed_page_is_reported_and_the_rest_continue(
    no_drawio: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _tool(no_drawio, "drawio")
    monkeypatch.setenv("FAIL_PAGE", "2")
    ws = _ws(tmp_path, target_views_drawio=VIEWS)
    diagram_export.export(ws)
    err = capsys.readouterr().err
    assert "target-deployment.png: draw.io exit 1, no image written" in err
    assert "exported 6 of 8 images" in err
    assert (ws.root / ".audit/diagrams/target-security.png").is_file()


def test_a_symlinked_output_is_refused(
    no_drawio: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _tool(no_drawio, "drawio")
    ws = _ws(tmp_path, target_drawio=ONE)
    outside = tmp_path / "outside.svg"
    outside.write_text("keep")
    (ws.root / ".audit/diagrams/target.svg").symlink_to(outside)
    diagram_export.export(ws)
    assert outside.read_text() == "keep"
    assert "exported 1 of 2 images" in capsys.readouterr().err


def test_no_drawio_skips_with_how_to_export_by_hand(
    no_drawio: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = _ws(tmp_path, target_drawio=ONE)
    diagram_export.export(ws)
    out = capsys.readouterr().out
    assert "diagrams have no images: draw.io not installed" in out
    assert "File > Export as" in out
    assert not (ws.root / ".audit/diagrams/target.png").exists()


def test_nothing_to_export_is_said_plainly(
    no_drawio: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    diagram_export.export(_ws(tmp_path))
    assert "no .audit/diagrams/*.drawio to export" in capsys.readouterr().out


def test_windows_app_gets_converted_paths(
    no_drawio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawio = _tool(no_drawio, "draw.io.exe")
    _tool(
        no_drawio,
        "wslpath",
        f"#!{sys.executable}\nimport sys\nprint('C:' + sys.argv[-1])\n",
    )
    monkeypatch.setattr(
        diagram_export,
        "find_exporter",
        lambda: Exporter((str(drawio),), windows=True),
    )
    ws = _ws(tmp_path, target_drawio=ONE)
    diagram_export.export(ws)
    call = _calls(tmp_path)[0]
    assert call[call.index("-o") + 1].startswith("C:")
    assert call[-1].startswith("C:") and call[-1].endswith("target.drawio")
