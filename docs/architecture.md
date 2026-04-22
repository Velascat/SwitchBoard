# Architecture

SwitchBoard follows a **hexagonal architecture** (ports and adapters). The core domain
has no dependencies on HTTP, filesystems, or any external library. All I/O is handled
by adapters that implement well-defined port interfaces.

**Architectural position:** SwitchBoard is an execution-lane selector. It classifies
tasks, evaluates policy, and returns a lane assignment (`claude_cli`, `codex_cli`, or
`aider_local`). It does not proxy API calls to external LLM providers.

**9router:** The `HttpNineRouterGateway` adapter and the `Forwarder` service that
forwarded requests to 9router are in the process of being replaced with a
lane-dispatch adapter. 9router has been removed from the architecture. See
[`WorkStation/docs/architecture/adr/0001-remove-9router.md`](https://github.com/Velascat/WorkStation/tree/main/docs/architecture/adr/0001-remove-9router.md)
for the full rationale. Until the adapter replacement lands in Phase 3, the
`HttpNineRouterGateway` code remains present but is not the target architecture.

---

## Layer diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                         HTTP Clients                                 ║
║          (curl, SDKs, any OpenAI-compatible client)                 ║
╚═════════════════════════════╦════════════════════════════════════════╝
                              │ POST /v1/chat/completions
                              │ GET  /v1/models  GET /health
                              │ GET  /admin/decisions/recent
                              │ GET  /admin/decisions/{request_id}
                              │ GET  /admin/summary
                              │ GET/POST /admin/adaptive[/*]
╔═════════════════════════════▼════════════════════════════════════════╗
║                       API Layer (FastAPI)                            ║
║                                                                      ║
║  routes_chat.py   routes_models.py   routes_health.py               ║
║  routes_admin.py  errors.py                                          ║
╚═════════════════════════════╦════════════════════════════════════════╝
                              │ calls
╔═════════════════════════════▼════════════════════════════════════════╗
║                      Service Layer                                   ║
║                                                                      ║
║  RequestClassifier                                                   ║
║       │                                                              ║
║       ▼                                                              ║
║  Selector ─────────────────────────────────────────────► Forwarder  ║
║    │  │  │  │                                               │        ║
║    │  │  │  └─ ProfileScorer (multi-factor ranking)         │        ║
║    │  │  └──── ExperimentRouter (A/B splits)                │        ║
║    │  └─────── AdjustmentStore ◄── AdjustmentEngine         │        ║
║    │                               ◄── SignalAggregator      │        ║
║    └─────────── PolicyEngine                                 │        ║
║                 CapabilityRegistry                           │        ║
║                                                              ▼        ║
║                                                         DecisionLogger║
╚══════════════╦═══════════════════════════════╦══════════════════════╝
               │ Port interfaces               │
╔══════════════▼══════════════╗  ╔════════════▼══════════════════════╗
║      Domain Layer           ║  ║       Adapter Layer               ║
║                             ║  ║                                   ║
║  SelectionContext           ║  ║  FilePolicyStore                  ║
║  SelectionResult            ║  ║  FileProfileStore                 ║
║  DecisionRecord             ║  ║  HttpNineRouterGateway            ║
║  PolicyRule / PolicyConfig  ║  ║  RetryingGateway (wraps above)   ║
║  ExperimentConfig           ║  ║  JsonlDecisionSink                ║
╚═════════════════════════════╝  ╚═══════════════════════════════════╝
```

---

## Layers and responsibilities

### API layer (`src/switchboard/api/`)

Owns all HTTP concerns: parsing request bodies, setting response codes, CORS, structured error responses. Contains no business logic — delegates immediately to the service layer. Reads services from `request.app.state`.

| Module | Responsibility |
|--------|---------------|
| `routes_chat.py` | Orchestrates classify → select → forward pipeline |
| `routes_models.py` | Lists available profiles as OpenAI model objects |
| `routes_health.py` | Checks local and downstream (9router) health |
| `routes_admin.py` | Decision log, summary stats, adaptive routing control |
| `errors.py` | OpenAI-compatible error response builders |

### Service layer (`src/switchboard/services/`)

All business logic. Services depend on **port interfaces**, not concrete adapters. No HTTP, no file I/O.

| Service | Responsibility |
|---------|---------------|
| `RequestClassifier` | raw request + headers → `SelectionContext` (task type, complexity, token estimate, structured output requirement) |
| `PolicyEngine` | evaluates ordered rules against a `SelectionContext`; returns matching rule |
| `CapabilityRegistry` | resolves profile name → downstream model string; checks capability requirements |
| `ExperimentRouter` | intercepts selections for A/B experiments; deterministic bucket assignment |
| `AdjustmentStore` | Per-profile adjustments (demoted/promoted); auto-refreshed every 300 s by background task; operator controls via admin API |
| `AdjustmentEngine` | derives adjustments from `ProfileSignals` (error rate, latency thresholds) |
| `SignalAggregator` | aggregates `DecisionRecord` ring buffer → `ProfileSignals` per profile |
| `ProfileScorer` | ranks eligible profiles by weighted quality/cost/latency tiers |
| `Selector` | orchestrates policy → A/B → adaptive → eligibility → scoring → result |
| `Forwarder` | sends the rewritten request to 9router, measures latency, records decision |
| `DecisionLogger` | appends `DecisionRecord` to JSONL and in-memory ring buffer |

### Domain layer (`src/switchboard/domain/`)

Pure data types with no behaviour beyond validation. No external dependencies.

| Type | Description |
|------|-------------|
| `SelectionContext` | Inferred properties of an incoming request |
| `SelectionResult` | Chosen profile, downstream model, rule, adaptive/A/B trace |
| `DecisionRecord` | Full audit record written to the decision log |
| `PolicyRule` | Typed representation of one policy rule |
| `PolicyConfig` | Full policy: rules, fallback profile, experiments |
| `ExperimentConfig` | A/B experiment definition |

### Port layer (`src/switchboard/ports/`)

Python `Protocol` classes that define contracts for adapters. Services import ports, never adapters directly — enabling lightweight test doubles.

| Port | Implemented by |
|------|---------------|
| `PolicyStore` | `FilePolicyStore` |
| `ProfileStore` | `FileProfileStore` |
| `ModelGateway` | `HttpNineRouterGateway` (wrapped by `RetryingGateway`) |
| `DecisionSink` | `JsonlDecisionSink` |

### Adapter layer (`src/switchboard/adapters/`)

Concrete implementations of ports. Allowed to import `httpx`, `yaml`, `pathlib`, etc.

| Adapter | Responsibility |
|---------|---------------|
| `FilePolicyStore` | Reads and parses `policy.yaml` |
| `FileProfileStore` | Reads and parses `profiles.yaml` |
| `HttpNineRouterGateway` | HTTP client for 9router (`/v1/chat/completions`, SSE streaming) |
| `RetryingGateway` | Wraps any `ModelGateway`; retries 429/5xx/timeout with backoff |

### Config layer (`src/switchboard/config/`)

| Module | Responsibility |
|--------|---------------|
| `__init__.py` | `Settings` (pydantic-settings); all env vars with defaults |
| `validator.py` | `ConfigValidator` — validates all three YAML files at startup; aborts on errors |

---

## Request flow (non-streaming)

```
1. routes_chat.py
   ├── Parse JSON body
   ├── Assign / extract request_id
   │
2. RequestClassifier.classify()
   ├── Infer task_type, complexity, estimated_tokens
   ├── Read X-SwitchBoard-* headers
   └── Returns SelectionContext
   │
3. Selector.select()
   ├── 3a. PolicyEngine — find first matching rule → profile_name
   ├── 3b. ExperimentRouter — maybe redirect to treatment profile (A/B)
   ├── 3c. AdjustmentStore — skip demoted profiles
   ├── 3d. Eligibility check — capability requirements (tools, structured output)
   ├── 3e. ProfileScorer — rank all eligible candidates
   └── Returns SelectionResult
   │
4. Rewrite request body: body["model"] = result.downstream_model
   │
5. Forwarder.forward()
   ├── RetryingGateway.create_chat_completion() (up to 3 attempts)
   ├── Measure latency
   ├── DecisionLogger.log()
   └── Returns response data
   │
6. Return JSONResponse(response_data)
```

---

## Dependency rule

Dependencies flow **inward only**:

```
API → Services → Domain
Adapters → Ports ← Services
```

The domain layer imports nothing from outside itself.
The service layer imports domain + ports, never adapters.
The API and adapter layers import services and domain.
Nothing imports the API layer except `app.py`.

---

## Application wiring

`app.py::lifespan()` is the composition root:

1. Load `Settings` from environment / `.env`
2. Run `ConfigValidator.validate_all()` — abort on errors
3. Instantiate adapters: `FilePolicyStore`, `FileProfileStore`, `CapabilityRegistry`, `HttpNineRouterGateway`, `RetryingGateway`, `DecisionLogger`
4. Instantiate services: `PolicyEngine`, `RequestClassifier`, `SignalAggregator`, `AdjustmentEngine`, `AdjustmentStore`, `ExperimentRouter`, `ProfileScorer`, `Selector`, `Forwarder`
5. Attach everything to `app.state` for route handler access
6. Start `_adaptive_refresh_loop` background asyncio task
7. On shutdown: cancel the background task, close the HTTP gateway, flush the decision log
