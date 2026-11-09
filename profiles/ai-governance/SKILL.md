---
name: ai-governance
description: Use when governing AI agents that perform the audit, when the audited code was AI-generated, or when the audited system contains AI features. Based on the DTA AI Reference Architecture (AIRA) v1.0 and its Companion Guide.
---

# AI governance profile (DTA AIRA)

## Sources
- AI Reference Architecture v1.0: https://www.digital.gov.au/ai-reference-architecture
- Companion Guide – Scenarios: https://www.digital.gov.au/ai-reference-architecture/companion-guide
Commonwealth guidance; not mandatory for states or councils, but a practical structure.

## A. Governing the audit agents (tech lead, lead reviewer)
**Control points** (Companion Guide): *govern* (assurance evidence, acceptable use,
residual risk – the model and harness vendor), *configure and govern* (harness
settings, permissions, guardrails), *design, configure and govern* (this kit).

**Trustworthiness and assurance domains → kit controls**
| Domain | Control |
|---|---|
| Observability | `.audit/run-log.md` records every stage and checkpoint; keep harness transcripts |
| Traceability | Provenance (kit version, commit, model, harness) on runs; event history per finding; findings.jsonl in git |
| Explainability and interpretability | Evidence + reasoning on every finding |
| Validity and reliability | Seeded evaluation (`evals/`); verifier false-positive rate per agent (`06-verification.md`); abstention via questions |
| Safety | Read-only agents; disposable clone; no production access |
| Fairness | Accessibility review included in engineer scope |
| Sustainability | Harness-independent kit; no lock-in; recorded decision on dependence on the AI vendor |
| Security and resilience | Prompt-injection rules (AGENTS.md rules 10–11); masked secrets; least-privilege tools; disposable workspace |
| Privacy | No production data to agents; confirm where the AI provider stores **and processes** data (the Companion Guide notes Copilot inference is not all processed in Australia) |

**Human agency, oversight and control**
- Design-time: decision scope (agents recommend, humans decide); checkpoints; abstention;
  irreversibility guardrail (no writes to code, no pushes); circuit breaker (stop if
  seeded recall below threshold).
- Run-time: an agent supervisor role (the tech lead) who verifies Critical/High, answers
  questions, escalates. Watch for **automation bias**, vigilance decrement and skill erosion:
  keep spot-checking on every run.
- For AI-assisted writing (reports), preserve human verification and authorship: the
  report states what was AI-generated and what a human checked.

The lead reviewer records the governance state (control in place per domain) under "Method and limitations".

## B. AI features inside the audited system
<!-- brief: script, component, inline script -->
If the system calls models or AI services (LLM APIs, AI SDKs, auto-classification):
- Disclosure to users that AI is involved; a non-AI path for the service
- Human oversight of AI-influenced decisions affecting individuals; contestability
- Where inference happens (jurisdiction) and what data is sent
- Prompt injection, output handling (never into eval/SQL/HTML unescaped), excessive agency,
  unbounded consumption (OWASP Top 10 for LLM Applications)
- Evaluation approach exists for the AI component
Findings use category `governance` or `security` and frameworks "AIRA-<domain>".

## C. AI-generated code
<!-- brief: script, component, inline script -->
Expect: duplicated blocks, inconsistent patterns per file, plausible-but-unused code,
leftover AI instruction files, missing tests, optimistic error handling. Engineer and
security agents should weight these; Chesterton's Fence still applies.
