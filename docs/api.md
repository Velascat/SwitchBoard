# API Reference

SwitchBoard exposes an OpenAI-compatible HTTP API on port `20401` (default).

Base URL: `http://localhost:20401`

---

## GET /health

Returns SwitchBoard's own health status and the reachability of the downstream 9router.

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
| `status` | string | `"ok"` if everything is healthy; `"degraded"` if 9router is unreachable. |
| `version` | string | SwitchBoard version string. |
| `uptime_s` | float | Seconds since the application started. |
| `nine_router.reachable` | boolean | Whether a probe to 9router's `/health` endpoint succeeded. |
| `nine_router.latency_ms` | float | Round-trip time to 9router in milliseconds. |
| `nine_router.error` | string\|null | Error message if the probe failed. |

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | SwitchBoard is running (even if `status` is `"degraded"`). |

---

## GET /v1/models

Returns all configured model profiles as an OpenAI-compatible model list.

Clients can use profile names in the `model` field of chat completion requests.

### Response

```json
{
  "object": "list",
  "data": [
    {
      "id": "capable",
      "object": "model",
      "created": 1714000000,
      "owned_by": "switchboard"
    },
    {
      "id": "default",
      "object": "model",
      "created": 1714000000,
      "owned_by": "switchboard"
    },
    {
      "id": "fast",
      "object": "model",
      "created": 1714000000,
      "owned_by": "switchboard"
    },
    {
      "id": "local",
      "object": "model",
      "created": 1714000000,
      "owned_by": "switchboard"
    }
  ]
}
```

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success. |

---

## POST /v1/chat/completions

Send a chat completion request.  SwitchBoard selects a model via policy and
proxies the request to 9router.

The request and response schemas are fully OpenAI-compatible.

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | yes | Must be `application/json`. |
| `X-SwitchBoard-Profile` | no | Force a specific profile, bypassing all policy rules. |
| `X-SwitchBoard-Priority` | no | Priority hint: `"high"`, `"low"`, or any custom string. |
| `X-SwitchBoard-Tenant-ID` | no | Tenant identifier for multi-tenant routing rules. |
| `X-Request-ID` | no | Request correlation ID, stored in the decision record. |

### Request Body

Follows the [OpenAI chat completion request](https://platform.openai.com/docs/api-reference/chat/create) schema.

```json
{
  "model": "fast",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": "What is 2 + 2?"}
  ],
  "stream": false,
  "max_tokens": 256,
  "temperature": 0.7
}
```

The `model` field is treated as a **hint** — SwitchBoard may route to a
different downstream model based on the active policy.

### Response Body

The raw provider response is returned verbatim.

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1714000000,
  "model": "gpt-4o-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "2 + 2 = 4."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 28,
    "completion_tokens": 10,
    "total_tokens": 38
  }
}
```

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success — provider response returned. |
| 400 | Request body is not valid JSON. |
| 422 | Request body is valid JSON but missing required `messages` field. |
| 500 | Policy evaluation or capability resolution failed. |
| 502 | 9router returned an error or could not be reached. |

---

## GET /admin/decisions/recent

Returns the most recent routing decisions from the in-memory decision log.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | integer | 20 | Number of decisions to return. Min: 1, Max: 500. |

### Response

```json
[
  {
    "timestamp": "2026-04-20T12:34:56.789012+00:00",
    "request_id": null,
    "original_model_hint": "fast",
    "profile_name": "capable",
    "downstream_model": "gpt-4o",
    "rule_name": "high_priority_tenant",
    "latency_ms": 312.5,
    "tenant_id": "acme"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO-8601 UTC timestamp of the decision. |
| `request_id` | string\|null | Value of the `X-Request-ID` header, if present. |
| `original_model_hint` | string | The `model` field as sent by the caller. |
| `profile_name` | string | The profile selected by the policy engine. |
| `downstream_model` | string | The concrete model forwarded to 9router. |
| `rule_name` | string | The policy rule that triggered, or `"fallback"`. |
| `latency_ms` | float\|null | Round-trip latency to 9router in milliseconds. |
| `tenant_id` | string\|null | Tenant identifier if present in the request. |

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success — list of decisions (may be empty). |
| 422 | Invalid query parameter value. |
