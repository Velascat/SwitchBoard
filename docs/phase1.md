# Phase 1 — Vertical Slice

Phase 1 proves the full request path works end-to-end:

```
Client → SwitchBoard → 9router → Provider → Response
```

It is the smallest real thing: SwitchBoard receives a request, selects a profile using deterministic rules, maps it to a downstream model, forwards through 9router, returns the response, and logs the decision.

---

## What Phase 1 Delivers

- `/health` — service liveness + 9router reachability
- `/v1/models` — configured profiles exposed as OpenAI model list
- `/v1/chat/completions` — full routing pipeline with JSONL decision log
- Static YAML policy: 3 profiles (`fast`, `capable`, `local`) + fallback `default`
- Structured decision log written to `runtime/decisions.jsonl`

---

## Prerequisites

- Python 3.11+
- A running 9router instance (default: `http://localhost:20128`)
  - If 9router is not available, SwitchBoard still starts and routes correctly; chat requests return HTTP 502.
  - Use `X-SwitchBoard-Profile` header to inspect selection without a live provider.

---

## Start SwitchBoard

```bash
cd /path/to/SwitchBoard

# 1. Create environment file
cp .env.example .env

# 2. Install (first time)
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 3. Start
bash scripts/run_dev.sh
```

SwitchBoard listens on **port 20401** by default.

---

## Verify Health

```bash
curl http://localhost:20401/health
```

Expected response (9router unreachable):

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "uptime_s": 0.42,
  "nine_router": {
    "reachable": false,
    "latency_ms": 1.2,
    "error": "..."
  }
}
```

Expected response (9router reachable):

```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime_s": 1.1,
  "nine_router": {
    "reachable": true,
    "latency_ms": 3.4
  }
}
```

---

## Query Available Models

```bash
curl http://localhost:20401/v1/models
```

Expected response:

```json
{
  "object": "list",
  "data": [
    {"id": "capable", "object": "model", "created": 1714000000, "owned_by": "switchboard"},
    {"id": "default", "object": "model", "created": 1714000000, "owned_by": "switchboard"},
    {"id": "fast",    "object": "model", "created": 1714000000, "owned_by": "switchboard"},
    {"id": "local",   "object": "model", "created": 1714000000, "owned_by": "switchboard"}
  ]
}
```

---

## Send a Chat Completion Request

```bash
curl -X POST http://localhost:20401/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "fast",
    "messages": [{"role": "user", "content": "Hello, what is 2+2?"}]
  }'
```

**With 9router running**, returns the provider response.

**Without 9router**, returns HTTP 502 — which confirms SwitchBoard routed correctly.

### Force a specific profile

```bash
curl -X POST http://localhost:20401/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-SwitchBoard-Profile: capable" \
  -d '{
    "model": "any",
    "messages": [{"role": "user", "content": "Write a poem."}]
  }'
```

### Set request priority

```bash
curl -X POST http://localhost:20401/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-SwitchBoard-Priority: high" \
  -d '{
    "messages": [{"role": "user", "content": "Urgent task."}]
  }'
```

---

## Profile Selection Rules

SwitchBoard selects a profile for each request using these rules (evaluated in priority order):

| Priority | Rule | Condition | Profile |
|----------|------|-----------|---------|
| 10 | `caller_requests_capable` | `model` in `["capable", "gpt-4o", "claude-3-5-sonnet"]` | `capable` |
| 11 | `caller_requests_local` | `model` in `["local", "private", "llama3"]` | `local` |
| 20 | `high_priority_tenant` | `X-SwitchBoard-Priority: high` | `capable` |
| 30 | `tool_use` | request includes `tools` array | `capable` |
| 40 | `streaming_short` | `stream: true` + ≤512 estimated tokens | `fast` |
| 50 | `large_context` | ≥4096 estimated tokens | `capable` |
| 60 | `long_output_requested` | `max_tokens` ≥ 2048 | `capable` |
| 70 | `low_priority_local` | `X-SwitchBoard-Priority: low` | `local` |
| 100 | `default_short_request` | ≤4096 estimated tokens | `fast` |
| — | fallback | no rule matched | `default` |

Override any rule by sending `X-SwitchBoard-Profile: <name>` header.

---

## Profile → Downstream Model Mapping

| Profile | Downstream Model |
|---------|-----------------|
| `fast` | `gpt-4o-mini` |
| `capable` | `gpt-4o` |
| `local` | `llama3` |
| `default` | `gpt-4o-mini` |

---

## Inspect the Decision Log

Each routed request appends one JSON line to `runtime/decisions.jsonl`:

```bash
# Watch live
tail -f runtime/decisions.jsonl

# Pretty-print the last entry
tail -1 runtime/decisions.jsonl | python3 -m json.tool
```

Example decision record:

```json
{
  "timestamp": "2026-04-20T17:00:00.123456+00:00",
  "client": null,
  "task_type": null,
  "selected_profile": "fast",
  "downstream_model": "gpt-4o-mini",
  "rule_name": "default_short_request",
  "reason": "",
  "request_id": null,
  "original_model_hint": "fast",
  "profile_name": "fast",
  "latency_ms": 243.7,
  "tenant_id": null,
  "error": null
}
```

### Query via API

```bash
curl http://localhost:20401/admin/decisions/recent?n=5
```

---

## Run the Test Suite

```bash
# All tests (must pass 100%)
.venv/bin/pytest

# Unit tests only
.venv/bin/pytest test/unit/ -v

# Integration tests
.venv/bin/pytest test/integration/ -v

# Smoke tests
.venv/bin/pytest test/smoke/ -v

# Contract tests (HTTP gateway)
.venv/bin/pytest test/contract/ -v
```

---

## Automated Smoke Verification

```bash
# Requires SwitchBoard running on http://localhost:20401
bash scripts/smoke_test.sh
```

---

## WorkStation (Docker) Path

If running the full stack via Docker Compose from the WorkStation repo:

```bash
cd /path/to/WorkStation
cp .env.example .env
./scripts/up.sh
./scripts/health.sh
./scripts/status.sh
```

---

## Phase 1 Constraints

The following are explicitly out of scope for Phase 1:

- Authentication / tenancy
- Streaming responses
- Adaptive or learned routing
- Fallback orchestration / retries
- Cost optimization
- Control Plane integration
- Dashboards or analytics

---

## Definition of Done

Phase 1 is complete when all of the following succeed locally:

1. `bash scripts/run_dev.sh` starts without errors
2. `curl http://localhost:20401/health` returns HTTP 200
3. `curl http://localhost:20401/v1/models` returns the 4 profiles
4. `curl -X POST http://localhost:20401/v1/chat/completions -d '{"messages":[{"role":"user","content":"hi"}]}'` returns HTTP 200 or 502 (200 = full path; 502 = routing reached 9router)
5. A JSONL entry appears in `runtime/decisions.jsonl` after any chat request
6. `pytest` reports 0 failures
