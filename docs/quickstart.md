# Quickstart

This guide walks you through installing SwitchBoard, starting the stack, and verifying that routing works end-to-end.

**Time to complete:** ~10 minutes (excluding 9router setup).

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | `python3 --version` |
| bash (Unix) or PowerShell 5.1+ (Windows) | For helper scripts |
| A running [9router](https://github.com/Velascat/9router) instance | Default: `http://localhost:20128` |
| `curl` (optional) | For manual verification |

SwitchBoard does not require a database, Redis, or any other service beyond 9router.

---

## Step 1 — Clone and install

```bash
git clone https://github.com/Velascat/SwitchBoard
cd SwitchBoard
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify:

```bash
switchboard --help   # should print uvicorn startup help, not an error
```

---

## Step 2 — Configure

```bash
cp .env.example .env
```

Open `.env` and check one line:

```
ROUTER9_BASE_URL=http://localhost:20128
```

Change this to point at your running 9router instance if it is on a different host or port. All other defaults work for local development.

The three config files in `config/` ship with working defaults. You do not need to edit them to complete this quickstart.

---

## Step 3 — Start SwitchBoard

```bash
bash scripts/run_dev.sh
```

Expected output:

```
[run_dev] Starting SwitchBoard on port 20401 (reload enabled)
INFO:     Started server process [...]
INFO:     Uvicorn running on http://0.0.0.0:20401 (Press CTRL+C to quit)
INFO     switchboard.app - SwitchBoard ready
```

If you see `Startup aborted due to configuration errors`, check that the three YAML files under `config/` exist and are valid. See [troubleshooting.md](troubleshooting.md).

---

## Step 4 — Verify health

```bash
curl -s http://localhost:20401/health | python3 -m json.tool
```

Expected:

```json
{
    "status": "ok",
    "version": "0.1.0",
    "uptime_s": 1.2,
    "nine_router": {
        "reachable": true,
        "latency_ms": 0.9,
        "error": null
    }
}
```

If `nine_router.reachable` is `false`, SwitchBoard is up but cannot reach 9router. Routing will still work if your request reaches SwitchBoard, but the forward step will fail. Fix: confirm 9router is running and `ROUTER9_BASE_URL` in `.env` is correct.

---

## Step 5 — Send a request

```bash
curl -s http://localhost:20401/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"fast","messages":[{"role":"user","content":"Say hello."}]}' \
  | python3 -m json.tool
```

Expected: a valid OpenAI chat completion response with `choices[0].message.content`.

If 9router is not connected you will see:

```json
{"error": {"type": "upstream_error", "code": "upstream_connection_error", ...}}
```

This confirms SwitchBoard received and classified the request correctly — the failure is in the forward step, not in SwitchBoard. Connect 9router to get a full end-to-end response.

---

## Step 6 — Inspect the routing decision

```bash
python scripts/inspect.py recent 1
```

Expected output showing the decision just made:

```
[1]
  timestamp:   2024-01-15T10:23:45.123456
  request_id:  a1b2c3d4...
  status:      success
  profile:     fast
  model:       gpt-4o-mini
  rule:        default_short_request
  reason:      ...
  latency_ms:  42.1
  task_type:   chat
```

This confirms the routing decision was recorded correctly.

---

## Step 7 — Run the smoke test

```bash
bash scripts/smoke_test.sh
```

The smoke test exercises health, model listing, chat completions, and admin endpoints. All four should PASS; the chat completion test accepts 200 or 502 (502 means SwitchBoard classified and tried to forward but 9router was not reachable).

---

## Next steps

| Goal | Where to look |
|------|---------------|
| Understand routing rules | [docs/policies.md](policies.md) |
| Add or change profiles | [docs/profiles.md](profiles.md) |
| See all configuration options | [docs/configuration.md](configuration.md) |
| Debug unexpected routing | [docs/troubleshooting.md](troubleshooting.md) |
| Monitor in production | [docs/observability.md](observability.md) |
| Contribute to the project | [CONTRIBUTING.md](../CONTRIBUTING.md) |
