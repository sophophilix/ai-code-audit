---
name: node-express
description: Use when the audited system is Node.js (JavaScript or TypeScript, CommonJS or ESM), especially with Express. Gives search patterns, scan commands, and the stack check catalogue.
---

# Node.js / Express stack profile

## Sources
- Express security best practices: https://expressjs.com/en/advanced/best-practice-security.html
- Express performance best practices: https://expressjs.com/en/advanced/best-practice-performance/
  (shows Express 5 by default; use the v4.x selector for Express 4. Its sample error
  handler sends `err.message` to the client: cite its principles, not that code)
- Express health checks and graceful shutdown: https://expressjs.com/en/advanced/healthcheck-graceful-shutdown.html
- Express middleware: https://expressjs.com/en/resources/middleware/ . The first group
  is "maintained by the Expressjs team"; each module's page states its own defaults
  and warnings, and is the source for checks on that module. The second group
  (helmet, passport) is third party and explicitly not endorsed.
- Moving to Express 5: https://expressjs.com/en/guide/migrating-5 (async error handling
  differs between 4 and 5; read it before citing the difference)
- Express docs for LLMs (pick the major version in use): https://expressjs.com/llms.txt (Express 4: `llms/guides-4x.txt`)
- Node.js `process` events (`uncaughtException`: "not safe to resume normal operation"): https://nodejs.org/api/process.html#event-uncaughtexception
- Node.js `server.close()`: https://nodejs.org/api/http.html#serverclosecallback
- Express error handling guide: https://expressjs.com/en/guide/error-handling.html
- Node.js `events` (`'error'` events, `captureRejections`): https://nodejs.org/api/events.html ; `stream.pipeline`: https://nodejs.org/api/stream.html
- Node.js release schedule: https://nodejs.org/en/about/previous-releases
- Node.js security best practices: https://nodejs.org/en/learn/getting-started/security-best-practices
- OWASP Node.js cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html
- Node.js, Don't Block the Event Loop (or the Worker Pool): https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop
  (its list of blocking core APIs says it is complete "as of Node.js v9"; check newer APIs against the current docs)
- ESLint core rules: https://eslint.org/docs/latest/rules/ ; regular-expression rules from the community plugin eslint-plugin-regexp: https://ota-meshi.github.io/eslint-plugin-regexp/

No official agent skill is published by the Node.js or Express projects (checked
November 2026). Their `AGENTS.md` files are contribution policies for their own
repositories, not coding guidance.

Community sources, accepted for this kit by its maintainer (2026-11-07). They aren't
on the allowed domains, so cite them by item number without fetching, as
`Source: nodebestpractices 8.6 (community)`. Where an official source says the same
thing, cite that instead. Details and licences: `THIRD_PARTY.md`.
- Node.js Best Practices (goldbergyoni/nodebestpractices, commit `dc3d60c`, CC BY-SA 4.0)
- Practica.js (practicajs/practica, commit `9d0cfc8`, MIT), the same author's boilerplate

## Service structure and entry point
`references/service-structure.md` holds the recommended layout, a minimal
`server.js`, the default middleware stack and how to assess a target against
them. Load it for the `NODE-ENTRY-*`, `NODE-COMPONENTS` and `NODE-LAYER-LEAK`
checks and whenever a recommendation proposes a new structure.

## Error handling
`references/error-handling.md` holds the error model (one app error class,
operational vs catastrophic, one central handler), sample code, the async and
emitter rules, and how to trace a failure through a target. Load it for the
`NODE-ERROR-*`, `NODE-AWAIT-RETURN`, `NODE-EMITTER-ERROR` and
`NODE-INPUT-VALIDATION` checks.

## Search patterns (`grep -n`)
<!-- brief: script -->
| Purpose | Pattern |
|---|---|
| Routes | `app\.(get\|post\|put\|patch\|delete\|use\|all)\(`, `router\.(get\|post\|put\|patch\|delete\|use)\(` |
| Body parsing and limits | `express\.(json\|urlencoded\|raw\|text)\(`, `limit:` |
| Outbound HTTP | `fetch\(`, `axios`, `https?\.request`, `got\(`, `undici` |
| Config | `process\.env\.`, `dotenv` |
| Files | `fs\.(write\|append\|createWriteStream\|rename\|unlink\|mkdir)`, `multer`, `busboy`, `formidable` |
| In-process state | `new Map\(`, `new Set\(` at module level; `setInterval\(`, `setTimeout\(` at module level |
| Dangerous sinks | `eval\(`, `new Function`, `child_process`, `exec\(`, `require\(` with a variable, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document\.write` |
| Proxy and IP | `trust proxy`, `x-forwarded-for`, `req\.ip`, `req\.ips` |
| Errors | `catch\s*\(`, `\.catch\(`, `unhandledRejection`, `uncaughtException`, `process\.exit` |
| Logging | `console\.(log\|info\|warn\|error)`, `pino`, `winston`, `morgan` |
| Headers | `helmet`, `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `cors\(` |
| Entry point and lifecycle | `\.listen\(`, `createServer\(`, `module\.exports\s*=\s*app`, `export default app`, `process\.on\(['"]SIG`, `server\.close\(` |
| Start command | `"start":`, `"main":` in `package.json`; `^(CMD\|ENTRYPOINT)` in `Dockerfile*`; `pm2`, `ecosystem.config`; startup command in pipeline or host config |
| Web objects past the routes | `\b(req\|res)\b` as an argument in files outside the route or middleware folders; `req\.(body\|query\|params)` outside them |
| Express-team middleware | `express-session`, `cookie-session`, `cookie-parser`, `multer`, `serve-static`, `express\.static`, `serve-index`, `errorhandler`, `connect-timeout`, `morgan`, `compression` |
| Async route handlers | `(get\|post\|put\|patch\|delete\|use)\([^)]*async\s*\(` |
| Error types and handlers | `class \w+ extends Error`, `isOperational`, `app\.use\(\s*\(?\s*err`, `function\s*\(\s*err\s*,\s*req` |
| Emitters and streams | `\.on\(['"]error`, `new EventEmitter`, `create(Read\|Write)Stream`, `\.pipe\(`, `pipeline\(`, `captureRejections` |
| Validation | `ajv`, `zod`, `typebox`, `joi`, `express-validator`, `\.safeParse\(`, `\.validate\(` |

## Scans (run by a human or pipeline, not by agents; see runbook)
Use pinned tool versions in an isolated environment. Never run the target's npm
scripts, and never load its lint or test config.

```
cloc --exclude-dir=node_modules --json . > .audit/scans/cloc.json
npm audit --json --package-lock-only > .audit/scans/deps-audit.json   # or: osv-scanner --format json -L package-lock.json
gitleaks git --redact --report-format json --report-path .audit/scans/secrets.json .
semgrep scan --config p/javascript --config p/expressjs --config p/owasp-top-ten --sarif -o .audit/scans/sast.sarif .
jscpd --reporters json --output .audit/scans/jscpd --ignore "**/node_modules/**" .   # copy jscpd-report.json → duplication.json
eslint --config .audit-kit/config/eslint.config.mjs --no-inline-config -f json -o .audit/scans/lint.json .   # `kit scan` runs this
tsc -p .audit/scans/tsconfig.audit.json --pretty false > .audit/scans/typecheck.txt   # `kit scan` writes the config and runs this
```
*`kit scan` runs ESLint with the kit's own config (`config/eslint.config.mjs`;
rule groups are mapped to checks in the `ai-generated-code-quality` skill),
`tsc` with the kit's own tsconfig, and the kit's own static unused-code analysis
(`unused.json`). Knip isn't used: its plugins load the target's config files,
which would run target code. All three cover `.js` files only.*

## Check catalogue
<!-- brief: script -->
| CHECK-ID | Check | Typical severity if failing |
|---|---|---|
| NODE-RUNTIME-LTS | The runtime is in Active or Maintenance LTS, and declared consistently (`engines`, `.nvmrc`, pipeline, host config) | High if end-of-life |
| EXP-VERSION | The Express major version still gets security fixes; note the gap to the current major | Medium–High |
| EXP-TRUST-PROXY | `trust proxy` matches the real proxy chain (e.g. a hop count or the platform's front door). `true` behind a front end trusts client-supplied `X-Forwarded-For`, so anything keyed on IP (rate limits, logs) can be spoofed | High if security depends on the IP |
| EXP-BODY-LIMIT | Every body parser has an explicit limit appropriate to the route. Large limits only where needed, and checked *after* auth and rate limits. body-parser's default is `'100kb'` and its docs advise against "a very high limit"; `req.body` is untrusted until validated | Medium |
| EXP-ERROR-LEAK | The production error handler doesn't return stack traces or internal messages. `errorhandler` is "only intended to be used in a development environment": flag it if it can run with `NODE_ENV=production` | Medium |
| EXP-SEC-HEADERS | CSP (watch for `unsafe-inline`), HSTS, `frame-ancestors`, `nosniff`, Referrer-Policy; `x-powered-by` disabled. Check the headers, not whether helmet is installed | Medium |
| EXP-CORS | CORS absent or allow-listed. Never reflects any origin together with credentials. The `cors` default is `origin: "*"`, and its docs say "CORS is not access control" | High if wrong |
| EXP-RATE-LIMIT | Rate limits exist on public write endpoints. Note where their state lives (memory = per instance). No Express-team module exists: `Source: none – reviewer judgement` unless OWASP covers the case | Medium–High |
| EXP-STATIC | Static serving doesn't expose dotfiles, source, private folders or backups. `serve-static` defaults: `dotfiles: 'ignore'`, `index` on. `serve-index` (directory listings) on a public path | High if exposed |
| EXP-UPLOAD | Upload size and count limits, content-type sniffing, filename handling. multer: "Never add multer as a global middleware"; `fileSize`, `files` and `parts` default to Infinity; `originalname` is client-supplied; memory storage can exhaust memory | High |
| EXP-SESSION | `express-session`: a production store, not `MemoryStore` ("purposely not designed for a production environment"); `secure` cookies, with `trust proxy` behind a proxy; a secret with at least 32 bytes of entropy; `sameSite` set (default `false`); `resave` and `saveUninitialized` set explicitly. `cookie-session`: nothing secret in the session (it is signed, not encrypted) and no reliance on it to stop replay | High if sessions carry auth |
| EXP-TIMEOUT | `connect-timeout` used top-level without checking `req.timedout`: the slow work keeps running after the 503 | Low–Medium |
| EXP-ASYNC-ERRORS | On Express 4, `async` handlers and middleware without a wrapper or `try/catch`: a rejection never reaches the error handler. Express 5 forwards it. Related: NODE-UNHANDLED, EXP-VERSION | Medium on Express 4 |
| NODE-UNHANDLED | The process never keeps running after an uncaught exception. Pass: no handler (Node prints the stack and exits 1), or a handler that logs and exits non-zero, within a time limit if it closes resources first. Fail: a handler that logs and carries on (Node: "not safe to resume"; Express: "dangerous"). Since Node 15 an unhandled rejection is raised as an uncaught exception unless an `unhandledRejection` listener swallows it. Also: no fire-and-forget promises on important paths | Medium; High if it keeps running |
| NODE-OUTBOUND-TIMEOUT | Every outbound call has a timeout (`fetch` has none by default; use `AbortSignal.timeout`), with bounded retries | Medium–High on critical paths |
| NODE-SHUTDOWN | SIGTERM handling: report not-ready, stop accepting requests, finish in-flight work (`server.close()`), close pools and timers, force an exit after a time limit, exit 0. Express's health-check page and nodebestpractices 8.6 | Medium |
| NODE-START-CMD | Production runs `node` directly under a supervisor that restarts it (App Service, a container platform, systemd). `npm start`, or PM2 starting npm, in the chain can stop SIGTERM reaching the app (nodebestpractices 8.2) | Low–Medium |
| NODE-ENV-PROD | `NODE_ENV=production` is set in the host or service config: Express caches templates and sends shorter errors (Express performance page) | Low–Medium |
| NODE-ENTRY-SPLIT | The Express app can be built without side effects: requiring it doesn't listen, connect, start timers or read the network. Tests can use it in-process. See `references/service-structure.md` | Low; `info` if it passes |
| NODE-ENTRY-LIFECYCLE | One entry point per process owns start-up and shutdown: config load, `listen`, signal and crash handlers, pool close. Report each entry file and its line count, and what it holds beyond that | Low–Medium |
| NODE-COMPONENTS | Code is grouped by business component, each with entry points, domain and data access (nodebestpractices 1.1, 1.2), or the current grouping is described and the gap stated. Flat technical folders are a maintainability finding, not a defect. Related: SLOP-GOD | Low–Medium |
| NODE-LAYER-LEAK | `req`, `res` or framework objects passed into business or data-access code, or SQL and HTTP calls inside route handlers (nodebestpractices 1.2) | Low–Medium |
| NODE-ERROR-TYPES | One app error class extending `Error`, carrying a stable name, an HTTP status and whether the error is operational or catastrophic, and code that uses the distinction (nodebestpractices 2.2, 2.3). Throws that aren't `Error`s belong to SLOP-SWALLOW | Low–Medium |
| NODE-ERROR-CENTRAL | One handler that Express error middleware, jobs, start-up and the crash handler all call; routes don't each log and respond (nodebestpractices 2.4). Evidence: one failure traced per critical journey | Medium |
| NODE-AWAIT-RETURN | `return somePromise()` without `await` inside `try` (the `catch` never runs) or on paths whose stack traces matter (nodebestpractices 2.12) | Low; Medium if a `catch` is skipped |
| NODE-EMITTER-ERROR | A long-lived emitter or stream (database or queue client, file stream, watcher) with no `'error'` listener, or a stream chain built with `.pipe()` that drops errors (nodebestpractices 2.13; Node `events` and `stream` docs) | Medium–High for connections |
| NODE-INPUT-VALIDATION | Route input (`req.body`, `req.query`, `req.params`) validated against a schema before the domain runs; failures return 400 (nodebestpractices 2.11; body-parser: `req.body` is untrusted). Related: cross-ref security | Medium |
| NODE-ERROR-CONTRACT | Error responses documented per endpoint (OpenAPI for REST) and failure paths covered by tests (nodebestpractices 2.5, 2.8) | Low |
| NODE-INPROC-STATE | Module-level Maps/Sets, local files or timers holding state that must be shared or durable (idempotency, rate limits, queues, caches) | Medium–High (blocks scale-out) |
| NODE-BACKGROUND-JOBS | Background jobs run inside the web process; with N instances they run N times unless leased or locked | Medium |
| NODE-LOGGING | Structured logs to stdout with correlation IDs (nodebestpractices 5.14, 5.18); no personal data or secrets; levels used consistently. `console.*` is synchronous to a terminal or file, so the Express performance page recommends a logger such as Pino; `morgan` writes to stdout by default | Medium |
| NODE-CONFIG | Config validated at startup (fail fast); every variable documented with its default; a `.env.example` exists | Medium |
| NODE-LOCKFILE | Lockfile committed and used (`npm ci`); no `*` or `latest` ranges | Medium |
| NODE-INSTALL-SCRIPTS | Dependencies with install scripts are known and justified | Medium |
| NODE-DANGEROUS-SINK | `eval`, `new Function`, `child_process` or dynamic `require` reachable from input | Critical–High |
| NODE-SSRF | A user-influenced URL or host passed to an outbound request | High |
| NODE-PATH-TRAVERSAL | User input in a file path without normalising and checking the base directory | High |
| NODE-TIMING-COMPARE | Secrets or tokens compared with `===` instead of `crypto.timingSafeEqual` | Low–Medium |
| NODE-REDOS | A regular expression with nested quantifiers (`(a+)*`), overlapping alternatives (`(a\|a)*`) or backreferences is applied to input a user controls. Node's guidance: use `indexOf` for simple matches. Evidence: `lint:regexp/no-super-linear-backtracking`, `lint:regexp/no-super-linear-move`, then trace the input | High if reachable from public input |
| NODE-BLOCKING-SYNC | Synchronous `crypto` (`pbkdf2Sync`, `randomFillSync`), `zlib` (`inflateSync`, `deflateSync`), `fs` or `child_process` (`execSync`, `spawnSync`, `execFileSync`) calls on a request path. At start-up they are fine | Medium–High on request paths |
| NODE-JSON-DOS | `JSON.parse` or `JSON.stringify` on bodies or files whose size a user controls, with no size limit before it | Medium |
| NODE-CPU-ON-LOOP | CPU-heavy work (image processing, PDF generation, large sorts, loops over unbounded input) on the event loop without partitioning or a worker. State `n` and who controls it; the growth claim is a hypothesis until measured | Medium–High |
| FE-XSS-SINK | Client script writes untrusted data into HTML sinks | High |
| FE-INLINE | Inline `<script>`/handlers forcing CSP `unsafe-inline`; one very large HTML file holding all the client logic | Medium (maintainability + CSP) |
| FE-THIRD-PARTY-SCRIPT | Third-party scripts loaded without integrity or pinning; API keys exposed to the browser without restrictions | Medium |

## Manifest checks
<!-- brief: manifest -->
The same checks as the catalogue above, for what `package.json` alone can show.
A check that needs the host, the pipeline or the lockfile's contents is an open
edge, not a pass.

| CHECK-ID | Check | Typical severity if failing |
|---|---|---|
| NODE-RUNTIME-LTS | The runtime is in Active or Maintenance LTS, and declared consistently (`engines`, `.nvmrc`, pipeline, host config) | High if end-of-life |
| EXP-VERSION | The Express major version still gets security fixes; note the gap to the current major | Medium–High |
| NODE-LOCKFILE | Lockfile committed and used (`npm ci`); no `*` or `latest` ranges | Medium |
| NODE-INSTALL-SCRIPTS | Dependencies with install scripts are known and justified; the manifest's own `preinstall`, `install` and `postinstall` scripts are read | Medium |
| NODE-START-CMD | Production runs `node` directly under a supervisor that restarts it. `npm start`, or PM2 starting npm, in the chain can stop SIGTERM reaching the app (nodebestpractices 8.2) | Low–Medium |

## CommonJS and plain JavaScript notes
<!-- brief: script -->
- Don't recommend converting to ESM or TypeScript as a quick fix. Recommend
  `checkJs` + JSDoc types first, and new modules in the existing style.
- Matteo Collina's `node` skill (github.com/mcollina/skills, MIT, a personal
  collection) has useful rules on graceful shutdown, error handling, config and
  logging, but it assumes ESM, TypeScript and Fastify. Adapt; don't copy.
