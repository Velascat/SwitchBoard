# SwitchBoard Routing Architecture

SwitchBoard is the platform's **execution-lane selector**. It accepts a canonical
`TaskProposal`, evaluates a configured routing policy, and produces a canonical
`LaneDecision`. It does not execute backends, proxy providers, host models, or
participate in the runtime request path.

---

## What SwitchBoard does

- **Accept** a `TaskProposal` from ControlPlane
- **Evaluate** routing factors from the proposal against the lane routing policy
- **Select** a lane (`aider_local`, `claude_cli`, `codex_cli`)
- **Select** a backend (`direct_local`, `kodo`, `archon_then_kodo`, `openclaw`)
- **Produce** a `LaneDecision` carrying the selection, confidence, and rationale
- **Explain** decisions in a concise, inspectable way (`LaneSelector.explain()`)
- **Validate** the routing policy configuration (`LaneSelector.validate_policy()`)

## What SwitchBoard does not do

- **Not a provider proxy.** SwitchBoard does not forward arbitrary LLM API traffic
  to external providers. It does not aggregate remote API access. It stops at
  route selection and handoff.

- **Not a model host.** If `aider_local` is selected, SwitchBoard is choosing a
  WorkStation-hosted capability. WorkStation deploys the local model services;
  SwitchBoard only decides to use them.

- **Not an execution layer.** Selecting `kodo` or `archon_then_kodo` means the lane
  runner will invoke those backends. SwitchBoard does not know or implement kodo or
  Archon execution semantics.

- **Not a task proposer.** SwitchBoard does not generate, prioritise, or filter
  TaskProposals. That is ControlPlane's responsibility.

- **Not an auth broker.** SwitchBoard does not hold or distribute backend credentials.

---

## How a TaskProposal becomes a LaneDecision

```
TaskProposal
  │
  ▼
LaneSelector.select(proposal)
  │
  ├── 1. Flatten proposal into routing signals
  │       task_type, risk_level, priority, local_only, ...
  │
  ├── 2. Evaluate policy rules (ascending priority order)
  │       First matching rule wins.
  │       Rules with excluded backends are skipped.
  │       No match → fallback policy.
  │
  ├── 3. Apply backend override rules
  │       Fine-tune backend selection within a chosen lane.
  │
  └── 4. Produce LaneDecision
          proposal_id, selected_lane, selected_backend,
          confidence, policy_rule_matched, rationale,
          alternatives_considered, decided_at
```

---

## Routing factors

The following proposal fields are extracted as routing signals:

| Signal | Source | Description |
|--------|--------|-------------|
| `task_type` | `proposal.task_type` | Broad task category (lint_fix, bug_fix, feature, …) |
| `risk_level` | `proposal.risk_level` | ControlPlane's estimate: low / medium / high |
| `priority` | `proposal.priority` | Scheduling priority |
| `execution_mode` | `proposal.execution_mode` | Execution strategy (goal, fix_pr, …) |
| `local_only` | `"local_only"` label present | Forces aider_local regardless of other factors |

Rules can match on any combination of these signals using exact-match or
`any-of` (list) semantics. The special `max_risk_level` condition enables
ceiling comparisons (`low < medium < high`).

---

## Lane and backend universe

### Lanes

| Lane | Description |
|------|-------------|
| `aider_local` | WorkStation-hosted local Aider execution. Zero marginal API cost. |
| `claude_cli` | Claude Code CLI execution. Requires OAuth. |
| `codex_cli` | Codex CLI execution. Requires subscription. |

### Backends

| Backend | Description |
|---------|-------------|
| `direct_local` | Direct invocation without a runner wrapper (aider_local lane) |
| `kodo` | kodo execution runner |
| `archon_then_kodo` | Archon workflow wrapper over kodo execution |
| `openclaw` | OpenClaw backend (selectable when policy permits) |

Backend selection is separate from lane selection. The lane determines the
execution environment; the backend determines the runner/orchestration strategy
within that environment.

---

## Policy model

Lane routing is driven by `LaneRoutingPolicy` (see `src/switchboard/lane/policy.py`).
The default policy lives in `src/switchboard/lane/defaults.py`.

```
LaneRoutingPolicy
  ├── rules: list[LaneRule]           ← ordered, priority-based
  ├── backend_rules: list[BackendRule] ← backend override within lane
  ├── fallback: FallbackPolicy         ← when no rule matches
  ├── thresholds: DecisionThresholds   ← confidence and risk ceilings
  └── excluded_backends: list[str]     ← never selected
```

**LaneRule** — matches signals from the proposal, selects a lane and backend:

```yaml
- name: local_low_risk
  priority: 20
  select_lane: aider_local
  select_backend: direct_local
  when:
    task_type: [lint_fix, documentation, simple_edit]
    max_risk_level: low
  confidence: 0.95
```

**BackendRule** — overrides backend selection within a named lane:

```yaml
- name: codex_kodo_low_risk
  lane: codex_cli
  select_backend: kodo
  when:
    risk_level: [low, medium]
```

**FallbackPolicy** — applied when no rule matches:

```yaml
fallback:
  lane: claude_cli
  backend: kodo
  rationale: "Default fallback: no policy rule matched"
```

---

## Selection is separate from execution

This is the core architectural principle:

> SwitchBoard tells the lane runner **what to use**. It does not do the work.

After SwitchBoard returns a `LaneDecision`, the lane runner (e.g. kodo) uses
`LaneDecision.selected_lane` and `LaneDecision.selected_backend` to prepare an
`ExecutionRequest` and invoke the appropriate adapter. SwitchBoard is not in
that path.

```
ControlPlane → TaskProposal → SwitchBoard → LaneDecision
                                                  │
                                                  ▼
                                           lane runner (kodo)
                                                  │
                                         ExecutionRequest
                                                  │
                                                  ▼
                                         backend adapter
```

---

## Policy transparency

Routing must be explicit and inspectable. This means:

- Every `LaneDecision` names the policy rule that fired (`policy_rule_matched`)
- Decisions can be explained via `LaneSelector.explain(proposal)`
- The full policy can be validated via `LaneSelector.validate_policy()`
- No routing depends on hidden global state or opaque heuristics

The explanation model (`DecisionExplanation`) captures:
- which rule matched
- which factors influenced the decision
- which alternatives were ruled out and why
- whether the fallback was used

---

## Entry point

```python
from switchboard.lane.engine import LaneSelector

selector = LaneSelector()                    # uses default policy
decision = selector.select(proposal)         # TaskProposal → LaneDecision
explanation = selector.explain(proposal)     # for logging/audit
issues = selector.validate_policy()          # [] = policy is valid
```

Custom policy:

```python
from switchboard.lane.policy import LaneRoutingPolicy
policy = LaneRoutingPolicy.from_dict(yaml_data)
selector = LaneSelector(policy=policy)
```
