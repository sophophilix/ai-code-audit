---
name: mssql
description: Use when the audited system talks to Microsoft SQL Server or Azure SQL from Node.js (the `mssql` / `tedious` packages), or contains T-SQL scripts. Gives the query-safety sharp edges and the database check catalogue.
---

# SQL Server from Node.js (mssql) profile

## Sources
- node-mssql README: https://github.com/tediousjs/node-mssql
- OWASP SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Microsoft Learn, SQL Server security best practices: https://learn.microsoft.com/en-us/sql/relational-databases/security/sql-server-security-best-practices
- Microsoft Learn, connect to Azure SQL with Microsoft Entra authentication: https://learn.microsoft.com/en-us/azure/azure-sql/database/authentication-aad-overview
- Community (not official): github/awesome-copilot `instructions/sql-server-safe-tsql.instructions.md` covers T-SQL script safety (transactions, `XACT_ABORT`, guarded deletes and updates).

No vendor-published agent skill covers `mssql` or T-SQL (checked November 2026).

## Microsoft's T-SQL code analysis rules
<!-- brief: sql -->
Microsoft publishes static analysis rules for T-SQL
(https://learn.microsoft.com/en-us/sql/tools/sql-database-projects/concepts/sql-code-analysis/sql-code-analysis).
They run when a SQL database project builds (`RunSqlCodeAnalysis`), which the
kit doesn't do yet, so apply them by reading `.sql` files and cite the rule ID
as the source:

| Rule | What it flags |
|---|---|
| SR0001 | `SELECT *` in stored procedures, views and table-valued functions |
| SR0008 | `@@IDENTITY` where `SCOPE_IDENTITY()` is meant |
| SR0009 | Variable-length types of size 1 or 2 |
| SR0010 | Deprecated join syntax |
| SR0013 | An output parameter not set on every code path |
| SR0014 | Data loss when casting between types |
| SR0011, SR0012, SR0016 | Special characters or reserved words in names; `sp_` prefix on procedures |
| SR0004, SR0005, SR0006, SR0007, SR0015 | Predicates that force table scans: unindexed `IN` columns, `LIKE '%…'`, a column wrapped in an expression, nullable columns in expressions, deterministic calls in `WHERE` |

The rules see `.sql` files only. SQL built inside JavaScript strings (most of
the SQL in a Node.js app) is reviewed by hand with the catalogue below, and the
same rule IDs may be cited where they apply.

## Sharp edge: tagged template vs template argument
<!-- brief: script, sql -->
In `mssql`, a **tagged template** is parameterised. A template literal
**passed as an argument** is plain string concatenation:

```js
await sql.query`SELECT * FROM t WHERE id = ${id}`                 // parameterised (tagged)
await request.query`SELECT * FROM t WHERE id = ${id}`             // parameterised (tagged)
await request.query(`SELECT * FROM t WHERE id = ${id}`)           // INJECTABLE (string)
await request.input('id', sql.Int, id).query('... WHERE id = @id') // parameterised (explicit)
```
Look for `query(` and `execute(` followed by a backtick, `+`, or a variable
holding SQL. The difference is one pair of parentheses, so read each hit.

## Search patterns
<!-- brief: script, sql -->
`require\(['"]mssql`, `\.query\(`, `\.query\``, `\.batch\(`, `\.execute\(`,
`\.input\(`, `new sql\.(Request|ConnectionPool|Transaction)`, `sql\.connect\(`,
`trustServerCertificate`, `encrypt`, `authentication`, `user:`, `password:`,
`requestTimeout`, `connectionTimeout`, and `.sql` files.

## Check catalogue
<!-- brief: script, sql -->
| CHECK-ID | Check | Typical severity if failing |
|---|---|---|
| SQL-INJECTION | User-influenced values reach SQL only as parameters (tagged templates or `.input`) | Critical–High |
| SQL-DYNAMIC-IDENT | Table, column or sort names built from input are matched against a fixed allow-list (identifiers can't be parameters) | High |
| SQL-PARAM-TYPES | Inputs declare explicit `sql.<Type>` with lengths where it matters (avoids implicit conversion and plan problems) | Low |
| SQL-AUTH | Uses Microsoft Entra / managed identity rather than SQL logins with passwords in app settings; if passwords are used, they come from a secrets store | Medium–High |
| SQL-ENCRYPT | `encrypt: true`; `trustServerCertificate` false outside local development | High if false in production |
| SQL-LEAST-PRIV | The database account has only the rights the app needs (no `db_owner`; read-only where the app only reads). Usually a question for the DBA | Medium (question) |
| SQL-POOL | One shared pool created once, with errors handled (`pool.on('error')`), closed on shutdown; no per-request connect | Medium |
| SQL-TIMEOUTS | `connectionTimeout` and `requestTimeout` set deliberately; long queries are bounded | Medium |
| SQL-TXN | Multi-statement writes use transactions that roll back on error (and `SET XACT_ABORT ON` in T-SQL) | Medium–High |
| SQL-SCRIPTS | Migration and DDL scripts are versioned, idempotent and reviewed; destructive statements have a selective `WHERE` and a dry-run path | Medium |
| SQL-PII | Personal data columns are identified, with retention and disposal defined; no personal data in SQL error logs | Medium (privacy) |
| SQL-ERROR-LEAK | SQL error text (object names, query text) isn't returned to clients | Medium |
| SQL-NETWORK | How the app reaches the server (private endpoint, VNet integration, on-premises link) is documented. Usually a question | Question |
