# Phase 9 — Platform Hardening

Phase 9 makes SwitchBoard dependable under real usage. The changes are intentionally minimal: standardised error responses, bounded retries, and startup validation. The core architecture is unchanged.

---

## Error Handling

All error responses from `/v1/chat/completions` use the OpenAI error format so that API-compatible clients can parse them without special-casing SwitchBoard.

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

`request_id` is included when an `X-Request-ID` header was sent or when one was auto-generated for the request. It is always present on errors.

### Error categories

| Condition | HTTP | `type` | `code` |
|-----------|------|--------|--------|
| Invalid JSON body | 400 | `invalid_request_error` | `invalid_json` |
| Missing `messages` field | 422 | `invalid_request_error` | `missing_required_field` |
| No eligible profile found | 503 | `routing_error` | `no_eligible_profile` |
| Selection internal failure | 503 | `routing_error` | `selection_failed` |
| Upstream timeout | 504 | `upstream_timeout_error` | `upstream_timeout` |
| Upstream HTTP error | 502 | `upstream_error` | `upstream_http_error` |
| Upstream connection refused | 502 | `upstream_error` | `upstream_connection_error` |
| Uncaught exception (global handler) | 500 | `internal_error` | `internal_server_error` |

### Helper module

`switchboard.api.errors` exposes one generic builder and convenience constructors:

```python
from switchboard.api.errors import (
    error_response,      # generic — takes status_code, type, message, code
    invalid_request,     # 400 or 422
    routing_error,       # 503
    upstream_error,      # 502
    upstream_timeout,    # 504
    internal_error,      # 500
)
```

All helpers accept an optional `request_id` keyword argument.

---

## Retrying Gateway

`RetryingGateway` wraps any gateway that implements `create_chat_completion` / `stream_chat_completion` / `close` and automatically retries transient upstream failures.

### Defaults

| Parameter | Value |
|-----------|-------|
| `max_retries` | 2 (3 total attempts) |
| `backoff` | `(0.5, 1.0)` seconds between attempts |

### Retryable conditions

- HTTP status codes: `429`, `500`, `502`, `503`, `504`
- `httpx.TimeoutException` (read/write/connect timeout)
- `httpx.RequestError` (connection refused, DNS failure, etc.)

### Non-retryable conditions

4xx responses other than 429 are raised immediately. Retrying a 401 or 422 would not help and would slow down error delivery.

### Streaming

Streaming responses (`stream_chat_completion`) are never retried — a partially consumed event stream cannot be safely replayed.

### Configuration

The gateway is wired in `app.py` lifespan:

```python
inner_gateway = HttpNineRouterGateway(settings.nine_router_url, timeout=timeout)
gateway = RetryingGateway(inner_gateway)
```

The timeout applied to each individual attempt is controlled by `ROUTER9_TIMEOUT_S` (default 120 s).

---

## Startup Config Validation

`ConfigValidator.validate_all()` runs during lifespan startup before any service is exposed. If it raises `ConfigValidationError`, the process aborts immediately with a `CRITICAL` log message listing every error found.

### Critical errors (abort startup)

| Check | Error message contains |
|-------|----------------------|
| Policy YAML file not found | `"Policy"` + path |
| Profiles YAML file not found | `"Profiles"` + path |
| Capabilities YAML file not found | `"Capabilities"` + path |
| Policy YAML could not be parsed | `"could not be loaded"` |
| Duplicate rule names in policy | `"Duplicate"` + rule name |
| Experiment `split_percent` outside 0–100 | `"split_percent"` |
| Experiment `profile_a == profile_b` | `"must be different"` |

### Non-critical warnings (logged, no abort)

- Rule references a profile not in the capability registry
- `fallback_profile` not in the capability registry
- Experiment profiles not in the capability registry

These are warnings because the registry may legitimately grow without a restart.

### ConfigValidationError

```python
try:
    ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
except ConfigValidationError as exc:
    print(exc.errors)   # list[str] — one entry per failure
    print(str(exc))     # human-readable summary with count
```

---

## Global Exception Handler

Any exception that escapes a route handler is caught by the global handler in `create_app()` and returned as a structured 500 response. This prevents FastAPI's default HTML error pages from reaching clients.

---

## Known failure modes

| Failure | Behaviour |
|---------|-----------|
| All retries exhausted — timeout | `upstream_timeout_error` 504 to client |
| All retries exhausted — HTTP error | `upstream_error` 502 to client |
| 9router unreachable at startup | First request fails; retries will attempt recovery |
| Config files deleted after startup | Existing in-memory config continues; no hot-reload |
| `YAML` parse error in config | Startup aborted; human must fix and restart |
