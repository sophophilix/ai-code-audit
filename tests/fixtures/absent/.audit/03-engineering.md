---
agent: security
model: m
commit: c
status: complete
---

### ENG-001 No graceful shutdown
- Key: NODE-SHUTDOWN:server.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: server.js:2
- Excerpt: `app.listen(8080);`
- Searched: `SIGTERM|server\.close` in `server.js lib/`
### ENG-002 No rate limiting
- Key: EXP-RATE-LIMIT:server.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: server.js:1
- Excerpt: `require('express')()`
- Searched: `rateLimit|express-rate-limit` in `server.js lib/`
### ENG-003 Search outside the target
- Key: X-outside:server.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: server.js:1
- Excerpt: `const app`
- Searched: `root` in `../`
### ENG-004 Refused pattern
- Key: X-redos:server.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: server.js:1
- Excerpt: `const app`
- Searched: `(a+)+` in `server.js`
