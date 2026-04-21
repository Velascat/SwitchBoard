# Contributing to SwitchBoard

---

## Repo layout

```
SwitchBoard/
├── src/switchboard/          # all application code
│   ├── app.py                # FastAPI factory and lifespan wiring
│   ├── api/                  # HTTP layer — routes, error helpers
│   ├── services/             # business logic — classifier, selector, forwarder, ...
│   ├── domain/               # pure data types — SelectionContext, SelectionResult, ...
│   ├── adapters/             # I/O adapters — file stores, HTTP gateway, retry wrapper
│   ├── ports/                # Protocol interfaces (typing only)
│   ├── config/               # Settings (pydantic-settings) and ConfigValidator
│   └── observability/        # Logging helpers
├── test/
│   ├── unit/                 # pure unit tests (no HTTP, no filesystem)
│   └── integration/          # ASGI integration tests via httpx AsyncClient
├── config/                   # YAML config files shipped with the repo
├── docs/                     # documentation
└── scripts/                  # helper scripts (run_dev, smoke_test, inspect)
```

---

## Architecture boundaries

SwitchBoard uses a hexagonal (ports and adapters) architecture. Understanding the layers prevents putting logic in the wrong place.

### Domain layer (`domain/`)

Pure data types: `SelectionContext`, `SelectionResult`, `DecisionRecord`, `PolicyRule`, `PolicyConfig`. No HTTP, no file I/O, no external dependencies. These are the contracts between layers.

### Service layer (`services/`)

All business logic lives here. Services depend on **port interfaces**, never on concrete adapters. They receive domain objects and return domain objects.

- `RequestClassifier` — raw request + headers → `SelectionContext`
- `PolicyEngine` — `SelectionContext` + rules → matching rule
- `Selector` — orchestrates policy engine, capability registry, adaptive routing, A/B experiments, and profile scoring → `SelectionResult`
- `Forwarder` — `SelectionResult` + request body → response data + decision record
- `DecisionLogger` — persists `DecisionRecord`

Do not put HTTP parsing, JSON serialisation, or file reading in services.

### Adapter layer (`adapters/`)

Concrete implementations of port interfaces:

- `FilePolicyStore` — reads `policy.yaml`
- `FileProfileStore` — reads `profiles.yaml`
- `HttpNineRouterGateway` — sends requests to 9router
- `RetryingGateway` — wraps any gateway with retry logic

### API layer (`api/`)

Owns HTTP concerns only: parsing request bodies, returning response codes, error formatting. Route handlers should:

1. Parse / validate input
2. Delegate immediately to services
3. Format and return the response

No business logic in route handlers.

---

## Running tests

```bash
# All tests
.venv/bin/pytest -q

# Unit tests only (fast, no ASGI overhead)
.venv/bin/pytest test/unit/ -q

# Integration tests
.venv/bin/pytest test/integration/ -q

# Single file
.venv/bin/pytest test/unit/test_selector.py -v

# With coverage (requires pytest-cov)
.venv/bin/pytest --cov=switchboard --cov-report=term-missing -q
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions work without any extra decorator.

Integration tests use `httpx.AsyncClient` with `ASGITransport` — no real HTTP server is started. Services are injected via `app.state` mocks.

---

## Running locally

```bash
# Install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start (requires 9router running or won't forward, but starts fine)
bash scripts/run_dev.sh

# Smoke test
bash scripts/smoke_test.sh

# Inspect decisions
python scripts/inspect.py recent
```

---

## Linting and formatting

```bash
.venv/bin/ruff check src test
.venv/bin/ruff format src test
```

The project uses `ruff` for both linting and formatting. Line length is 100. Import sorting is enforced.

Before submitting a change, run both commands and fix any issues.

---

## Making changes

### Adding a new routing signal

1. Add the field to `SelectionContext` in `domain/selection_context.py`
2. Populate it in `RequestClassifier.classify()` in `services/classifier.py`
3. Add a `when` condition handler in `_condition_matches()` in `services/policy_engine.py`
4. Add tests in `test/unit/test_classifier.py` and `test/unit/test_policy_engine.py`

### Adding a new profile field

1. Add the field to `config/profiles.yaml` with comments
2. The field is available to services via `profile_store.get_profiles()[name]` — no code change needed unless you want to use it in routing logic

### Adding a new API endpoint

1. Add the route to the appropriate `api/routes_*.py` file (or create a new one)
2. Register the router in `app.py` `create_app()`
3. Return structured error responses using helpers from `api/errors.py` — do not raise `HTTPException`
4. Add an integration test in `test/integration/`

### Changing service wiring

Service dependencies are wired in `app.py` lifespan and injected into `app.state`. Route handlers access them via `request.app.state.<name>`. If you add a new service, follow this pattern.

---

## Phase conventions

The codebase was built in phases (1–10). Phase comments in source files (`# Phase 7 — ...`) exist to explain *why* a field was added, not as permanent documentation. When modifying code, you do not need to add new phase comments — treat the existing ones as historical context.

---

## What not to do

- Do not put business logic in `api/` route handlers
- Do not put HTTP calls or file I/O in `services/` or `domain/`
- Do not add new features in Phase 10 — this phase is documentation and externalization only
- Do not use `HTTPException` in route handlers — use the helpers in `api/errors.py` instead
- Do not skip validation: all config is validated at startup via `ConfigValidator`
