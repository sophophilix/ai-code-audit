"""Workspace lifecycle: create, seed, install, detect, status, list.

A workspace is a disposable clone (real, git sources) or a history-free snapshot
(eval, or any folder or tar archive), with the kit installed into it. Every step
checks what exists first, so re-running a command does only what's missing.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from audit_kit.console import ok, say, skip, warn
from audit_kit.detection import detect, write_outputs
from audit_kit.errors import AuditKitError
from audit_kit.inventory import AI_INSTRUCTION_FILES, Inventory, build
from audit_kit.projects import NAME as WORKSPACE_NAME
from audit_kit.projects import list_lines, project_dir
from audit_kit.runner import LONG, git, run
from audit_kit.seeding import seed
from audit_kit.settings import KitSettings
from audit_kit.state import STATE_FILE, State
from audit_kit.workspace import Workspace

KIT_PARTS = (
    "AGENTS.md",
    "VERSION",
    "bin",
    "core",
    "profiles",
    "evals",
    "templates",
    "config",
)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CREDENTIALS_IN_URL = re.compile(r"//[^/@]*@")
TAR = re.compile(r"\.(tar|tar\.gz|tgz)$")
SHOWN = 10


@dataclass(frozen=True)
class Located:
    """A resolved workspace with its state and project folder."""

    ws: Workspace
    state: State
    project: Path


def today() -> str:
    """Return today's date in UTC as YYYY-MM-DD."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def utc_minute() -> str:
    """Return the current UTC time to the minute."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")


def locate(s: KitSettings, given: str) -> Located:
    """Resolve a workspace path or name (in the workspaces folder)."""
    if not given:
        raise AuditKitError("give a workspace path or name (kit list)")
    path = Path(given)
    if not path.is_dir() and (s.workspaces_dir / given).is_dir():
        path = s.workspaces_dir / given
    if not (path / STATE_FILE).is_file():
        raise AuditKitError(
            f"{given} is not a kit workspace (create one with: kit workspace)"
        )
    ws = Workspace(path)
    state = State(ws)
    return Located(
        ws=ws, state=state, project=project_dir(s.projects_dir, state.get("project"))
    )


def extract_archive(archive: bytes, dest: Path) -> None:
    """Extract a tar archive into dest, refusing entries that would escape it.

    Raises:
        AuditKitError: If the archive contains absolute paths, `..` or unsafe links.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            # The "data" filter refuses absolute paths, ".." and links that leave dest.
            tar.extractall(dest, filter="data")
    except tarfile.FilterError as exc:
        raise AuditKitError(f"unsafe entry in the repository archive: {exc}") from exc


def _source_kind(source: str) -> str:
    """Return "git", "folder" or "archive" for a source path or URL."""
    local = Path(source).expanduser()
    if local.is_file():
        if TAR.search(local.name):
            return "archive"
        raise AuditKitError(
            f"{source}: unsupported archive (use .tar, .tar.gz or .tgz; zip has no safe extraction filter yet)"
        )
    if local.is_dir():
        inside = run(["git", "rev-parse", "--show-toplevel"], cwd=local, check=False)
        if inside.code == 0 and Path(inside.text).resolve() == local.resolve():
            return "git"
        return "folder"
    return "git"


def _manifest_sha256(ws: Workspace) -> str:
    """Hash the sorted (path, sha256) list of every file: a non-git source's fingerprint."""
    tree = ws.tree(frozenset())
    lines = [f"{r.as_posix()}\0{ws.digest(r).sha256}\n" for r in tree.files]
    lines += [f"{r.as_posix()}\0->{ws.link_target(r)}\n" for r in tree.skipped_symlinks]
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def _ls_tree(repo: Path, ref: str) -> dict[str, tuple[str, str]]:
    """Return {path: (object type, object id)} for every entry in a commit's tree."""
    out = run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", ref], cwd=repo, timeout=LONG
    )
    found: dict[str, tuple[str, str]] = {}
    for record in out.stdout.split(b"\0"):
        if record:
            meta, path = record.split(b"\t", 1)
            _mode, kind, oid = meta.decode().split()
            found[path.decode("utf-8", errors="surrogateescape")] = (kind, oid)
    return found


def _restore_export_ignored(ws: Workspace, repo: Path, ref: str) -> list[str]:
    """Write back files `git archive` left out (export-ignore), from git objects."""
    on_disk = {r.as_posix() for r in ws.tree(frozenset()).files}
    on_disk |= {r.as_posix() for r in ws.tree(frozenset()).skipped_symlinks}
    missing = sorted(
        p
        for p, (kind, _) in _ls_tree(repo, ref).items()
        if kind == "blob" and p not in on_disk
    )
    for path in missing:
        blob = run(["git", "cat-file", "blob", f"{ref}:{path}"], cwd=repo, timeout=LONG)
        ws.write_bytes(path, blob.stdout)
    return missing


def _refuse_kit_names(ws: Workspace) -> None:
    clash = sorted(n for n in (".audit", ".audit-kit") if ws.exists(n))
    if clash:
        raise AuditKitError(
            f"the source has its own {', '.join(clash)}, which the kit uses; rename it in a copy and retry"
        )


def _disk_blobs(ws: Workspace) -> dict[str, str]:
    """Return {path: git blob id} for every file and symlink on disk, without writing objects."""
    tree = ws.tree()
    blobs = {r.as_posix(): ws.digest(r).git_blob for r in tree.files}
    blobs |= {
        r.as_posix(): _blob_id(
            ws.link_target(r).encode("utf-8", errors="surrogateescape")
        )
        for r in tree.skipped_symlinks
    }
    return blobs


def _check_copy(ws: Workspace, tree: dict[str, tuple[str, str]], commit: str) -> None:
    """Refuse a snapshot whose files differ from the source commit they were taken from.

    Raises:
        AuditKitError: If any path is missing, extra or has different content.
    """
    differences = tree_differences(_disk_blobs(ws), tree, "the source commit")
    if differences:
        shown = "\n  ".join(differences[:SHOWN])
        more = (
            f"\n  ... and {len(differences) - SHOWN} more"
            if len(differences) > SHOWN
            else ""
        )
        raise AuditKitError(
            f"the copy doesn't match source commit {commit[:12]} ({len(differences)} difference(s)); "
            f"delete {ws.root} and retry:\n  {shown}{more}"
        )


def _snapshot_from(source: str, kind: str, ref: str, path: Path) -> dict[str, str]:
    """Fill path with the source's files; return the facts that prove what was taken."""
    ws = Workspace(path)
    if kind == "folder":
        shutil.copytree(
            Path(source).expanduser(), path, symlinks=True, dirs_exist_ok=True
        )
        return {"source_sha256": _manifest_sha256(ws)}
    if kind == "archive":
        data = Path(source).expanduser().read_bytes()
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
                tar.extractall(path, filter="data")
        except tarfile.FilterError as exc:
            raise AuditKitError(f"unsafe entry in the archive: {exc}") from exc
        except tarfile.TarError as exc:
            raise AuditKitError(
                f"{source}: not a readable tar archive ({exc})"
            ) from exc
        return {
            "archive_sha256": hashlib.sha256(data).hexdigest(),
            "source_sha256": _manifest_sha256(ws),
        }
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(source).expanduser()
        if not local.is_dir():
            git("clone", "-q", source, Path(tmp) / "src", timeout=LONG)
            local = Path(tmp) / "src"
        commit = git("rev-parse", f"{ref}^{{commit}}", cwd=local)
        archive = run(
            ["git", "archive", "--format=tar", commit], cwd=local, timeout=LONG
        )
        extract_archive(archive.stdout, path)
        restored = _restore_export_ignored(ws, local, commit)
        _check_copy(ws, _ls_tree(local, commit), commit)
        tree = git("rev-parse", f"{commit}^{{tree}}", cwd=local)
    for rel in restored[:SHOWN]:
        warn(f"restored {rel} (git archive leaves out export-ignore paths)")
    if len(restored) > SHOWN:
        warn(f"restored {len(restored) - SHOWN} more export-ignore paths")
    return {"source_commit": commit, "source_tree": tree}


def delta_key(ws: Workspace) -> PurePosixPath:
    """Where an eval workspace's differences from its source are listed, under the project."""
    return PurePosixPath("keys") / f"source-delta-{ws.root.name}.txt"


def _record_delta(project: Path, audited: Workspace, lines: list[str]) -> int:
    """Append to the eval delta list in the project's keys/; return its length.

    The agents can read everything under .audit/, so the paths that were removed
    or seeded stay with the answer key, never inside the audited workspace.
    """
    ws = Workspace(project)
    rel = delta_key(audited)
    ws.mkdir("keys")
    before = ws.read_text(rel) if ws.is_file(rel) else ""
    text = before + "".join(f"{line}\n" for line in lines)
    ws.write_text(rel, text)
    return len(text.splitlines())


def _commit_snapshot(path: Path, branch: str) -> str:
    """Commit every file, ignored or not, as the single snapshot commit."""
    git("init", "-q", "-b", branch, cwd=path)
    git("add", "-A", "--force", cwd=path, timeout=LONG)
    git("commit", "-qm", "snapshot", cwd=path, timeout=LONG)
    return git("rev-parse", "HEAD", cwd=path)


def create_workspace(
    s: KitSettings,
    name: str,
    source: str,
    ref: str,
    mode: str,
    date: str,
    *,
    folder: str | None = None,
) -> Path:
    """Create a workspace from a git repository, a folder or a tar archive.

    Real mode on a git source clones it, keeping history. Everything else becomes
    a single snapshot commit holding every file (ignore rules don't apply). Eval
    mode then removes the project's eval-remove.txt paths. Skips if it exists.

    Args:
        s: Kit settings.
        name: The project's name.
        source: A git URL, a local repository, a folder or a tar archive.
        ref: The commit, tag or branch to audit.
        mode: `eval` or `real`.
        date: The audit date, YYYY-MM-DD; it names the audit branch.
        folder: The workspace folder's name; defaults to `<name>-<mode>-<date>`.
            Give one to run a second audit of the same kind on the same day.

    Raises:
        AuditKitError: If an argument is invalid or the project doesn't exist.
    """
    if mode not in ("eval", "real"):
        raise AuditKitError("--mode must be eval or real")
    if not DATE.match(date):
        raise AuditKitError("--date must be YYYY-MM-DD")
    if folder is not None and not WORKSPACE_NAME.match(folder):
        raise AuditKitError(
            f"--name {folder!r}: use letters, digits, '.', '_' and '-', "
            "starting with a letter or digit"
        )
    project = project_dir(s.projects_dir, name)
    if not project.is_dir():
        raise AuditKitError(f"no project '{name}' (run: kit project {name})")
    path = s.workspaces_dir / (folder or f"{name}-{mode}-{date}")
    if (path / STATE_FILE).is_file():
        skip(f"workspace exists: {path}")
        return path
    if path.exists():
        raise AuditKitError(f"{path} exists but isn't a kit workspace; move it aside")
    kind = _source_kind(source)
    if kind != "git" and ref not in ("", "-"):
        warn(f"--ref {ref} ignored: a {kind} has no commits")
    s.workspaces_dir.mkdir(parents=True, exist_ok=True)
    branch = f"audit/eval-{date}" if mode == "eval" else f"audit/{date}"
    if mode == "real" and kind == "git":
        git("clone", "-q", source, path, timeout=LONG)
        git("checkout", "-q", ref, cwd=path)
        git("checkout", "-q", "-b", branch, cwd=path)
        ws = Workspace(path)
        _refuse_kit_names(ws)
        facts = {
            "source_commit": git("rev-parse", "HEAD", cwd=path),
            "source_tree": git("rev-parse", "HEAD^{tree}", cwd=path),
        }
        snapshot = facts["source_commit"]
    else:
        path.mkdir()
        facts = _snapshot_from(source, kind, ref, path)
        ws = Workspace(path)
        _refuse_kit_names(ws)
        removed: list[str] = []
        if mode == "eval":
            for rel in list_lines(project / "eval-remove.txt"):
                if ws.exists(rel) and ws.remove(rel):
                    removed.append(rel)
                    ok(f"removed {rel} (eval-remove.txt)")
            facts["source_delta"] = str(
                _record_delta(project, ws, [f"removed\t{rel}" for rel in removed])
            )
        facts["eval_removed"] = str(len(removed))
        snapshot = _commit_snapshot(path, branch)
    state = State(ws)
    for key, value in (
        ("project", name),
        ("mode", mode),
        ("source", CREDENTIALS_IN_URL.sub("//", source)),
        ("source_kind", kind),
        ("ref", ref if kind == "git" else "-"),
        *facts.items(),
        ("snapshot", snapshot),
        ("created", utc_minute()),
    ):
        state.set(key, value)
    ok(f"workspace {path}")
    if kind != "git":
        warn(
            "no git history: history checks (secrets in past commits, churn) become limitations"
        )
    if mode == "eval":
        say(
            f"Next: kit seed {path}   (or plant by hand and record them in {project}/keys/), then: kit ready {path}"
        )
    else:
        say(f"Next: kit ready {path}")
    return path


def seed_workspace(s: KitSettings, given: str) -> None:
    """Plant seeded issues in an eval workspace; the key goes to the project's keys/."""
    loc = locate(s, given)
    if loc.state.get("mode") != "eval":
        raise AuditKitError("seeding is for eval workspaces only")
    if loc.state.get("seeded") == "yes":
        skip("already seeded")
        return
    if loc.state.get("sealed") == "yes":
        raise AuditKitError(
            "snapshot already sealed; create a fresh eval workspace to seed"
        )
    key = loc.project / "keys" / f"seeded-{loc.ws.root.name}.md"
    plan = seed(loc.ws, key)
    ok(f"planted {len(plan.plants)} issues; key: {key}")
    loc.state.set("seeded", "yes")
    say(
        f"Next: kit ready {loc.ws.root}   (the plants are sealed into the snapshot; the key stays outside the workspace)"
    )


def _outside_changes(root: Path) -> str:
    return git("status", "--porcelain", "--", ".", ":(exclude).audit", cwd=root)


def install(s: KitSettings, given: str, *, no_seed: bool = False) -> None:
    """Seal eval plants, quarantine AI instruction files, install the kit, commit setup."""
    loc = locate(s, given)
    ws, state, root = loc.ws, loc.state, loc.ws.root
    if not loc.project.is_dir():
        raise AuditKitError(f"project folder missing: {loc.project}")
    first = state.get("installed") != "yes"
    outside = _outside_changes(root)

    if state.get("mode") == "eval" and state.get("sealed") != "yes":
        if outside:
            if git("rev-list", "--count", "HEAD", cwd=root) != "1":
                raise AuditKitError("eval snapshot has more than one commit")
            git("add", "-A", "--force", "--", ".", ":(exclude).audit", cwd=root)
            seeded = git("diff", "--cached", "--name-status", "--no-renames", cwd=root)
            count = _record_delta(
                loc.project, ws, [f"seeded {line}" for line in seeded.splitlines()]
            )
            git("commit", "-q", "--amend", "-m", "snapshot", cwd=root)
            state.set("snapshot", git("rev-parse", "HEAD", cwd=root))
            state.set("source_delta", str(count))
            ok("sealed seeded changes into the snapshot commit")
        elif no_seed:
            warn(
                "no seeded issues (--no-seed): recall can only be scored against known issues"
            )
        else:
            raise AuditKitError(
                f"no seeded issues found. Run: kit seed {root} (or plant by hand), "
                f"or deliberately: kit install {root} --no-seed"
            )
        state.set("sealed", "yes")
    elif first and outside:
        raise AuditKitError(
            "target has uncommitted changes; commit or discard them first"
        )

    if first:
        for rel in AI_INSTRUCTION_FILES:
            if ws.exists(rel):
                tracked = (
                    run(
                        ["git", "ls-files", "--error-unmatch", rel],
                        cwd=root,
                        check=False,
                    ).code
                    == 0
                )
                target = f".audit/quarantine/{rel}"
                ws.mkdir(str(Path(target).parent))
                if tracked:
                    git("mv", "-k", rel, target, cwd=root)
                else:
                    ws.move(rel, target)
                ok(f"quarantined {rel}")

    ws.remove(".audit-kit")
    for part in KIT_PARTS:
        ws.copy_in(f".audit-kit/{part}", s.kit_home / part)
    for script in ws.path(".audit-kit/bin").iterdir():
        script.chmod(0o755)
    ok(f"kit {s.version} -> .audit-kit")

    adapter = s.kit_home / "adapters/claude-code"
    for sub in ("agents", "commands"):
        for md in sorted((adapter / sub).glob("*.md")):
            ws.copy_in(f".claude/{sub}/{md.name}", md)
    for skill in [
        *sorted((s.kit_home / "core/skills").iterdir()),
        *sorted((s.kit_home / "profiles").iterdir()),
    ]:
        if skill.is_dir():
            ws.copy_in(f".claude/skills/{skill.name}", skill)
    example = adapter / "settings.audit.example.json"
    if not ws.exists(".claude/settings.json"):
        ws.copy_in(".claude/settings.json", example)
        ok("created .claude/settings.json")
    elif ws.read_text(".claude/settings.json") != example.read_text(encoding="utf-8"):
        warn(
            ".claude/settings.json differs from the kit's example (kept yours; review it)"
        )
    ok("claude-code adapter")

    for folder in ("scans", "adr", "diagrams", "work"):
        ws.mkdir(f".audit/{folder}")
    if (loc.project / "beliefs.md").is_file() and not ws.exists(".audit/beliefs.md"):
        ws.copy_in(".audit/beliefs.md", loc.project / "beliefs.md")
        ok(
            "copied beliefs.md (read only by discovery's last step and the lead reviewer)"
        )
    for name in ("project.md", "models.yaml", "policy.yaml"):
        source = loc.project / name
        if name == "policy.yaml" and not source.is_file():
            continue  # projects made before 0.10.0: every policy default (deny)
        if not ws.exists(f".audit/{name}"):
            ws.copy_in(f".audit/{name}", source)
            ok(f"copied {name} from project")
        elif ws.read_text(f".audit/{name}") != source.read_text(encoding="utf-8"):
            warn(f".audit/{name} differs from {source} (kept the workspace copy)")
        else:
            skip(f"{name} up to date")

    state.set("kit_version", s.version)
    state.set("kit_commit", git("rev-parse", "--short", "HEAD", cwd=s.kit_home))
    state.set("installed", "yes")
    if ws.is_file(".audit/detected.md"):
        # A kit upgrade changes the rules, so derived files must not keep the old stamp.
        detect_workspace(s, given)
    git("add", "-A", cwd=root)
    if run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False).code == 0:
        skip("setup unchanged")
    else:
        git("commit", "-qm", f"audit setup: kit {s.version}", cwd=root)
        ok("committed setup")


def snapshot_commit(loc: Located) -> str:
    """Return the commit holding the audited files, before any kit setup commit."""
    recorded = loc.state.get("snapshot")
    if recorded:
        return recorded
    root = loc.ws.root
    if loc.state.get("mode") == "eval":  # workspaces made before 0.10.0
        return git("rev-list", "--max-parents=0", "HEAD", cwd=root)
    return git("rev-parse", f"{loc.state.get('ref')}^{{commit}}", cwd=root)


def _blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def cross_check(inv: Inventory, tree: dict[str, tuple[str, str]]) -> list[str]:
    """Compare the inventory with the snapshot's git tree; return the differences.

    Args:
        inv: The inventory built from the files on disk.
        tree: {path: (object type, object id)} from `git ls-tree -r`.

    Returns:
        One line per path that is missing, extra, or has different content.
    """
    disk: dict[str, str] = {}
    for e in inv.entries:
        if e.kind == "file":
            disk[e.path] = e.git_blob
        elif e.kind == "symlink":
            disk[e.path] = _blob_id(e.target.encode("utf-8", errors="surrogateescape"))
    return tree_differences(disk, tree, "the snapshot commit")


def tree_differences(
    disk: dict[str, str], tree: dict[str, tuple[str, str]], name: str
) -> list[str]:
    """Compare {path: blob id} on disk with a git tree; return one line per difference.

    Submodule entries are left out: their contents are never in a snapshot.
    """
    git_files = {p: oid for p, (kind, oid) in tree.items() if kind == "blob"}
    lines = [
        f"in {name}, not on disk: {p}" for p in sorted(git_files.keys() - disk.keys())
    ]
    lines += [
        f"on disk, not in {name}: {p}" for p in sorted(disk.keys() - git_files.keys())
    ]
    lines += [
        f"content differs from {name}: {p}"
        for p in sorted(git_files.keys() & disk.keys())
        if git_files[p] != disk[p]
    ]
    return lines


def inventory_workspace(loc: Located) -> tuple[Inventory, str]:
    """Build the inventory and prove it matches the snapshot commit.

    Raises:
        AuditKitError: If any path differs between the files and the snapshot commit.
    """
    root = loc.ws.root
    commit = snapshot_commit(loc)
    tree = _ls_tree(root, commit)
    gitlinks = tuple(
        sorted((p, oid) for p, (kind, oid) in tree.items() if kind == "commit")
    )
    inv = build(loc.ws, gitlinks)
    differences = cross_check(inv, tree)
    if differences:
        shown = "\n  ".join(differences[:SHOWN])
        more = (
            f"\n  ... and {len(differences) - SHOWN} more"
            if len(differences) > SHOWN
            else ""
        )
        raise AuditKitError(
            f"the files don't match snapshot commit {commit[:12]} ({len(differences)} difference(s)):\n  {shown}{more}"
        )
    return inv, commit


def detect_workspace(s: KitSettings, given: str) -> None:
    """Write the inventory, checked against the snapshot commit, then run detection."""
    loc = locate(s, given)
    inv, commit = inventory_workspace(loc)
    found = detect(loc.ws, inv)
    write_outputs(loc.ws, found, commit[:12], s.version)
    ok(f"inventory: {len(inv.entries)} paths, matches snapshot {commit[:12]}")
    ok(f"profiles: {', '.join(found.resolved)}")
    ok(f"excluded: {', '.join(e.pattern for e in found.scope.exclusions) or 'none'}")
    for problem in found.problems:
        warn(problem)
    say(f"  see {loc.ws.root}/.audit/detected.md (confirm it at Checkpoint 1)")


def checkpoint(root: Path, message: str) -> bool:
    """Commit .audit/ with the workspace's own checkpoint script; return True if it ran."""
    return (
        run([root / ".audit-kit/bin/checkpoint", message], cwd=root, check=False).code
        == 0
    )


def status(s: KitSettings, given: str) -> None:
    """Show a workspace's state, run state and any active locks."""
    loc = locate(s, given)
    say(str(loc.ws.root))
    for line in loc.state.lines():
        say(f"  {line}")
    if loc.ws.is_file(".audit/run-state.md"):
        say("run-state:")
        for line in loc.ws.read_text(".audit/run-state.md").splitlines():
            say(f"  {line}")
    else:
        say(f"  no run yet (cd {loc.ws.root} && claude, then /audit)")
    work = loc.ws.root / ".audit/work"
    for lock in sorted(work.glob("*/LOCK")) if work.is_dir() else []:
        rel = lock.relative_to(loc.ws.root).as_posix()
        if "state: active" in loc.ws.read_text(rel):
            warn(f"active lock: {rel}")


def list_workspaces(s: KitSettings) -> None:
    """List workspaces with their kit version and where their run is up to."""
    if not s.workspaces_dir.is_dir():
        return
    for path in sorted(s.workspaces_dir.iterdir()):
        if not (path / STATE_FILE).is_file():
            continue
        ws = Workspace(path)
        nxt = "not started"
        if ws.is_file(".audit/run-state.md"):
            match = re.search(
                r"^next: (.*)$", ws.read_text(".audit/run-state.md"), re.M
            )
            nxt = match.group(1) if match else ""
        say(f"  {path.name:<45} kit {State(ws).get('kit_version'):<7} {nxt}")
