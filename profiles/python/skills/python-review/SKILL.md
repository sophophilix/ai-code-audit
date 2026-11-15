---
name: python-review
description: Use when reviewing a Python file (.py, .pyi) or a section of one, one unit per pass. Gives the PY-* check catalogue for language, errors, resources, data, concurrency, security, typing and tests, each with its evidence source, severity guide and official source.
---

# Python review

## Overview
This skill is the rulebook for reviewing one Python unit at a time: an own `.py`
or `.pyi` file, or a section of a file over 1,000 lines (ADR 0002, ADR 0010). The
`file-reviewer` agent applies it to every Python unit in `units.tsv`; the `tracer`
applies it across files. When the file review is off, the engineer agent applies
it to the ten files at the top of `scans/hotspots.json` and to files over 300 lines.

The rules come from the people who maintain Python and its main libraries: the
Python documentation and PEPs, the Python Packaging Authority, the `sqlite3`,
`subprocess`, `pickle` and `tempfile` module documentation, and OWASP.

You never run code to prove how the language behaves (`AGENTS.md` rule 2), and you
never import the target. Cite the documentation instead.

## Before you start
<!-- brief: python -->
1. Read the whole unit. Line numbers you cite are the file's line numbers.
2. Read the scan rows for this file only:
   - `scans/lint-python.json`: Ruff with the kit's config. The target's own
     `# noqa` comments were ignored, so a row can be one the team switched off.
   - `scans/suppressions.json`: `# noqa`, `# type: ignore`, `# nosec`,
     `# pragma: no cover` and similar directives in this file (ADR 0004 D4).
   - `scans/sast.sarif`: Semgrep results, `p/python` included.
   - `scans/blindspots.json` and `scans/sweep.json`: entries for this file.
   - There's no type-check scan for Python (ADR 0010 D3). Don't report a type
     error as found by a tool. Report it only when you can show it from the code.
3. Note the libraries the file imports, and use only the parts of the catalogue
   that apply.
4. List the comments and docstrings that make a claim about behaviour: "never
   None", "validated", "thread-safe", "atomic", "safe", "can't happen", "only
   called from". Check each one against the code (rule 4). A claim the code
   contradicts is a finding with Key `PY-COMMENT-CLAIM:<file>`. A claim the file
   can't settle is an open edge (ADR 0002 D3).

## How to write a finding
<!-- brief: python -->
Use the `audit-findings` format. For every finding:

- **Rule**: the CHECK-ID, in the Key (`PY-BROAD-EXCEPT:src/app/cli.py`).
- **Line and excerpt**: the location, plus `- Excerpt:` copied verbatim from
  those lines (ADR 0004 D1).
- **Consequence**: what goes wrong for this system, in one or two sentences.
- **Fix**: the smallest change, as a short code sketch where it helps.
- **Severity**: from the guide in the catalogue, then these caps:
  - Critical or High needs `- Trigger:`: a concrete input or call sequence and
    what happens (ADR 0004 D7). Without one, Medium at most.
  - A finding that depends on another file is Medium at most until a trace
    resolves the open edge (ADR 0002 D3).
- **Sources**: the source key from the catalogue, expanded from the list at the end.

Don't restate a Ruff message as a finding. Use it as the lead, read the code, and
rate the consequence. Many rows in one file with one cause are one finding.

When a check also exists in another catalogue, use that ID: the `python` profile
(`PYAPP-*`) for packaging, configuration, storage, subprocess and model clients,
and `ai-generated-code-quality` (`SLOP-*`) for dead code, duplication and
swallowed errors.

## Check catalogue
<!-- brief: python -->

In the evidence column, `ruff:<code>` means a `scans/lint-python.json` row with
that code, and `grep` means a pattern to search this file for.

### Language
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| PY-MUTABLE-DEFAULT | A list, dict, set or other mutable object as a parameter default or a dataclass field default, shared across calls | `ruff:B006`, `ruff:B008`, `ruff:RUF009`; grep `=\s*\[\]\)`, `=\s*\{\}\)` | Medium if state leaks between calls or requests | Py-defaults |
| PY-LATE-BINDING | A closure or lambda created in a loop that reads the loop variable later | `ruff:B023` | Medium | Py-faq-lambda |
| PY-IS-LITERAL | `is` or `is not` used to compare with a string, number or tuple literal | `ruff:F632` | Medium (works by accident on CPython) | Py-is |
| PY-TRUTHY-ZERO | `x or default`, or `if not x`, where `0`, `""`, `Decimal(0)` or an empty list is a valid value | read defaults and guards | Medium where it changes an amount, a limit or a decision | Py-truth |
| PY-FLOAT-MONEY | Money, tax or totals held, summed or compared as `float`, or a `Decimal` built from a float | grep `float(`, `Decimal(\d+\.\d+)`; read arithmetic on amounts | High for figures a person relies on | Py-decimal |
| PY-NAIVE-DATETIME | `datetime.now()` or `utcnow()` without a time zone where times are stored, compared or shown across zones; date maths done by hand | `ruff:DTZ*`; grep `utcnow`, `timedelta(days` | Medium; High for deadlines or legal dates | Py-datetime |
| PY-SHADOW | A module, parameter or variable named after a built-in or a standard module (`id`, `type`, `input`, `json`) that hides it later | `ruff:A001`, `ruff:A002` | Low | Py-builtins |

### Errors
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| PY-BROAD-EXCEPT | `except Exception` or a bare `except:` inside application logic rather than at a process or command boundary; `except BaseException` that catches `KeyboardInterrupt` | `ruff:BLE001`, `ruff:E722`; grep `except Exception`, `except:` | Medium; High if it hides a failed write, a failed check or a security decision | Py-exceptions | SLOP-SWALLOW for an empty handler |
| PY-CAUSE-DROPPED | A translated exception raised inside `except` without `from exc`, so the original traceback is lost | `ruff:B904` | Low; Medium on storage or integration paths | Py-raise-from | |
| PY-ASSERT-CHECK | `assert` used to enforce input validation, permissions or invariants at run time; `python -O` removes it | `ruff:S101` outside tests | Medium; High if it guards security or data integrity | Py-assert | |
| PY-RETURN-FINALLY | `return`, `break` or `continue` inside `finally`, which discards an exception in flight | `ruff:B012` | Medium | Py-finally | |

### Resources and files
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| PY-NO-CONTEXT | A file, socket, lock, database connection or temporary directory opened without `with`, `contextlib.closing` or a `try/finally` that closes it | `ruff:SIM115`; grep `open(`, `connect(`, `mkdtemp(` | Low; Medium for connections or locks on long-running paths | Py-with |
| PY-NON-ATOMIC-WRITE | A file that matters (a record, a config, a ledger) rewritten in place, so a crash leaves it half-written; no write to a temporary file and `os.replace` | read writes to files that hold state | Medium; High if it can lose a person's data | Py-os-replace |
| PY-TEMPFILE | `tempfile.mktemp`, or temporary paths built by hand in a shared directory | `ruff:S306`, `ruff:S108` | Medium | Py-tempfile |
| PY-PATH-TRUST | A path from input or from a document joined to a base folder without `resolve()` and a check that it stays inside; symlinks followed where they shouldn't be | read path joins; grep `/ ` on `Path`, `os.path.join` | High if input chooses a path that's written or deleted | OWASP-path |
| PY-ENCODING | `open()` or `read_text()` without `encoding=` on text whose encoding matters | `ruff:PLW1514` | Low | PEP-597 |

### Data and storage
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| PY-SQL-STRING | SQL built with f-strings, `%` or `+` from values instead of `?` or named placeholders. Built identifiers (table or column names) must come from a fixed allow-list | `ruff:S608`; grep `execute(f"`, `execute(.*%` | High if any part comes from input or a document; Medium for an internal identifier with no allow-list | Py-sqlite3, OWASP-sqli |
| PY-SQLITE-TX | `sqlite3` writes with no clear transaction boundary, `isolation_level` or `autocommit` assumptions that don't match the code, or a connection shared across threads | read `connect(`, `commit(`, `with conn` | Medium; High if a failure leaves records half-written | Py-sqlite3-tx |
| PY-DESERIALISE | `pickle`, `marshal`, `shelve`, `yaml.load` without `SafeLoader`, or `jsonpickle` on data that isn't fully trusted | `ruff:S301`, `ruff:S506`; grep `pickle.load` | Critical if the data can come from a document, a network or another user | Py-pickle |
| PY-VALIDATE-LATE | Untrusted structured data (JSON, TOML, model output) used as dicts deep in the code instead of validated once at the boundary | read where parsed data enters | Medium | Pydantic-validation |
| PY-MODEL-OUTPUT | Output from a language model or OCR treated as correct or as a fact without a deterministic check, or shown to a person as verified | read where model results are stored or acted on | Medium; High if it changes files, money or a decision | Source: none – reviewer judgement |

### Concurrency
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| PY-BLOCKING-ASYNC | A blocking call (`time.sleep`, file I/O, `requests`, `subprocess.run`) inside `async def` | `ruff:ASYNC*` | Medium | Py-asyncio-dev |
| PY-FIRE-FORGET | `asyncio.create_task` whose result isn't kept, so the task can be garbage-collected or its error lost | `ruff:RUF006` | Medium | Py-create-task |
| PY-SHARED-STATE | Module-level mutable state changed from threads, signal handlers or a background watcher without a lock | read globals that functions assign to | Medium | Py-threading |
| PY-CHECK-THEN-ACT | `exists()` followed by create, delete or copy, where another process can act in between (TOCTOU) | grep `.exists()` followed by a write | Medium; High if it can overwrite or delete a person's file | Py-os-open |

### Security
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| PY-SUBPROCESS | `shell=True`, `os.system`, `os.popen`, or an argument list built from input without validation; a command run with no timeout | `ruff:S602`, `ruff:S604`, `ruff:S605`, `ruff:S607`; grep `subprocess` | High if input reaches the command | Py-subprocess-security | PYAPP-SUBPROCESS |
| PY-EVAL | `eval`, `exec` or `compile` on anything not written by the developer | `ruff:S307`, `ruff:S102` | Critical if input reaches it | Py-eval | |
| PY-WEAK-RANDOM | `random` used for tokens, identifiers, passwords or nonces instead of `secrets` | `ruff:S311` | High for security tokens | Py-secrets | |
| PY-WEAK-HASH | `md5` or `sha1` used for a security purpose; a password stored with a fast hash | `ruff:S324` | High for passwords or integrity checks | OWASP-passwords | |
| PY-CRYPTO-DIY | Encryption or key handling built by hand: a fixed or reused nonce, a key in source or config, ECB mode, no authentication | read uses of `cryptography`, `hashlib`, `hmac` | High | Cryptography-docs | |
| PY-SECRET-LOG | A secret, token, key or personal data passed to a logger, an exception message or stdout | grep `log`, `print`, `raise` near secret names | High for credentials; Medium for personal data | OWASP-logging | |
| PY-HARDCODED-SECRET | A credential written as a literal in source or in a committed config file: a password, token, API key or private key. A value the brief shows as `****` is one the secret scan found. Decide from the code around it whether it is real, a test value or a placeholder, and say what decides it | `scans/secrets.json`; `ruff:S105`, `ruff:S106`, `ruff:S107` | High if it grants access to anything; Low for a test value or a placeholder | OWASP-secrets | |
| PY-TLS-OFF | `verify=False`, an unverified SSL context, or certificate checks disabled | `ruff:S501`, `ruff:S323` | High for any non-loopback call | Py-ssl | |

### Typing and API surface
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source |
|---|---|---|---|---|
| PY-ANY-LEAK | `Any`, `cast()` or `# type: ignore` at a boundary, so unchecked data spreads through typed code | `scans/suppressions.json`; grep `Any`, `cast(` | Low; Medium where it hides a money or security type | Py-typing |
| PY-OPTIONAL-UNCHECKED | A function that can return `None` whose callers use the result without a check | read the callers in this file | Medium | Py-typing |
| PY-MIXED-RETURN | One condition reported three ways (`None`, an empty container and an exception) by the same function or its siblings | read return paths | Low | Source: none – reviewer judgement |

### Tests (only for test files)
<!-- brief: python -->

| CHECK-ID | What to look for | Evidence | Severity guide | Source | See |
|---|---|---|---|---|---|
| PY-TEST-NO-ASSERT | A test that can't fail: no assertion, an assertion on a mock it set itself, or `assert` on a non-empty tuple | `ruff:F631`, `ruff:PT*`; read tests | Low; Medium if it's the only test for a risky path | Pytest-assert | SLOP-FAKE-TEST |
| PY-TEST-PATCH-UNIT | `monkeypatch` or `mock.patch` that replaces the code under test, so the test proves nothing about it | read patches | Medium | Pytest-monkeypatch | |
| PY-TEST-SLEEP | `time.sleep` used to wait for a background event | grep `sleep(` | Low (flaky tests) | Source: none – reviewer judgement | |

## Sources
- Py-defaults: https://docs.python.org/3/tutorial/controlflow.html#default-argument-values
- Py-faq-lambda: https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
- Py-is: https://docs.python.org/3/reference/expressions.html#is-not
- Py-truth: https://docs.python.org/3/library/stdtypes.html#truth-value-testing
- Py-decimal: https://docs.python.org/3/library/decimal.html
- Py-datetime: https://docs.python.org/3/library/datetime.html#aware-and-naive-objects
- Py-builtins: https://docs.python.org/3/library/functions.html
- Py-exceptions: https://docs.python.org/3/tutorial/errors.html
- Py-raise-from: https://docs.python.org/3/reference/simple_stmts.html#the-raise-statement
- Py-assert: https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement
- Py-finally: https://docs.python.org/3/reference/compound_stmts.html#finally-clause
- Py-with: https://docs.python.org/3/reference/compound_stmts.html#the-with-statement
- Py-os-replace: https://docs.python.org/3/library/os.html#os.replace
- Py-os-open: https://docs.python.org/3/library/os.html#os.open
- Py-tempfile: https://docs.python.org/3/library/tempfile.html
- PEP-597: https://peps.python.org/pep-0597/
- Py-sqlite3: https://docs.python.org/3/library/sqlite3.html#sqlite3-placeholders
- Py-sqlite3-tx: https://docs.python.org/3/library/sqlite3.html#sqlite3-transaction-control
- Py-pickle: https://docs.python.org/3/library/pickle.html
- Pydantic-validation: https://docs.pydantic.dev/latest/concepts/models/
- Py-asyncio-dev: https://docs.python.org/3/library/asyncio-dev.html
- Py-create-task: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
- Py-threading: https://docs.python.org/3/library/threading.html
- Py-subprocess-security: https://docs.python.org/3/library/subprocess.html#security-considerations
- Py-eval: https://docs.python.org/3/library/functions.html#eval
- Py-secrets: https://docs.python.org/3/library/secrets.html
- Py-ssl: https://docs.python.org/3/library/ssl.html#security-considerations
- Py-typing: https://docs.python.org/3/library/typing.html
- Cryptography-docs: https://cryptography.io/en/latest/
- Pytest-assert: https://docs.pytest.org/en/stable/how-to/assert.html
- Pytest-monkeypatch: https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- OWASP-path: https://owasp.org/www-community/attacks/Path_Traversal
- OWASP-sqli: https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html
- OWASP-passwords: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP-logging: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP-secrets: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- Ruff rules: https://docs.astral.sh/ruff/rules/

These URLs were written on 2026-11-13 and not each fetched by the kit. Cite a page
only after reading the part you rely on.
