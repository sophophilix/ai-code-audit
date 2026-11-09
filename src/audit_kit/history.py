"""Where change concentrates: hotspots and files that change together (no AI).

ADR 0004 D9. Reads `git log` up to the audited commit, never to today, so a re-run
on the same snapshot gives the same file. Authors are counted, never named
(AGENTS.md rule 6). Without history (an eval snapshot), the file says so and
nothing is estimated.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from itertools import combinations
from typing import Any

from audit_kit.code_facts import match_tool_paths
from audit_kit.workspace import Workspace

OUTPUT = ".audit/scans/hotspots.json"
LINT = ".audit/scans/lint.json"
SHOWN = 30
COUPLED_MIN = 5
# A commit touching more files than this is a bulk change (formatting, rename,
# vendoring) and says nothing about which files depend on each other.
BULK = 50
COMPLEXITY = re.compile(r"complexity of (\d+)")
RECORD = "\x1e"


def parse_log(text: str) -> list[tuple[str, list[tuple[str, int]]]]:
    """Parse `git log --numstat --format=<RS>%ae` into (author, [(path, lines)])."""
    commits: list[tuple[str, list[tuple[str, int]]]] = []
    for block in text.split(RECORD)[1:]:
        head, _, body = block.partition("\n")
        files: list[tuple[str, int]] = []
        for line in body.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[2]:
                added, deleted = (int(p) if p.isdigit() else 0 for p in parts[:2])
                files.append((parts[2], added + deleted))
        commits.append((head.strip().lower(), files))
    return commits


def complexity(ws: Workspace, own: set[str]) -> dict[str, int]:
    """Highest ESLint `complexity` per own file, from lint.json.

    Lint paths are absolute for the machine the scan ran on, so they're matched
    the same way coverage.json matches them, which survives a moved workspace.
    """
    if not ws.is_file(LINT):
        return {}
    try:
        results = json.loads(ws.read_text(LINT, limit=500_000_000))
    except json.JSONDecodeError:
        return {}
    rows = (
        [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []
    )
    paths = match_tool_paths(ws.root, [str(r.get("filePath", "")) for r in rows], own)
    worst: dict[str, int] = {}
    for result in rows:
        path = paths.get(str(result.get("filePath", "")).strip())
        if path is None:
            continue
        for message in result.get("messages") or []:
            m = COMPLEXITY.search(str(message.get("message", "")))
            if message.get("ruleId") == "complexity" and m:
                worst[path] = max(worst.get(path, 0), int(m.group(1)))
    return worst


def analyse(
    commits: list[tuple[str, list[tuple[str, int]]]],
    own: set[str],
    worst: dict[str, int],
) -> dict[str, Any]:
    """Rank own files by changes times complexity, and find coupled pairs."""
    changes: Counter[str] = Counter()
    churn: Counter[str] = Counter()
    authors: dict[str, set[str]] = {}
    pairs: Counter[tuple[str, str]] = Counter()
    for author, files in commits:
        paths = sorted({p for p, _ in files if p in own})
        for path, lines in files:
            if path in own:
                churn[path] += lines
                authors.setdefault(path, set()).add(author)
        changes.update(paths)
        if len(paths) <= BULK:
            pairs.update(combinations(paths, 2))
    most = max(changes.values(), default=1)
    hardest = max(worst.values(), default=1)
    ranked: list[dict[str, Any]] = [
        {
            "file": path,
            "commits": n,
            "lines_changed": churn[path],
            "authors": len(authors.get(path, ())),
            "max_complexity": worst.get(path, 0),
            # Normalised changes times normalised complexity; files lint didn't
            # score count as complexity 1, so change alone still ranks them.
            "score": round(n / most * max(worst.get(path, 1), 1) / hardest, 4),
        }
        for path, n in changes.items()
    ]
    ranked.sort(key=lambda f: (-f["score"], -f["commits"], f["file"]))
    coupled = [
        {"files": list(pair), "commits_together": n}
        for pair, n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))
        if n >= COUPLED_MIN
    ]
    return {
        "commits": len(commits),
        "files_changed": len(changes),
        "hotspots": ranked[:SHOWN],
        "coupled": coupled[:SHOWN],
    }


def report(
    log: str | None, own: set[str], ws: Workspace, commit: str, failure: str = ""
) -> dict[str, Any]:
    """Build hotspots.json.

    Args:
        log: `git log` output, or None when there's no history or it failed.
        own: Own files, the only ones ranked.
        ws: The workspace, for lint.json.
        commit: The audited commit the log ends at.
        failure: Why `git log` failed, if it did; recorded as the gap.
    """
    head = {
        "generated_by": "kit scan: git history (deterministic, ends at the audited commit)",
        "commit": commit,
    }
    if failure:
        return {**head, "gap": f"{failure}; hotspots and coupling are not estimated"}
    if log is None:
        return {
            **head,
            "gap": "no git history in this workspace (an eval snapshot or a copy); "
            "hotspots and coupling are not estimated",
        }
    commits = parse_log(log)
    if len(commits) < 2:
        return {**head, "gap": f"{len(commits)} commit(s): too little history to rank"}
    return {
        **head,
        "method": (
            "Own files only. score = (commits / most commits) x (max ESLint "
            "complexity / highest complexity). Pairs that change together in at "
            f"least {COUPLED_MIN} commits, ignoring commits that touch over {BULK} "
            "own files. Authors counted, never named."
        ),
        **analyse(commits, own, complexity(ws, own)),
    }
