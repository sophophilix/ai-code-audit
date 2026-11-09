"""Static unused-code analysis for JavaScript (CommonJS and ES modules).

Reads the target's own `.js`/`.cjs`/`.mjs` files, its HTML `<script src>` tags and
`package.json` as text. Nothing is imported, built or run (AGENTS.md rule 2), which
is why the kit doesn't use knip: its plugins load the target's config files.

Results are leads, not verdicts. A string-built `require`, a route that serves a
file by name, or a script run by hand can all make used code look unused, so each
lead carries what the analysis could see about it.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any

from audit_kit.inventory import Inventory
from audit_kit.workspace import Workspace

OUTPUT = ".audit/scans/unused.json"
JS = (".js", ".cjs", ".mjs")
SHOWN = 5
# Node.js core modules (https://nodejs.org/api/), matched on the first path segment.
BUILTINS = frozenset(
    [
        "assert",
        "async_hooks",
        "buffer",
        "child_process",
        "cluster",
        "console",
        "constants",
        "crypto",
        "dgram",
        "diagnostics_channel",
        "dns",
        "domain",
        "events",
        "fs",
        "http",
        "http2",
        "https",
        "inspector",
        "module",
        "net",
        "os",
        "path",
        "perf_hooks",
        "process",
        "punycode",
        "querystring",
        "readline",
        "repl",
        "sea",
        "sqlite",
        "stream",
        "string_decoder",
        "sys",
        "test",
        "timers",
        "tls",
        "trace_events",
        "tty",
        "url",
        "util",
        "v8",
        "vm",
        "wasi",
        "worker_threads",
        "zlib",
    ]
)
STATIC = re.compile(
    r"""\brequire\s*\(\s*(['"])([^'"\n]+)\1\s*\)"""
    r"""|\bimport\s*\(\s*(['"])([^'"\n]+)\3\s*\)"""
    r"""|\bimport\s+(?:[\w*${}\s,]+\s+from\s+)?(['"])([^'"\n]+)\5"""
    r"""|\bexport\s+(?:\*|\{[^}]*\})\s+from\s+(['"])([^'"\n]+)\7"""
)
DYNAMIC = re.compile(r"""\b(?:require|import)\s*\(\s*(?!['"][^'"$\n]*['"]\s*\))""")
SCRIPT_SRC = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*(['"])([^'"]+)\1""", re.I)
EXPORT_OBJECT = re.compile(r"\bmodule\.exports\s*=\s*\{")
EXPORT_PROPERTY = re.compile(r"\b(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=(?!=)")
EXPORT_DECLARED = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)"
)
EXPORT_LIST = re.compile(r"\bexport\s*\{([^}]*)\}(?!\s*from)")
NAME = re.compile(r"[A-Za-z_$][\w$]*")
SCRIPT_FILE = re.compile(r"[\w./-]+\.(?:c|m)?js\b")
# path.join/path.resolve whose first argument is a name and the rest string literals.
_LITERALS = r"((?:\s*,\s*(?:'[^'\n]*'|\"[^\"\n]*\"))*)"
PATH_CALL = re.compile(
    rf"path\.(?:join|resolve)\s*\(\s*([A-Za-z_$][\w$]*){_LITERALS}\s*\)\s*\)"
)
LITERAL = re.compile(r"""'([^'\n]*)'|"([^"\n]*)\"""")


def _literals(text: str) -> list[str]:
    return [a or b for a, b in LITERAL.findall(text)]


def _base_dir(path: str, code: str, name: str) -> str | None:
    """Resolve `__dirname`, or a constant built only from it and literals, to a folder."""
    if name == "__dirname":
        return posixpath.dirname(path)
    m = re.search(
        rf"(?:\b(?:const|let|var)\s+|,\s*){re.escape(name)}\s*=\s*"
        rf"(?:__dirname\b|path\.(?:join|resolve)\s*\(\s*__dirname{_LITERALS}\s*\))",
        code,
    )
    if not m:
        return None
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(path), *_literals(m.group(1) or ""))
    )


def strip_comments(text: str) -> str:
    """Blank out comments, keeping strings, offsets and line breaks.

    Regular-expression literals aren't recognised, so a `//` inside one that isn't
    escaped would be read as a comment. That only hides code from this analysis.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            i += 1
            while i < n and text[i] != c:
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for j in range(i, end):
                if out[j] != "\n":
                    out[j] = " "
            i = end
        else:
            i += 1
    return "".join(out)


def package_name(spec: str) -> str | None:
    """Return the package a bare specifier names, or None for a Node.js core module."""
    spec = spec.removeprefix("node:")
    parts = spec.split("/")
    name = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
    return None if name in BUILTINS else name


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _key_line(text: str, key: str) -> int | None:
    """Return the line of the first `"key":` in a JSON text, or None."""
    found = re.search(rf'"{re.escape(key)}"\s*:', text)
    return _line(text, found.start()) if found else None


def _exported_names(code: str) -> list[tuple[str, int]]:
    """Return (name, line) for each name a file exports by a recognisable pattern."""
    found: list[tuple[str, int]] = []
    for m in EXPORT_OBJECT.finditer(code):
        depth, i = 1, m.end()
        start = i
        while i < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        body, inner = code[start : i - 1], 0
        part_start = 0
        for j, ch in enumerate(body + ","):
            inner += {"{": 1, "(": 1, "[": 1, "}": -1, ")": -1, "]": -1}.get(ch, 0)
            if ch == "," and inner == 0:
                part = re.sub(
                    r"^(?:async|get|set)\s+(?=[\w$]+\s*\()",
                    "",
                    body[part_start:j].strip(),
                )
                part_start = j + 1
                key = NAME.match(part)
                if key and not part.startswith("..."):
                    found.append((key.group(), _line(code, start)))
    found += [
        (m.group(1), _line(code, m.start())) for m in EXPORT_PROPERTY.finditer(code)
    ]
    found += [
        (m.group(1), _line(code, m.start())) for m in EXPORT_DECLARED.finditer(code)
    ]
    for m in EXPORT_LIST.finditer(code):
        for part in m.group(1).split(","):
            names = NAME.findall(part)
            if names:
                found.append((names[-1], _line(code, m.start())))
    return sorted(set(found), key=lambda x: (x[1], x[0]))


@dataclass
class _Graph:
    files: dict[str, str]
    edges: dict[str, set[str]] = field(default_factory=dict)
    packages: dict[str, tuple[str, int]] = field(default_factory=dict)
    dynamic: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)

    def resolve(self, source: str, spec: str) -> str | None:
        base = posixpath.normpath(posixpath.join(posixpath.dirname(source), spec))
        for candidate in (
            base,
            *(base + ext for ext in (*JS, ".json")),
            *(f"{base}/index{ext}" for ext in JS),
        ):
            if candidate in self.files:
                return candidate
        return None


def _scan_imports(graph: _Graph) -> None:
    for path, code in graph.files.items():
        if not path.endswith(JS):
            continue
        targets = graph.edges.setdefault(path, set())
        for m in STATIC.finditer(code):
            spec = next(g for g in m.groups()[1::2] if g)
            if spec.startswith("."):
                target = graph.resolve(path, spec)
                if target:
                    targets.add(target)
                else:
                    graph.unresolved.append(
                        {"file": path, "line": _line(code, m.start()), "text": spec}
                    )
            elif "${" not in spec:
                name = package_name(spec)
                if name and name not in graph.packages:
                    graph.packages[name] = (path, _line(code, m.start()))
        for m in DYNAMIC.finditer(code):
            # require(path.join(__dirname or a constant from it, 'lit', ...)) is
            # knowable, so follow it instead of listing it.
            call = PATH_CALL.match(code, m.end())
            base = call and _base_dir(path, code, call.group(1))
            if call and base is not None:
                spec = posixpath.join(base, *_literals(call.group(2) or ""))
                target = graph.resolve("", "./" + posixpath.normpath(spec))
                if target:
                    targets.add(target)
                    continue
            line = _line(code, m.start())
            snippet = code.splitlines()[line - 1].strip()[:100]
            graph.dynamic.append({"file": path, "line": line, "text": snippet})


def _entry_points(
    graph: _Graph, manifest: dict[str, Any], html: dict[str, str]
) -> dict[str, str]:
    """Return {file: why it's an entry point}."""
    js = [p for p in graph.files if p.endswith(JS)]
    entries: dict[str, str] = {}
    main = graph.resolve("package.json", "./" + str(manifest.get("main") or "index.js"))
    if main:
        entries[main] = "package.json main"
    bins = manifest.get("bin") or {}
    for target in [bins] if isinstance(bins, str) else list(bins.values()):
        resolved = graph.resolve("package.json", "./" + str(target))
        if resolved:
            entries[resolved] = "package.json bin"
    for name, command in (manifest.get("scripts") or {}).items():
        for token in SCRIPT_FILE.findall(str(command)):
            resolved = graph.resolve("package.json", "./" + token)
            if resolved:
                entries.setdefault(resolved, f"package.json scripts.{name}")
    for page, text in html.items():
        for m in SCRIPT_SRC.finditer(text):
            src = m.group(2).split("?")[0].split("#")[0]
            if "//" in src:
                continue  # another host
            local = graph.resolve(page, "./" + src.lstrip("/"))
            hits = (
                [local]
                if local
                else [p for p in js if p.endswith("/" + src.lstrip("/"))]
            )
            for hit in hits:
                entries.setdefault(hit, f"<script src> in {page}")
    return entries


def analyse(ws: Workspace, inv: Inventory, excluded: tuple[str, ...]) -> dict[str, Any]:
    """Build the unused-code report from the target's own files.

    Args:
        ws: The workspace.
        inv: Its inventory; only `own` files are analysed.
        excluded: Folders or files left out of review (detected and project exclusions).
    """

    def kept(path: str) -> bool:
        return not any(
            path == e or path.startswith(e.rstrip("/") + "/") for e in excluded
        )

    own = [e.path for e in inv.of("own") if e.kind == "file" and kept(e.path)]
    code = {p: strip_comments(ws.read_text(p)) for p in own if p.endswith(JS)}
    html = {p: ws.read_text(p) for p in own if p.endswith((".html", ".htm"))}
    manifest: dict[str, Any] = {}
    manifest_text = ""
    if ws.is_file("package.json"):
        manifest_text = ws.read_text("package.json")
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError:
            manifest = {}
    graph = _Graph(files={**code, **{p: "" for p in own if p.endswith(".json")}})
    _scan_imports(graph)
    entries = _entry_points(graph, manifest, html)

    reached: set[str] = set()
    todo = list(entries)
    while todo:
        path = todo.pop()
        if path not in reached:
            reached.add(path)
            todo += sorted(graph.edges.get(path, ()))
    required_by: dict[str, list[str]] = {}
    for source, targets in graph.edges.items():
        for target in targets:
            required_by.setdefault(target, []).append(source)
    texts = {**code, **html}
    unreachable = []
    for path in sorted(p for p in code if p not in reached):
        stem = posixpath.splitext(posixpath.basename(path))[0]
        word = re.compile(rf"\b{re.escape(stem)}\b")
        unreachable.append(
            {
                "file": path,
                "required_by": sorted(required_by.get(path, []))[:SHOWN],
                "name_mentioned_in": sorted(
                    p for p, t in texts.items() if p != path and word.search(t)
                )[:SHOWN],
            }
        )

    sections = (
        "dependencies",
        "devDependencies",
        "optionalDependencies",
        "peerDependencies",
    )
    declared = {n: s for s in sections for n in (manifest.get(s) or {})}
    scripts = " ".join(str(v) for v in (manifest.get("scripts") or {}).values())
    unused_deps = [
        {
            "name": n,
            "section": s,
            "file": "package.json",
            "line": _key_line(manifest_text, n),
        }
        for n, s in sorted(declared.items())
        if n not in graph.packages and not re.search(rf"\b{re.escape(n)}\b", scripts)
    ]
    undeclared = [
        {"name": n, "file": f, "line": line}
        for n, (f, line) in sorted(graph.packages.items())
        if n not in declared
    ]

    unused_exports = []
    for path, text in sorted(code.items()):
        others = [t for p, t in texts.items() if p != path]
        for name, line in _exported_names(text):
            word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
            if not any(word.search(t) for t in others):
                unused_exports.append({"file": path, "name": name, "line": line})

    return {
        "generated_by": "kit scan: static unused-code analysis (deterministic, no execution)",
        "method": (
            "Own .js/.cjs/.mjs files, comments removed, parsed with regular expressions "
            "for require(), import and export. Entry points: package.json main, bin and "
            "files named in scripts, and <script src> in own HTML. A file is unreachable "
            "if no entry point leads to it through relative requires. An export is "
            "unused if its name appears in no other own .js or .html file."
        ),
        "limits": [
            "Dynamic require() or import() with a computed path is listed, not followed.",
            "Files served or run by name (static folders, routes, cron, manual scripts) "
            "look unreachable; check name_mentioned_in and Chesterton's Fence first.",
            "Regular-expression literals containing // can hide code from the parser.",
            "Unused exports are matched by name only, so a common name can hide one.",
        ],
        "counts": {
            "files": len(code),
            "entry_points": len(entries),
            "unreachable_files": len(unreachable),
            "dynamic_requires": len(graph.dynamic),
            "unresolved_imports": len(graph.unresolved),
            "unused_dependencies": len(unused_deps),
            "undeclared_dependencies": len(undeclared),
            "unused_exports": len(unused_exports),
        },
        "entry_points": [{"file": f, "why": w} for f, w in sorted(entries.items())],
        "unreachable_files": unreachable,
        "dynamic_requires": graph.dynamic,
        "unresolved_imports": graph.unresolved,
        "unused_dependencies": unused_deps,
        "undeclared_dependencies": undeclared,
        "unused_exports": unused_exports,
    }


def write_report(ws: Workspace, inv: Inventory, excluded: tuple[str, ...]) -> None:
    """Write .audit/scans/unused.json."""
    report = analyse(ws, inv, excluded)
    ws.write_text(OUTPUT, json.dumps(report, indent=1) + "\n")
