# Roadmap

## Phase 1 — v0 (Current)

The current release establishes the core routing pipeline and makes it
production-usable for teams that already run 9router.

**Delivered:**

- Policy-driven model selection via YAML rules (`when` / `select_profile`).
- Profile registry decoupling profile names from concrete model identifiers.
- Capability registry describing downstream model features.
- Full classify → select → forward → log pipeline on `POST /v1/chat/completions`.
- OpenAI-compatible model listing at `GET /v1/models`.
- Decision logging to JSONL with in-memory ring buffer + admin API.
- `X-SwitchBoard-Profile` header for caller-side profile override.
- `X-SwitchBoard-Priority` and `X-SwitchBoard-Tenant-ID` header support.
- Health check endpoint (`GET /health`) with 9router probe.
- Hot-reloadable policy config via admin endpoint (planned, scaffolded).
- Hexagonal architecture: domain / ports / adapters / services clearly separated.

**Intentionally out of scope for v0:**

- Authentication or API-key management (handled upstream or by 9router).
- Per-tenant billing or quota enforcement.
- Streaming response proxying (SSE pass-through) — non-streaming only.
- Multi-region or multi-9router failover.
- Prometheus metrics or OpenTelemetry tracing.
- Persistent decision log beyond the local JSONL file.
- Web UI or dashboard.
- Dynamic policy reload without process restart (groundwork laid, not wired).

---

## Phase 2 — Streaming & Observability

- **SSE streaming pass-through** — proxy `stream: true` requests as a chunked
  SSE response rather than buffering the full response.
- **Prometheus metrics endpoint** (`GET /metrics`) — request counts, latency
  histograms, error rates, and per-profile routing distribution.
- **OpenTelemetry tracing** — emit spans for classify, select, and forward
  stages; propagate trace context to 9router.
- **Dynamic policy reload** — `POST /admin/reload` picks up edited `policy.yaml`
  without a process restart.

---

## Phase 3 — Multi-Tenancy & Access Control

- **API-key middleware** — validate caller API keys and attach tenant identity
  automatically (removes the need for callers to send `X-SwitchBoard-Tenant-ID`).
- **Per-tenant policy overrides** — allow different fallback profiles or rule
  sets for different tenants without maintaining multiple SwitchBoard instances.
- **Rate limiting** — per-tenant or per-profile request quotas enforced at the
  SwitchBoard layer before hitting 9router.
- **Audit log retention** — ship decision records to a structured store
  (PostgreSQL, Loki, S3) instead of a local JSONL file.

---

## Phase 4 — Intelligent Routing

- **Classifier improvements** — detect task type (code, summarisation, Q&A,
  etc.) from message content and use it as a routing signal.
- **Cost-aware routing** — estimate request cost before forwarding and apply
  budget guardrails.
- **Latency-aware routing** — probe downstream model latency and adjust profile
  selection dynamically when 9router reports high tail latency.
- **A/B routing** — split traffic between two profiles to compare quality or
  cost without a full migration.
- **Feedback loop** — feed structured response quality signals back into policy
  weight adjustments.
