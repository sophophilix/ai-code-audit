"""Command-line entry point: `audit-kit <command>` (bin/kit and the Makefile call this).

Exit codes (docs/architecture/ARCHITECTURE.md, "Error and exit contract"):
0 success; 1 verify, validate or the data check found failures; 2 invalid input or
refused operation; 3 unexpected internal error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from audit_kit import (
    __version__,
    diagram_style,
    machine,
    outputs,
    projects,
    review,
    sandbox,
    scans,
    store,
    workspaces,
)
from audit_kit.console import say
from audit_kit.detection import detect, write_outputs
from audit_kit.errors import AuditKitError
from audit_kit.runner import run
from audit_kit.seeding import seed
from audit_kit.settings import KitSettings
from audit_kit.state import STATE_FILE
from audit_kit.validation import OUTPUT, known_profiles, models_schema, validate
from audit_kit.validation import render as render_validation
from audit_kit.verification import check
from audit_kit.workspace import Workspace

EXIT_OK = 0
EXIT_CHECKS_FAILED = 1
EXIT_INVALID = 2
EXIT_INTERNAL = 3

Handler = Callable[[argparse.Namespace, KitSettings], int]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kit",
        description="agent-audit-kit. Every command is idempotent: re-running does only what's missing.",
    )
    parser.add_argument(
        "--version", action="version", version=f"audit-kit {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name: str, text: str, workspace: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=text, description=text)
        if workspace:
            p.add_argument(
                "workspace",
                help="workspace path, or its name under the workspaces folder",
            )
        return p

    add("help", "show this help", workspace=False)
    add("doctor", "check tools, the drawio-skill pin and the kit tag", workspace=False)
    add("tools", "install what doctor reports missing", workspace=False).add_argument(
        "--dry-run", action="store_true"
    )
    add("tag", "tag this kit version (skips if tagged)", workspace=False)
    add(
        "project", "create ~/audit-projects/<name> (never overwrites)", workspace=False
    ).add_argument("name")
    w = add(
        "workspace",
        "create an eval snapshot or a real clone (skips if it exists)",
        workspace=False,
    )
    w.add_argument("name")
    w.add_argument("--source", required=True, help="git URL or local repository path")
    w.add_argument("--ref", required=True, help="commit, tag or branch to audit")
    w.add_argument("--mode", default="eval", choices=["eval", "real"])
    w.add_argument("--date", default=None, help="YYYY-MM-DD (default: today, UTC)")
    w.add_argument(
        "--name",
        dest="folder",
        default=None,
        help="workspace folder name (default: <project>-<mode>-<date>)",
    )
    add(
        "seed",
        "eval only: plant seeded issues; the answer key goes outside the workspace",
    ).add_argument(
        "key",
        nargs="?",
        type=Path,
        help="answer key path (default: the project's keys/ folder)",
    )
    add("install", "install or refresh the kit in a workspace").add_argument(
        "--no-seed", action="store_true"
    )
    d = add("detect", "write .audit/detected.md and detected-excludes.txt (no AI)")
    d.add_argument(
        "--commit",
        default=None,
        help="commit to record (default: last commit that changed the code)",
    )
    d.add_argument("--kit-version", default=None)
    for name in ("check-data", "check"):
        add(
            name,
            "data check: credentials, dumps and exports in the tree and git history",
        )
    v = add(
        "validate", "check .audit/models.yaml and the intake (pre-flight needs a pass)"
    )
    v.add_argument(
        "--profiles-dir",
        type=Path,
        default=None,
        help="kit profiles folder (default: the kit's)",
    )
    add("scan", "run the installed scanners into .audit/scans").add_argument(
        "--force", action="store_true"
    )
    add("units", "list the file review's units and write a brief for each (no AI)")
    r = add(
        "review",
        "run the file review: one claude -p pass per unit, checked before it's written",
    )
    r.add_argument("--units", default=None, help="comma-separated unit ids (u001,u002)")
    r.add_argument(
        "--reuse-from",
        default=None,
        help="an earlier audit's workspace: keep its records for unchanged units",
    )
    r.add_argument("--dry-run", action="store_true", help="list what would run")
    add("store", "rebuild .audit/findings.duckdb from the records, traces and passes")
    q = add("query", "run one read-only SQL query on the findings store")
    q.add_argument("sql")
    q.add_argument("--format", choices=("table", "csv", "json"), default="table")
    add(
        "cost",
        "turns, tokens, cost and time per stage and model (writes .audit/cost.md)",
    )
    b = add(
        "sandbox",
        "run one job in the Docker sandbox, if .audit/policy.yaml allows (ADR 0005)",
    )
    b.add_argument("job", choices=sandbox.JOBS)
    b.add_argument(
        "file",
        nargs="?",
        help="prove: a .test.js under .audit/work/; try: a .js snippet under .audit/work/",
    )
    add(
        "lookup",
        "public supply-chain metadata (npm, GitHub, endoflife.date) if .audit/policy.yaml allows",
    )
    add(
        "ready", "install + detect + data check + scans + lookups + validate"
    ).add_argument("--no-seed", action="store_true")
    add(
        "diagrams", "build .audit/diagrams/*.ir.json with the pinned drawio-skill"
    ).add_argument(
        "--style",
        choices=diagram_style.STYLES,
        default="handdrawn",
        help="house style: handdrawn (default) or clean",
    )
    add("publish", "Word, PowerPoint and PDF from the Markdown outputs")
    add("verify", "run the automated output checks")
    add("status", "workspace details, run state and active locks")
    add("list", "list workspaces", workspace=False)
    add("schema", "print the JSON Schema for models.yaml", workspace=False)
    add("selftest", "run the kit's own tests", workspace=False)
    return parser


def _is_kit_workspace(path: str) -> bool:
    return (Path(path) / STATE_FILE).is_file()


def _detect(args: argparse.Namespace, s: KitSettings) -> int:
    if args.commit is None and _is_kit_workspace(args.workspace):
        workspaces.detect_workspace(s, args.workspace)
        return EXIT_OK
    ws = Workspace(Path(args.workspace))
    found = detect(ws)
    write_outputs(ws, found, args.commit or "unknown", args.kit_version or s.version)
    say(f"profiles: {', '.join(found.resolved)}")
    say(f"excluded: {', '.join(e.pattern for e in found.scope.exclusions) or 'none'}")
    for problem in found.problems:
        print(f"warning: {problem}", file=sys.stderr)
    return EXIT_OK


def _seed(args: argparse.Namespace, s: KitSettings) -> int:
    if args.key is None:
        workspaces.seed_workspace(s, args.workspace)
        return EXIT_OK
    plan = seed(Workspace(Path(args.workspace)), args.key)
    say(f"planted {len(plan.plants)} issues; key: {args.key.expanduser().resolve()}")
    return EXIT_OK


def _validate_workspace(ws: Workspace, profiles_dir: Path | None) -> bool:
    result = validate(ws, known_profiles(profiles_dir))
    ws.write_text(OUTPUT, render_validation(result))
    for issue in result.issues:
        say(f"{issue.level:7} {issue.where}: {issue.message}")
    errors = sum(i.level == "error" for i in result.issues)
    say(f"{'pass' if result.passed else 'fail'}: {errors} error(s); see {OUTPUT}")
    return result.passed


def _validate(args: argparse.Namespace, s: KitSettings) -> int:
    path = Path(args.workspace)
    if not path.is_dir() and (s.workspaces_dir / args.workspace).is_dir():
        path = s.workspaces_dir / args.workspace
    passed = _validate_workspace(
        Workspace(path), args.profiles_dir or s.kit_home / "profiles"
    )
    return EXIT_OK if passed else EXIT_CHECKS_FAILED


def _verify(args: argparse.Namespace, _s: KitSettings) -> int:
    report = check(Workspace(Path(args.workspace)))
    say("\n".join(r.line() for r in report.results))
    say(
        f"\n{report.failed} failed. Checks a person must do: see evals/output-checks.md (marked 'person')."
    )
    return EXIT_CHECKS_FAILED if report.failed else EXIT_OK


def _ready(args: argparse.Namespace, s: KitSettings) -> int:
    say("== install")
    workspaces.install(s, args.workspace, no_seed=args.no_seed)
    say("== detect")
    workspaces.detect_workspace(s, args.workspace)
    say("== data check")
    if not scans.check_data(s, args.workspace):
        raise AuditKitError(
            f"data check found files to review; fix, then re-run: kit ready {args.workspace}"
        )
    say("== scans")
    scans.scan(s, args.workspace)
    say("== lookups")
    scans.lookup(s, args.workspace)
    say("== validate")
    loc = workspaces.locate(s, args.workspace)
    valid = _validate_workspace(loc.ws, s.kit_home / "profiles")
    workspaces.checkpoint(loc.ws.root, "validation")
    root = loc.ws.root
    say("")
    if valid:
        say("Ready. Next:")
    else:
        say(
            f"Set up, but NOT ready: fix the errors in {root}/.audit/validation.md (models.yaml or the intake),"
        )
        say(
            f"then run: kit validate {root}    (pre-flight refuses to start until it passes). After that:"
        )
    say(
        f"  1. read {root}/.audit/detected.md (profiles, exclusions); you confirm it at Checkpoint 1"
    )
    say(f"  2. cd {root} && claude      then type: /audit")
    say("  3. interrupted? new session in the same folder: /audit resume")
    return EXIT_OK


def _selftest(_args: argparse.Namespace, s: KitSettings) -> int:
    result = run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=s.kit_home,
        timeout=1800,
        check=False,
    )
    say(result.text)
    return EXIT_OK if result.code == 0 else EXIT_CHECKS_FAILED


def _review(args: argparse.Namespace, s: KitSettings) -> int:
    left = review.review(
        s,
        args.workspace,
        only=[u.strip() for u in args.units.split(",") if u.strip()]
        if args.units
        else None,
        reuse_from=args.reuse_from,
        dry_run=args.dry_run,
    )
    return EXIT_CHECKS_FAILED if left else EXIT_OK


def _check_data(args: argparse.Namespace, s: KitSettings) -> int:
    return EXIT_OK if scans.check_data(s, args.workspace) else EXIT_CHECKS_FAILED


def _done(action: Callable[[argparse.Namespace, KitSettings], object]) -> Handler:
    """Wrap a command that reports through output and errors, returning success."""

    def handler(args: argparse.Namespace, s: KitSettings) -> int:
        action(args, s)
        return EXIT_OK

    return handler


HANDLERS: dict[str, Handler] = {
    "doctor": _done(lambda a, s: machine.doctor(s)),
    "tools": _done(lambda a, s: machine.tools(s, dry_run=a.dry_run)),
    "tag": _done(lambda a, s: machine.tag(s)),
    "project": _done(
        lambda a, s: projects.create_project(s.kit_home, s.projects_dir, a.name)
    ),
    "workspace": _done(
        lambda a, s: workspaces.create_workspace(
            s,
            a.name,
            a.source,
            a.ref,
            a.mode,
            a.date or workspaces.today(),
            folder=a.folder,
        )
    ),
    "seed": _seed,
    "install": _done(
        lambda a, s: workspaces.install(s, a.workspace, no_seed=a.no_seed)
    ),
    "detect": _detect,
    "check-data": _check_data,
    "check": _check_data,
    "validate": _validate,
    "scan": _done(lambda a, s: scans.scan(s, a.workspace, force=a.force)),
    "lookup": _done(lambda a, s: scans.lookup(s, a.workspace)),
    "units": _done(lambda a, s: scans.refresh_units(s, a.workspace)),
    "review": _review,
    "store": _done(lambda a, s: store.store(s, a.workspace)),
    "query": _done(lambda a, s: store.run_query(s, a.workspace, a.sql, a.format)),
    "cost": _done(lambda a, s: store.cost(s, a.workspace)),
    "sandbox": _done(lambda a, s: sandbox.sandbox(s, a.workspace, a.job, a.file)),
    "ready": _ready,
    "diagrams": _done(lambda a, s: outputs.diagrams(s, a.workspace, a.style)),
    "publish": _done(lambda a, s: outputs.publish(s, a.workspace)),
    "verify": _verify,
    "status": _done(lambda a, s: workspaces.status(s, a.workspace)),
    "list": _done(lambda a, s: workspaces.list_workspaces(s)),
    "schema": _done(lambda a, s: print(models_schema(), end="")),
    "selftest": _selftest,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "help":
        parser.print_help()
        return EXIT_OK
    try:
        settings = KitSettings.load()
        return HANDLERS[args.command](args, settings)
    except AuditKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except Exception as exc:  # process boundary: report and map to an exit code
        print(f"internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
