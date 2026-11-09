"""Public metadata lookups for supply-chain status, gated by the engagement policy.

This is the kit's only network boundary. It runs only when a person runs
`kit lookup` and `.audit/policy.yaml` allows it, contacts only the hosts in
HOSTS, and sends package names, versions and repository names: never code, file
contents, hashes or the target's own name. A failed lookup is recorded and the
run continues; nothing here is retried, because a person re-runs the command.
"""

from __future__ import annotations

import datetime
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote, urlparse

from audit_kit.errors import AuditKitError, WorkspaceError
from audit_kit.findings import parse_findings
from audit_kit.inventory import INVENTORY_PATH
from audit_kit.manifest import load_manifest
from audit_kit.workspace import Workspace

HOSTS = frozenset({"registry.npmjs.org", "api.github.com", "endoflife.date"})
OUTPUT = ".audit/scans/upstream-status.json"
TIMEOUT = 20.0
MAX_RESPONSE_BYTES = 64_000_000
GITHUB_REPO = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?]|$)")
LOCK_LIMIT = 50_000_000
# A recommended package with no release for this long is reported as stale.
STALE_DAYS = 730
FINDINGS = ("01-discovery.md", "02-architecture.md", "03-engineering.md",
            "04-security.md", "05-accessibility.md")  # fmt: skip
PACKAGE_NAME = re.compile(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$")
# Built-ins a report should recommend instead of these packages (ADR 0004 D8).
# The kit's own list; each entry links the page that documents the built-in.
NATIVE = {
    "lodash.clonedeep": ("structuredClone()", "https://developer.mozilla.org/en-US/docs/Web/API/Window/structuredClone"),
    "node-fetch": ("the global fetch() in Node.js", "https://nodejs.org/api/globals.html#fetch"),
    "uuid": ("crypto.randomUUID(), for version 4 UUIDs", "https://nodejs.org/api/crypto.html#cryptorandomuuidoptions"),
    "left-pad": ("String.prototype.padStart()", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/padStart"),
    "object-assign": ("Object.assign()", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/assign"),
    "array-includes": ("Array.prototype.includes()", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/includes"),
    "array-flatten": ("Array.prototype.flat()", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/flat"),
    "abort-controller": ("the global AbortController in Node.js", "https://nodejs.org/api/globals.html#class-abortcontroller"),
    "rimraf": ("fs.rm(path, { recursive: true })", "https://nodejs.org/api/fs.html#fspromisesrmpath-options"),
    "mkdirp": ("fs.mkdir(path, { recursive: true })", "https://nodejs.org/api/fs.html#fspromisesmkdirpath-options"),
}  # fmt: skip

Fetch = Callable[[str], Any]


class FetchError(AuditKitError):
    """A lookup failed (network, HTTP status, or a response that isn't JSON).

    Attributes:
        status: The HTTP status for an HTTP error, otherwise None.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        """Record the message and, for an HTTP error, its status."""
        super().__init__(message)
        self.status = status


def https_fetch(url: str) -> Any:
    """GET a JSON document from an allow-listed host.

    Raises:
        AuditKitError: If the URL isn't https on an allow-listed host.
        FetchError: If the request fails or the response isn't JSON.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS:
        raise AuditKitError(f"refused: {url} is not an allow-listed https host")
    request = urllib.request.Request(  # noqa: S310  scheme and host checked above
        url,
        headers={"Accept": "application/json", "User-Agent": "agent-audit-kit"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310  # nosec B310
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"unreachable ({exc})") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise FetchError("response too large")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError("response is not JSON") from exc


@dataclass(frozen=True)
class Status:
    """One looked-up fact, with where it came from."""

    subject: str
    check: str
    result: str
    detail: str
    source: str


def _locked_versions(ws: Workspace) -> dict[str, str]:
    """Return {package: version} for top-level packages in package-lock.json."""
    if not ws.is_file("package-lock.json"):
        return {}
    try:
        raw = json.loads(ws.read_text("package-lock.json", limit=LOCK_LIMIT))
    except (WorkspaceError, json.JSONDecodeError):
        return {}
    packages = raw.get("packages") if isinstance(raw, dict) else None
    if not isinstance(packages, dict):
        return {}
    found: dict[str, str] = {}
    for key, value in packages.items():
        if (
            isinstance(key, str)
            and key.startswith("node_modules/")
            and "/node_modules/" not in key
            and isinstance(value, dict)
            and isinstance(value.get("version"), str)
        ):
            found[key.removeprefix("node_modules/")] = value["version"]
    return found


def _github_repo(url: str) -> str:
    match = GITHUB_REPO.search(url)
    return f"{match.group(1)}/{match.group(2)}" if match else ""


def _npm(name: str, version: str, fetch: Fetch) -> tuple[list[Status], str]:
    """Check deprecation of the locked version; return statuses and the repository."""
    url = f"https://registry.npmjs.org/{quote(name, safe='@')}"
    try:
        doc = fetch(url)
    except FetchError as exc:
        return [Status(name, "npm deprecated", "unknown", str(exc), url)], ""
    versions = doc.get("versions", {}) if isinstance(doc, dict) else {}
    latest = (
        (doc.get("dist-tags") or {}).get("latest", "") if isinstance(doc, dict) else ""
    )
    meta = versions.get(version) if isinstance(versions, dict) else None
    statuses: list[Status] = []
    if not isinstance(meta, dict):
        statuses.append(
            Status(
                f"{name}@{version}",
                "npm deprecated",
                "unknown",
                "version not in the registry",
                url,
            )
        )
    elif meta.get("deprecated"):
        statuses.append(
            Status(
                f"{name}@{version}",
                "npm deprecated",
                "deprecated",
                str(meta["deprecated"])[:300],
                url,
            )
        )
    else:
        statuses.append(
            Status(
                f"{name}@{version}",
                "npm deprecated",
                "not deprecated",
                f"latest {latest}",
                url,
            )
        )
    repository = doc.get("repository") if isinstance(doc, dict) else None
    repo_url = (
        repository.get("url", "")
        if isinstance(repository, dict)
        else str(repository or "")
    )
    return statuses, _github_repo(repo_url)


def _github(repo: str, why: str, fetch: Fetch) -> Status:
    url = f"https://api.github.com/repos/{repo}"
    try:
        doc = fetch(url)
    except FetchError as exc:
        result = "not found" if "HTTP 404" in str(exc) else "unknown"
        return Status(repo, "GitHub archived", result, f"{why}; {exc}", url)
    if not isinstance(doc, dict):
        return Status(
            repo, "GitHub archived", "unknown", f"{why}; unexpected response", url
        )
    archived = doc.get("archived") is True
    pushed = str(doc.get("pushed_at") or "")[:10]
    return Status(
        repo,
        "GitHub archived",
        "archived" if archived else "not archived",
        f"{why}; last push {pushed or 'unknown'}",
        url,
    )


def _node(ws: Workspace, fetch: Fetch) -> list[Status]:
    """Compare the lowest Node.js major the project allows with its end-of-life date."""
    try:
        raw = (
            json.loads(ws.read_text("package.json"))
            if ws.is_file("package.json")
            else {}
        )
    except (WorkspaceError, json.JSONDecodeError):
        return []
    engines = raw.get("engines") if isinstance(raw, dict) else None
    declared = engines.get("node") if isinstance(engines, dict) else None
    url = "https://endoflife.date/api/nodejs.json"
    if not isinstance(declared, str):
        return [
            Status(
                "node",
                "Node.js end of life",
                "unknown",
                "engines.node not declared in package.json",
                "package.json",
            )
        ]
    match = re.search(r"\d+", declared)
    if not match:
        return [
            Status(
                "node",
                "Node.js end of life",
                "unknown",
                f"engines.node '{declared}' has no version",
                "package.json",
            )
        ]
    major = match.group(0)
    try:
        cycles = fetch(url)
    except FetchError as exc:
        return [
            Status(f"node {major}", "Node.js end of life", "unknown", str(exc), url)
        ]
    for cycle in cycles if isinstance(cycles, list) else []:
        if isinstance(cycle, dict) and str(cycle.get("cycle")) == major:
            return [
                Status(
                    f"node {major}",
                    "Node.js end of life",
                    "dated",
                    f"engines.node '{declared}'; end of life {cycle.get('eol')}; support {cycle.get('support')}",
                    url,
                )
            ]
    return [
        Status(
            f"node {major}", "Node.js end of life", "unknown", "cycle not listed", url
        )
    ]


def vendored_upstreams(ws: Workspace) -> dict[str, list[str]]:
    """Return {owner/repo: [vendored paths]} from the inventory's upstream leads."""
    if not ws.is_file(INVENTORY_PATH):
        return {}
    try:
        raw = json.loads(ws.read_text(INVENTORY_PATH, limit=LOCK_LIMIT))
    except (WorkspaceError, json.JSONDecodeError):
        return {}
    found: dict[str, list[str]] = {}
    for entry in raw.get("entries", []) if isinstance(raw, dict) else []:
        if isinstance(entry, dict) and entry.get("cls") == "vendored":
            repo = _github_repo(str(entry.get("upstream") or ""))
            if repo:
                found.setdefault(repo, []).append(str(entry.get("path")))
    return found


def recommended_packages(ws: Workspace) -> dict[str, list[str]]:
    """Return {package: [finding IDs]} from `- Packages:` fields in the findings."""
    found: dict[str, list[str]] = {}
    for name in FINDINGS:
        rel = f".audit/{name}"
        if not ws.is_file(rel):
            continue
        for f in parse_findings(ws.read_text(rel, limit=LOCK_LIMIT)):
            for package in re.split(r"[\s,]+", f.get("Packages").strip("` ")):
                package = package.strip("`")
                if package and PACKAGE_NAME.match(package):
                    found.setdefault(package, []).append(f.id)
    return dict(sorted(found.items()))


def _recommended(
    name: str, ids: list[str], fetch: Fetch, today: datetime.date
) -> list[Status]:
    """Check a package an agent recommends: it exists, is current, has no built-in."""
    url = f"https://registry.npmjs.org/{quote(name, safe='@')}"
    who = f"recommended in {', '.join(ids)}"
    statuses: list[Status] = []
    if name in NATIVE:
        builtin, source = NATIVE[name]
        statuses.append(
            Status(
                name,
                "recommended package",
                "prefer built-in",
                f"{who}; use {builtin}",
                source,
            )
        )
    try:
        doc = fetch(url)
    except FetchError as exc:
        missing = exc.status == 404
        result = "not found" if missing else "unknown"
        detail = (
            "no such package on npm: remove the recommendation" if missing else str(exc)
        )
        return [
            *statuses,
            Status(name, "recommended package", result, f"{who}; {detail}", url),
        ]
    doc = doc if isinstance(doc, dict) else {}
    latest = str((doc.get("dist-tags") or {}).get("latest", ""))
    meta = (doc.get("versions") or {}).get(latest) or {}
    published = str((doc.get("time") or {}).get(latest, ""))[:10]
    try:
        age = (today - datetime.date.fromisoformat(published)).days
    except ValueError:
        age = -1
    if isinstance(meta, dict) and meta.get("deprecated"):
        result, detail = "deprecated", str(meta["deprecated"])[:300]
    elif age > STALE_DAYS:
        result, detail = "stale", f"latest {latest} published {published}"
    elif age < 0:
        result, detail = "unknown", f"latest {latest}, publish date not given"
    else:
        result, detail = "exists", f"latest {latest} published {published}"
    return [
        *statuses,
        Status(name, "recommended package", result, f"{who}; {detail}", url),
    ]


def look_up(
    ws: Workspace, fetch: Fetch | None = None, today: datetime.date | None = None
) -> list[Status]:
    """Run every lookup for a workspace. The caller has checked the policy.

    Args:
        ws: The workspace.
        fetch: Replaces https_fetch (tests); resolved at call time.
        today: The date staleness is measured from (tests); today in UTC otherwise.
    """
    fetch = fetch or https_fetch
    today = today or datetime.datetime.now(datetime.UTC).date()
    statuses: list[Status] = []
    repos: dict[str, str] = {}
    loaded = load_manifest(ws).manifest
    locked = _locked_versions(ws)
    for name in sorted(loaded.dependencies if loaded else {}):
        version = locked.get(name)
        if not version:
            statuses.append(
                Status(
                    name,
                    "npm deprecated",
                    "unknown",
                    "no locked version in package-lock.json",
                    "package-lock.json",
                )
            )
            continue
        found, repo = _npm(name, version, fetch)
        statuses += found
        if repo:
            repos.setdefault(repo, f"repository of dependency {name}")
    for repo, paths in sorted(vendored_upstreams(ws).items()):
        repos.setdefault(repo, f"named in the header of {', '.join(paths)}")
    statuses += [_github(repo, why, fetch) for repo, why in sorted(repos.items())]
    statuses += _node(ws, fetch)
    for name, ids in recommended_packages(ws).items():
        statuses += _recommended(name, ids, fetch, today)
    return statuses


def render(statuses: list[Status], allowed: bool) -> str:
    """Serialise the results; a denied run says so instead of listing results."""
    body = {
        "generated_by": "kit lookup (public metadata; names and versions only)",
        "policy": "allow" if allowed else "deny",
        "results": [asdict(s) for s in statuses],
    }
    return json.dumps(body, indent=1) + "\n"
