# Stability and Maturity

SwitchBoard is a working system built through nine incremental phases. This document is honest about what is stable, what is experimental, and what is not yet built.

---

## Current version

**v0.1.0** — functional pre-release. The API surface and configuration format are not yet stable. Breaking changes may happen between releases.

---

## What is stable and ready to use

These features have complete test coverage, work end-to-end, and are used in the reference configuration:

| Feature | Status |
|---------|--------|
| `POST /v1/chat/completions` proxy | Stable |
| Policy-driven routing via `config/policy.yaml` | Stable |
| Profile registry via `config/profiles.yaml` | Stable |
| Capability registry via `config/capabilities.yaml` | Stable |
| Task classification (code, analysis, planning, summarization, chat) | Stable |
| Structured output capability routing | Stable |
| Multi-factor profile scoring | Stable |
| SSE streaming pass-through | Stable |
| Decision logging to JSONL | Stable |
| In-memory ring buffer + `/admin/decisions/recent` | Stable |
| Health check (`GET /health`) | Stable |
| Model listing (`GET /v1/models`) | Stable |
| OpenAI-compatible error responses | Stable |
| Retry with backoff on transient upstream errors | Stable |
| Startup config validation | Stable |
| Global exception handler | Stable |
| `X-SwitchBoard-*` caller headers | Stable |

---

## What is present but experimental

These features work but have rough edges, limited real-world testing, or interfaces likely to change:

| Feature | Limitation |
|---------|-----------|
| Adaptive routing (error rate / latency monitoring) | Thresholds are hardcoded; no operator-configurable tuning |
| A/B experiment routing | No results tracking or statistical analysis built in |
| Admin adaptive endpoints (`/admin/adaptive/*`) | Interface may change as the feature matures |
| `scripts/inspect.py` | Useful but not fully polished; summary endpoint may change |

---

## What is not yet built

These are known gaps. They are intentionally out of scope for v0.

| Feature | Notes |
|---------|-------|
| Authentication / API key validation | Handle at the reverse proxy layer or in 9router |
| Per-tenant policy overrides | All requests share the same policy |
| Rate limiting | Not implemented |
| Prometheus metrics | No `/metrics` endpoint |
| OpenTelemetry tracing | No span emission |
| Dynamic policy reload | Restart required to pick up config changes |
| Persistent decision log | Local JSONL only; no remote sink |
| Multi-9router failover | Single upstream only |
| Web UI or dashboard | Use `scripts/inspect.py` or the admin API |
| Windows native support | Shell scripts are bash; PowerShell variants exist but are less tested |

---

## Known limitations

- **Single upstream**: SwitchBoard routes to one 9router instance. If that instance is unreachable, all forward requests fail. The retry layer handles transient failures but not complete outages.

- **In-memory state**: The decision ring buffer, adaptive routing state, and adjustment store are all in-memory. They reset on restart. This is by design for simplicity but means you lose observability state across restarts.

- **No auth**: SwitchBoard accepts requests from any caller. Deploy behind a reverse proxy or firewall as appropriate for your threat model.

- **Config reload requires restart**: Changes to `policy.yaml`, `profiles.yaml`, or `capabilities.yaml` take effect only after restarting the process.

- **Adaptive routing thresholds are not configurable**: Demotion triggers at 40% error rate or 8 000 ms latency. These are hardcoded in `adjustment_engine.py`.

---

## Supported workflows

The following workflows are verified to work with the current release:

1. **Basic routing** — send a request, have it routed to a profile by rule match, receive a response
2. **Streaming** — request with `stream: true` passes through as SSE
3. **Structured output routing** — requests requiring JSON output are directed to capable profiles
4. **A/B experiments** — declarative traffic splitting by percent with deterministic assignment
5. **Adaptive routing** — automatic demotion of profiles with high error rate or latency
6. **Decision inspection** — view recent decisions via admin API or `inspect.py`
7. **Operator control** — enable/disable/reset adaptive routing via admin API

---

## Assumptions about the environment

- SwitchBoard assumes it runs behind a reverse proxy or in a trusted network. It does not validate API keys or enforce auth.
- SwitchBoard assumes 9router handles provider-level auth (API keys to OpenAI, Anthropic, etc.).
- SwitchBoard assumes the three config YAML files are valid at startup. It will refuse to start if they contain errors.
- SwitchBoard is tested on Python 3.11 and 3.12 on Linux. macOS should work. Windows is untested beyond the PowerShell scripts.
