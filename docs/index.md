# SwitchBoard

**Execution-lane selector and policy-driven routing service.**

SwitchBoard receives a task request, classifies it (complexity, cost sensitivity,
capability requirements), evaluates a declarative policy, and selects the execution
lane that should handle it — `claude_cli`, `codex_cli`, or `aider_local`.

```
Task request
  │
  ▼
SwitchBoard  (port 20401)
  │  classify → score → select lane
  ▼
Execution lane
  ├── claude_cli   (Claude Code CLI, premium, OAuth)
  ├── codex_cli    (Codex CLI, premium, subscription)
  └── aider_local  (Aider + WorkStation tiny models, local, free)
```

The routing logic lives in a YAML file. No code changes are needed to change which
lane handles which kind of task.

---

## Why SwitchBoard

When you have multiple LLM providers and model tiers (fast/cheap, capable/expensive, local/private), embedding the routing logic in every client is fragile and hard to maintain. SwitchBoard externalises that decision into a single, testable, hot-reloadable policy.

| Capability | Description |
|------------|-------------|
| **Transparent proxy** | Clients send standard OpenAI requests and receive standard responses |
| **Policy as code** | Edit `config/policy.yaml`; routing changes immediately without redeploy |
| **Adaptive routing** | Monitors error rates and latency; automatically demotes unhealthy profiles every 5 minutes |
| **A/B experiments** | Declarative traffic splitting between profiles with no code changes |
| **Full audit trail** | Every routing decision is logged for debugging and analysis |
| **Structured output routing** | Requests requiring JSON output are directed to capable profiles |
| **Multi-factor scoring** | Ranks eligible profiles by weighted quality, cost, and latency tiers |

---

## What SwitchBoard Is Not

- **Not a universal provider proxy.** SwitchBoard selects execution lanes. It does not
  forward requests to external LLM provider APIs (OpenAI, Anthropic, etc.) on behalf of
  clients. That pattern was removed when `9router` was retired. See
  `WorkStation/docs/architecture/adr/0001-remove-9router.md`.

- **Not a credential broker.** SwitchBoard does not hold API keys for LLM providers.
  The CLI lanes (`claude_cli`, `codex_cli`) manage their own OAuth sessions. The local
  lane (`aider_local`) uses WorkStation-deployed models with no external credentials.

- **Not a recreation of 9router.** 9router was a provider-routing proxy. SwitchBoard
  is a lane-selection policy engine. The distinction matters: SwitchBoard produces a
  lane assignment; it does not proxy HTTP calls to provider APIs.

- **Not the decision engine.** SwitchBoard does not decide *what* work to do. It
  decides *how* to run a task that has already been selected by ControlPlane.

- **Not the execution runner.** SwitchBoard selects the lane and hands off. kodo and
  the lane runners do the actual coding.

---

## Quick start

**Prerequisites:** Python 3.11+.

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
