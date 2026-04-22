# Routing Examples

Concrete examples showing how proposals of different shapes route through the
default policy. Use these to understand routing tendencies and to calibrate
custom policy rules.

---

## Example 1 — local-safe coding task → `aider_local`

**Proposal:**
```json
{
  "task_type": "lint_fix",
  "risk_level": "low",
  "priority": "normal",
  "labels": []
}
```

**Rule matched:** `local_low_risk` (priority 20)

```
Condition: task_type IN [lint_fix, documentation, simple_edit] → ✓
Condition: max_risk_level=low (risk_level=low ≤ low) → ✓
```

**Decision:**
```json
{
  "selected_lane": "aider_local",
  "selected_backend": "direct_local",
  "confidence": 0.95,
  "policy_rule_matched": "local_low_risk",
  "rationale": "task_type=lint_fix, risk_level=low → lane=aider_local, backend=direct_local [rule: local_low_risk]"
}
```

**Why local:** This task is bounded, low-risk, and acceptable for tiny model
execution. Zero marginal API cost.

---

## Example 2 — medium implementation task → `kodo`

**Proposal:**
```json
{
  "task_type": "bug_fix",
  "risk_level": "medium",
  "priority": "normal",
  "labels": []
}
```

**Rule matched:** `medium_implementation` (priority 30)

```
Condition: task_type IN [bug_fix, test_write, dependency_update] → ✓
Condition: risk_level IN [low, medium] → ✓
```

**Decision:**
```json
{
  "selected_lane": "claude_cli",
  "selected_backend": "kodo",
  "confidence": 0.90,
  "policy_rule_matched": "medium_implementation",
  "rationale": "task_type=bug_fix, risk_level=medium → lane=claude_cli, backend=kodo [rule: medium_implementation]"
}
```

**Why claude_cli + kodo:** Bug fixes at medium risk require a capable model.
kodo provides execution support without Archon overhead.

---

## Example 3 — structured premium workflow → `archon_then_kodo`

**Proposal:**
```json
{
  "task_type": "refactor",
  "risk_level": "high",
  "priority": "high",
  "labels": []
}
```

**Rule matched:** `premium_structured` (priority 40)

```
Condition: task_type IN [refactor, feature] → ✓
Condition: risk_level IN [medium, high] → ✓
```

**Decision:**
```json
{
  "selected_lane": "claude_cli",
  "selected_backend": "archon_then_kodo",
  "confidence": 0.85,
  "policy_rule_matched": "premium_structured",
  "rationale": "task_type=refactor, risk_level=high → lane=claude_cli, backend=archon_then_kodo [rule: premium_structured]"
}
```

**Why archon_then_kodo:** High-risk refactor benefits from Archon's structured
workflow wrapper over raw kodo execution — multi-step planning, validation gates.

---

## Example 4 — explicit policy exclusion

**Scenario:** `direct_local` is excluded from the policy (e.g. local models are
down). A lint_fix proposal that would normally go to `aider_local` must
reroute.

**Config:**
```yaml
excluded_backends:
  - direct_local
```

**Proposal:**
```json
{
  "task_type": "lint_fix",
  "risk_level": "low",
  "labels": []
}
```

**Rule evaluation:**
```
local_low_risk (priority 20):
  conditions match → ✓
  select_backend=direct_local → EXCLUDED → skip

medium_implementation (priority 30):
  task_type=lint_fix NOT IN [bug_fix, test_write, dependency_update] → ✗

local_catchall (priority 60):
  task_type=lint_fix IN [lint_fix, documentation, simple_edit] → ✓
  select_backend=direct_local → EXCLUDED → skip

No rule matched → fallback
```

**Decision:**
```json
{
  "selected_lane": "claude_cli",
  "selected_backend": "kodo",
  "confidence": 0.7,
  "policy_rule_matched": null,
  "rationale": "Default fallback: no policy rule matched; using premium lane with kodo."
}
```

**Why:** When the local backend is excluded, no local rule can fire. The system
falls back to the premium lane rather than failing hard.

---

## Example 5 — force_local_only label

**Proposal:**
```json
{
  "task_type": "feature",
  "risk_level": "high",
  "labels": ["local_only"]
}
```

Even though `feature` + `high` would normally escalate to the premium lane,
the `local_only` label forces routing to `aider_local`.

**Rule matched:** `force_local_only` (priority 10)

```
Condition: local_only=true → ✓ (label present)
```

**Decision:**
```json
{
  "selected_lane": "aider_local",
  "selected_backend": "direct_local",
  "confidence": 1.0,
  "policy_rule_matched": "force_local_only",
  "rationale": "task_type=feature, risk_level=high → lane=aider_local, backend=direct_local [rule: force_local_only]"
}
```

**Use case:** Integration tests, local development workflows, or budget
constraints that require all execution to stay on local hardware.

---

## Example 6 — no matching rule (pure fallback)

**Proposal:**
```json
{
  "task_type": "unknown",
  "risk_level": "low",
  "labels": []
}
```

No rule in the default policy matches `task_type=unknown`.

**Decision:**
```json
{
  "selected_lane": "claude_cli",
  "selected_backend": "kodo",
  "confidence": 0.7,
  "policy_rule_matched": null,
  "rationale": "Default fallback: no policy rule matched; using premium lane with kodo."
}
```

**Why:** Unknown task types are safest routed to a capable premium lane. The
fallback is documented and explicit, not silent.

---

## Decision explanation example

```python
selector = LaneSelector()
explanation = selector.explain(proposal)

# explanation.summary:
# "lane=aider_local, backend=direct_local, rule=local_low_risk"

# explanation.factors:
# [
#   DecisionFactor(name="task_type", value="lint_fix", influence="selected_lane"),
#   DecisionFactor(name="risk_level", value="low", influence="selected_lane"),
# ]

# explanation.alternatives_ruled_out:
# [
#   "claude_cli (rule 'medium_implementation' conditions not met)",
#   "claude_cli (rule 'premium_structured' conditions not met)",
# ]
```

---

## Reading the routing table

The full default routing tendencies can be summarised as:

| Task type | Risk level | → Lane | → Backend |
|-----------|-----------|--------|-----------|
| lint_fix, documentation, simple_edit | low | aider_local | direct_local |
| bug_fix, test_write, dependency_update | low, medium | claude_cli | kodo |
| refactor, feature | medium, high | claude_cli | archon_then_kodo |
| any | high | claude_cli | kodo (escalation) |
| (any with local_only label) | any | aider_local | direct_local |
| (no match) | any | claude_cli | kodo (fallback) |

These are policy tendencies. Rules are evaluated in priority order and the
first match wins. Custom policy files can alter any of these tendencies.
