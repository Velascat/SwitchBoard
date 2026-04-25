# Contributing to SwitchBoard

---

## Repo layout

```
SwitchBoard/
├── src/switchboard/          # all application code
│   ├── app.py                # FastAPI factory and lifespan wiring
│   ├── api/                  # HTTP layer — canonical route + health endpoints
│   ├── lane/                 # canonical lane-routing policy and selector logic
│   ├── services/             # runtime support services such as decision logging
│   ├── domain/               # pure data types — DecisionRecord, PolicyRule, ...
│   ├── adapters/             # I/O adapters — decision sink + policy loading helpers
│   ├── ports/                # Protocol interfaces (typing only)
│   ├── config/               # Settings (pydantic-settings)
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

Pure data types: `DecisionRecord`, `PolicyRule`, `PolicyConfig`. No HTTP, no file I/O, no external dependencies. These are the contracts between layers.

### Service layer (`services/`)

All business logic lives here. Services depend on **port interfaces**, never on concrete adapters. They receive domain objects and return domain objects.

- `LaneSelector` — canonical `TaskProposal` → `LaneDecision`
- `DecisionPlanner` — primary route + fallbacks + escalations → `RoutingPlan`
- `DecisionLogger` — persists `DecisionRecord`

Do not put HTTP parsing, JSON serialisation, or file reading in services.

### Adapter layer (`adapters/`)

Concrete implementations of runtime persistence:

- `JsonlDecisionSink` — writes canonical routing evidence to JSONL

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
.venv/bin/pytest test/unit/test_lane_engine.py -v

# With coverage (requires pytest-cov)
.venv/bin/pytest --cov=switchboard --cov-report=term-missing -q
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions work without any extra decorator.

Integration tests use `httpx.AsyncClient` with `ASGITransport` — no real HTTP server is started. Services are injected via `app.state` mocks.

---

## Running locally

```bash
# Install (uv preferred — respects uv.lock for reproducible installs)
uv sync
# or with pip:
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start selector runtime
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

1. Add the field to the canonical `TaskProposal` contract when it belongs in the shared proposal boundary
2. Plumb it into `LaneSelector` / routing policy evaluation
3. Add tests in the routing and policy suites

### Changing lane policy

1. Edit `config/policy.yaml`
2. Keep rule names, lane names, and backend names aligned with the canonical contracts
3. Add or update tests in the lane routing suites

### Adding a new API endpoint

1. Add the route to the appropriate `api/routes_*.py` file (or create a new one)
2. Register the router in `app.py` `create_app()`
3. Return structured error responses using helpers from `api/errors.py` — do not raise `HTTPException`
4. Add an integration test in `test/integration/`

### Changing service wiring

Service dependencies are wired in `app.py` lifespan and injected into `app.state`. Route handlers access them via `request.app.state.<name>`. If you add a new service, follow this pattern.

---

## Commit Style

| Prefix | Use for |
|--------|---------|
| `feat:` | new user-facing feature |
| `fix:` | bug fix |
| `refactor:` | internal restructure, no behavior change |
| `docs:` | documentation only |
| `test:` | test additions or fixes |
| `chore:` | tooling, CI, dependency updates |

---

## Code of Conduct

This project follows the [Contributor Covenant v2.1](CODE_OF_CONDUCT.md). By participating you agree to uphold its standards.

---

## What not to do

- Do not put business logic in `api/` route handlers
- Do not put HTTP calls or file I/O in `services/` or `domain/`
- Do not use `HTTPException` in route handlers — use the helpers in `api/errors.py` instead
- Do not reintroduce profile/model-routing code beside the canonical lane router
