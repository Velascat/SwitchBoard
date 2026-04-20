# SwitchBoard Architecture

## Overview

SwitchBoard follows a **hexagonal architecture** (also known as "ports and adapters").
The core domain has no dependencies on HTTP, filesystems, or any external library.
All I/O is handled by adapters that implement well-defined port interfaces.

---

## Layer Diagram

```
╔═══════════════════════════════════════════════════════════════════════╗
║                         HTTP Clients                                  ║
║          (curl, SDKs, any OpenAI-compatible client)                  ║
╚══════════════════════════════╦════════════════════════════════════════╝
                               │ POST /v1/chat/completions
                               │ GET  /v1/models
                               │ GET  /health
                               │ GET  /admin/decisions/recent
╔══════════════════════════════▼════════════════════════════════════════╗
║                        API Layer (FastAPI)                            ║
║                                                                       ║
║   routes_chat.py   routes_models.py   routes_health.py               ║
║   routes_admin.py                                                     ║
╚══════════════════════════════╦════════════════════════════════════════╝
                               │ calls
╔══════════════════════════════▼════════════════════════════════════════╗
║                       Service Layer                                   ║
║                                                                       ║
║   RequestClassifier ──► Selector ──► Forwarder                       ║
║                           │                                           ║
║                    ┌──────┴──────┐                                   ║
║                    │             │                                    ║
║              PolicyEngine  CapabilityRegistry                        ║
║                                                                       ║
║   DecisionLog                                                         ║
╚════════╦══════════════════════════════════╦═══════════════════════════╝
         │ Port interfaces                  │
╔════════▼══════════════╗   ╔══════════════▼════════════════════════════╗
║     Domain Layer      ║   ║          Adapter Layer                    ║
║                       ║   ║                                           ║
║   SelectionContext    ║   ║  FilePolicyStore   → reads policy.yaml   ║
║   SelectionResult     ║   ║  FileProfileStore  → reads profiles.yaml ║
║   DecisionRecord      ║   ║  HttpNineRouterGateway → HTTP to 9router ║
║   PolicyRule          ║   ║                                           ║
║   PolicyConfig        ║   ╚═══════════════════════════════════════════╝
╚═══════════════════════╝
```

---

## Layers and Responsibilities

### API Layer (`src/switchboard/api/`)

- Owns all HTTP concerns: parsing request bodies, setting response codes, CORS.
- Reads from `request.app.state` to access injected service instances.
- Contains no business logic — delegates immediately to the service layer.

| Module | Responsibility |
|--------|---------------|
| `routes_chat.py` | Orchestrates classify → select → forward pipeline |
| `routes_models.py` | Lists available profiles as OpenAI model objects |
| `routes_health.py` | Checks local and downstream (9router) health |
| `routes_admin.py` | Exposes recent decision records for debugging |

### Service Layer (`src/switchboard/services/`)

- Contains all business logic.
- Services depend on **port interfaces**, not concrete adapters.
- No HTTP, no file I/O — only pure Python.

| Service | Responsibility |
|---------|---------------|
| `RequestClassifier` | Converts raw request + headers → `SelectionContext` |
| `PolicyEngine` | Evaluates ordered rules against a context |
| `CapabilityRegistry` | Resolves profile name → downstream model string |
| `Selector` | Orchestrates PolicyEngine + CapabilityRegistry |
| `Forwarder` | Sends the rewritten request to 9router, measures latency |
| `DecisionLog` | Appends decision records to JSONL + in-memory buffer |

### Domain Layer (`src/switchboard/domain/`)

- Pure data models with no behaviour beyond validation.
- `SelectionContext` (§8.1), `SelectionResult` (§8.2), `DecisionRecord` (§8.3).
- `PolicyRule`, `PolicyConfig` — typed representations of policy YAML.

### Port Layer (`src/switchboard/ports/`)

- Python `Protocol` classes (structural typing).
- Define the contracts that adapters must implement.
- Allow the service layer to be tested with simple doubles.

| Port | Implemented by |
|------|---------------|
| `PolicyStore` | `FilePolicyStore` |
| `ProfileStore` | `FileProfileStore` |
| `ModelGateway` | `HttpNineRouterGateway` |
| `DecisionSink` | `DecisionLog` |

### Adapter Layer (`src/switchboard/adapters/`)

- Concrete implementations of ports.
- Allowed to import `httpx`, `yaml`, `pathlib`, etc.
- Thin — translate between the port interface and the external resource.

### Observability (`src/switchboard/observability/`)

- `logging.py` — structured log configuration.
- `metrics.py` — in-process counter stubs (Prometheus-compatible API shape).
- `tracing.py` — no-op OpenTelemetry-compatible tracer stubs.

---

## Dependency Rule

Dependencies flow **inward only**:

```
API → Services → Domain
Adapters → Ports ← Services
```

The domain layer imports nothing from outside itself.
The service layer imports domain + ports.
The API and adapter layers import services + domain.
Nothing imports the API layer except `app.py`.

---

## Application Wiring

`app.py::lifespan()` is the composition root.  It:
1. Loads `Settings` from environment.
2. Instantiates all adapters (stores, gateway).
3. Instantiates all services, injecting adapters via ports.
4. Attaches everything to `app.state` for use by route handlers.
