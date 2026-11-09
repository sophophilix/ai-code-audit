---
agent: security
model: m
commit: c
status: complete
---

### SEC-001 Exact excerpt
- Key: X-exact:app.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: app.js:4
- Excerpt: `const folder = req.query.folder;`
### SEC-002 Indentation and two lines
- Key: X-span:app.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: app.js:4-5
- Excerpt: `const   folder = req.query.folder; res.sendFile(folder);`
### SEC-003 Masked secret
- Key: X-masked:app.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: app.js:7
- Excerpt: `const token = 'sk-****';`
### SEC-004 Wrong line
- Key: X-wrong-line:app.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: app.js:2
- Excerpt: `const folder = req.query.folder;`
### SEC-005 Paraphrase
- Key: X-paraphrase:app.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: app.js:5
- Excerpt: `res.sendFile(req.query.folder)`
### SEC-006 No excerpt
- Key: X-none:app.js
- Category: security
- Severity: medium
- Confidence: high
- Evidence: seen
- Location: app.js:3
