# Node.js service structure: reference layout and how to assess it

Load this when running `NODE-ENTRY-SPLIT`, `NODE-ENTRY-LIFECYCLE`,
`NODE-COMPONENTS` or `NODE-LAYER-LEAK`, or when a recommendation proposes a
structure. It is the kit's recommended target, not a rule the target broke:
a finding needs code evidence of a cost (tests that can't run in-process,
startup with side effects, business rules duplicated across routes), not just
a difference from this layout.

Sources: nodebestpractices (community, commit `dc3d60c`) items 1.1–1.4, 2.3,
2.6, 4.11, 4.12, 5.12, 5.14, 5.18, 8.2, 8.6; Practica.js (commit `9d0cfc8`) for the
start/stop shape; Express health-check and performance pages; Node.js
`process` and `http` docs. Where a point has no source it is marked
`reviewer judgement`. The text is the kit's own; nothing is copied from the
CC BY-SA guide.

## 1. Layout

Group by business component, then by layer inside each component (1.1, 1.2).
A single service in one repository looks like this. A monorepo with one
folder per service is the same shape one level down.

```
<service>/
├─ server.js                # start-up and shutdown only
├─ src/
│  ├─ app.js                # createApp(deps): builds the Express app, never listens
│  ├─ config.js             # one schema, validated at start-up (1.4)
│  ├─ components/
│  │  └─ <component>/
│  │     ├─ entry-points/
│  │     │  ├─ api/         # routes: parse, validate, call the domain, respond
│  │     │  └─ jobs/        # schedules and queue consumers
│  │     ├─ domain/         # plain objects in and out; no req/res, no SQL
│  │     └─ data-access/    # database and external stores; plain objects out
│  └─ libraries/            # logger, errors, outbound HTTP client, db pool (1.3)
├─ public/                  # static assets; the proxy or CDN serves them in production
├─ test/                    # component tests: import createApp, listen on port 0
├─ .env.example             # every variable, with its default
└─ package.json             # "start": "node server.js"; engines; lockfile committed
```

What each layer may depend on (reviewer judgement; 1.2 states the principle
but gives no import rules):

| Layer | May use | Must not use |
|---|---|---|
| `entry-points` | domain, libraries | data-access directly, SQL |
| `domain` | data-access, libraries | `req`, `res`, Express, HTTP status codes |
| `data-access` | libraries, drivers | domain, Express |
| `libraries` | npm packages | components |

Jobs that must run once (schedules, queue drains, keep-warm pings) run in a
separate process or under a lease when there is more than one instance.
Related: `NODE-BACKGROUND-JOBS`, `NODE-INPROC-STATE`.

## 2. A minimal `server.js`

Keep `server.js` to start-up and shutdown. Practica's `server.ts` exposes
`startWebServer`/`stopWebServer` for the same reason: tests control when the
server starts. There is no line limit in any source; the test is what the
file holds. CommonJS shown; write it in the target's existing module style.

```js
'use strict';
const http = require('node:http');
const { loadConfig } = require('./src/config');
const { createLogger } = require('./src/libraries/logger');
const { createPool } = require('./src/libraries/db');
const { createApp } = require('./src/app');

async function main() {
  const config = loadConfig();                 // throws on bad config: fail fast
  const logger = createLogger(config.log);

  process.on('uncaughtException', (err, origin) => {
    logger.fatal({ err, origin }, 'uncaught exception');
    process.exit(1);                           // never resume (Node, Express)
  });

  const pool = await createPool(config.db);
  const app = createApp({ config, logger, pool });
  const server = http.createServer(app);
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(config.port, resolve);
  });
  app.locals.ready = true;
  logger.info({ port: server.address().port }, 'listening');

  let stopping = false;
  async function shutdown(signal) {
    if (stopping) return;
    stopping = true;
    logger.info({ signal }, 'shutting down');
    app.locals.ready = false;                  // readiness now answers 503
    setTimeout(() => process.exit(1), config.shutdownTimeoutMs).unref();
    await new Promise((resolve) => setTimeout(resolve, config.drainDelayMs));
    await new Promise((resolve) => server.close(resolve));
    await pool.close();
    process.exit(0);
  }
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((err) => {
  console.error(err);                          // the logger may not exist yet
  process.exit(1);
});
```

Notes for the reviewer:
- No `unhandledRejection` listener: since Node 15 an unhandled rejection is
  raised as an uncaught exception, which the handler above logs (`origin` is
  `'unhandledRejection'`). A listener that only logs would keep the process
  running. Check the Node `process` docs for the target's Node version.
- `drainDelayMs` gives the load balancer time to see the 503 before the
  server stops accepting connections. The right value depends on the probe
  interval of the platform (reviewer judgement; 8.6 states the steps, no
  source gives the code).
- `server.close()` stops new connections and calls back once open ones end.
  How it treats idle keep-alive connections changed in Node 19; read the
  `http` docs for the target's Node version before citing it.
- The logger must write the fatal line before `process.exit`; check the
  logger's docs for a synchronous destination (reviewer judgement).

## 3. A matching `src/app.js`

```js
'use strict';
const express = require('express');
const { reportsApi } = require('./components/reports/entry-points/api');
const { errorHandler } = require('./libraries/errors');

function createApp({ config, logger, pool }) {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', config.trustProxy);   // match the real proxy chain
  app.locals.ready = false;

  app.get('/health/live', (req, res) => res.sendStatus(200));
  app.get('/health/ready', (req, res) => res.sendStatus(app.locals.ready ? 200 : 503));

  app.use(express.json({ limit: '100kb' }));
  app.use('/api/reports', reportsApi({ logger, pool }));

  app.use((req, res) => res.sendStatus(404));
  app.use(errorHandler(logger));               // no stack or message to the client
  return app;
}

module.exports = { createApp };
```

A test then needs no port and no network:
`request(createApp({ config, logger, pool: fakePool })).get('/health/live')`,
or `listen(0)` for a real socket (4.12).

Middleware gets its own tests (4.11): a fault in one middleware hits most
requests, and a middleware is a plain function, so call it with mock `req`,
`res` and `next` (for example node-mocks-http) and assert on what it did,
without a server. This needs each middleware in its own module, not defined
inline in the entry file.

## 4. Default middleware, when the app needs the job

Prefer the Express-team module for each job
(https://expressjs.com/en/resources/middleware/). Add none the app doesn't need.

| Need | Use | Settings that matter |
|---|---|---|
| JSON and form bodies | `express.json`, `express.urlencoded` | explicit `limit` per route group |
| Security headers | helmet (third party) or set them by hand | CSP without `unsafe-inline`; `x-powered-by` off |
| Calls from another origin | `cors` | allow-list of origins; never `*` with credentials |
| Server-side sessions | `express-session` | shared store (not `MemoryStore`), `secure`, `sameSite`, `trust proxy`, explicit `resave`/`saveUninitialized` |
| Uploads | `multer`, on the upload routes only | every limit set; disk or blob storage, not memory, for large files |
| Static files | `express.static` | development only; `dotfiles: 'deny'`; no `serve-index` |
| Request logs | `pino-http` (third party) or `morgan` | to stdout, with a request ID |
| Compression | the reverse proxy; `compression` only without one | not on server-sent events |
| Development errors | `errorhandler` | only when `NODE_ENV=development` |

## 5. Assessing a target

1. List every entry file (`package.json` `main` and `start`, `Dockerfile`
   `CMD`, each file that calls `listen`). For each, record its line count from
   `scans/cloc.json` and **what it holds**: config, middleware, routes,
   business rules, SQL, timers, shutdown. A large file is a pointer; the
   finding is what is mixed into it, cited by line range.
2. `NODE-ENTRY-SPLIT`: does requiring the app module listen, connect or start
   timers? Do the tests (if any) start it in-process or call a running server?
   Read the tests before saying "can't be tested". Note whether custom
   middleware (auth, validation, rate limits, error handling) lives in its
   own modules and has tests of its own (4.11).
3. `NODE-COMPONENTS` and `NODE-LAYER-LEAK`: describe the current grouping
   (by technical role, by file, flat) in one line, then trace two or three
   routes from handler to database and record where validation, business
   rules and data access sit.
4. Recommend in steps a small team can take one at a time, each behind
   characterisation tests (Related: engineer's refactoring roadmap):
   1. Extract `createApp` from the entry file without changing behaviour.
   2. Move start-up and shutdown into a minimal `server.js` (section 2).
   3. Move routes into `components/<component>/entry-points/api`, one
      component at a time.
   4. Split the largest mixed files along entry point, domain and data access.
   Don't recommend a rewrite, a framework change, or ESM/TypeScript as part of
   this (see the profile's CommonJS notes).
