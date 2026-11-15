"""Python dependencies declared but not imported, and imported but not declared."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audit_kit import scan_rows, unused, unused_python
from audit_kit.inventory import build
from audit_kit.unused_python import analyse, declared, import_names, imports
from audit_kit.workspace import Workspace

PYPROJECT = """\
[project]
name = "demo"
dependencies = [
    "pillow>=10",
    "python-dateutil>=2.9",
    "opentelemetry-sdk>=1.39",
    "requests[socks]>=2 ; python_version >= '3.11'",
    "structlog",
]

[project.optional-dependencies]
office = ["markitdown>=0.1", "demo[extra]"]

[dependency-groups]
dev = ["pytest>=8", "ruff", {include-group = "docs"}]
docs = ["mkdocs"]

[tool.uv]
dev-dependencies = ["mypy"]
"""
FILES = {
    "pyproject.toml": PYPROJECT,
    "src/demo/__init__.py": "",
    "src/demo/app.py": (
        "from __future__ import annotations\n"
        "import os\n"
        "import requests\n"
        "from PIL import Image\n"
        "from opentelemetry import trace\n"
        "from importlib import import_module\n"
        "from . import helpers\n"
        "from demo.helpers import go\n"
        "import click\n"
        "def load():\n"
        "    import yaml\n"
        "    return import_module('markitdown.converter')\n"
        "def other(name):\n"
        "    return import_module(name)\n"
    ),
    "src/demo/helpers.py": "import click\n",
    "tests/test_app.py": "import pytest\nimport demo\n",
    "plugins/extra/pyproject.toml": (
        '[project]\nname = "demo-extra"\ndependencies = ["docling", "demo"]\n'
    ),
    "plugins/extra/src/demo_extra/driver.py": "import demo\nimport typer\n",
}


def write(root: Path, files: dict[str, str]) -> Workspace:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return Workspace(root)


@pytest.fixture
def report(tmp_path: Path) -> unused_python.Report:
    return analyse(write(tmp_path, FILES), FILES)


def names(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(r["file"], r["name"]) for r in rows]


def test_a_runtime_dependency_nothing_imports_is_listed(
    report: unused_python.Report,
) -> None:
    assert names(report.unused) == [
        ("plugins/extra/pyproject.toml", "docling"),
        ("pyproject.toml", "python-dateutil"),
        ("pyproject.toml", "structlog"),
    ]


def test_an_unused_row_says_where_it_is_declared_and_what_was_looked_for(
    report: unused_python.Report,
) -> None:
    row = next(r for r in report.unused if r["name"] == "python-dateutil")
    assert (row["section"], row["line"]) == ("[project] dependencies", 5)
    assert "looked for: python_dateutil, dateutil, python" in row["note"]
    assert "A package can be used with no import" in row["note"]


def test_an_import_under_another_name_counts_as_used(
    report: unused_python.Report,
) -> None:
    used = {"pillow", "opentelemetry-sdk", "requests", "markitdown"}
    assert not used & {name for _file, name in names(report.unused)}


def test_development_dependencies_are_not_checked_for_use(
    report: unused_python.Report,
) -> None:
    assert not {"ruff", "mypy", "mkdocs"} & {n for _f, n in names(report.unused)}


def test_an_import_no_dependency_provides_is_listed_once_with_its_line(
    report: unused_python.Report,
) -> None:
    assert [(r["file"], r["name"], r["line"]) for r in report.undeclared] == [
        ("plugins/extra/src/demo_extra/driver.py", "typer", 2),
        ("src/demo/app.py", "click", 9),
        ("src/demo/app.py", "yaml", 11),
    ]
    assert (
        "no dependency in pyproject.toml provides that name"
        in (report.undeclared[1]["note"])
    )


def test_a_file_belongs_to_the_nearest_manifest(report: unused_python.Report) -> None:
    assert (report.manifests, report.files) == (2, 5)
    # `demo` is declared by the plugin and is an own package: neither row applies.
    assert "demo" not in {n for _f, n in names(report.unused + report.undeclared)}


def test_a_file_that_does_not_parse_is_a_stated_problem(tmp_path: Path) -> None:
    files = {"pyproject.toml": '[project]\nname = "d"\n', "bad.py": "def (:\n"}
    found = analyse(write(tmp_path, files), files)
    assert found.problems == ["bad.py: not parsed (line 1)"]


def test_a_manifest_that_is_not_toml_is_a_stated_problem(tmp_path: Path) -> None:
    files = {"pyproject.toml": "[project\n", "a.py": "import x\n"}
    found = analyse(write(tmp_path, files), files)
    assert found.problems == ["pyproject.toml: not valid TOML"]
    assert (found.unused, found.undeclared) == ([], [])


def test_python_files_with_no_manifest_are_left_alone(tmp_path: Path) -> None:
    files = {"a.py": "import requests\n"}
    found = analyse(write(tmp_path, files), files)
    assert (found.files, found.unused, found.undeclared) == (0, [], [])


@pytest.mark.parametrize(
    ("distribution", "expected"),
    [
        ("Pillow", "PIL"),
        ("PyYAML", "yaml"),
        ("python-dateutil", "dateutil"),
        ("typing_extensions", "typing_extensions"),
        ("opentelemetry-api", "opentelemetry"),
        ("azure.identity", "azure"),
        ("requests", "requests"),
    ],
)
def test_import_names_cover_the_usual_differences(
    distribution: str, expected: str
) -> None:
    assert expected in import_names(distribution)


def test_declared_skips_what_is_not_a_requirement() -> None:
    found = declared(
        {
            "project": {"name": "d", "dependencies": ["a>=1", 7, "  "]},
            "dependency-groups": "wrong",
            "tool": {"uv": []},
        }
    )
    assert [(d.name, d.runtime) for d in found] == [("a", True)]


def test_imports_ignore_relative_imports_and_computed_names() -> None:
    text = "from . import a\nfrom .b import c\nimport_module(name)\nimport_module()\n"
    assert imports(text) == {}


def test_the_unused_report_and_the_brief_rows_carry_the_python_facts(
    tmp_path: Path,
) -> None:
    ws = write(tmp_path, FILES)
    (tmp_path / ".audit/scans").mkdir(parents=True)
    unused.write_report(ws, build(ws), ())
    index = scan_rows.build_index(ws, set(FILES))
    rows = index.of("unused", "pyproject.toml")
    assert [r.line for r in rows] == [5, 8]
    assert rows[0].text.startswith("`python-dateutil` is declared in [project]")
    (row,) = (
        index.of("unused", "src/demo/helpers.py")
        or index.of("unused", "src/demo/app.py")[:1]
    )
    assert "`click` is imported" in row.text


@pytest.mark.parametrize(
    ("source", "path", "status"),
    [
        ("unused", "pyproject.toml", "ran"),
        ("unused", "src/demo/app.py", "ran"),
        ("unused", "README.md", "not covered"),
        ("similar", "src/demo/app.py", "not covered"),
        ("design", "src/demo/app.py", "not covered"),
        ("secrets", "src/demo/app.py", "ran"),
        ("knip", "src/demo/app.py", "not run"),
    ],
)
def test_a_scan_that_does_not_read_a_file_says_not_covered(
    source: str, path: str, status: str
) -> None:
    index = scan_rows.ScanIndex(
        status={
            s.name: scan_rows.ScanStatus.RAN
            for s in scan_rows.SOURCES
            if s.name != "knip"
        }
    )
    chosen = next(s for s in scan_rows.SOURCES if s.name == source)
    assert index.status_for(chosen, path) == status


def test_a_tools_own_list_of_examined_files_decides_coverage() -> None:
    index = scan_rows.ScanIndex(
        status={"lint-python": scan_rows.ScanStatus.RAN},
        examined={"lint-python": frozenset({"a.py"})},
    )
    ruff = next(s for s in scan_rows.SOURCES if s.name == "lint-python")
    assert index.status_for(ruff, "a.py") == "ran"
    assert index.status_for(ruff, "b.py") == "not covered"
