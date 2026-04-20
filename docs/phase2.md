# Phase 2 — Aider Client Integration

Phase 2 proves the platform is practical for real developer workflows, not just internally testable.

```
Aider → LiteLLM → SwitchBoard → 9router → Provider → Response
```

Phase 1 proved one request could flow through the system. Phase 2 proves a real coding tool can use SwitchBoard as its model backend, with routing decisions visible and profiles intentionally selectable.

---

## What Phase 2 Delivers

- SSE streaming passthrough (`stream: true` requests proxied verbatim to 9router)
- Aider model settings file (`config/aider/model-settings.yml`) for clean model registration
- Helper launcher script (`scripts/aider.sh`) that wires all environment variables
- `openai/fast`, `openai/capable`, `openai/local` as documented model aliases
- All Phase 1 capabilities remain intact

---

## Prerequisites

- Python 3.11+
- SwitchBoard running (see Phase 1)
- 9router running at `http://localhost:20128`
- Aider installed: `pip install aider-chat`
- Any non-empty value for `OPENAI_API_KEY`

---

## How to Start the Stack

```bash
# Terminal 1 — SwitchBoard
cd /path/to/SwitchBoard
bash scripts/run_dev.sh

# Terminal 2 — verify health
curl http://localhost:20401/health
```

---

## Aider Configuration

Aider uses LiteLLM internally. The `openai/<name>` prefix tells LiteLLM to route through an OpenAI-compatible endpoint.

### Critical: API base URL must include `/v1`

```bash
export OPENAI_API_BASE="http://localhost:20401/v1"
export OPENAI_API_KEY="sk-switchboard"   # any non-empty value
```

Without `/v1` in the base URL, LiteLLM calls `/chat/completions` instead of `/v1/chat/completions`.

### Model aliases

| Aider model name | SwitchBoard profile | Downstream model |
|------------------|--------------------|--------------------|
| `openai/fast`    | `fast`             | `gpt-4o-mini`      |
| `openai/capable` | `capable`          | `gpt-4o`           |
| `openai/local`   | `local`            | `llama3`           |

Policy rules still apply — the model name is treated as a hint and may be upgraded/downgraded by policy (e.g., a request with `X-SwitchBoard-Priority: high` always routes to `capable`).

---

## Using the Helper Script (Recommended)

The helper script sets all required environment variables and starts Aider:

```bash
# Start Aider with the fast profile (default)
bash scripts/aider.sh

# Start with the capable profile
bash scripts/aider.sh --profile capable

# Start with the local profile
bash scripts/aider.sh --profile local

# Pass extra Aider arguments after --
bash scripts/aider.sh --profile capable -- --no-auto-commits
```

The script:
1. Verifies SwitchBoard is reachable before launching
2. Sets `OPENAI_API_BASE=http://localhost:20401/v1`
3. Sets `OPENAI_API_KEY=sk-switchboard` if not already set
4. Passes `--model-settings-file config/aider/model-settings.yml`
5. Launches Aider

---

## Manual Setup

If you prefer to configure manually:

```bash
export OPENAI_API_BASE="http://localhost:20401/v1"
export OPENAI_API_KEY="sk-switchboard"

aider \
  --model openai/fast \
  --model-settings-file config/aider/model-settings.yml
```

### Single-line no-install test (non-streaming)

```bash
OPENAI_API_BASE=http://localhost:20401/v1 OPENAI_API_KEY=dummy \
  aider --model openai/fast --no-stream --message "What is 2+2?" /dev/null
```

---

## Intentional Profile Selection

### Method 1 — Model alias

```bash
# Force capable profile via model name
aider --model openai/capable ...

# Force local profile
aider --model openai/local ...
```

### Method 2 — X-SwitchBoard-Profile header

Set the profile explicitly, bypassing all policy rules:

```bash
curl -X POST http://localhost:20401/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-SwitchBoard-Profile: capable" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Method 3 — X-SwitchBoard-Priority header

Let the policy engine decide based on priority:

```bash
curl -X POST http://localhost:20401/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-SwitchBoard-Priority: high" \
  -d '{"messages": [{"role": "user", "content": "Urgent task"}]}'
# → routes to "capable" profile (policy rule: high_priority_tenant)
```

---

## Verifying Profile Selection

### Decision log (primary method)

Every routed request writes one JSON line to `runtime/decisions.jsonl`:

```bash
# Watch live as Aider sends requests
tail -f runtime/decisions.jsonl

# Pretty-print last entry
tail -1 runtime/decisions.jsonl | python3 -m json.tool
```

Example decision record from an Aider request:

```json
{
  "timestamp": "2026-04-20T17:30:00.000000+00:00",
  "selected_profile": "fast",
  "downstream_model": "gpt-4o-mini",
  "rule_name": "default_short_request",
  "original_model_hint": "fast",
  "profile_name": "fast",
  "latency_ms": 1243.7,
  "error": null
}
```

Fields to check:
- `selected_profile` — which profile SwitchBoard chose
- `downstream_model` — what model was sent to 9router
- `rule_name` — which policy rule fired (or `"force_profile"` for header overrides)

### Admin API (in-process buffer)

```bash
curl http://localhost:20401/admin/decisions/recent?n=5 | python3 -m json.tool
```

---

## Streaming

Aider sends `stream: true` by default. SwitchBoard proxies SSE chunks verbatim from 9router to Aider. No special configuration is needed.

If you need to disable streaming for debugging:

```bash
aider --model openai/fast --no-stream ...
```

---

## Troubleshooting

### `Model not found` or `no model info`

Aider may warn about unknown models if you don't pass `--model-settings-file`. Use the helper script or pass the flag explicitly:

```bash
aider --model openai/fast --model-settings-file config/aider/model-settings.yml
```

### `Connection refused` or `502 Bad Gateway`

SwitchBoard is not running. Start it:

```bash
bash scripts/run_dev.sh
```

9router is not running. SwitchBoard will return HTTP 502. This means routing worked — the failure is downstream. Check:

```bash
curl http://localhost:20401/health
# Look for "nine_router": {"reachable": false}
```

### `401 Unauthorized` from 9router

9router requires a real API key. Set `OPENAI_API_KEY` to your actual provider API key in `.env` and restart the stack. SwitchBoard passes the Authorization header through to 9router.

### Requests don't appear in decision log

Check `SWITCHBOARD_DECISION_LOG_PATH` in `.env`. Default is `./runtime/decisions.jsonl`. The directory is created automatically.

### Wrong URL — `/chat/completions` vs `/v1/chat/completions`

If you see 404 errors, ensure `OPENAI_API_BASE` ends with `/v1`:

```bash
export OPENAI_API_BASE="http://localhost:20401/v1"   # correct
export OPENAI_API_BASE="http://localhost:20401"       # wrong — LiteLLM calls /chat/completions
```

---

## Phase 2 Constraints

- Authentication is pass-through: SwitchBoard does not validate API keys
- No multi-tenancy in this phase
- Profile selection is policy-driven, not Aider-version-aware
- Streaming is proxied verbatim — no token counting in streaming mode
- Aider's `--weak-model` sub-calls use the same SwitchBoard routing

---

## Definition of Done

Phase 2 is complete when all of the following succeed:

1. `bash scripts/aider.sh` starts Aider without errors
2. At least one Aider message is sent through SwitchBoard
3. A JSONL decision entry appears in `runtime/decisions.jsonl`
4. `selected_profile` and `downstream_model` are visible in the entry
5. Running with `--profile capable` routes to the `capable` profile
6. `pytest` reports 0 failures (123 tests)
