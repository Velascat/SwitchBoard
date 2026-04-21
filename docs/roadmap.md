# Roadmap

---

## Current: v0.1.0

The following phases have been delivered and are available in the current release.

### Core pipeline (Phases 1–3)

- Policy-driven model selection via YAML rules (`when` / `select_profile`)
- Profile registry decoupling profile names from concrete model identifiers
- Capability registry describing downstream model features
- Full classify → select → forward → log pipeline on `POST /v1/chat/completions`
- OpenAI-compatible model listing at `GET /v1/models`
- Decision logging to JSONL with in-memory ring buffer + admin API
- `X-SwitchBoard-*` header support (priority, tenant, cost/latency sensitivity)
- Health check endpoint (`GET /health`) with 9router probe
- SSE streaming pass-through (`stream: true`)
- Dynamic policy reload via admin endpoint (`POST /admin/reload`)
- Hexagonal architecture: domain / ports / adapters / services clearly separated

### Observability (Phase 4)

- Prometheus-style summary endpoint (`GET /admin/summary`)
- Per-profile routing distribution, error rates, latency percentiles
- Decision log enriched with context summary and rejected profiles

### Advanced routing (Phases 5–6)

- Task classification: detects code, analysis, planning, summarization, chat
- Long-context detection and routing
- Complexity estimation
- Streaming-aware routing rules

### Adaptive policy (Phase 7)

- Signal aggregation from decision ring buffer into per-profile `ProfileSignals`
- `AdjustmentEngine` derives demotion/promotion decisions from error rate and latency
- `AdjustmentStore` caches adjustments with 300 s TTL; background task refreshes automatically every 5 minutes
- Selector bypasses demoted profiles and finds the next eligible alternative
- Admin API: `/admin/adaptive`, `/admin/adaptive/enable|disable|reset|refresh`

### Advanced routing II (Phase 8)

- A/B experiment routing: deterministic percentage split, recorded in decision log
- Structured output capability routing: requests requiring JSON directed to capable profiles
- Multi-factor profile scoring: weighted quality/cost/latency tiers
- Cost estimate in decision trace
- `analysis` task type added to classifier

### Platform hardening (Phase 9)

- Standardised OpenAI-compatible error responses for all failure cases
- Retry with exponential backoff on transient upstream errors (max 2 retries)
- Startup config validation: refuses to start on bad config with detailed errors
- Global exception handler: unhandled exceptions return structured 500 responses

### Externalization (Phase 10)

- Complete public-facing documentation: quickstart, configuration guide, troubleshooting, stability statement
- Contributor guide with architecture boundaries and development workflow
- Accurate README with correct license, working commands, and docs index

---

## Known gaps (not yet planned)

These are intentionally out of scope for v0. They may be addressed in future releases.

| Gap | Notes |
|-----|-------|
| Authentication / API key validation | Recommended: handle at reverse proxy layer |
| Per-tenant policy overrides | All requests share one policy today |
| Rate limiting | Not implemented |
| Prometheus metrics endpoint | No `/metrics` today |
| OpenTelemetry tracing | No span emission |
| Dynamic config reload | Restart required to pick up config changes |
| Persistent decision log sink | Local JSONL only; no database or remote sink |
| Multi-9router failover | Single upstream only |
| Configurable adaptive thresholds | Currently hardcoded in `adjustment_engine.py` |
| Windows native support | Bash scripts work; PowerShell variants exist but less tested |

---

## Contributing

If you want to work on one of the known gaps or a new capability, see [CONTRIBUTING.md](../CONTRIBUTING.md) for architecture boundaries and development workflow.
