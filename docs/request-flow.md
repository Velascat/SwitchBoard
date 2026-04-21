# Request Flow

End-to-end lifecycle of a `POST /v1/chat/completions` request through SwitchBoard.

---

## Step-by-step

```
Client
  │
  │  POST /v1/chat/completions
  │  Content-Type: application/json
  │  X-SwitchBoard-Priority: high          (optional)
  │  X-SwitchBoard-Tenant-ID: acme         (optional)
  │  X-SwitchBoard-Cost-Sensitivity: high  (optional)
  │  X-SwitchBoard-Latency-Sensitivity: high (optional)
  │  X-SwitchBoard-Profile: capable        (optional — bypasses all rules)
  │  X-Request-ID: trace-abc               (optional — echoed in errors and logs)
  │  Body: {"model": "fast", "messages": [...], "stream": false}
  │
  ▼
┌─────────────────────────────────────────────────┐
│  1. RECEIVE  (routes_chat.py)                   │
│                                                 │
│  Assign / extract request_id.                   │
│  Parse JSON body.                               │
│  Return 400 invalid_json if body not valid JSON.│
│  Return 422 missing_required_field if no        │
│  'messages' array.                              │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│  2. CLASSIFY  (RequestClassifier)               │
│                                                 │
│  Headers:                                       │
│    X-SwitchBoard-Tenant-ID → tenant_id          │
│    X-SwitchBoard-Priority  → priority           │
│    X-SwitchBoard-Profile   → force_profile      │
│    X-SwitchBoard-Cost-Sensitivity → cost_sens.  │
│    X-SwitchBoard-Latency-Sensitivity → lat_sens.│
│                                                 │
│  Body heuristics:                               │
│    stream, max_tokens, model_hint               │
│    tools_present (bool)                         │
│    estimated_tokens (chars / 4)                 │
│    task_type: code | analysis | planning |      │
│               summarization | chat              │
│    complexity: low | medium | high              │
│    requires_structured_output (from             │
│      response_format.type)                      │
│                                                 │
│  Output: SelectionContext                       │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│  3. SELECT  (Selector)                          │
│                                                 │
│  3a. PolicyEngine                               │
│      If force_profile header → use it directly  │
│      Else: evaluate rules in priority order;    │
│      first match wins.                          │
│      No match → fallback_profile                │
│                                                 │
│  3b. ExperimentRouter (A/B)                     │
│      If an enabled experiment applies to this   │
│      rule, and the request hashes into the      │
│      treatment bucket → redirect to profile_b.  │
│      force_profile rules skip this step.        │
│                                                 │
│  3c. AdjustmentStore (adaptive routing)         │
│      If the selected profile is demoted (high   │
│      error rate or latency), find the next      │
│      eligible non-demoted profile.              │
│      Fail-open: if all profiles are demoted,    │
│      keep the original selection.               │
│                                                 │
│  3d. Eligibility check                          │
│      For each candidate profile:                │
│        requires_tools? → supports_tools must    │
│          be true.                               │
│        requires_structured_output? →            │
│          supports_structured_output must be     │
│          true.                                  │
│      Ineligible profiles are skipped.           │
│                                                 │
│  3e. ProfileScorer                              │
│      All eligible candidates are scored by a    │
│      weighted combination of quality_tier,      │
│      cost_tier/cost_weight, and latency_tier.   │
│      Highest-scoring profile is selected.       │
│                                                 │
│  Output: SelectionResult                        │
│    profile_name, downstream_model, rule_name,   │
│    adjustment_applied, ab_experiment,           │
│    cost_estimate, scored_profiles               │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│  4. REWRITE  (routes_chat.py)                   │
│                                                 │
│  body["model"] = result.downstream_model        │
│                                                 │
│  All other fields preserved verbatim:           │
│  tools, stream, response_format, temperature,   │
│  max_tokens, …                                  │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│  5. FORWARD  (Forwarder + RetryingGateway)      │
│                                                 │
│  RetryingGateway wraps HttpNineRouterGateway:   │
│    Attempt 1 → if 429/5xx/timeout/conn error:   │
│    sleep 0.5 s → Attempt 2                      │
│    sleep 1.0 s → Attempt 3                      │
│    4xx (except 429) raised immediately.         │
│    After 3 failed attempts: raise exception.    │
│                                                 │
│  Streaming (stream: true):                      │
│    No retry. SSE chunks forwarded directly.     │
│                                                 │
│  Timer wraps the full attempt sequence.         │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│  6. LOG  (DecisionLogger)                       │
│                                                 │
│  DecisionRecord appended to:                    │
│    - In-memory ring buffer (last 1 000)         │
│    - decisions.jsonl (if path configured)       │
│                                                 │
│  Fields include: timestamp, request_id,         │
│  profile_name, downstream_model, rule_name,     │
│  task_type, complexity, estimated_tokens,       │
│  adjustment_applied, ab_experiment, ab_bucket,  │
│  cost_estimate, scored_profiles, latency_ms,    │
│  status, error                                  │
└────────────────────────┬────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│  7. RESPOND  (routes_chat.py)                   │
│                                                 │
│  Success: return provider response verbatim,    │
│  HTTP 200.                                      │
│                                                 │
│  Failure: return structured error response      │
│  (see error table below).                       │
└─────────────────────────────────────────────────┘
```

---

## Error responses

All errors use the OpenAI error format: `{"error": {"type": "...", "code": "...", "message": "...", "request_id": "..."}}`.

| HTTP | `type` | `code` | When |
|------|--------|--------|------|
| 400 | `invalid_request_error` | `invalid_json` | Body is not valid JSON |
| 422 | `invalid_request_error` | `missing_required_field` | `messages` array absent |
| 503 | `routing_error` | `no_eligible_profile` | No profile could be selected |
| 503 | `routing_error` | `selection_failed` | Unexpected error in Selector |
| 502 | `upstream_error` | `upstream_http_error` | 9router returned an HTTP error |
| 502 | `upstream_error` | `upstream_connection_error` | Cannot connect to 9router |
| 504 | `upstream_timeout_error` | `upstream_timeout` | 9router timed out after retries |
| 500 | `internal_error` | `internal_server_error` | Unhandled exception |

---

## Header reference

| Header | Effect |
|--------|--------|
| `X-SwitchBoard-Profile` | Forces a specific profile; bypasses all rules, A/B routing, and adaptive routing |
| `X-SwitchBoard-Priority` | Sets `context.priority`; matched by `priority` rule condition |
| `X-SwitchBoard-Tenant-ID` | Sets `context.tenant_id`; matched by `tenant_id` rule condition |
| `X-SwitchBoard-Cost-Sensitivity` | `"high"` shifts profile scorer to favour low-cost profiles |
| `X-SwitchBoard-Latency-Sensitivity` | `"high"` shifts profile scorer to favour low-latency profiles |
| `X-Request-ID` | Captured as `request_id`; echoed in error responses and decision log |
