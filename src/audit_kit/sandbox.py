"""The kit's Docker sandbox: the few jobs that need code to run (ADR 0005).

AGENTS.md rule 2 still binds every agent. Only a person runs `kit sandbox`, and
only when `.audit/policy.yaml` says `sandbox: allow`. The target runs on a copy of
the snapshot, inside a container with no network (after a scripts-off install),
no host files, no credentials, a read-only root and hard limits.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import secrets
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from audit_kit.console import ok, warn
from audit_kit.errors import AuditKitError, WorkspaceError
from audit_kit.inventory import KIT_ROOT
from audit_kit.policy import load_policy
from audit_kit.runner import LONG, QUICK, CommandError, run
from audit_kit.settings import KitSettings
from audit_kit.workspace import Workspace
from audit_kit.workspaces import locate, utc_minute

JOBS = ("structure", "tests", "prove", "try")
OUT = PurePosixPath(".audit/scans/dynamic")
LOG = OUT / "jobs.log"
DEFAULT_NODE = "26"
SNIPPET_LINES = 20
# The container's own /tmp, the only writable place once the root is read-only.
TMPFS = "/tmp:rw,nosuid,size=512m"  # noqa: S108  # nosec B108
# The limits every container gets. The network is off for everything but install.
LIMITS = (
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--read-only",
    "--tmpfs", TMPFS,
    "--pids-limit", "256",
    "--memory", "2g",
    "--cpus", "2",
)  # fmt: skip
SKIP_COPY = frozenset({*KIT_ROOT, ".claude", "node_modules"})
# Every part of an agent-written path. Docker's --mount value is comma-separated
# key=value pairs, so a comma or '=' in a name would set mount options.
SAFE_PART = re.compile(r"[A-Za-z0-9._-]+")
UNSAFE_MOUNT = re.compile(r"[,=\"'\n]")
# The container stops itself first; the client timeout (LONG) is the backstop,
# after which the kit removes the container by name.
JOB_SECONDS = 1500
# Exit codes from `timeout --signal=KILL` (137) and plain `timeout` (124).
TIMED_OUT = frozenset({124, 137})
# Where the snapshot copy lives during a job. colima and Docker Desktop share
# only the home folder with their VM, so the system temp folder (/var/folders on
# macOS) isn't visible to the daemon.
COPY_PARENT = Path.home() / ".cache/audit-kit/sandbox"
# Never root in the container. A kit run as root uses the node image's user.
FALLBACK_USER = "1000:1000"


@dataclass(frozen=True)
class Job:
    """One container run: what to mount, what to run, and where its output goes."""

    name: str
    command: tuple[str, ...]
    output: str
    network: bool = False
    mount_target: bool = True
    target_writable: bool = False
    extra_mounts: tuple[tuple[Path, str], ...] = ()


def _mount(source: Path | str, target: str, writable: bool) -> str:
    """One --mount value, refusing characters that would add mount options.

    Docker's --mount takes `readonly` for a read-only bind; it rejects `ro` and
    `rw` (found in the first run against a real daemon).
    """
    for value in (str(source), target):
        if UNSAFE_MOUNT.search(value):
            raise AuditKitError(
                f"refused mount path {value!r}: contains , = or a quote"
            )
    return f"type=bind,source={source},target={target}" + (
        "" if writable else ",readonly"
    )


def docker_args(image: str, job: Job, copy: Path | None, name: str) -> list[str]:
    """Return the `docker run` argument list for a job (pure, so it can be tested).

    Raises:
        AuditKitError: If a mount path holds characters that would add options.
    """
    args = ["docker", "run", "--rm", "--name", name, *LIMITS, "--user", _user()]
    args += ["--network", "bridge" if job.network else "none"]
    if job.mount_target and copy is not None:
        args += [
            "--mount",
            _mount(copy, "/work", job.target_writable),
        ]
    for source, target in job.extra_mounts:
        args += ["--mount", _mount(source, target, writable=False)]
    timed = ("timeout", "--signal=KILL", str(JOB_SECONDS), *job.command)
    return [*args, image, *timed]


def _user() -> str:
    """The host's own uid and gid, so the kit can delete what the container wrote."""
    uid, gid = os.getuid(), os.getgid()
    return FALLBACK_USER if uid == 0 else f"{uid}:{gid}"


def node_major(ws: Workspace) -> str:
    """The Node.js major from engines or .nvmrc; the current LTS if neither says."""
    for rel in (".nvmrc", ".node-version"):
        if ws.is_file(rel) and (m := re.search(r"\d+", ws.read_text(rel))):
            return m.group(0)
    if ws.is_file("package.json"):
        try:
            engines = json.loads(ws.read_text("package.json")).get("engines") or {}
        except (json.JSONDecodeError, AttributeError):
            engines = {}
        if m := re.search(r"\d+", str(engines.get("node", ""))):
            return m.group(0)
    return DEFAULT_NODE


def copy_target(source: Workspace, dest: Path) -> int:
    """Copy the target's regular files (no kit folders, no symlinks) into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    ws = Workspace(dest)
    count = 0
    for rel in source.tree(skip_root=SKIP_COPY).files:
        ws.copy_file(rel, source.path(rel))
        count += 1
    return count


def _confined(loc_ws: Workspace, given: str, suffix: str) -> Path:
    """An agent-written file: under .audit/work/, with the expected suffix."""
    # Normalise first, so `.audit/work/../../lib/a.js` can't pass the prefix check.
    rel = PurePosixPath(posixpath.normpath(given or "."))
    if rel.parts[:2] != (".audit", "work") or not rel.name.endswith(suffix):
        raise AuditKitError(f"{given}: must be a {suffix} file under .audit/work/")
    if not all(SAFE_PART.fullmatch(part) for part in rel.parts):
        raise AuditKitError(
            f"{given}: use only letters, digits, '.', '_' and '-' in names"
        )
    if not loc_ws.is_file(rel):
        raise AuditKitError(f"{given}: not found")
    return loc_ws.path(rel)


def plan(name: str, ws: Workspace, arg: str | None) -> list[Job]:
    """The container runs a job needs, in order."""
    install = Job(
        "install",
        ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"),
        "install.txt",
        network=True,
        target_writable=True,
    )
    with_deps = [install] if ws.is_file("package-lock.json") else []
    if name == "structure":
        return [
            *with_deps,
            Job("knip", ("knip", "--reporter", "json", "--no-progress"), "knip.json"),
            Job(
                "depcruise",
                (
                    "depcruise",
                    "--no-config",
                    "--output-type",
                    "json",
                    "--do-not-follow",
                    "node_modules",
                    "--exclude",
                    "node_modules",
                    ".",
                ),
                "depcruise.json",
            ),
        ]
    if name == "tests":
        return [
            *with_deps,
            # Test runners write caches and coverage next to the code; the copy
            # is thrown away after the job, so it's mounted writable.
            Job(
                "tests",
                ("npm", "test", "--ignore-scripts"),
                "tests.txt",
                target_writable=True,
            ),
        ]
    if name == "prove":
        test = _confined(ws, arg or "", ".test.js")
        return [
            *with_deps,
            Job(
                f"prove-{test.parent.name}",
                ("node", "--test", f"/prove/{test.name}"),
                f"prove-{test.parent.name}.txt",
                extra_mounts=((test, f"/prove/{test.name}"),),
            ),
        ]
    if name == "try":
        snippet = _confined(ws, arg or "", ".js")
        lines = snippet.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > SNIPPET_LINES:
            raise AuditKitError(
                f"{arg}: {len(lines)} lines; a snippet has at most {SNIPPET_LINES}"
            )
        return [
            Job(
                f"try-{snippet.stem}",
                ("node", f"/snippet/{snippet.name}"),
                f"try-{snippet.stem}.txt",
                mount_target=False,
                extra_mounts=((snippet, f"/snippet/{snippet.name}"),),
            )
        ]
    raise AuditKitError(f"unknown sandbox job {name!r}; use one of {JOBS}")


def sandbox(s: KitSettings, given: str, name: str, arg: str | None = None) -> None:
    """`kit sandbox`: run one job for a workspace (see run_jobs)."""
    run_jobs(locate(s, given).ws, s.version, s.kit_home, name, arg)


def run_jobs(
    ws: Workspace, version: str, kit_home: Path, name: str, arg: str | None = None
) -> None:
    """Run one sandbox job and write its output under .audit/scans/dynamic/.

    Raises:
        AuditKitError: If the policy denies the sandbox, the job or its file is
            invalid, or the image can't be built.
    """
    if load_policy(ws).sandbox != "allow":
        raise AuditKitError(
            "sandbox denied by .audit/policy.yaml (sandbox: deny); only the tech lead "
            "can allow it for this engagement"
        )
    jobs = plan(name, ws, arg)
    major = node_major(ws)
    tag = f"audit-kit-sandbox:{version}-node{major}"
    run(
        ["docker", "build", "--quiet", "--build-arg", f"NODE_MAJOR={major}",
         "-t", tag, kit_home / "config/sandbox"],
        timeout=LONG,
    )  # fmt: skip
    image = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag]).text.strip()
    ws.mkdir(OUT)
    # ignore_cleanup_errors: a file the container left unremovable mustn't hide
    # the job's results, which are already written.
    COPY_PARENT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="audit-sandbox-", dir=COPY_PARENT, ignore_cleanup_errors=True
    ) as tmp:
        copy = Path(tmp) / "work"
        files = copy_target(ws, copy)
        ok(f"sandbox: copied {files} files; image {image[:19]}")
        for job in jobs:
            job = _stage_agent_files(job, Path(tmp) / "agent")
            code, text = _run_job(image, job, copy)
            ws.write_text(OUT / job.output, text)
            _log(ws, name, job.name, image, code)
            (ok if code == 0 else warn)(f"{job.name}: exit {code} ({OUT / job.output})")
            if job.name == "install" and code != 0:
                warn("install failed; later steps run without dependencies")


def _stage_agent_files(job: Job, staging: Path) -> Job:
    """Copy a job's agent-written files next to the snapshot copy and mount those.

    The daemon may run in a VM that sees only the home folder (colima, Docker
    Desktop), and the workspace can live anywhere, so files are mounted from the
    same place as the copy. Names were already confined by plan().
    """
    if not job.extra_mounts:
        return job
    staging.mkdir(parents=True, exist_ok=True)
    ws = Workspace(staging)
    mounts = []
    for source, target in job.extra_mounts:
        ws.copy_file(source.name, source)
        mounts.append((staging / source.name, target))
    return replace(job, extra_mounts=tuple(mounts))


def _run_job(image: str, job: Job, copy: Path) -> tuple[int, str]:
    name = f"audit-kit-{secrets.token_hex(6)}"
    try:
        result = run(docker_args(image, job, copy, name), timeout=LONG, check=False)
    except CommandError as exc:
        # Killing the docker client doesn't stop the container; remove it by name
        # so untrusted code can't keep running after the job reports failure.
        try:
            run(["docker", "rm", "--force", name], timeout=QUICK, check=False)
        except CommandError:
            warn(f"couldn't remove container {name}; run: docker rm --force {name}")
        return -1, f"not run: {exc}\n"
    out = result.stdout.decode("utf-8", errors="replace")
    err = result.stderr.decode("utf-8", errors="replace")
    if result.code in TIMED_OUT:
        err += f"\n(timed out: stopped after {JOB_SECONDS} s)"
    if job.output.endswith(".json"):
        return result.code, out or json.dumps(
            {"exit": result.code, "stderr": err[-4000:]}
        )
    return result.code, f"exit: {result.code}\n--- stdout\n{out}\n--- stderr\n{err}"


def _log(ws: Workspace, job: str, step: str, image: str, code: int) -> None:
    try:
        before = ws.read_text(LOG) if ws.is_file(LOG) else ""
    except WorkspaceError:
        before = ""
    ws.write_text(
        LOG, before + f"{utc_minute()}\t{job}\t{step}\t{image}\texit {code}\n"
    )
