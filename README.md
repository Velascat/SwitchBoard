# SwitchBoard

**Policy-driven model selection service.**

SwitchBoard sits between API clients and [9router](https://github.com/Velascat/9router), inspecting every chat-completion request, evaluating a declarative policy, and routing the request to the most appropriate downstream model profile — transparently to the caller.

```
Client
  │  POST /v1/chat/completions
  ▼
SwitchBoard  (port 20401)
  │  classify → select → forward
  ▼
9router      (port 20128)
  │  provider routing
  ▼
LLM Provider (OpenAI, Anthropic, local, …)
```

Any OpenAI-compatible client works without modification. The model selection logic lives in a YAML policy file — no code changes needed to change routing behaviour.

---

## Why SwitchBoard

When you have multiple LLM providers and model tiers (fast/cheap, capable/expensive, local/private), embedding the routing logic in every client is fragile and hard to maintain. SwitchBoard externalises that decision into a single, testable, hot-reloadable policy.

- **Transparent proxy** — clients send standard OpenAI requests and receive standard responses
- **Policy as code** — edit `config/policy.yaml` and routing changes immediately, no redeploy
- **Adaptive routing** — monitors error rates and latency; automatically demotes unhealthy profiles every 5 minutes
- **A/B experiments** — declarative traffic splitting between profiles with no code changes
- **Full audit trail** — every routing decision is logged for debugging and analysis

---

## Quick Start

**Prerequisites:** Python 3.11+ and a running [9router](https://github.com/Velascat/9router) instance.

```bash
# 1. Clone and install
git clone https://github.com/Velascat/SwitchBoard
cd SwitchBoard
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env to set ROUTER9_BASE_URL if 9router is not on localhost:20128

# 3. Start
bash scripts/run_dev.sh

# 4. Verify
bash scripts/smoke_test.sh
```

For a detailed walkthrough including verification steps and the first real request, see **[docs/quickstart.md](docs/quickstart.md)**.

---

## Configuration

| File | Purpose |
|------|---------|
| `config/policy.yaml` | Ordered routing rules — first match wins |
| `config/profiles.yaml` | Named model profiles with capability metadata |
| `config/capabilities.yaml` | Downstream model capability descriptions |
| `.env` | Service binding, log level, file paths, 9router URL |

Each config file is heavily commented. For a first-time walkthrough see **[docs/configuration.md](docs/configuration.md)**. For full schema reference see [docs/policies.md](docs/policies.md), [docs/profiles.md](docs/profiles.md), and [docs/capabilities.md](docs/capabilities.md).

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health + 9router reachability |
| `GET` | `/v1/models` | OpenAI-style model list derived from profiles |
| `POST` | `/v1/chat/completions` | Chat completion proxy with policy routing |
| `GET` | `/admin/decisions/recent` | Last N routing decisions |
| `GET` | `/admin/decisions/{request_id}` | Single decision lookup by correlation ID |
| `GET` | `/admin/summary` | Aggregated stats over last N decisions |
| `GET` | `/admin/adaptive` | Adaptive routing adjustment state |

Full endpoint reference: **[docs/api.md](docs/api.md)**

---

## Inspect routing decisions

```bash
# Last 20 decisions
python scripts/inspect.py recent

# Aggregated stats over last 100 decisions
python scripts/inspect.py summary

# Single decision by request ID
python scripts/inspect.py show <request_id>
```

---

## Development

```bash
make install      # create .venv and install with dev dependencies
make test         # run full test suite
make smoke        # smoke-test a running instance
make lint         # ruff check
make fmt          # ruff format
make docs-check   # verify all doc-referenced files exist
```

Or directly:

```bash
.venv/bin/pytest -q                   # run tests
.venv/bin/ruff check src test         # lint
.venv/bin/ruff format src test        # format
```

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for repo layout, architecture boundaries, and contribution workflow.

---

## Documentation

| Document | Audience |
|----------|----------|
| [docs/quickstart.md](docs/quickstart.md) | First-time user |
| [docs/configuration.md](docs/configuration.md) | First-time operator |
| [docs/architecture.md](docs/architecture.md) | Contributor / deep dive |
| [docs/request-flow.md](docs/request-flow.md) | Contributor / integrator |
| [docs/api.md](docs/api.md) | Integrator |
| [docs/observability.md](docs/observability.md) | Operator |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Operator |
| [docs/policies.md](docs/policies.md) | Policy author |
| [docs/profiles.md](docs/profiles.md) | Policy author |
| [docs/capabilities.md](docs/capabilities.md) | Policy author |
| [docs/stability.md](docs/stability.md) | Evaluator |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributor |

---

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).
