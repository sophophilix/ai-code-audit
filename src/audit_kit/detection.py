"""Detect profiles, exclusions and facts from the inventory (no AI).

The output depends only on the workspace contents and the arguments, so a
re-run on the same commit is byte-identical (architecture constraint C4).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from audit_kit.errors import WorkspaceError
from audit_kit.intake import parse_intake as read_intake
from audit_kit.inventory import (
    INVENTORY_PATH,
    NOT_REVIEWED,
    Inventory,
    build,
    exclusions,
)
from audit_kit.manifest import load_manifest
from audit_kit.workspace import Workspace

LOCKFILES = frozenset({"package-lock.json", "yarn.lock", "pnpm-lock.yaml"})
UI_EXT = frozenset(
    {
        ".html",
        ".htm",
        ".cshtml",
        ".razor",
        ".jsx",
        ".tsx",
        ".vue",
        ".ejs",
        ".hbs",
        ".pug",
    }
)
AI_DEPS = frozenset(
    {
        "openai",
        "@azure/openai",
        "@anthropic-ai/sdk",
        "langchain",
        "@langchain/core",
        "@google/generative-ai",
        "@azure-rest/ai-inference",
        "@azure/ai-projects",
    }
)
AI_HOSTS = re.compile(
    r"openai\.azure\.com|api\.openai\.com|api\.anthropic\.com|cognitiveservices\.azure\.com|"
    r"generativelanguage\.googleapis\.com"
)
AZURE_HOSTS = re.compile(
    r"\.azurewebsites\.net|\.blob\.core\.windows\.net|\.azure\.com\b|\.vault\.azure\.net|login\.microsoftonline\.com"
)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|[._](test|spec)\.[a-z]+$")
INTAKE_PATH = PurePosixPath(".audit/project.md")
# Programming languages by extension. Data, config and prose formats are left out:
# every profile handles them, so they never make a stack "uncovered".
LANGUAGES = {
    **dict.fromkeys((".js", ".cjs", ".mjs", ".jsx"), "JavaScript"),
    **dict.fromkeys((".ts", ".tsx", ".mts", ".cts"), "TypeScript"),
    **dict.fromkeys((".html", ".htm", ".ejs", ".hbs", ".pug"), "HTML"),
    **dict.fromkeys((".css", ".scss", ".sass", ".less"), "CSS"),
    **dict.fromkeys((".cs", ".csx"), "C#"),
    **dict.fromkeys((".cshtml", ".razor"), "Razor"),
    **dict.fromkeys((".py", ".pyw"), "Python"),
    **dict.fromkeys((".java",), "Java"),
    **dict.fromkeys((".kt", ".kts"), "Kotlin"),
    **dict.fromkeys((".go",), "Go"),
    **dict.fromkeys((".rb",), "Ruby"),
    **dict.fromkeys((".php",), "PHP"),
    **dict.fromkeys((".rs",), "Rust"),
    **dict.fromkeys((".swift",), "Swift"),
    **dict.fromkeys((".c", ".h", ".cc", ".cpp", ".hpp"), "C/C++"),
    **dict.fromkeys((".sql",), "SQL"),
    **dict.fromkeys((".vue",), "Vue"),
    **dict.fromkeys((".svelte",), "Svelte"),
    **dict.fromkeys((".ps1", ".psm1"), "PowerShell"),
    **dict.fromkeys((".bicep",), "Bicep"),
    **dict.fromkeys((".tf",), "Terraform"),
}
# Languages each profile knows. Shell is small glue in most repositories and is
# covered by the general rules, so it is never flagged.
PROFILE_LANGUAGES = {
    "node-express": frozenset({"JavaScript", "TypeScript"}),
    "mssql": frozenset({"SQL"}),
    "web-accessibility": frozenset({"HTML", "CSS", "Razor", "Vue", "Svelte"}),
    "azure-architecture": frozenset({"Bicep", "Terraform", "PowerShell"}),
}
UNCOVERED_SHARE = 0.05


@dataclass(frozen=True)
class Profile:
    """A profile the evidence supports."""

    name: str
    evidence: str


@dataclass(frozen=True)
class Exclusion:
    """A folder or file pattern left out of scans, with the reason."""

    pattern: str
    evidence: str


@dataclass(frozen=True)
class Intake:
    """The parts of the intake that affect detection."""

    jurisdiction: str
    add: tuple[str, ...]
    remove: tuple[str, ...]


@dataclass(frozen=True)
class Scope:
    """The inventory, the folders and files left out of scans, and the files reviewed."""

    inventory: Inventory
    exclusions: tuple[Exclusion, ...]
    own: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class Detection:
    """Everything detect found, ready to render."""

    profiles: tuple[Profile, ...]
    resolved: tuple[str, ...]
    intake: Intake
    scope: Scope
    lines_own: int
    extensions: tuple[tuple[str, int], ...]
    largest: tuple[tuple[str, int], ...]
    dependencies: int
    dev_dependencies: int
    lockfiles: tuple[str, ...]
    pipelines: tuple[str, ...]
    iac: tuple[str, ...]
    tests: tuple[str, ...]
    ai_files: tuple[str, ...]
    ai_signals: tuple[str, ...]
    problems: tuple[str, ...]
    languages: tuple[tuple[str, int], ...] = ()
    uncovered: tuple[str, ...] = ()


def scope(ws: Workspace, inv: Inventory | None = None) -> Scope:
    """Split the inventory into files left out of scans and files reviewed."""
    inv = inv if inv is not None else build(ws)
    own = tuple(
        PurePosixPath(e.path)
        for e in inv.entries
        if e.kind == "file" and e.cls not in NOT_REVIEWED and ws.is_file(e.path)
    )
    excluded = tuple(Exclusion(p, r) for p, r in exclusions(inv))
    return Scope(inventory=inv, exclusions=excluded, own=own)


def parse_intake(text: str) -> Intake:
    """Read jurisdiction and profile overrides from project.md text.

    Placeholder values such as `<e.g. NSW local council>` count as empty.
    """
    doc = read_intake(text)
    return Intake(jurisdiction=doc.get("organisation"), add=doc.add, remove=doc.remove)


def detect(ws: Workspace, inv: Inventory | None = None) -> Detection:
    """Detect profiles, exclusions and facts for a workspace.

    Args:
        ws: The workspace.
        inv: Its inventory; built from the files when not given.
    """
    sc = scope(ws, inv)
    problems: list[str] = list(sc.inventory.problems)
    intake_text = ""
    if ws.exists(INTAKE_PATH):
        try:
            intake_text = ws.read_text(INTAKE_PATH)
        except WorkspaceError as exc:
            problems.append(str(exc))
    intake = parse_intake(intake_text)

    loaded = load_manifest(ws)
    if loaded.problem:
        problems.append(loaded.problem)
    manifest = loaded.manifest
    deps = manifest.all_dependencies() if manifest else {}

    binary = {e.path for e in sc.inventory.of("binary", "data-candidate")}
    texts: dict[PurePosixPath, str] = {}
    for rel in sc.own:
        if rel.as_posix() in binary:
            continue
        try:
            texts[rel] = ws.read_text(rel)
        except WorkspaceError as exc:
            problems.append(str(exc))

    def first_hits(pattern: re.Pattern[str], limit: int = 3) -> list[str]:
        hits: list[str] = []
        for rel, body in texts.items():
            match = pattern.search(body)
            if match:
                hits.append(f"{rel}:{body.count(chr(10), 0, match.start()) + 1}")
                if len(hits) == limit:
                    break
        return hits

    profiles: list[Profile] = []
    if manifest is not None:
        express = (
            f"; express {deps['express']}"
            if "express" in deps
            else "; Node.js (no express dependency)"
        )
        profiles.append(Profile("node-express", "package.json" + express))
    sql_files = [r for r in sc.own if r.suffix.lower() == ".sql"]
    sql_deps = [d for d in ("mssql", "tedious") if d in deps]
    if sql_deps or sql_files:
        parts = [f"package.json: {', '.join(sql_deps)}"] if sql_deps else []
        if sql_files:
            parts.append(f"{len(sql_files)} .sql file(s), e.g. {sql_files[0]}")
        profiles.append(Profile("mssql", "; ".join(parts)))
    az_deps = sorted(d for d in deps if d.startswith("@azure/"))
    az_iac = [
        r
        for r in sc.own
        if r.suffix in (".bicep", ".tf")
        or r.name in ("azure-pipelines.yml", "azuredeploy.json")
    ]
    az_hosts = first_hits(AZURE_HOSTS)
    if az_deps or az_iac or az_hosts:
        parts = []
        if az_deps:
            parts.append(f"package.json: {', '.join(az_deps)}")
        if az_iac:
            parts.append(f"IaC/pipeline: {', '.join(map(str, az_iac[:3]))}")
        if az_hosts:
            parts.append(f"Azure hostnames at {', '.join(az_hosts)}")
        profiles.append(Profile("azure-architecture", "; ".join(parts)))
    ui = [r for r in sc.own if r.suffix.lower() in UI_EXT]
    if ui:
        profiles.append(
            Profile(
                "web-accessibility", f"{len(ui)} user-interface file(s), e.g. {ui[0]}"
            )
        )
    j = intake.jurisdiction
    if re.search(r"\bnsw\b|new south wales", j, re.I) and re.search(
        r"council|local government", j, re.I
    ):
        profiles.append(Profile("nsw-local-government", f'intake: "{j}"'))
    profiles.append(Profile("ai-governance", "always: the auditors are AI agents"))

    resolved = [p.name for p in profiles if p.name not in intake.remove]
    resolved += [p for p in intake.add if p not in resolved]

    ai_deps = sorted(d for d in deps if d in AI_DEPS)
    ai_signals = ([f"package.json: {', '.join(ai_deps)}"] if ai_deps else []) + [
        f"AI service hostname at {h}" for h in first_hits(AI_HOSTS)
    ]
    lines = {
        r: t.count("\n") + (1 if t and not t.endswith("\n") else 0)
        for r, t in texts.items()
        if r.name not in LOCKFILES
    }
    exts = Counter((r.suffix.lower() or r.name) for r in sc.own)
    by_language: Counter[str] = Counter()
    for rel, n in lines.items():
        if lang := LANGUAGES.get(rel.suffix.lower()):
            by_language[lang] += n
    languages = tuple(sorted(by_language.items(), key=lambda kv: (-kv[1], kv[0])))
    total = sum(by_language.values())
    covered = {lang for p in resolved for lang in PROFILE_LANGUAGES.get(p, ())}
    own_text = [r.as_posix() for r in sc.own]
    return Detection(
        profiles=tuple(profiles),
        resolved=tuple(resolved),
        intake=intake,
        scope=sc,
        lines_own=sum(lines.values()),
        extensions=tuple(exts.most_common(10)),
        largest=tuple(
            (str(r), n)
            for r, n in sorted(lines.items(), key=lambda kv: (-kv[1], str(kv[0])))[:10]
        ),
        dependencies=len(manifest.dependencies) if manifest else 0,
        dev_dependencies=len(manifest.dev_dependencies) if manifest else 0,
        lockfiles=tuple(n for n in sorted(LOCKFILES) if ws.is_file(n)),
        pipelines=tuple(
            p
            for p in own_text
            if PurePosixPath(p).name
            in ("azure-pipelines.yml", "Jenkinsfile", ".gitlab-ci.yml")
            or p.startswith(".github/workflows/")
        ),
        iac=tuple(
            [str(r) for r in az_iac]
            + [p for p in own_text if PurePosixPath(p).name == "Dockerfile"]
        ),
        tests=tuple(p for p in own_text if TEST_PATH.search(p)),
        ai_files=tuple(e.path for e in sc.inventory.of("ai-instructions")),
        ai_signals=tuple(ai_signals),
        problems=tuple(problems),
        languages=languages,
        uncovered=tuple(
            lang
            for lang, n in languages
            if lang not in covered and n >= UNCOVERED_SHARE * total
        ),
    )


def loaded_profiles(detected_md: str) -> tuple[str, ...]:
    """The "Profiles to load" line of detected.md, which includes intake overrides."""
    m = re.search(r"^## Profiles to load\s*\n\s*\n(.*)$", detected_md, re.M)
    if m is None:
        return ()
    return tuple(p.strip() for p in m.group(1).split(",") if p.strip())


def render(d: Detection, commit: str, kit_version: str) -> str:
    """Render detected.md. Contains no timestamp, so re-runs are byte-identical."""
    out = [
        "---",
        "generated_by: kit detect (deterministic, no AI)",
        f"kit_version: {kit_version}",
        f"commit: {commit}",
        f"inventory_sha256: {hashlib.sha256(d.scope.inventory.to_json(commit).encode()).hexdigest()}",
        "---",
        "# Detected project profile",
        "",
        "Produced from the files alone. Confirm or correct it at Checkpoint 1 (profile",
        "overrides go in `.audit/project.md` → Profile overrides; then re-run `make detect`).",
        "",
        "## Profiles to load",
        "",
        ", ".join(d.resolved),
        "",
        "| Profile | Apply | Evidence |",
        "|---|---|---|",
    ]
    out += [f"| {p.name} | yes | {p.evidence} |" for p in d.profiles]
    if d.intake.add or d.intake.remove:
        out += [
            "",
            f"Overrides from intake: add {list(d.intake.add) or '-'}, remove {list(d.intake.remove) or '-'}",
        ]
    out += [
        "",
        "## Excluded from scans (vendored or generated)",
        "",
        "Every file is still recorded in `.audit/inventory.json` with its class, hashes and",
        "the rule that matched. Agents inventory these as third-party code (supply chain),",
        "but don't review them.",
        "",
    ]
    out += [f"- `{e.pattern}`: {e.evidence}" for e in d.scope.exclusions] or ["- none"]
    sc = d.scope
    clues = [e for e in sc.inventory.of("vendored") if e.upstream or e.version]
    if clues:
        out += [
            "",
            "Leads for identifying vendored files (unconfirmed; the security agent checks",
            "each upstream's maintenance status and the version's advisories):",
            "",
            "| File | Upstream named in the header | First version marker |",
            "|---|---|---|",
        ]
        out += [
            f"| `{e.path}` | {e.upstream or '-'} | {e.version or '-'} |" for e in clues
        ]
    counts = ", ".join(f"{c} {n}" for c, n in sc.inventory.counts().items())
    out += [
        "",
        "## Facts",
        "",
        f"- Inventory: {len(sc.inventory.entries)} paths ({counts}); reviewed: {len(sc.own)}",
        f"- Text lines in reviewed files (excluding lockfiles): {d.lines_own}",
        f"- File types: {', '.join(f'{e} {n}' for e, n in d.extensions)}",
        f"- Dependencies: {d.dependencies} runtime, {d.dev_dependencies} dev; lockfile: {', '.join(d.lockfiles) or 'none'}",
        f"- Pipelines: {', '.join(d.pipelines) or 'none found'}",
        f"- IaC / containers: {', '.join(d.iac) or 'none found'}",
        f"- Test-like files: {len(d.tests)}"
        + (f" (e.g. {', '.join(d.tests[:3])})" if d.tests else ""),
        f"- AI instruction files: {', '.join(d.ai_files) or 'none'}",
        f"- AI service signals: {'; '.join(d.ai_signals) or 'none found'}",
        f"- Languages (lines in reviewed files): {', '.join(f'{lang} {n}' for lang, n in d.languages) or 'none recognised'}",
        "",
        "Largest own files (lines):",
        "",
    ]
    out += [f"- {r}: {n}" for r, n in d.largest]
    out += ["", "## Needs a person", ""]
    share = dict(d.languages)
    total = sum(share.values()) or 1
    out += [
        f"- No profile covers {lang} ({share[lang] * 100 // total}% of reviewed code lines): "
        "agents review it with the general rules only. Add a profile, or record this as a limitation."
        for lang in d.uncovered
    ]
    if not d.intake.jurisdiction:
        out.append(
            "- Organisation and jurisdiction aren't in the intake, so no compliance profile was chosen."
        )
    out += [
        f"- Symlink not followed (check what it points to): `{e.path}`"
        for e in sc.inventory.of("symlink")
    ]
    out += [
        f"- Submodule not in the snapshot (audit it separately or record it as out of scope): `{e.path}`"
        for e in sc.inventory.of("submodule")
    ]
    out += [
        f"- Possible data or credential file: `{e.path}`"
        for e in sc.inventory.of("data-candidate")
    ]
    out += [f"- Couldn't use: {p}" for p in d.problems]
    out.append(
        "- Purpose, users and data handled: discovery proposes these; confirm them at Checkpoint 1."
    )
    return "\n".join(out) + "\n"


def write_outputs(ws: Workspace, d: Detection, commit: str, kit_version: str) -> None:
    """Write .audit/inventory.json, .audit/detected.md and .audit/detected-excludes.txt."""
    ws.write_text(INVENTORY_PATH, d.scope.inventory.to_json(commit))
    ws.write_text(".audit/detected.md", render(d, commit, kit_version))
    ws.write_text(
        ".audit/detected-excludes.txt",
        "".join(f"{e.pattern}\n" for e in d.scope.exclusions),
    )
