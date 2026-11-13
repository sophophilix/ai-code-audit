---
name: python
description: Use when the audited system is a Python application, library or CLI. Gives search patterns, what the kit's Python scans show and don't, and the stack check catalogue for packaging, configuration, storage, subprocesses, local model clients and releases.
---

# Python stack profile

## Sources
- Python Packaging User Guide: https://packaging.python.org/en/latest/
- `pyproject.toml` specification: https://packaging.python.org/en/latest/specifications/pyproject-toml/
- Dependency groups (PEP 735): https://peps.python.org/pep-0735/
- Python release status and end-of-life dates: https://devguide.python.org/versions/
- uv documentation (lockfile, `uv sync --locked`, tool installs): https://docs.astral.sh/uv/
- Ruff rules: https://docs.astral.sh/ruff/rules/
- `subprocess` security considerations: https://docs.python.org/3/library/subprocess.html#security-considerations
- `sqlite3` placeholders and transaction control: https://docs.python.org/3/library/sqlite3.html
- `logging` and structlog: https://docs.python.org/3/library/logging.html, https://www.structlog.org/en/stable/
- Pydantic models and strict mode: https://docs.pydantic.dev/latest/
- OWASP Secure Coding (Python-relevant cheat sheets): https://cheatsheetseries.owasp.org/
- OpenSSF Concise Guide for Evaluating Open Source Software: https://best.openssf.org/

The `python-review` core skill holds the language checks (`PY-*`). This profile
holds the stack and operations checks (`PYAPP-*`) that the stage agents apply.

## What the kit's Python scans show (ADR 0010)
- `scans/lint-python.json`: Ruff with the kit's `config/ruff.audit.toml`. The
  target's Ruff settings and `# noqa` comments are ignored, so a row may be one the
  team decided to switch off. Read the suppression before you call it a defect.
- `scans/deps-audit.json`: osv-scanner over each `uv.lock`, `poetry.lock`,
  `pdm.lock` or `Pipfile.lock`. A project with only `requirements.txt` and no pins
  has no reliable audit. Record that as a limitation.
- `scans/sast.sarif`: Semgrep, with `p/python` when Python is present.
- **Not run:** type checking (the target's dependencies are never installed) and
  unused-code analysis. Say so in Limitations. Don't call the code type-safe
  because the target's CI runs mypy: `scans/gates.md` shows what the target
  claims to run, and that's evidence of the pipeline, not of the code.

## Search patterns (`grep -n`)
<!-- brief: python -->
| Purpose | Pattern |
|---|---|
| Entry points | `^\[project\.scripts\]` in `pyproject.toml`; `if __name__ == "__main__"`; `@app\.command`, `typer\.Typer(`, `click\.(command\|group)` |
| Configuration reads | `os\.environ`, `os\.getenv`, `tomllib\.load`, `BaseSettings` |
| Subprocesses | `subprocess\.`, `os\.system`, `os\.popen`, `shlex` |
| SQL | `\.execute\(`, `\.executemany\(`, `\.executescript\(` |
| Network | `httpx\.`, `requests\.`, `urllib\.request`, `socket\.`, `OpenAI\(`, `base_url` |
| File writes and deletes | `\.write_text\(`, `\.write_bytes\(`, `open\(.*['"]w`, `os\.replace`, `shutil\.(copy\|move\|rmtree)`, `\.unlink\(` |
| Plugin loading | `entry_points\(`, `importlib\.import_module`, `__import__` |
| Secrets | `keyring\.`, `api_key`, `token`, `password`, `secret` |

## Check catalogue
<!-- brief: python -->

| CHECK-ID | Check | Evidence | Typical severity if failing |
|---|---|---|---|
| PYAPP-RUNTIME | `requires-python` covers only supported Python versions, and CI tests every version it claims | `pyproject.toml`; `.python-version`; CI matrix; devguide versions page | High if a claimed version is end-of-life |
| PYAPP-LOCK | Applications commit a lockfile, and CI installs from it (`uv sync --locked`, `--frozen`); version ranges have honest lower bounds | `uv.lock`; CI config | Medium |
| PYAPP-DEPS | Each runtime dependency is used, maintained and needed in the base install; heavy or optional engines are extras | `pyproject.toml` vs imports; `scans/deps-audit.json` | Low–Medium; High with a known advisory on a reachable path |
| PYAPP-CONFIG | Configuration is loaded and validated once at start-up, with clear errors; no scattered `os.getenv` calls; secret values never in TOML or source | grep config reads; read the loader | Medium; High for a secret in a committed file |
| PYAPP-SUBPROCESS | External commands run with an argument list, a timeout, a known executable path, and checked exit status | grep subprocess calls | High if input reaches a command |
| PYAPP-STORAGE | Database writes have explicit transactions, migrations are versioned and recoverable, and file plus database changes that must agree have a recovery path | read the store and migration code | Medium; High if a crash can lose or corrupt records |
| PYAPP-FILE-SAFETY | Code that copies, moves or deletes a person's files checks permission, never overwrites without a check, and can be undone or recovered | read file operations end to end | High |
| PYAPP-MODEL-CLIENT | Calls to model servers have timeouts, bounded retries, a size limit on what's sent, and a check that the endpoint is the one configured (loopback when the product promises local processing) | read the client and its config | Medium; High if document content can reach an endpoint the person didn't choose |
| PYAPP-PLUGINS | Plugins loaded through entry points can't bypass validation or permissions, and a missing or broken plugin fails with a clear message | read the loader and the plugin contract | Medium |
| PYAPP-LOGGING | Logs go to stderr, data output to stdout; no document content, personal data or secrets in logs or exceptions | grep logger calls near content | Medium; High for personal data in logs |
| PYAPP-CLI-EXIT | Each command has documented exit codes, and a failure never exits 0 | read command handlers | Low–Medium |
| PYAPP-RELEASE | The sdist and wheel contain only what's intended (no private data, tests with personal data, or local config); version, licence and metadata are correct | `[tool.hatch.build]` or equivalent; `MANIFEST.in` | High if private data would be published |
| PYAPP-CI-GATES | CI runs lint, type check, tests with a coverage floor, a dependency audit and SAST on every change, with pinned action versions | `.github/workflows/*`; `scans/gates.md` | Medium |

## Manifest checks
<!-- brief: manifest -->
For a `pyproject.toml` unit: what the file alone can show. A check that needs the
lockfile's contents, the pipeline or the host is an open edge, not a pass.

| CHECK-ID | Check | Typical severity if failing |
|---|---|---|
| PYAPP-RUNTIME | `requires-python` names only supported versions; classifiers agree | High if end-of-life |
| PYAPP-DEPS | No runtime dependency is only used by tests or tools; no unbounded or `*` ranges; heavy optional engines are extras | Low–Medium |
| PYAPP-RELEASE | Build includes and excludes keep private data, playgrounds and caches out of the sdist and wheel; licence and readme are declared | High if private data would ship |
| SLOP-PHANTOM-DEP | A declared distribution that no own file imports, or a name that looks like a typosquat of a well-known package | Low; Medium with a known advisory |

## Notes for recommendations
<!-- brief: python -->
- Recommend incremental change behind tests (characterisation tests first), not
  rewrites. Large modules usually split along their existing command or
  operation boundaries.
- Recommend the target's own toolchain (its `pyproject.toml` and CI) where it's
  sound, rather than a new one.
