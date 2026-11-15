"""The kit finds the secret scan's values again, masks them, and keeps them out."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from audit_kit import leaks, scan_rows, scans, verification
from audit_kit.verification import Status
from audit_kit.workspace import Workspace

KIT = Path(__file__).resolve().parents[2]
# Made up for these tests: no service issues a value of this shape.
VALUE = "q7Jx2mPz9LkR4tVb8NcW3sHd"
OTHER = "Zr5Tg1Yh6Uj2Ik8Ol3Pq9Wm4"
CODE = (
    f'first = "{VALUE}"\n'  # 1: the rule matched the value and its quotes
    f'r.add_header("Authorization", "Bearer {VALUE}")\n'  # 2
    f"{OTHER}\n"  # 3: the rule matched nothing but the value
    f'a = "x"; b = "{OTHER}"; c = "y"\n'  # 4
)


def leak(line: int, start: int, end: int, match: str, **more: Any) -> dict[str, Any]:
    """Return one finding as gitleaks writes it with --redact."""
    base = {
        "RuleID": "rule",
        "Description": "d",
        "File": "app.py",
        "StartLine": line,
        "EndLine": line,
        "StartColumn": start,
        "EndColumn": end,
        "Match": match,
        "Secret": "REDACTED",
    }
    return base | more


# Columns as gitleaks reports them: from 1 on the first line, from 2 after it.
FOUND = [
    leak(1, 9, 34, '"REDACTED"'),
    leak(2, 32, 64, '"Bearer REDACTED"'),
    leak(3, 2, 25, "REDACTED"),
    leak(4, 15, 40, '"REDACTED"'),
]


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    (root / ".audit/scans").mkdir(parents=True)
    (root / "app.py").write_text(CODE)
    (root / ".audit/scans/secrets.json").write_text(json.dumps(FOUND))
    return Workspace(root)


def rewrite(ws: Workspace, found: list[dict[str, Any]]) -> None:
    ws.write_text(leaks.SCAN, json.dumps(found))


def test_every_value_is_found_again_from_the_redacted_scan(ws: Workspace) -> None:
    found = leaks.load(ws)
    assert (found.total, found.unlocated) == (4, 0)
    assert found.values == {VALUE, OTHER}


def test_a_masked_file_holds_no_value_and_keeps_the_rest(ws: Workspace) -> None:
    masked = leaks.load(ws).mask("app.py", CODE.split("\n"))
    assert masked[:4] == [
        'first = "****"',
        'r.add_header("Authorization", "Bearer ****")',
        "****",
        'a = "x"; b = "****"; c = "y"',
    ]


def test_a_file_with_no_finding_is_returned_as_it_is(ws: Workspace) -> None:
    lines = ["a", "b"]
    assert leaks.load(ws).mask("other.py", lines) is lines


def test_the_text_around_the_value_decides_not_the_column(ws: Workspace) -> None:
    # The column is two out; `"x"` and `"y"` would fit a shorter value only.
    rewrite(ws, [leak(4, 13, 38, '"REDACTED"')])
    assert leaks.load(ws).spans == {"app.py": [leaks.Span(4, 14, 38)]}


def test_two_rules_on_one_value_leave_one_mask(ws: Workspace) -> None:
    rewrite(ws, [FOUND[1], leak(2, 40, 64, 'REDACTED"')])
    masked = leaks.load(ws).mask("app.py", CODE.split("\n"))
    assert masked[1] == 'r.add_header("Authorization", "Bearer ****")'


def test_a_value_that_moved_since_the_scanned_commit_is_found_by_its_text(
    ws: Workspace,
) -> None:
    moved = "# a new first line\n" + CODE
    ws.write_text("app.py", moved)
    rewrite(ws, [FOUND[1]])
    found = leaks.load(ws)
    assert found.spans == {"app.py": [leaks.Span(3, 38, 62)]}
    assert found.values == {VALUE}


def test_a_key_over_several_lines_is_masked_line_by_line(ws: Workspace) -> None:
    body = "MIIEowIBAAKCAQEAx0y1z2"
    ws.write_text(
        "key.pem", f"-----BEGIN KEY-----\n  {body}\n\n-----END KEY-----\nafter\n"
    )
    rewrite(ws, [leak(1, 1, 18, "REDACTED", File="key.pem", EndLine=4)])
    found = leaks.load(ws)
    masked = found.mask("key.pem", ws.read_text("key.pem").split("\n"))
    assert masked == ["****", "  ****", "", "****", "after", ""]
    # The first and last line of a key are the same in every key: not a value.
    assert found.values == {body}


@pytest.mark.parametrize(
    "finding",
    [
        leak(9, 1, 5, "REDACTED"),  # a line the file doesn't have
        leak(1, 1, 5, "no value marker"),
        leak(1, 1, 5, "REDACTED and REDACTED"),
        leak(1, 9, 9, '"REDACTED"'),  # shorter than what surrounds it
        leak(2, 1, 30, 'nothing like this"REDACTED"'),
        leak(1, 1, 5, "REDACTED", File="gone.py"),
        leak(1, 1, 5, "REDACTED", File="../outside.py"),
    ],
)
def test_a_finding_that_cannot_be_placed_is_counted_not_guessed(
    ws: Workspace, finding: dict[str, Any]
) -> None:
    rewrite(ws, [finding])
    found = leaks.load(ws)
    assert (found.total, found.unlocated, found.spans) == (1, 1, {})


def test_a_finding_in_a_kit_folder_is_not_the_targets(ws: Workspace) -> None:
    ws.write_text(".audit/04-security.md", f'"{VALUE}"\n')
    rewrite(ws, [leak(1, 1, 26, '"REDACTED"', File=".audit/04-security.md")])
    assert leaks.load(ws) == leaks.Leaks()


def test_a_file_too_large_to_read_leaves_its_findings_unplaced(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(leaks, "FILE_BYTES", 10)
    assert leaks.load(ws).unlocated == 4


def test_no_scan_and_an_unreadable_scan_are_told_apart(ws: Workspace) -> None:
    ws.write_text(leaks.SCAN, "{not json")
    assert leaks.load(ws).problem == "ValidationError"
    ws.path(leaks.SCAN).unlink()
    assert leaks.load(ws) == leaks.Leaks()


def test_a_short_value_is_not_searched_for_in_outputs() -> None:
    found = leaks.Leaks(values=frozenset({"abc", VALUE}))
    assert found.lines_holding(f"abc\nfine\nkey {VALUE} here\n") == [3]
    assert leaks.Leaks(values=frozenset({"abc"})).lines_holding("abc\n") == []


def test_the_brief_index_carries_the_masks(ws: Workspace) -> None:
    index = scan_rows.build_index(ws, {"app.py"})
    assert VALUE not in "\n".join(index.leaks.mask("app.py", CODE.split("\n")))
    assert scan_rows.build_index(ws, {"other.py"}).leaks.spans == {}


def r7(ws: Workspace) -> list[verification.Result]:
    report = verification.Report()
    verification._check_secret_values(ws, report)
    return report.results


def test_an_output_that_holds_a_value_fails_with_its_lines_only(ws: Workspace) -> None:
    ws.write_text(".audit/04-security.md", f"ok\n`Bearer {VALUE}`\nok\n{OTHER}\n")
    ws.write_text(".audit/files/app.py.md", "masked: `Bearer ****`\n")
    ws.write_text(".audit/scans/raw.txt", VALUE)
    ws.write_text(".audit/audit.duckdb", VALUE)
    (result,) = r7(ws)
    assert result.status is Status.FAIL
    assert result.detail.startswith(
        "04-security.md: holds a value the secret scan found, at line(s) 2, 4;"
    )
    assert VALUE not in result.detail
    assert OTHER not in result.detail


def test_many_outputs_with_a_value_are_listed_up_to_a_limit(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verification, "SECRET_FILES_SHOWN", 2)
    for n in range(4):
        ws.write_text(f".audit/files/f{n}.md", "\n".join([VALUE] * 7))
    details = [r.detail for r in r7(ws)]
    assert len(details) == 3
    assert "at line(s) 1, 2, 3, 4, 5 and 2 more" in details[0]
    assert details[2] == "2 more outputs hold a value"


def test_clean_outputs_pass_and_say_what_was_not_searched_for(ws: Workspace) -> None:
    ws.write_text(".audit/04-security.md", "`Bearer ****`\n")
    rewrite(ws, [*FOUND, leak(1, 1, 5, "REDACTED", File="gone.py")])
    (result,) = r7(ws)
    assert result.status is Status.PASS
    assert "1 outputs searched for 4 of 5 scan findings" in result.detail
    assert "1 not in the files as they are now" in result.detail


def test_the_check_waits_for_the_scan_and_fails_on_one_it_cannot_read(
    ws: Workspace,
) -> None:
    ws.write_text(leaks.SCAN, "[")
    assert [r.status for r in r7(ws)] == [Status.FAIL]
    ws.path(leaks.SCAN).unlink()
    assert [r.status for r in r7(ws)] == [Status.SKIP]


def test_a_target_ignore_file_is_counted(ws: Workspace) -> None:
    assert scans._ignored_leaks(ws) == 0
    ws.write_text(".gitleaksignore", "# why\n\napp.py:rule:1\napp.py:rule:2\n")
    assert scans._ignored_leaks(ws) == 2


HITS = (
    f'r.add_header("Authorization", "Bearer {VALUE}")\n'
    f'h = {{"Authorization": "Token {VALUE}"}}\n'
    f'c.set("X-Api-Key", "{VALUE}")\n'
    f'x = "Bearer {OTHER}"  # gitleaks:allow\n'
)
MISSES = (
    'r.add_header("Authorization", f"Bearer {token}")\n'
    'h = {"Authorization": "Bearer <your-token-goes-here-please>"}\n'
    'h = {"Authorization": "Bearer xxxxxxxxxxxxxxxxxxxxxxxx"}\n'
    'c.set("token", "application/octet-stream")\n'
    'log("token", "the token was refused by the server")\n'
    'print("Basic usage of the tool is described below")\n'
)


@pytest.mark.integration
def test_the_kit_rules_find_credentials_the_default_rules_miss(tmp_path: Path) -> None:
    gitleaks = shutil.which("gitleaks")
    if gitleaks is None:
        pytest.skip("gitleaks not installed")
    root = tmp_path / "ws"
    (root / ".audit/scans").mkdir(parents=True)
    (root / "hits.py").write_text(HITS)
    (root / "misses.py").write_text(MISSES)
    # A target's own config that allows everything must not apply.
    (root / ".gitleaks.toml").write_text('[allowlist]\npaths = [".*"]\n')
    subprocess.run(
        [gitleaks, "dir", "--no-banner", "--redact", "--exit-code", "0",
         "--config", str(KIT / scans.GITLEAKS_CONFIG), "--ignore-gitleaks-allow",
         "-f", "json", "-r", str(root / leaks.SCAN), "."],
        cwd=root, check=True, capture_output=True, timeout=120,
    )  # fmt: skip
    rows = json.loads((root / leaks.SCAN).read_text())
    assert sorted((r["File"], r["StartLine"], r["RuleID"]) for r in rows) == [
        ("hits.py", 1, "kit-authorization-literal"),
        ("hits.py", 2, "kit-authorization-literal"),
        ("hits.py", 3, "kit-credential-argument"),
        ("hits.py", 4, "kit-authorization-literal"),
    ]
    # The redacted report is enough to mask every value in the real file.
    found = leaks.load(Workspace(root))
    assert found.unlocated == 0
    masked = "\n".join(found.mask("hits.py", HITS.split("\n")))
    assert VALUE not in masked
    assert OTHER not in masked
    assert masked.count(leaks.MASK) == 4
