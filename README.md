# SwitchBoard

**Policy-driven execution-lane selector.**

SwitchBoard sits between ControlPlane and the coding execution backend. It inspects
each task request, evaluates a declarative policy, and selects the appropriate
execution lane — transparently to the caller.

```
ControlPlane
  │  task + lane hints
  ▼
SwitchBoard  (port 20401)
  │  evaluate policy → select lane
  ▼
Execution lane
  ├── claude_cli    (Claude Code CLI, OAuth/subscription)
  ├── codex_cli     (Codex CLI, OpenAI subscription)
  └── aider_local   (Aider + WorkStation tiny models, no API cost)
```

SwitchBoard decides **how** a task runs. It does not decide **what** to work on
(that is ControlPlane's job) and it does not perform the coding (that is kodo's job).

---

## What SwitchBoard Is Not

- **Not a provider proxy.** SwitchBoard does not forward HTTP requests to external
  LLM providers. It selects an execution lane and stops at `LaneDecision`.

- **Not a universal auth broker.** SwitchBoard does not hold or manage provider
  credentials. The `claude_cli` and `codex_cli` lanes handle their own OAuth sessions
  via their respective CLIs. The `aider_local` lane requires no external auth.

- **Not a local model host.** SwitchBoard selects the `aider_local` lane but does not
  deploy or serve the tiny models that lane uses. WorkStation owns local model
  deployment.

- **Not the decision engine.** SwitchBoard does not decide what work to do next, what
  repo to observe, or what tasks to create. That is ControlPlane's responsibility.

- **Not the workflow harness.** SwitchBoard does not define or execute multi-step
  coding workflows. That is Archon's responsibility.

---

## Execution Lanes

| Lane | Runner | Auth | Cost |
|------|--------|------|------|
| `claude_cli` | Claude Code CLI | OAuth / Claude.ai subscription | Premium |
| `codex_cli` | Codex CLI | OpenAI subscription | Premium |
| `aider_local` | Aider + WorkStation tiny models | None | Free (local) |

Lane selection is policy-driven. Changing cost/quality tradeoffs is a config edit
to `config/policy.yaml` — no code change required.

---

## Why SwitchBoard

When tasks have varying complexity and cost requirements, hardcoding lane logic in
every caller is fragile and hard to maintain. SwitchBoard externalises that decision
into a single, testable, hot-reloadable policy.

- **Lane selection as policy** — edit `config/policy.yaml` and routing changes
  immediately, no redeploy
- **Adaptive routing** — monitors error rates and latency; automatically demotes
  unhealthy lanes every 5 minutes
- **A/B experiments** — declarative traffic splitting between lanes with no code
  changes
- **Full audit trail** — every lane-selection decision is logged for debugging and
  analysis

---

## Quick Start

**Prerequisites:** Python 3.11+. No other services required for local dev/test.

```bash
# 1. Clone and install
git clone https://github.com/Velascat/SwitchBoard
cd SwitchBoard
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env — see .env.example for all available variables

# 3. Start
bash scripts/run_dev.sh

# 4. Verify
bash scripts/smoke_test.sh
```

For a detailed walkthrough including verification steps and the first real request,
see **[docs/quickstart.md](docs/quickstart.md)**.

---

## Configuration

| File | Purpose |
|------|---------|
| `config/policy.yaml` | Ordered lane-selection rules — first match wins |
| `.env` | Service binding, log level, file paths |

Each config file is heavily commented. For a first-time walkthrough see
**[docs/configuration.md](docs/configuration.md)**. For the lane-policy schema see
**[docs/policies.md](docs/policies.md)**.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health |
| `POST` | `/route` | Canonical `TaskProposal -> LaneDecision` selection |
| `POST` | `/route-plan` | Full primary/fallback/escalation routing plan |

Full endpoint reference: **[docs/api.md](docs/api.md)**

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

Or directly with `uv`:

```bash
uv run pytest -q                   # run tests
uv run ruff check src test         # lint
uv run ruff format src test        # format
```

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for repo layout, architecture boundaries,
and contribution workflow.

---

## Lane Selection (Phase 4)

SwitchBoard implements canonical proposal-based lane selection using the
platform's `TaskProposal` → `LaneDecision` contract layer.

```python
from switchboard.lane.engine import LaneSelector
from control_plane.contracts import TaskProposal

selector = LaneSelector()                    # uses default policy
decision = selector.select(proposal)         # TaskProposal → LaneDecision
explanation = selector.explain(proposal)     # for logging/audit
issues = selector.validate_policy()          # [] = policy is valid
```

See **[docs/routing.md](docs/routing.md)** for the full routing architecture and
**[docs/routing-examples.md](docs/routing-examples.md)** for concrete routing examples.

---

## Fallback and Escalation Policy (Phase 9)

SwitchBoard now owns not just primary route selection but also the full set of
alternative routes: fallbacks (cheaper paths if primary fails) and escalations
(higher-capability paths if primary is insufficient).

```python
from switchboard.lane.planner import DecisionPlanner

planner = DecisionPlanner()
plan = planner.plan(proposal)                # TaskProposal → RoutingPlan

print(plan.primary.lane)                     # "aider_local"
print(plan.fallbacks.candidates)             # eligible fallback routes
print(plan.escalations.candidates)           # eligible escalation routes
print(plan.blocked_candidates)               # blocked paths with reasons
print(plan.policy_summary)                   # "primary=aider_local/direct_local; fallbacks=1"

# Or via LaneSelector directly
plan = selector.plan_routes(proposal)        # same result
```

Key design constraints:
- `local_only` / `no_remote` labels **block** remote alternatives explicitly (not silently skip them)
- Blocked-by-constraint is distinct from blocked-by-policy; execution layers need to know which is which
- Escalation to `archon_then_kodo` requires positive justification — not offered merely because it exists
- SwitchBoard does not execute backends, run retries, or chain runs; it only expresses intent

What SwitchBoard still does **not** own:
- Backend execution (that is kodo's/Archon's job)
- Retry orchestration (that is the lane runner's job)
- Workflow step sequencing (that is Archon's job)
- Whether or when to act on a fallback/escalation (that is the execution layer's decision)

See **[WorkStation/docs/architecture/routing-fallback-escalation.md](https://github.com/Velascat/WorkStation/blob/main/docs/architecture/routing-fallback-escalation.md)** for architecture and
**[WorkStation/docs/architecture/routing-fallback-escalation-examples.md](https://github.com/Velascat/WorkStation/blob/main/docs/architecture/routing-fallback-escalation-examples.md)** for examples.

---

## Documentation

| Document | Audience |
|----------|----------|
| [docs/routing.md](docs/routing.md) | Integrator / policy author (Phase 4) |
| [docs/routing-examples.md](docs/routing-examples.md) | Policy author / debugger |
| [docs/quickstart.md](docs/quickstart.md) | First-time user |
| [docs/configuration.md](docs/configuration.md) | First-time operator |
| [docs/architecture.md](docs/architecture.md) | Contributor / deep dive |
| [docs/request-flow.md](docs/request-flow.md) | Contributor / integrator |
| [docs/api.md](docs/api.md) | Integrator |
| [docs/observability.md](docs/observability.md) | Operator |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Operator |
| [docs/policies.md](docs/policies.md) | Policy author |
| [docs/stability.md](docs/stability.md) | Evaluator |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributor |

Cross-repo architecture (component roles, ADRs, glossary):
**[WorkStation/docs/architecture/](https://github.com/Velascat/WorkStation/tree/main/docs/architecture)**

---

## Ownership boundary

SwitchBoard owns everything about canonical lane-selection decisions: lane policy,
lane-selection logic, routing evidence, and service-local configuration.

SwitchBoard does **not** own the Dockerfile or compose service definition used to
run it in the shared stack — those belong to
[WorkStation](https://github.com/Velascat/WorkStation). SwitchBoard's `.env.example`
documents the environment contract that WorkStation satisfies at runtime.

For the full platform ownership model see `WorkStation/docs/architecture/ownership.md`.

---

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).
