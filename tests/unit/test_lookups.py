"""Engagement policy and public metadata lookups, with the network replaced by a fake.

These prove which URLs the kit asks for and how it reads the answers; they don't
prove the real services answer that way (python-testing, optional adapters).
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from audit_kit.errors import AuditKitError
from audit_kit.lookups import FetchError, https_fetch, look_up, render
from audit_kit.policy import load_policy
from audit_kit.workspace import Workspace

NPM = "https://registry.npmjs.org/"
LOCK = {
    "lockfileVersion": 3,
    "packages": {
        "": {"name": "demo"},
        "node_modules/express": {"version": "4.22.3"},
        "node_modules/@azure/identity": {"version": "4.0.0"},
        "node_modules/express/node_modules/debug": {"version": "2.6.9"},
    },
}
ANSWERS: dict[str, Any] = {
    NPM + "express": {
        "dist-tags": {"latest": "5.1.0"},
        "versions": {"4.22.3": {}},
        "repository": {"url": "git+https://github.com/expressjs/express.git"},
    },
    NPM + "@azure%2Fidentity": {
        "versions": {"4.0.0": {"deprecated": "use 4.1.0"}},
        "repository": {"url": "https://github.com/Azure/azure-sdk-for-js"},
    },
    "https://api.github.com/repos/expressjs/express": {
        "archived": False,
        "pushed_at": "2026-10-01T00:00:00Z",
    },
    "https://api.github.com/repos/Azure/azure-sdk-for-js": {"archived": False},
    "https://api.github.com/repos/vladmandic/face-api": {
        "archived": True,
        "pushed_at": "2025-02-05T00:00:00Z",
    },
    "https://endoflife.date/api/nodejs.json": [
        {"cycle": "22", "eol": "2027-04-30", "support": "2025-10-21"}
    ],
}


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    (root / ".audit").mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"express": "^4.22.3", "@azure/identity": "^4.0.0"},
                "engines": {"node": ">=22"},
            }
        )
    )
    (root / "package-lock.json").write_text(json.dumps(LOCK))
    entry = {
        "path": "public/vendor/face-api.js",
        "cls": "vendored",
        "upstream": "https://github.com/vladmandic/face-api",
    }
    (root / ".audit/inventory.json").write_text(json.dumps({"entries": [entry]}))
    return Workspace(root)


def recording(answers: dict[str, Any]) -> tuple[Callable[[str], Any], list[str]]:
    asked: list[str] = []

    def fetch(url: str) -> Any:
        asked.append(url)
        if url not in answers:
            raise FetchError("HTTP 404", status=404)
        return answers[url]

    return fetch, asked


def test_policy_defaults_to_deny_when_the_file_is_missing(ws: Workspace) -> None:
    assert load_policy(ws).network.metadata_lookups == "deny"


def test_policy_rejects_unknown_keys_and_values(ws: Workspace) -> None:
    (ws.root / ".audit/policy.yaml").write_text(
        "version: 1\nnetwork: {metadata_lookup: allow}\n"
    )
    with pytest.raises(AuditKitError, match="metadata_lookup"):
        load_policy(ws)
    (ws.root / ".audit/policy.yaml").write_text(
        "version: 1\nnetwork: {metadata_lookups: yes}\n"
    )
    with pytest.raises(AuditKitError, match="metadata_lookups"):
        load_policy(ws)


def test_lookups_find_deprecated_archived_and_end_of_life(ws: Workspace) -> None:
    fetch, asked = recording(ANSWERS)
    results = {(s.subject, s.check): s for s in look_up(ws, fetch)}
    assert results[("@azure/identity@4.0.0", "npm deprecated")].result == "deprecated"
    assert results[("express@4.22.3", "npm deprecated")].result == "not deprecated"
    face = results[("vladmandic/face-api", "GitHub archived")]
    assert face.result == "archived"
    assert "public/vendor/face-api.js" in face.detail
    node = results[("node 22", "Node.js end of life")]
    assert "end of life 2027-04-30" in node.detail
    # Only names, versions and repository names are sent; nested packages are not.
    assert all("debug" not in url for url in asked)


def test_a_failed_lookup_is_recorded_not_fatal(ws: Workspace) -> None:
    fetch, _ = recording({})
    results = look_up(ws, fetch)
    assert {s.result for s in results} <= {"unknown", "not found"}
    assert any(s.result == "not found" for s in results)


def test_only_allow_listed_https_hosts_are_contacted() -> None:
    for url in ("http://registry.npmjs.org/x", "https://example.com/x"):
        with pytest.raises(AuditKitError, match="refused"):
            https_fetch(url)


def test_a_denied_run_says_so(ws: Workspace) -> None:
    assert json.loads(render([], allowed=False))["policy"] == "deny"


def test_recommended_packages_are_checked(ws: Workspace) -> None:
    (ws.root / ".audit/03-engineering.md").write_text(
        "### ENG-001 Clone\n- Packages: `lodash.clonedeep`, made-up-pkg\n"
        "### ENG-002 Old\n- Packages: request old-lib\n"
    )
    answers = {
        **ANSWERS,
        NPM + "lodash.clonedeep": {
            "dist-tags": {"latest": "4.5.0"},
            "versions": {"4.5.0": {}},
            "time": {"4.5.0": "2016-08-13T00:00:00Z"},
        },
        NPM + "request": {
            "dist-tags": {"latest": "2.88.2"},
            "versions": {"2.88.2": {"deprecated": "request has been deprecated"}},
        },
        NPM + "old-lib": {
            "dist-tags": {"latest": "1.0.0"},
            "versions": {"1.0.0": {}},
            "time": {"1.0.0": "2026-01-01T00:00:00Z"},
        },
    }
    fetch, _ = recording(answers)
    found = [
        (s.subject, s.result)
        for s in look_up(ws, fetch, today=datetime.date(2026, 11, 7))
        if s.check == "recommended package"
    ]
    assert found == [
        ("lodash.clonedeep", "prefer built-in"),
        ("lodash.clonedeep", "stale"),
        ("made-up-pkg", "not found"),
        ("old-lib", "exists"),
        ("request", "deprecated"),
    ]


def test_only_a_404_means_a_recommended_package_does_not_exist(ws: Workspace) -> None:
    # Review finding F9: decided by status, not by the message text.
    (ws.root / ".audit/03-engineering.md").write_text(
        "### ENG-001 X\n- Packages: busy-pkg\n"
    )

    def fetch(url: str) -> Any:
        raise FetchError("HTTP 503 (mentions 404 in passing)", status=503)

    found = [s for s in look_up(ws, fetch) if s.check == "recommended package"]
    assert [s.result for s in found] == ["unknown"]
