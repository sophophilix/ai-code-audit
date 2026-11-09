# Node.js error handling: reference and how to assess it

Load this when running `NODE-ERROR-TYPES`, `NODE-ERROR-CENTRAL`,
`NODE-AWAIT-RETURN`, `NODE-EMITTER-ERROR`, `NODE-INPUT-VALIDATION` or
`NODE-ERROR-CONTRACT`, or when a recommendation proposes an error design.
It sits beside `service-structure.md`: that file owns the crash handler and
shutdown (`NODE-UNHANDLED`, `NODE-SHUTDOWN`); this one owns everything
before an error reaches them.

Sources: nodebestpractices section 2 (community, commit `dc3d60c`), items
2.1–2.13; Node.js `process`, `events` and `stream` docs; the Express error
handling guide (https://expressjs.com/en/guide/error-handling.html). The
text is the kit's own; the code samples are written for the kit, not copied.
Yoni Goldberg's 2016 blog checklist (last updated 2018) is the source of
section 2 and is superseded by it: don't cite the blog.

## 1. The model

1. **Only `Error` objects are thrown or rejected** (2.2). A string or plain
   object has no stack trace. Related: `SLOP-SWALLOW`, which already finds
   these with `lint:no-throw-literal` and `lint:prefer-promise-reject-errors`.
2. **One app error class**, extending `Error` once, not a class per case
   (2.2). It carries a stable name or code, an HTTP status where one applies,
   and whether the error is **operational** (expected: bad input, not found,
   a timeout from a dependency) or **catastrophic** (a bug, unknown state)
   (2.3). 2.2's text calls the flag `isCatastrophic` while its code uses
   `isOperational`; either works if the code base uses one.
3. **One handler** that every entry point calls: Express error middleware,
   scheduled jobs, queue consumers, start-up and the crash handler (2.4).
   It logs, records a metric, and decides: operational, respond and carry on;
   catastrophic, start shutdown. Express error middleware only hands the
   error to it.
4. **Validate input at the edge** with a schema library (ajv, zod, typebox,
   or the one already in use) before the domain runs (2.11). Failures become
   operational errors with a 400.
5. **Errors are part of the API contract**: each endpoint's error responses
   are documented (OpenAPI for REST, 2.5) and the failure paths are tested
   (2.8).

## 2. Sample code

CommonJS shown; write it in the target's existing module style.

```js
// src/libraries/errors/app-error.js
'use strict';

class AppError extends Error {
  constructor(name, message, { httpStatus = 500, isOperational = true, cause } = {}) {
    super(message, { cause });
    this.name = name;                    // stable code, e.g. 'report-not-found'
    this.httpStatus = httpStatus;
    this.isOperational = isOperational;
  }
}

module.exports = { AppError };
```

```js
// src/libraries/errors/handler.js
'use strict';
const { AppError } = require('./app-error');

function createErrorHandler({ logger, metrics, onCatastrophic }) {
  function normalise(err) {
    if (err instanceof AppError) return err;
    return new AppError('unexpected', 'Unexpected error', { isOperational: false, cause: err });
  }

  function handle(err, context = {}) {
    const appError = normalise(err);
    logger.error({ err: appError.cause ?? appError, name: appError.name, ...context }, appError.message);
    metrics.increment('errors', { name: appError.name, operational: appError.isOperational });
    if (!appError.isOperational) onCatastrophic(appError);   // server.js starts shutdown
    return appError;
  }

  // Express error middleware: hand over, respond, nothing else
  function middleware(err, req, res, next) {
    if (res.headersSent) return next(err);
    const appError = handle(err, { requestId: req.id });
    res.status(appError.httpStatus).json({ error: appError.name });  // no message or stack
  }

  return { handle, middleware };
}

module.exports = { createErrorHandler };
```

A scheduled job uses the same handler:
`job().catch((err) => errors.handle(err, { job: 'nightly-sync' }))`.

Notes for the reviewer:
- `onCatastrophic` connects to the shutdown in `service-structure.md`
  section 2. Whether a catastrophic error in one request should stop the
  process is a trade-off: Node's guidance on `uncaughtException` is not to
  resume, but an error caught in a route didn't escape. The kit's position
  (reviewer judgement): exit on errors that leave shared state unknown
  (a broken pool, a half-written file); respond 500 and alert on the rest.
  State what the target does; don't fail it for choosing either.
- `super(message, { cause })` needs Node 16.9 or later.
- Express 5 forwards rejected promises from async handlers to the error
  middleware; Express 4 doesn't (`EXP-ASYNC-ERRORS`).
- The client gets only the stable name. Related: `EXP-ERROR-LEAK`.

## 3. Async specifics

- **`return await` inside `try`, and in async functions generally** (2.12).
  V8's async stack traces only follow awaited promises, so a function that
  returns a promise without awaiting it drops out of the trace; inside
  `try`, a returned promise that rejects also skips the `catch`. The kit
  doesn't run ESLint's `no-return-await`, which discourages this.
- **Every emitter and stream has an `'error'` listener** (2.13). `try/catch`
  doesn't see these errors, and an `'error'` event with no listener throws,
  which ends the process. Long-lived emitters (database clients, queue
  connections, file watchers) matter most: without a listener the failure
  either crashes the process or, if swallowed, leaves it running with the
  connection dead. `captureRejections: true` routes rejections from async
  listeners to `'error'` (2.13). For stream chains, `stream.pipeline`
  forwards errors and cleans up; `.pipe()` doesn't (Node `stream` docs; check
  them for the target's Node version; not in 2.13).
- **Callbacks** (2.1): don't recommend converting callback code as a quick
  fix. Recommend promises for new code, and check that every callback's
  `err` argument is checked first.

## 4. Assessing a target

1. Find the error types: `class \w+ extends Error`, `new Error\(`,
   `throw `, `reject\(`. Is there one app error class or several? Is the
   operational/catastrophic distinction made anywhere, and is it used?
2. Find the handlers: `app.use\(\s*\(?\s*err`, `function\s*\(\s*err\s*,\s*req`,
   `.catch\(`, `catch\s*\(`. Count where errors are logged and responded to.
   Several routes that each log and respond is `NODE-ERROR-CENTRAL`; give
   up to five examples, one finding.
3. Pick two or three critical journeys and trace one failure each (a
   dependency timeout, invalid input, a database error) from where it is
   raised to what the user sees and what is logged. That trace is the
   evidence; the pattern counts are pointers.
4. Find emitters: `\.on\(['"]error`, `new EventEmitter`, `createReadStream`,
   `createWriteStream`, `\.pipe\(`, `pipeline\(`, database and queue client
   constructors. For each long-lived one, is there an `'error'` listener and
   what does it do?
5. Find validation: the schema library in `package.json`, and whether routes
   that read `req.body`, `req.query` or `req.params` validate first.
6. Read the tests for failure-path cases before saying there are none.
