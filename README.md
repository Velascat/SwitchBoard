# SwitchBoard

**Policy-driven model selection service.**

SwitchBoard sits between API clients and [9router](https://github.com/Velascat/9router), inspecting every chat-completion request, evaluating a declarative policy, and routing the request to the most appropriate downstream model profile — all transparently to the caller.

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

---

## 5.3 Design Overview

### Problem

When multiple LLM providers and model tiers are available (e.g., a cheap fast model, a capable expensive model, a local private model), deciding which model to use for each request is a cross-cutting concern. Embedding that logic in every client is fragile, duplicated, and hard to change.

### Solution

SwitchBoard externalises model selection into a **policy engine** backed by a **declarative YAML policy file**. Clients send standard OpenAI-compatible requests and receive standard OpenAI-compatible responses. SwitchBoard intercepts each request, classifies it into a `SelectionContext`, evaluates the policy rules in priority order, picks a **profile**, resolves the profile to a concrete downstream model name via the **capability registry**, then forwards the (potentially rewritten) request to 9router.

Every routing decision is recorded to a **decision log** (JSONL) for audit, debugging, and offline analysis.

### Key Design Principles

| Principle | Implementation |
|-----------|---------------|
| OpenAI-compatible surface | `/v1/chat/completions`, `/v1/models` |
| Policy as code | `config/policy.yaml` — no redeploy required |
| Hexagonal architecture | Ports & adapters; core domain never touches HTTP or files directly |
| Transparent proxy | Upstream receives the full provider response unmodified |
| Zero-trust headers | `X-SwitchBoard-*` headers accepted but validated |

### Component Map

```
┌─────────────────────────────────────────────────────┐
│                    SwitchBoard                       │
│                                                     │
│  API Layer          Domain / Services               │
│  ──────────         ─────────────────               │
│  routes_chat   ───► RequestClassifier               │
│  routes_models │    Selector                        │
│  routes_health │      PolicyEngine                  │
│  routes_admin  │      CapabilityRegistry             │
│                └──► Forwarder ──────────────────────┼──► 9router
│                     DecisionLog                     │
│                                                     │
│  Adapters                   Ports (Protocols)       │
│  ────────                   ──────────────────      │
│  HttpNineRouterGateway       ModelGateway            │
│  FilePolicyStore             PolicyStore             │
│  FileProfileStore            ProfileStore            │
│                              DecisionSink            │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- A running [9router](https://github.com/Velascat/9router) instance (default: `http://localhost:20128`)

### Install

```bash
git clone https://github.com/Velascat/SwitchBoard
cd SwitchBoard
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Configure

```bash
cp .env.example .env
# Edit .env as needed
```

Review and customise:
- `config/policy.yaml` — routing rules
- `config/profiles.yaml` — model profiles
- `config/capabilities.yaml` — capability registry

### Run

```bash
# Unix
bash scripts/run_dev.sh

# Windows PowerShell
pwsh scripts/run_dev.ps1

# Or directly:
switchboard
```

### Smoke test

```bash
bash scripts/smoke_test.sh
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config/policy.yaml` | Ordered list of policy rules; first match wins |
| `config/profiles.yaml` | Named model profiles (capability requirements, preferred model) |
| `config/capabilities.yaml` | Maps profile names to concrete downstream model identifiers |

See `docs/policies.md`, `docs/profiles.md`, and `docs/capabilities.md` for full schema documentation.

---

## API Reference

See `docs/api.md` for the full endpoint reference.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service + 9router reachability |
| `GET` | `/v1/models` | OpenAI-style model list from profiles |
| `POST` | `/v1/chat/completions` | Chat completion proxy with policy routing |
| `GET` | `/admin/decisions/recent` | Last N decision log records |

---

## Development

```bash
# Run tests
pytest

# Lint / format
ruff check src test
ruff format src test
```

---

## Architecture

See `docs/architecture.md` for the full hexagonal architecture diagram and layer responsibilities.

---

## License

MIT — see [LICENSE](LICENSE).
