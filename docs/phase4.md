# Phase 4 — Observability & Feedback

Phase 4 adds request correlation, structured error visibility, and operator-
facing inspection tools to SwitchBoard.  Every request now carries a unique
ID through the full pipeline, every decision record captures whether it
succeeded or failed (and why), and the admin API exposes aggregated stats
and per-request drill-down.

```
Client → SwitchBoard [request_id] → classify → select → forward → 9router
                                ↓                 ↓
                          decision log      admin API / inspect.py
```

---

## What Changed from Phase 3

| Area | Phase 3 | Phase 4 |
|------|---------|---------|
| Correlation | no request ID | `X-Request-ID` header (or auto-generated UUID hex) |
| Decision record | profile + rule + context | + `status`, `error_category`, `request_id` |
| Error visibility | `error` string only | categorized: upstream\_error / upstream\_timeout / selection\_error / internal\_error |
| Admin API | recent N decisions (minimal fields) | enriched fields + per-request lookup + summary stats |
| Inspection | grep JSONL manually | `scripts/inspect.py` CLI |

---

## Request Correlation

Every request through `POST /v1/chat/completions` is assigned a correlation ID:

1. If the caller sends `X-Request-ID: <value>`, that value is used verbatim.
2. Otherwise SwitchBoard generates a UUID hex (`uuid.uuid4().hex`).

The ID is stored in `SelectionContext.extra["request_id"]` and written to
the decision record's `request_id` field.  Use it to correlate:
- decision records in the log
- `/admin/decisions/{request_id}` lookup
- upstream provider logs (if you propagate the header to 9router)

---

## Decision Record — New Fields

```json
{
  "status": "success",
  "error_category": null,
  "request_id": "b3d1f4a8c2e04f9a8b7c6d5e4f3a2b1c"
}
```

| Field | Values | Description |
|-------|--------|-------------|
| `status` | `"success"` \| `"error"` | Outcome of the forwarding attempt |
| `error_category` | see table below | Set only when `status = "error"` |
| `request_id` | UUID hex or caller-supplied | Correlation token |

### Error categories

| Category | Trigger |
|----------|---------|
| `upstream_timeout` | `httpx.TimeoutException` from 9router |
| `upstream_error` | `httpx.HTTPStatusError` or `httpx.RequestError` from 9router |
| `internal_error` | Any other unhandled exception in the forwarding path |
| `selection_error` | *(reserved)* Selection step raised an exception |

---

## Admin API

### `GET /admin/decisions/recent?n=20`

Returns the last N decision records, newest last.  All Phase 3 and Phase 4
fields are included.

```json
[
  {
    "timestamp": "2026-04-20T18:00:00+00:00",
    "request_id": "b3d1f4a8...",
    "original_model_hint": "fast",
    "profile_name": "fast",
    "downstream_model": "gpt-4o-mini",
    "rule_name": "default_short_request",
    "reason": "rule:default_short_request → profile:fast",
    "task_type": "chat",
    "status": "success",
    "error_category": null,
    "latency_ms": 8.3,
    "context_summary": { ... },
    "rejected_profiles": []
  }
]
```

### `GET /admin/decisions/{request_id}`

Look up a single decision by its correlation ID.  Returns the same shape as
one element of the recent list.  Returns 404 if the ID is not in the
in-memory ring buffer (oldest records are evicted after 1 000 requests).

### `GET /admin/summary?n=100`

Aggregated statistics over the last N decisions.

```json
{
  "window": 100,
  "total": 87,
  "success_count": 84,
  "error_count": 3,
  "profile_counts": { "fast": 60, "capable": 24, "local": 3 },
  "rule_counts": { "default_short_request": 55, "coding_task": 20 },
  "error_category_counts": { "upstream_timeout": 2, "upstream_error": 1 },
  "latency_p50_ms": 12.4,
  "latency_p95_ms": 45.1,
  "latency_mean_ms": 15.8
}
```

Latency stats are computed over successful requests only.

---

## `scripts/inspect.py` CLI

A stdlib-only (no pip install required) inspection tool that queries the
admin API.

```bash
# Last 10 decisions
python scripts/inspect.py recent 10

# Summary over last 200 decisions
python scripts/inspect.py summary 200

# Full trace for a specific request
python scripts/inspect.py show b3d1f4a8c2e04f9a8b7c6d5e4f3a2b1c
```

Override the SwitchBoard URL with `SWITCHBOARD_URL`:

```bash
SWITCHBOARD_URL=http://prod-switchboard:20401 python scripts/inspect.py summary
```

Example `recent` output:

```
[1]
  timestamp:   2026-04-20T18:00:00+00:00
  request_id:  b3d1f4a8c2e04f9a8b7c6d5e4f3a2b1c
  status:      success
  profile:     fast
  model:       gpt-4o-mini
  rule:        default_short_request
  reason:      rule:default_short_request → profile:fast
  latency_ms:  8.3
  context:     task=chat complexity=low tokens=12 tools=False long_ctx=False
```

---

## Troubleshooting

### How do I find why a specific request routed unexpectedly?

1. Capture the `X-Request-ID` response header (SwitchBoard echoes it if you
   set it; otherwise generate one client-side and pass it in).
2. `python scripts/inspect.py show <request_id>` — check `rule_name`, `reason`,
   and `context_summary` to understand what the classifier derived.

### How do I see error rates over the last hour?

```bash
python scripts/inspect.py summary 1000
```

Check `error_count` and `error_category_counts`.  `upstream_timeout` means
9router is slow or unreachable.  `upstream_error` means 9router returned a
4xx/5xx.

### Why is latency_p95 high?

Check `profile_counts` — if most traffic is landing on `capable` (gpt-4o),
that's expected.  Add a `cost_sensitive_non_complex` rule or lower the
complexity threshold if `capable` is being selected for simple requests.

---

## Current Limitations

- **Ring buffer only.** `find_by_request_id` searches the in-memory buffer
  (1 000 records).  Older requests require grepping the JSONL file directly.
- **Single-process only.** The ring buffer is per-process; multi-worker
  deployments will have split state.
- **No latency percentiles from JSONL.** `inspect.py` uses the live admin API;
  historical JSONL analysis requires external tooling (jq, pandas, etc.).
- **No streaming TTFT.** `latency_ms` for streaming decisions measures
  time-to-last-chunk, not time-to-first-token.
