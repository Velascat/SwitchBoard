# Observability

## Decision Logging

Every request routed through SwitchBoard produces a **decision record** that is
written to a JSONL file (one JSON object per line).  This makes the log easy to
tail, grep, and process with standard tooling (`jq`, `mlr`, pandas, etc.).

### Location

The log file path is controlled by the `SWITCHBOARD_DECISION_LOG_PATH`
environment variable.  The default is `./runtime/decisions.jsonl`.  The parent
directory is created automatically on startup if it does not exist.

Set the variable to an empty string to disable disk logging (records are still
kept in the in-memory ring buffer and accessible via the admin API).

### JSONL Record Format

Each line is a JSON object matching the `DecisionRecord` schema:

```json
{
  "timestamp": "2026-04-20T14:32:01.123456+00:00",
  "client": "acme-corp",
  "task_type": null,
  "selected_profile": "capable",
  "downstream_model": "gpt-4o",
  "rule_name": "tool_use",
  "reason": "",
  "request_id": "req-abc123",
  "original_model_hint": "gpt-4o",
  "profile_name": "capable",
  "latency_ms": 412.5,
  "tenant_id": "acme-corp",
  "error": null
}
```

| Field | Type | Description |
|---|---|---|
| `timestamp` | ISO-8601 string | UTC time the decision was made |
| `client` | string \| null | Tenant/client identifier from `X-SwitchBoard-Tenant-ID` |
| `task_type` | string \| null | High-level task category (future: inferred by classifier) |
| `selected_profile` | string | Profile chosen by the policy engine |
| `downstream_model` | string | Concrete model identifier sent to 9router |
| `rule_name` | string | Name of the matching policy rule, or `"fallback"` |
| `reason` | string | Human-readable explanation (populated in future) |
| `request_id` | string \| null | Value of the `X-Request-ID` header, if present |
| `original_model_hint` | string | The `model` field as the caller sent it |
| `profile_name` | string | Alias for `selected_profile` (legacy compat) |
| `latency_ms` | float \| null | Round-trip latency to 9router in milliseconds |
| `tenant_id` | string \| null | Alias for `client` (legacy compat) |
| `error` | string \| null | Non-null if forwarding produced an error |

### In-Memory Ring Buffer

The last 1 000 decision records are always kept in memory regardless of whether
disk logging is enabled.  They are accessible via:

```
GET /admin/decisions/recent?n=20
```

### Example: Querying the Log with jq

```bash
# Show last 10 decisions
tail -n 10 runtime/decisions.jsonl | jq .

# Count decisions per profile in the last hour
jq -r '.selected_profile' runtime/decisions.jsonl | sort | uniq -c | sort -rn

# Find slow requests (> 1 000 ms)
jq 'select(.latency_ms != null and .latency_ms > 1000)' runtime/decisions.jsonl
```

## Future Metrics Direction

The current decision log is a lightweight starting point.  Future observability
improvements may include:

- **Prometheus metrics** — counters and histograms for request volume, latency
  percentiles, error rates, and per-profile routing distribution.
- **Structured tracing** — OpenTelemetry spans propagated to 9router so that a
  single request can be traced end-to-end across services.
- **Log aggregation** — shipping the JSONL log to an aggregation platform
  (Loki, Elasticsearch, CloudWatch) for dashboarding and alerting.
- **Anomaly detection** — alerting when routing distribution shifts unexpectedly
  (e.g. a sudden spike in `capable` profile usage suggesting cost blowout).
