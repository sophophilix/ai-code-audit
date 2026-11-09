# Cost, usage and traces

Three levels. Start at level 1; add level 2 when you want trends across runs.

## Level 1: in the run files (no infrastructure)
The coordinator records, per pass, in `.audit/run-state.md` and `run-log.md`:
sessions used, resumes, duration, and the token count the harness reports
for that agent (Claude Code reports tokens per subagent; other tools vary).
If a harness doesn't report usage, the cell says `not reported`, never a guess.

The file review records its own usage (ADR 0007 D8). `kit review` reads each pass's
turns, tokens by type (input, output, cache read, cache write), cost and seconds
from `claude -p --output-format json` into `.audit/work/files/passes.jsonl`, one
line per attempt. `kit cost <workspace>` prints totals by stage and model and
writes `.audit/cost.md`, which the lead reviewer puts in the report. The cost is
what Claude Code reports at API prices, labelled "API-equivalent cost": a plan is
billed differently, and the session and weekly percentages `/status` shows can't
be read from a script, so the kit doesn't use them.

## Level 2: OpenTelemetry from Claude Code
Claude Code exports metrics, events and (beta) traces over OTLP. The
variables below come from the Claude Code monitoring docs
(https://code.claude.com/docs/en/monitoring-usage, checked 2026-11-06).

```zsh
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp                  # events: api_request, api_error, tool_result
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# Tag every datapoint with the audit run. No spaces, commas or quotes in values.
export OTEL_RESOURCE_ATTRIBUTES="audit.project=<name>,audit.run=<yyyy-mm-dd>-<n>,audit.kit_version=$(cat .audit-kit/VERSION)"
# Optional, beta: span tree including subagents
# export CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 OTEL_TRACES_EXPORTER=otlp
```

**Don't export content.** Leave `OTEL_LOG_USER_PROMPTS` and
`OTEL_LOG_ASSISTANT_RESPONSES` unset. Prompts and responses can contain
code and findings, and they're redacted by default.

### What you get
| Signal | Name | Useful attributes |
|---|---|---|
| Metric | `claude_code.token.usage` | `type` (input, output, cacheRead, cacheCreation), `model`, **`agent.name`**, `skill.name` |
| Metric | `claude_code.cost.usage` (USD) | `model`, **`agent.name`** |
| Event | `claude_code.api_request` | `model`, `cost_usd`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `duration_ms` |
| Event | `claude_code.api_error` | `status_code` (429 = rate limited), `attempt`, `error` |
| Event | `claude_code.tool_result` | `tool_name`, `success`, `duration_ms`: shows which steps are slow or failing |
| Trace (beta) | `claude_code.interaction` → `llm_request`, `tool` → subagent spans | per-agent latency tree |

`agent.name` is the subagent name (`audit-security` …), so cost per agent
comes straight from the metrics. For a pass run in a separate session (another
harness, or a resume), add `audit.agent=<role>,audit.pass=<label>` to
`OTEL_RESOURCE_ATTRIBUTES` before starting it.

### Where to send it
| Option | When |
|---|---|
| **Azure Monitor / Application Insights** through an OpenTelemetry Collector | The organisation's own tenant and region. Best for council use |
| Local Collector + Prometheus + Grafana (Docker) | Personal experiments, nothing leaves the machine |
| `OTEL_METRICS_EXPORTER=console` | A quick check that telemetry works |

Other harnesses (Codex CLI, Gemini CLI) have their own telemetry settings.
Check their current docs and use the same `audit.*` resource attributes, so
everything lands in one view.

## Level 3: improving the kit with the data
| Question | Measure |
|---|---|
| Which agent costs most, and is it worth it? | Cost per agent ÷ **confirmed** findings (after verification) |
| Which model suits which role? | Per role and model: recall on the eval sets, false-positive rate, cost |
| Is resuming cheap? | Tokens in the first 10 minutes of a resumed session vs a fresh plan; resumes per run |
| Are we hitting limits? | `api_error` with 429 per run; correlate with `max_parallel_passes` |
| Are agents re-reading too much? | `tool_result` counts for Read/Grep per item; cache-read share of input tokens |
| Is drift creeping in after resumes? | Findings per item before vs after a resume; verifier rejection rate for resumed passes |

Record the per-run summary (total cost, cost per agent, resumes, 429s,
confirmed findings) in `project.md` → Evaluation, next to recall and false
positives. That's the data for deciding model assignments and kit changes.
