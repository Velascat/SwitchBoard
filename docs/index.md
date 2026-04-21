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

Any OpenAI-compatible client works without modification. The routing logic lives in a YAML file — no code changes needed to change routing behaviour.

---

## Why SwitchBoard

When you have multiple LLM providers and model tiers (fast/cheap, capable/expensive, local/private), embedding the routing logic in every client is fragile and hard to maintain. SwitchBoard externalises that decision into a single, testable, hot-reloadable policy.

| Capability | Description |
|------------|-------------|
| **Transparent proxy** | Clients send standard OpenAI requests and receive standard responses |
| **Policy as code** | Edit `config/policy.yaml`; routing changes immediately without redeploy |
| **Adaptive routing** | Monitors error rates and latency; automatically demotes unhealthy profiles |
| **A/B experiments** | Declarative traffic splitting between profiles with no code changes |
| **Full audit trail** | Every routing decision is logged for debugging and analysis |
| **Structured output routing** | Requests requiring JSON output are directed to capable profiles |
| **Multi-factor scoring** | Ranks eligible profiles by weighted quality, cost, and latency tiers |

---

## Quick start

**Prerequisites:** Python 3.11+ and a running [9router](https://github.com/Velascat/9router) instance.

```bash
git clone https://github.com/Velascat/SwitchBoard
cd SwitchBoard
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env           # set ROUTER9_BASE_URL if needed
bash scripts/run_dev.sh
bash scripts/smoke_test.sh     # verify it works
```

For the complete step-by-step guide with expected output at each step, see the [Quickstart](quickstart.md).

---

## Documentation map

| Document | Audience |
|----------|----------|
| [Quickstart](quickstart.md) | New user — first-time setup and verification |
| [Configuration](configuration.md) | Operator — env vars, policy rules, profiles |
| [API Reference](api.md) | Integrator — all endpoints with request/response schemas |
| [Architecture](architecture.md) | Contributor — layer diagram, service responsibilities |
| [Request Flow](request-flow.md) | Contributor — step-by-step request lifecycle with error handling |
| [Observability](observability.md) | Operator — decision log format, admin API, adaptive monitoring |
| [Troubleshooting](troubleshooting.md) | Operator — common failure cases with fixes |
| [Policies](policies.md) | Policy author — rule conditions reference |
| [Profiles](profiles.md) | Policy author — profile fields reference |
| [Capabilities](capabilities.md) | Policy author — capability registry schema |
| [Stability](stability.md) | Evaluator — what is stable, what is experimental, known gaps |
| [Roadmap](roadmap.md) | Everyone — what is delivered, what is planned |
