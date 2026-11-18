# Contributing

Thanks for looking. Issues, questions and pull requests are all welcome.

## Report a problem or suggest a change

Open an issue. For a wrong or missed finding, the most useful report has:

- the kit version (`cat VERSION`)
- the check ID, such as `SLOP-SWALLOW`
- a small code sample that shows the problem, with nothing private in it

Report a security problem in the kit itself as `SECURITY.md` describes, not in
a public issue.

## Make a change

1. Fork the repository and create a branch from `main`.
2. Run `uv sync --frozen` once to create the locked environment.
3. Make the change. Add or update tests for any change in behaviour.
4. Run `make check`. It runs Ruff, mypy, Bandit, Semgrep, the tests with
   coverage, and the dependency audit.
5. Bump `VERSION` (and the matching lines in `pyproject.toml`,
   `src/audit_kit/__init__.py` and `uv.lock`), and add a `CHANGELOG.md` entry.
6. Open a pull request. `main` needs a passing check run and one approval.

A change to an agent definition, a skill or a check catalogue changes what the
agents report. Say in the changelog entry how you tested it: a live review of a
few units is enough, and the entry should give the result even when it is
mixed. `evals/README.md` describes the full evaluation.

## Where things go

| Change | Put it in |
|---|---|
| A rule for every agent | `AGENTS.md` |
| How one role works | `core/agents/<role>.md` |
| A check, or knowledge of a stack, cloud or regulator | a pack in `profiles/<name>/` with `pack.toml` and `SKILL.md` (ADR 0012) |
| A decision that changes how the kit works | a new record in `docs/decisions/` |
| Tool-specific settings | `adapters/` |

## Keep client details out of this repository

This repository is public. A client's name, systems, file names and findings
stay in its audit workspace or in `use-cases/<name>.local.md`. Git ignores
every `*.local.*` file. In decision records and the changelog, call a client
codebase "a pilot app" or describe its type, such as "a council reporting
site".

A hook blocks a commit or push that contains a client term:

1. Create `client-terms.local.txt` in the repository root.
2. Write one term per line: client names, system names and product names.
   Matching ignores case.
3. Install the hooks:

   ```sh
   printf '#!/bin/sh\nexec "$(git rev-parse --show-toplevel)/bin/check-client-terms"\n' > .git/hooks/pre-commit
   printf '#!/bin/sh\nexec "$(git rev-parse --show-toplevel)/bin/check-client-terms" --all\n' > .git/hooks/pre-push
   chmod +x .git/hooks/pre-commit .git/hooks/pre-push
   ```

   If you use pre-commit, `.pre-commit-config.yaml` runs the same check.

4. Check the whole tree at any time with `bin/check-client-terms --all`.

Without `client-terms.local.txt`, the hook checks nothing and says so.
