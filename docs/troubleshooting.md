# Troubleshooting

---

## Startup failures

### `Startup aborted due to configuration errors`

SwitchBoard validates all config files before accepting any requests. The log output lists every problem found:

```
CRITICAL switchboard.app - Startup aborted due to configuration errors:
  2 configuration error(s):
  - Policy file not found: /path/to/policy.yaml
  - Experiment 'my_exp': split_percent must be between 0 and 100, got 150
```

**Fix:** Address each listed error then restart.

Common causes:
- Config file path in `.env` points to a file that does not exist
- `SWITCHBOARD_POLICY_PATH` relative path is resolved from the working directory, not the script location — run from the repo root
- Experiment `split_percent` outside 0–100
- Two rules in `policy.yaml` have the same `name` field
- Experiment `profile_a` and `profile_b` are the same profile name

---

### `ModuleNotFoundError: No module named 'switchboard'`

The package is not installed in the current Python environment.

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

---

### Port already in use

```
ERROR:    [Errno 98] Address already in use
```

Another process is already listening on port 20401. Either stop that process or change `SWITCHBOARD_PORT` in `.env`.

```bash
# Find the process
lsof -i :20401
```

---

## Health check failures

### `nine_router.reachable: false`

SwitchBoard is running but cannot reach 9router.

1. Confirm 9router is running: `curl http://localhost:20128/health`
2. Check `ROUTER9_BASE_URL` in `.env` matches where 9router is actually running
3. Check firewall rules if running on different machines

SwitchBoard remains fully functional for classification and selection; only the forward step will fail until 9router is reachable.

---

## Request failures

### HTTP 400 — `invalid_json`

The request body is not valid JSON.

```json
{"error": {"type": "invalid_request_error", "code": "invalid_json", ...}}
```

Ensure the request includes `Content-Type: application/json` and a valid JSON body.

---

### HTTP 422 — `missing_required_field`

The request body does not include a `messages` array.

```json
{"error": {"type": "invalid_request_error", "code": "missing_required_field", ...}}
```

The `messages` field is required. Example of a valid body:

```json
{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}
```

---

### HTTP 503 — `no_eligible_profile`

No profile could be found to serve the request. This usually means:

- The selected profile is demoted by the adaptive routing system (high error rate or high latency)
- All eligible profiles have been filtered out by capability requirements (e.g., request requires structured output but no profile supports it)

**Check adaptive state:**

```bash
curl -s http://localhost:20401/admin/adaptive | python3 -m json.tool
```

If profiles are demoted, wait for them to recover or reset manually:

```bash
curl -s -X POST http://localhost:20401/admin/adaptive/reset
```

---

### HTTP 502 — `upstream_connection_error`

SwitchBoard could not connect to 9router. See [nine_router.reachable: false](#nine_routerreachable-false) above.

---

### HTTP 502 — `upstream_http_error`

9router returned an HTTP error (e.g., 503, 500). The routing itself worked correctly. Check 9router's logs for the root cause.

---

### HTTP 504 — `upstream_timeout`

9router did not respond within `ROUTER9_TIMEOUT_S` seconds (default 120). SwitchBoard retries up to 2 times before returning this error. If you see this consistently, check 9router latency and consider increasing the timeout or investigating the provider.

---

## Routing decisions

### Request went to the wrong profile

1. Check what rule fired:

```bash
python scripts/inspect.py recent 1
```

Look at the `rule` and `reason` fields.

2. Check what context SwitchBoard inferred:

The `context_summary` in the decision record shows `task_type`, `complexity`, `estimated_tokens`, `requires_tools`, and other signals. If the inferred context differs from what you expected, the wrong rule may have matched.

3. Trace through the policy manually:

Rules are evaluated in ascending `priority` order. The first matching rule wins. Check `config/policy.yaml` for rules with lower priority numbers that might be matching before your intended rule.

---

### Adaptive routing is demoting a profile unexpectedly

```bash
# Check current adjustments
python scripts/inspect.py summary 100

# View adaptive state
curl -s http://localhost:20401/admin/adaptive | python3 -m json.tool
```

The adaptive system demotes a profile when its error rate exceeds 40% or mean latency exceeds 8 000 ms over the last N requests. Adjustments expire after 300 seconds.

To reset:

```bash
curl -s -X POST http://localhost:20401/admin/adaptive/reset
```

To disable adaptive routing entirely:

```bash
curl -s -X POST http://localhost:20401/admin/adaptive/disable
```

---

## Decision log

### Decision log file not being written

Check `SWITCHBOARD_DECISION_LOG_PATH` in `.env`. If it is blank, logging is disabled by design.

The `runtime/` directory is created automatically if it does not exist. If the process does not have write permission to the target directory, decision logging silently fails but requests are still routed correctly.

---

### `GET /admin/decisions/recent` returns an empty list

The in-memory ring buffer holds the last 1 000 decisions and is reset when SwitchBoard restarts. If you just restarted and have not sent any requests yet, the list will be empty.

---

## Performance

### High latency on first request after startup

SwitchBoard makes no upstream connections until the first request arrives. The initial TCP handshake and TLS setup to 9router adds latency to the first request only.

---

## Getting more information

```bash
# Increase log verbosity
SWITCHBOARD_LOG_LEVEL=debug bash scripts/run_dev.sh

# Recent decisions with full context
python scripts/inspect.py recent 20

# Aggregated stats
python scripts/inspect.py summary 200
```
