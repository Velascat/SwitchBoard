# Request Flow

This document describes the end-to-end lifecycle of a `POST /v1/chat/completions` request through SwitchBoard.

---

## Step-by-Step

```
Client
  │
  │  POST /v1/chat/completions
  │  Headers: Content-Type: application/json
  │           X-SwitchBoard-Priority: high        (optional)
  │           X-SwitchBoard-Tenant-ID: acme       (optional)
  │           X-SwitchBoard-Profile: capable      (optional override)
  │  Body:    {"model": "fast", "messages": [...], "stream": false}
  │
  ▼
┌─────────────────────────────────────────────┐
│  1. RECEIVE  (routes_chat.py)               │
│                                             │
│  FastAPI parses the request body.           │
│  Returns 400 if body is not valid JSON.     │
│  Returns 422 if 'messages' is missing.      │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  2. CLASSIFY  (RequestClassifier)           │
│                                             │
│  Pass 1 — Headers:                         │
│    X-SwitchBoard-Tenant-ID → tenant_id      │
│    X-SwitchBoard-Priority  → priority       │
│    X-SwitchBoard-Profile   → force_profile  │
│                                             │
│  Pass 2 — Body heuristics:                 │
│    stream, max_tokens, temperature          │
│    tools_present (bool)                     │
│    estimated_tokens (chars / 4)             │
│    model_hint = body["model"]               │
│                                             │
│  Output: SelectionContext                   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  3. SELECT  (Selector)                      │
│                                             │
│  3a. PolicyEngine.select_profile(context)   │
│      → If force_profile set: return it      │
│      → Else: evaluate rules in priority     │
│        order; first match wins.             │
│        No match → fallback_profile          │
│                                             │
│  3b. CapabilityRegistry.resolve_profile()   │
│      profile_name → downstream_model string │
│                                             │
│  Output: SelectionResult                    │
│    profile_name = "capable"                 │
│    downstream_model = "gpt-4o"              │
│    rule_name = "high_priority_tenant"       │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  4. REWRITE  (routes_chat.py)               │
│                                             │
│  body["model"] = result.downstream_model    │
│                                             │
│  All other fields in the body are           │
│  preserved verbatim (tools, stream,         │
│  response_format, temperature, …).          │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  5. FORWARD  (Forwarder + Gateway)          │
│                                             │
│  HttpNineRouterGateway:                     │
│    POST {NINE_ROUTER_URL}/v1/chat/          │
│         completions                         │
│    body = rewritten request                 │
│                                             │
│  Timer started before request.              │
│  httpx raises on 4xx / 5xx.                 │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  6. LOG  (DecisionLog)                      │
│                                             │
│  DecisionRecord appended to:                │
│    - In-memory ring buffer (last 1000)      │
│    - decisions.jsonl (if path configured)   │
│                                             │
│  Fields logged:                             │
│    timestamp, request_id, original_model,  │
│    profile, downstream_model, rule,         │
│    latency_ms, tenant_id, error             │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  7. RESPOND  (routes_chat.py)               │
│                                             │
│  The provider response JSON is returned     │
│  verbatim to the client as-is.              │
│                                             │
│  HTTP status mirrors the upstream status.   │
│  Errors: 502 Bad Gateway with detail.       │
└─────────────────────────────────────────────┘
```

---

## Error Handling

| Failure point | HTTP status | Detail |
|---------------|-------------|--------|
| Invalid JSON body | 400 | `"Invalid JSON body: ..."` |
| Missing `messages` field | 422 | Pydantic validation error |
| Policy engine error | 500 | `"Model selection failed."` |
| 9router connection refused | 502 | `"Upstream error: ..."` |
| 9router 4xx/5xx | 502 | `"Upstream error: ..."` |

---

## Header Reference

| Header | Effect |
|--------|--------|
| `X-SwitchBoard-Profile` | Forces a specific profile, bypassing all policy rules |
| `X-SwitchBoard-Priority` | Sets `context.priority`; matched by rules (e.g. `"high"`, `"low"`) |
| `X-SwitchBoard-Tenant-ID` | Sets `context.tenant_id`; used for tenant-aware rules |
| `X-Request-ID` | Captured and stored in the decision record for correlation |
