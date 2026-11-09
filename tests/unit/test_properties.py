"""Properties of the checks that guard evidence and paths (review finding F10).

Hand-picked examples missed the mount-option bug (F1), so these generate inputs.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from audit_kit import sandbox as sb
from audit_kit.errors import AuditKitError
from audit_kit.units import (
    BOUNDARY,
    MARKUP_BOUNDARY,
    MAX_LINES,
    STYLE_BOUNDARY,
    sections,
)
from audit_kit.verification import excerpt_problem
from audit_kit.workspace import Workspace

CODE_LINE = st.text(
    alphabet=string.ascii_letters + string.digits + " (){};=.'\"",
    max_size=40,
)
DECLARATION = st.sampled_from(["function f() {", "const x = 1;", "class A {", "  x();"])
PLAIN = st.text(
    alphabet=string.ascii_letters + string.digits + " ();=", min_size=1, max_size=30
)
SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


BOUNDARIES = st.sampled_from([BOUNDARY, MARKUP_BOUNDARY, STYLE_BOUNDARY])
REGION = st.sampled_from(["<section>", "<div class='x'>", ".btn {", "@media (x) {"])


@SETTINGS
@given(
    st.lists(st.one_of(CODE_LINE, DECLARATION, REGION), max_size=3500),
    st.integers(1, 5000),
    BOUNDARIES,
)
def test_sections_cover_every_line_once_within_the_limit(
    lines: list[str], first: int, boundary: re.Pattern[str]
) -> None:
    spans = sections(lines, first, boundary)
    covered = [n for a, b in spans for n in range(a, b + 1)]
    assert covered == list(range(first, first + len(lines)))
    assert all(b - a + 1 <= MAX_LINES for a, b in spans)


@SETTINGS
@given(st.lists(PLAIN, min_size=1, max_size=30), st.data())
def test_any_span_cut_from_a_file_matches_its_lines(
    tmp_path_factory: pytest.TempPathFactory, lines: list[str], data: st.DataObject
) -> None:
    root = tmp_path_factory.mktemp("ws")
    (root / "a.js").write_text("\n".join(lines) + "\n")
    ws = Workspace(root)
    start = data.draw(st.integers(1, len(lines)))
    end = data.draw(st.integers(start, len(lines)))
    excerpt = "`" + " ".join(lines[start - 1 : end]) + "`"
    if not excerpt.strip("` "):
        return
    assert excerpt_problem(ws, f"a.js:{start}-{end}", excerpt) is None
    missing = "`zz" + "".join(lines[start - 1 : end]).replace(" ", "") + "zz`"
    assert excerpt_problem(ws, f"a.js:{start}-{end}", missing) is not None


NAME = st.text(alphabet=string.printable, min_size=1, max_size=20)


@SETTINGS
@given(st.lists(NAME, min_size=1, max_size=4))
def test_agent_paths_never_leave_work_or_carry_mount_options(
    tmp_path_factory: pytest.TempPathFactory, parts: list[str]
) -> None:
    root = tmp_path_factory.mktemp("ws")
    (root / ".audit/work").mkdir(parents=True)
    given_path = "/".join([".audit", "work", *parts]) + ".js"
    target = root / given_path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x();\n")
    except (OSError, ValueError):
        return
    try:
        (job,) = sb.plan("try", Workspace(root), given_path)
    except AuditKitError:
        return
    source, mounted = job.extra_mounts[0]
    assert Path(source).resolve().is_relative_to((root / ".audit/work").resolve())
    assert not any(c in str(source) + mounted for c in ",=\"'\n")
