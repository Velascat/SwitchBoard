# API Reference

SwitchBoard exposes an OpenAI-compatible HTTP API on port `20401` (default).

Base URL: `http://localhost:20401`

---

## GET /health

Returns SwitchBoard's own health and the reachability of the downstream 9router.

### Response

```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime_s": 42.3,
  "nine_router": {
    "reachable": true,
    "latency_ms": 1.4,
    "error": null
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ok"` or `"degraded"` (9router unreachable). |
| `version` | string | SwitchBoard version string. |
| `uptime_s` | float | Seconds since startup. |
| `nine_router.reachable` | boolean | Whether a probe to 9router's `/health` succeeded. |
| `nine_router.latency_ms` | float | Round-trip time to 9router in milliseconds. |
| `nine_router.error` | string\|null | Error message if the probe failed. |

**Status codes:** `200` always (even when `status` is `"degraded"`).

---

## GET /v1/models

Returns all configured model profiles as an OpenAI-compatible model list.

### Response

```json
{
  "object": "list",
  "data": [
    {"id": "fast",    "object": "model", "created": 1714000000, "owned_by": "switchboard"},
    {"id": "capable", "object": "model", "created": 1714000000, "owned_by": "switchboard"}
  ]
}
```

**Status codes:** `200`.

---

## POST /v1/chat/completions

Accept a chat completion request, select a model via policy, and proxy to 9router.

### Request headers

| Header | Description |
|--------|-------------|
| `Content-Type: application/json` | Required. |
| `X-SwitchBoard-Profile` | Force a specific profile, bypassing all policy rules. |
| `X-SwitchBoard-Priority` | Priority hint: `"high"` or `"low"`. Matched by `priority` rule condition. |
| `X-SwitchBoard-Tenant-ID` | Tenant identifier. Matched by `tenant_id` rule condition. |
| `X-SwitchBoard-Cost-Sensitivity` | `"high"` — enables cost-sensitive routing rules. |
| `X-SwitchBoard-Latency-Sensitivity` | `"high"` — shifts profile scorer to favour low-latency profiles. |
| `X-Request-ID` | Correlation ID. Returned in error responses and recorded in the decision log. |

### Request body

Standard OpenAI chat completion request. The `model` field is treated as a routing hint and may be overwritten by the policy.

```json
{
  "model": "fast",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "max_tokens": 256
}
```

### Success response

The provider response is returned verbatim with HTTP `200`.

### Error responses

All errors use the OpenAI error format:

```json
{
  "error": {
    "type": "invalid_request_error",
    "message": "Field 'messages' is required.",
    "code": "missing_required_field",
    "request_id": "trace-abc"
  }
}
```

| HTTP | `type` | `code` | Cause |
|------|--------|--------|-------|
| 400 | `invalid_request_error` | `invalid_json` | Request body is not valid JSON |
| 422 | `invalid_request_error` | `missing_required_field` | `messages` array missing |
| 503 | `routing_error` | `no_eligible_profile` | No profile could be selected |
| 503 | `routing_error` | `selection_failed` | Unexpected error in selector |
| 502 | `upstream_error` | `upstream_http_error` | 9router returned an HTTP error |
| 502 | `upstream_error` | `upstream_connection_error` | Could not connect to 9router |
| 504 | `upstream_timeout_error` | `upstream_timeout` | 9router timed out (after retries) |
| 500 | `internal_error` | `internal_server_error` | Unhandled exception |

---

## GET /admin/decisions/recent

Returns the most recent routing decisions from the in-memory ring buffer (last 1 000).

### Query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | integer | 20 | Number of decisions to return (1–500). |

### Response

```json
[
  {
    "timestamp": "2026-04-20T12:34:56.789012+00:00",
    "request_id": "trace-abc",
    "original_model_hint": "fast",
    "profile_name": "capable",
    "downstream_model": "gpt-4o",
    "rule_name": "coding_task",
    "reason": "",
    "status": "success",
    "latency_ms": 312.5,
    "tenant_id": "acme",
    "task_type": "code",
    "complexity": "high",
    "estimated_tokens": 1240,
    "adjustment_applied": false,
    "adjustment_reason": null,
    "cost_estimate": 10.0,
    "ab_experiment": null,
    "ab_bucket": null,
    "scored_profiles": null,
    "error": null,
    "error_category": null
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO-8601 UTC timestamp |
| `request_id` | string\|null | `X-Request-ID` header value, or null |
| `original_model_hint` | string | The `model` field sent by the caller |
| `profile_name` | string | Profile selected by the policy engine |
| `downstream_model` | string | Concrete model identifier forwarded to 9router |
| `rule_name` | string | Policy rule that triggered, or `"fallback"` |
| `status` | string | `"success"` or `"error"` |
| `latency_ms` | float\|null | Round-trip latency to 9router in ms |
| `tenant_id` | string\|null | Tenant identifier if present |
| `task_type` | string\|null | Inferred task type: `code`, `analysis`, `planning`, `summarization`, `chat` |
| `complexity` | string\|null | Inferred complexity: `low`, `medium`, `high` |
| `estimated_tokens` | integer\|null | Estimated context token count |
| `adjustment_applied` | boolean | Whether adaptive routing redirected this request |
| `adjustment_reason` | string\|null | Reason for adaptive redirect, if any |
| `cost_estimate` | float\|null | Relative cost weight of the selected profile |
| `ab_experiment` | string\|null | A/B experiment name if this request was intercepted |
| `ab_bucket` | string\|null | `"A"` or `"B"` if assigned to an experiment |
| `scored_profiles` | array\|null | Multi-factor scoring results for all eligible profiles |
| `error` | string\|null | Error message if forwarding failed |
| `error_category` | string\|null | Error category for aggregation |

**Status codes:** `200`, `422` (invalid `n` value).

---

## GET /admin/summary

Returns aggregated routing statistics over the last N decisions.

### Query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | integer | 100 | Window size (1–1000). |

### Response

```json
{
  "window": 100,
  "total": 87,
  "success_count": 82,
  "error_count": 5,
  "profile_counts": {"fast": 61, "capable": 26},
  "rule_counts": {"default_short_request": 55, "coding_task": 20},
  "error_category_counts": {"upstream_connection_error": 5},
  "latency_p50_ms": 134.2,
  "latency_p95_ms": 891.0,
  "latency_mean_ms": 201.3
}
```

**Status codes:** `200`.

---

## GET /admin/adaptive

Returns the current state of the adaptive routing system.

### Response

```json
{
  "enabled": true,
  "adjustments": {
    "capable": {
      "action": "demote",
      "reason": "error_rate=0.52 exceeds threshold 0.40",
      "expires_in_s": 142.3
    }
  },
  "last_refresh": "2026-04-20T12:30:00.000000+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether adaptive routing is active |
| `adjustments` | object | Per-profile adjustments (only non-neutral entries) |
| `adjustments[profile].action` | string | `"demote"` or `"promote"` |
| `adjustments[profile].reason` | string | Human-readable explanation |
| `adjustments[profile].expires_in_s` | float | Seconds until this adjustment expires |
| `last_refresh` | string\|null | When adjustments were last computed |

**Status codes:** `200`.

---

## POST /admin/adaptive/enable

Re-enables adaptive routing if it was disabled. Returns the new state.

**Status codes:** `200`.

---

## POST /admin/adaptive/disable

Disables adaptive routing. Existing adjustments are preserved but not applied.
The Selector will ignore adjustments until re-enabled.

**Status codes:** `200`.

---

## POST /admin/adaptive/reset

Clears all current adjustments. Useful when a profile recovers and you want
to re-enable it immediately without waiting for the TTL to expire.

**Status codes:** `200`.

---

## POST /admin/adaptive/refresh

Forces an immediate recomputation of adjustments from the last N decisions.
Useful after a config change or incident investigation.

### Query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | integer | 200 | Number of recent decisions to analyse. |

**Status codes:** `200`.
