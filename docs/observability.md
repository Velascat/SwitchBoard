# Observability

---

## Decision Logging

Every request routed through SwitchBoard produces a **decision record** written to a JSONL file (one JSON object per line). The log is easy to tail, grep, and process with standard tooling (`jq`, pandas, etc.).

### Location

Controlled by `SWITCHBOARD_DECISION_LOG_PATH` (default: `./runtime/decisions.jsonl`). The parent directory is created automatically on startup.

Set to an empty string to disable disk logging — records are still kept in the in-memory ring buffer and accessible via the admin API.

### JSONL record format

```json
{
  "timestamp": "2026-04-20T14:32:01.123456+00:00",
  "request_id": "trace-abc",
  "original_model_hint": "fast",
  "profile_name": "capable",
  "downstream_model": "gpt-4o",
  "rule_name": "coding_task",
  "reason": "",
  "status": "success",
  "latency_ms": 412.5,
  "tenant_id": "acme-corp",
  "task_type": "code",
  "complexity": "high",
  "estimated_tokens": 1840,
  "requires_tools": false,
  "requires_long_context": false,
  "adjustment_applied": false,
  "adjustment_reason": null,
  "cost_estimate": 10.0,
  "ab_experiment": null,
  "ab_bucket": null,
  "scored_profiles": null,
  "error": null,
  "error_category": null,
  "rejected_profiles": [
    {"profile": "fast", "reason": "task type code requires capable profile"}
  ]
}
```

| Field | Description |
|-------|-------------|
| `timestamp` | ISO-8601 UTC time the decision was made |
| `request_id` | `X-Request-ID` header value, or null |
| `original_model_hint` | The `model` field the caller sent |
| `profile_name` | Profile selected by the policy engine |
| `downstream_model` | Concrete model identifier forwarded to 9router |
| `rule_name` | Matching policy rule name, or `"fallback"` |
| `status` | `"success"` or `"error"` |
| `latency_ms` | Round-trip latency to 9router in milliseconds |
| `tenant_id` | Tenant identifier from `X-SwitchBoard-Tenant-ID` header |
| `task_type` | Inferred task: `code`, `analysis`, `planning`, `summarization`, `chat` |
| `complexity` | Inferred complexity: `low`, `medium`, `high` |
| `estimated_tokens` | Estimated context token count |
| `requires_tools` | Whether the request included a `tools` array |
| `requires_long_context` | Whether long context was inferred |
| `adjustment_applied` | `true` if adaptive routing redirected this request |
| `adjustment_reason` | Reason for the adaptive redirect, if any |
| `cost_estimate` | Relative cost weight of the selected profile |
| `ab_experiment` | A/B experiment name if this request was intercepted |
| `ab_bucket` | `"A"` or `"B"` if assigned to an experiment |
| `scored_profiles` | Multi-factor scoring breakdown for all candidates, if scored |
| `error` | Error message if forwarding failed |
| `error_category` | Error category string for aggregation |
| `rejected_profiles` | Profiles considered but filtered out, each with `profile` and `reason` keys |
| `context_summary` | Nested object with key classifier fields: `task_type`, `complexity`, `estimated_tokens`, `requires_tools`, `requires_long_context`, `stream`, `cost_sensitivity`, `latency_sensitivity` |

### In-memory ring buffer

The last 1 000 decisions are always kept in memory regardless of disk logging.
Accessible via the admin API:

```bash
curl http://localhost:20401/admin/decisions/recent?n=20
```

---

## CLI inspector

`scripts/inspect.py` provides a human-readable view of the decision log via the admin API.
No JSONL parsing needed — it works against a running instance.

```bash
# Last 20 decisions
python scripts/inspect.py recent

# Last 50 decisions
python scripts/inspect.py recent 50

# Aggregated stats over last 100 decisions
python scripts/inspect.py summary

# Stats over last 500 decisions
python scripts/inspect.py summary 500

# Single decision by request ID
python scripts/inspect.py show <request_id>
```

Override the base URL with `SWITCHBOARD_URL`:

```bash
SWITCHBOARD_URL=http://my-server:20401 python scripts/inspect.py summary
```

---

## Admin API

### Decision log endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /admin/decisions/recent?n=N` | Last N decisions from ring buffer |
| `GET /admin/summary?n=N` | Aggregated stats: counts, profile distribution, latency percentiles |

### Adaptive routing endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /admin/adaptive` | Current adjustment state and per-profile demotion/promotion status |
| `POST /admin/adaptive/enable` | Re-enable adaptive routing |
| `POST /admin/adaptive/disable` | Disable without clearing adjustments |
| `POST /admin/adaptive/reset` | Clear all adjustments immediately |
| `POST /admin/adaptive/refresh?n=N` | Force recomputation from last N decisions |

Full request/response schemas: [docs/api.md](api.md).

---

## Adaptive routing observability

The adaptive system tracks per-profile error rates and latency. A background task recomputes adjustments automatically every 5 minutes (300 s TTL). Operators can also force an immediate refresh via `POST /admin/adaptive/refresh`.

Check the current state:

```bash
curl -s http://localhost:20401/admin/adaptive | python3 -m json.tool
```

A demoted profile looks like:

```json
{
  "enabled": true,
  "adjustment_count": 1,
  "demoted_profiles": ["capable"],
  "promoted_profiles": [],
  "adjustments": [
    {
      "profile": "capable",
      "action": "demote",
      "reason": "error rate 52% over 10 requests exceeds threshold (40%)"
    }
  ],
  "last_refresh": "2026-04-20T12:30:00.000000+00:00",
  "window_size": 200
}
```

Adjustments are recomputed automatically every 5 minutes by a background task. To force an immediate refresh or to reset all profiles to neutral:

```bash
curl -s -X POST http://localhost:20401/admin/adaptive/reset
```

Demotion thresholds (hardcoded, require at least 5 samples before triggering):
- Error rate ≥ 40% over the measurement window → demote
- Mean latency ≥ 8 000 ms → demote
- Error rate ≤ 2% over 20+ requests → promote

---

## Querying the JSONL log

```bash
# Show last 10 decisions
tail -n 10 runtime/decisions.jsonl | jq .

# Count decisions per profile
jq -r '.profile_name' runtime/decisions.jsonl | sort | uniq -c | sort -rn

# Count decisions per task type
jq -r '.task_type // "unknown"' runtime/decisions.jsonl | sort | uniq -c | sort -rn

# Find slow requests (> 1 000 ms)
jq 'select(.latency_ms != null and .latency_ms > 1000)' runtime/decisions.jsonl

# Find requests where adaptive routing redirected
jq 'select(.adjustment_applied == true)' runtime/decisions.jsonl

# Find A/B experiment participants
jq 'select(.ab_experiment != null)' runtime/decisions.jsonl

# Error rate by profile (requires mlr or awk)
jq -r '[.profile_name, .status] | @tsv' runtime/decisions.jsonl | sort | uniq -c
```

---

## Log level

Increase log verbosity to see per-request routing decisions in the console:

```bash
SWITCHBOARD_LOG_LEVEL=debug bash scripts/run_dev.sh
```

At `debug` level, SwitchBoard logs the full `SelectionContext` and `SelectionResult` for every request.

---

## Future observability

These are not yet implemented:

- **Prometheus metrics** (`GET /metrics`) — request counters, latency histograms, per-profile distribution
- **OpenTelemetry tracing** — spans for classify, select, and forward stages
- **Remote log sink** — shipping JSONL to a database or aggregation platform
