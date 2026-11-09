"""Gate tables: which tools passed a unit, and which the target runs itself.

ADR 0007 D5. A unit's gate is `pass`, `fail`, `unavailable` or `not_applicable`,
always with the evidence. A tool that didn't run, or didn't examine the file, is
`unavailable`: never a pass. `fail` means the tool reported something in the
unit's lines; the kit's ESLint rules are all warnings, so a fail is a lead for
the review, not a defect.

The repository table reads the target's CI config and package scripts as text
(AGENTS.md rule 2: config files are code, so they're never run or loaded).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from audit_kit.errors import WorkspaceError
from audit_kit.scan_rows import ScanIndex, unit_rows
from audit_kit.units import Unit
from audit_kit.workspace import Workspace

GateName = Literal["eslint", "tsc", "semgrep", "knip", "complexity", "duplication"]
GateStatus = Literal["pass", "fail", "unavailable", "not_applicable"]
TargetRuns = Literal["runs in CI", "package script only", "not found"]
GATES: tuple[GateName, ...] = (
    "eslint",
    "tsc",
    "semgrep",
    "knip",
    "complexity",
    "duplication",
)
# What the kit's own configs cover (config/eslint.config.mjs, scans.tsconfig).
SCRIPTS = (".js", ".cjs", ".mjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")
JSON_OUT = PurePosixPath(".audit/scans/gates.json")
MD_OUT = PurePosixPath(".audit/scans/gates.md")
SHOWN = 3
INLINE_GAP = "inline scripts in HTML aren't checked by this tool"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Gate(_Model):
    """One tool's verdict on one unit."""

    gate: GateName
    status: GateStatus
    evidence: str


def _from_rows(gate: GateName, rows: list[str], ran: str, clean: str) -> Gate:
    if not rows:
        return Gate(gate=gate, status="pass", evidence=f"{ran}; {clean}")
    more = f" (and {len(rows) - SHOWN} more)" if len(rows) > SHOWN else ""
    shown = "; ".join(rows[:SHOWN])
    return Gate(gate=gate, status="fail", evidence=f"{len(rows)} rows: {shown}{more}")


class _UnitView:
    """What one unit's kind and the scans let the gates say about it."""

    def __init__(self, index: ScanIndex, unit: Unit) -> None:
        self.index = index
        self.unit = unit
        self.script = unit.kind == "file" and unit.path.endswith(SCRIPTS)
        self.inline = unit.kind == "inline script"
        self.rows = {
            name: [f"{r.line or 'file'}: {r.text}" for r in rows.inside]
            for name, rows in unit_rows(index, unit).items()
        }

    def cannot_judge(self, gate: GateName, source: str, *, listed: bool) -> Gate | None:
        """Return the gate when the tool can't speak for this unit, else None.

        Args:
            gate: The gate being decided.
            source: The scan the gate reads.
            listed: Whether the tool lists the files it examined.
        """
        if self.inline:
            return Gate(gate=gate, status="unavailable", evidence=INLINE_GAP)
        if not self.script:
            return Gate(
                gate=gate,
                status="not_applicable",
                evidence=f"a {self.unit.kind} unit isn't JavaScript",
            )
        if not self.index.ran(source):
            state = self.index.status.get(source, "not run")
            return Gate(gate=gate, status="unavailable", evidence=f"{source}: {state}")
        if listed and source not in self.index.examined:
            why = self.index.problems.get(f"{source} examined list", "no list")
            return Gate(
                gate=gate,
                status="unavailable",
                evidence=f"no readable list of the files the tool examined ({why})",
            )
        if listed and self.unit.path not in self.index.examined[source]:
            return Gate(
                gate=gate,
                status="unavailable",
                evidence="the tool didn't examine this file",
            )
        return None


def _is_complexity(row: str) -> bool:
    return row.split(": ", 1)[-1].startswith("complexity:")


def _knip(view: _UnitView) -> Gate:
    if not view.script:
        return Gate(
            gate="knip",
            status="not_applicable",
            evidence=f"knip checks module files, not a {view.unit.kind} unit",
        )
    if not view.index.ran("knip"):
        return Gate(
            gate="knip",
            status="unavailable",
            evidence="kit sandbox structure hasn't run (scans/dynamic/knip.json)",
        )
    return _from_rows(
        "knip", view.rows["knip"], "knip ran in the sandbox", "no rows in this unit"
    )


def _duplication(view: _UnitView) -> Gate:
    if not view.index.ran("duplication"):
        state = view.index.status.get("duplication", "not run")
        return Gate(
            gate="duplication", status="unavailable", evidence=f"duplication: {state}"
        )
    return _from_rows(
        "duplication", view.rows["duplication"], "jscpd ran", "no clones in this unit"
    )


def unit_gates(index: ScanIndex, unit: Unit) -> list[Gate]:
    """Return the six gates for one unit, in a fixed order."""
    view = _UnitView(index, unit)
    lint = [r for r in view.rows["lint"] if not _is_complexity(r)]
    complexity = [r for r in view.rows["lint"] if _is_complexity(r)]
    eslint = view.cannot_judge("eslint", "lint", listed=True) or _from_rows(
        "eslint", lint, "ESLint ran with the kit's config", "no rows in this unit"
    )
    tsc = view.cannot_judge("tsc", "typecheck", listed=True) or _from_rows(
        "tsc", view.rows["typecheck"], "tsc --checkJs ran", "no rows in this unit"
    )
    semgrep = view.cannot_judge("semgrep", "sast", listed=False) or _from_rows(
        "semgrep",
        view.rows["sast"],
        "Semgrep ran",
        "no results here (Semgrep doesn't list the files it scanned)",
    )
    cyclomatic = view.cannot_judge("complexity", "lint", listed=True) or _from_rows(
        "complexity",
        complexity,
        "ESLint complexity rule (10) ran",
        "no function over 10",
    )
    return [eslint, tsc, semgrep, _knip(view), cyclomatic, _duplication(view)]


def render_table(gates: list[Gate]) -> str:
    """Render a unit's gate table as Markdown."""
    out = ["| Gate | Status | Evidence |", "|---|---|---|"]
    out += [
        f"| {g.gate} | {g.status} | {g.evidence.replace('|', chr(92) + '|')} |"
        for g in gates
    ]
    return "\n".join(out)


# The target's own gates: tool names in CI config and package scripts.
CI_FILES = (
    ".github/workflows",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "azure-pipelines",
    ".azure-pipelines",
    "bitbucket-pipelines.yml",
    "Jenkinsfile",
    ".circleci/config.yml",
    ".husky",
    ".pre-commit-config.yaml",
    ".lintstagedrc",
    ".lintstagedrc.json",
)
ESLINT = re.compile(r"\beslint\b|\bnext lint\b")
TOOL_PATTERNS: dict[GateName, re.Pattern[str]] = {
    "eslint": ESLINT,
    "tsc": re.compile(r"\b(?:vue-)?tsc\b"),
    "semgrep": re.compile(r"\bsemgrep\b"),
    "knip": re.compile(r"\bknip\b"),
    # The target has a complexity gate when it runs ESLint with that rule on.
    "complexity": ESLINT,
    "duplication": re.compile(r"\bjscpd\b|\bcpd\b"),
}
COMPLEXITY_RULE = re.compile(r"""["']?complexity["']?\s*:""")
ESLINT_CONFIGS = re.compile(
    r"(?:^|/)(?:eslint\.config\.[cm]?[jt]s|\.eslintrc(?:\.\w+)?)$"
)
RUN_SCRIPT = re.compile(
    r"\b(?:npm|pnpm|yarn)\s+(?:run(?:-script)?\s+)?(?P<name>[\w:.-]+)"
)
KIT_CONFIG: dict[GateName, str] = {
    "eslint": (
        "config/eslint.config.mjs (the kit's baseline; the target's config is "
        "never loaded)"
    ),
    "tsc": (
        ".audit/scans/tsconfig.audit.json (checkJs, not strict; the target's "
        "tsconfig isn't used)"
    ),
    "semgrep": "p/javascript, p/expressjs, p/owasp-top-ten",
    "knip": "knip with no config, in the sandbox only (ADR 0005)",
    "complexity": "ESLint `complexity` at 10 (kit baseline)",
    "duplication": "jscpd defaults",
}
KIT_OUTPUT: dict[GateName, str] = {
    "eslint": ".audit/scans/lint.json",
    "tsc": ".audit/scans/typecheck.txt",
    "semgrep": ".audit/scans/sast.sarif",
    "knip": ".audit/scans/dynamic/knip.json",
    "complexity": ".audit/scans/lint.json",
    "duplication": ".audit/scans/duplication.json",
}


class RepoGate(_Model):
    """Whether the target runs one gate itself, and how the kit ran it."""

    gate: GateName
    target: TargetRuns
    where: list[str]
    scripts: list[str]
    target_config: str
    kit_config: str
    kit_ran: bool
    kit_output: str


class RepoGates(_Model):
    """The repository gate table (scans/gates.json)."""

    generated_by: str = (
        "kit scan: repository gates (CI config and package scripts read as text)"
    )
    ci_files: list[str]
    gates: list[RepoGate] = Field(min_length=len(GATES), max_length=len(GATES))


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    scripts: dict[str, str] = Field(default_factory=dict)


def _scripts(ws: Workspace) -> dict[str, str]:
    """Return the target's package scripts; none if package.json is missing or odd."""
    if not ws.is_file("package.json"):
        return {}
    try:
        return _Manifest.model_validate_json(ws.read_text("package.json")).scripts
    except (WorkspaceError, ValidationError):
        return {}


def _lines(ws: Workspace, path: str) -> list[str]:
    try:
        return ws.read_text(path, limit=5_000_000).splitlines()
    except WorkspaceError:
        return []


def _mentions(
    ws: Workspace, files: list[str], pattern: re.Pattern[str], scripts: set[str]
) -> list[str]:
    """Return CI lines that run the tool directly or through a package script."""
    where: list[str] = []
    for path in files:
        for number, line in enumerate(_lines(ws, path), 1):
            named = {m.group("name") for m in RUN_SCRIPT.finditer(line)}
            if pattern.search(line) or named & scripts:
                where.append(f"{path}:{number}")
    return where


def _complexity_rule(ws: Workspace, configs: list[str]) -> list[str]:
    return [
        f"{path}:{number}"
        for path in configs
        for number, line in enumerate(_lines(ws, path), 1)
        if COMPLEXITY_RULE.search(line)
    ]


def repository(ws: Workspace, files: set[str]) -> RepoGates:
    """Return which gates the target runs itself, and which config the kit used.

    Args:
        ws: The workspace.
        files: Every file in the target (relative paths), from the inventory.
    """
    scripts = _scripts(ws)
    ci = sorted(
        p for p in files if any(p == c or p.startswith(c + "/") for c in CI_FILES)
    )
    rule_at = _complexity_rule(ws, sorted(p for p in files if ESLINT_CONFIGS.search(p)))
    rows: list[RepoGate] = []
    for gate in GATES:
        pattern = TOOL_PATTERNS[gate]
        in_scripts = sorted(n for n, cmd in scripts.items() if pattern.search(cmd))
        where = _mentions(ws, ci, pattern, set(in_scripts))
        rule = ""
        if gate == "complexity":
            if not rule_at:
                in_scripts, where = [], []
            rule = (
                ", ".join(rule_at[:SHOWN])
                or "no `complexity` rule in the target's ESLint config"
            )
        target: TargetRuns = "not found"
        if where:
            target = "runs in CI"
        elif in_scripts:
            target = "package script only"
        output = KIT_OUTPUT[gate]
        rows.append(
            RepoGate(
                gate=gate,
                target=target,
                where=where[:SHOWN],
                scripts=[f"package.json scripts.{n}" for n in in_scripts][:SHOWN],
                target_config=rule,
                kit_config=KIT_CONFIG[gate],
                kit_ran=ws.is_file(output) and ws.size(output) > 0,
                kit_output=output,
            )
        )
    return RepoGates(ci_files=ci, gates=rows)


def render_repository(data: RepoGates) -> str:
    """Render the repository gate table for the final report."""
    out = [
        "# Repository gates",
        "",
        "Which checks the target runs itself (from its CI config and package "
        "scripts, read as text), and which config the kit used. The target's own "
        "configs are code, so the kit never runs them outside the sandbox.",
        "",
        f"CI files read: {', '.join(data.ci_files) or 'none found'}",
        "",
        "| Gate | Target runs it | Where | Kit config | Kit ran it |",
        "|---|---|---|---|---|",
    ]
    for g in data.gates:
        where = ", ".join(g.where + g.scripts) or "\u2013"
        if g.target_config:
            where += f"; rule: {g.target_config}"
        ran = "yes" if g.kit_ran else "no"
        out.append(f"| {g.gate} | {g.target} | {where} | {g.kit_config} | {ran} |")
    return "\n".join(out) + "\n"


def write_repository(ws: Workspace, files: set[str]) -> RepoGates:
    """Write scans/gates.json and gates.md, and return the table."""
    data = repository(ws, files)
    ws.write_text(JSON_OUT, data.model_dump_json(indent=1) + "\n")
    ws.write_text(MD_OUT, render_repository(data))
    return data


def read_repository(ws: Workspace) -> RepoGates | None:
    """Return scans/gates.json, or None if `kit scan` hasn't written it.

    Raises:
        pydantic.ValidationError: If the file isn't a gate table.
    """
    if not ws.is_file(JSON_OUT):
        return None
    return RepoGates.model_validate_json(ws.read_text(JSON_OUT))
