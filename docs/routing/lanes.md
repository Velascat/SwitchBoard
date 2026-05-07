# Lanes Reference

A **lane** is a named execution path that SwitchBoard selects based on task attributes. Each lane has a canonical backend that performs the actual work.

## Lane inventory

| Lane | Backend | Cost | Capability |
|------|---------|------|------------|
| `aider_local` | `aider_local` | Free | CPU-only Aider via local Ollama |
| `claude_cli` | `kodo` | Medium | Claude-powered Kodo executor |
| `claude_cli` | `archon_then_kodo` | High | Archon workflow + Kodo execution |
| `codex_cli` | `kodo` | Medium | Codex routing, Kodo execution |

## aider_local

**When selected:** Low-risk, bounded tasks eligible for local execution.

Default routing rules (from `switchboard/lane/defaults.py`):

| Priority | Rule | Condition | Backend |
|----------|------|-----------|---------|
| 10 | `force_local_only` | `local_only` label | `aider_local` |
| 20 | `local_low_risk` | `task_type` ∈ {lint_fix, documentation, simple_edit} AND `max_risk_level=low` | `aider_local` |
| 60 | `local_catchall` | `task_type` ∈ {lint_fix, documentation, simple_edit} | `aider_local` |

**Fallback:** If Ollama is unavailable, alternatives include `claude_cli + kodo` (see `local_to_remote_fallback` in defaults).

**Infrastructure:** Requires a running Ollama instance at `http://localhost:11434` with `qwen2.5-coder:3b` pulled. See [WorkStation docs](../../../WorkStation/docs/local_aider_lane.md).

## claude_cli

**When selected:** Medium-to-high complexity tasks, or anything not matched by a local rule.

Default routing rules:

| Priority | Rule | Condition | Backend |
|----------|------|-----------|---------|
| 30 | `medium_implementation` | `task_type` ∈ {bug_fix, test_write, dependency_update} AND risk ∈ {low, medium} | `kodo` |
| 40 | `premium_structured` | `task_type` ∈ {refactor, feature} AND risk ∈ {medium, high} | `archon_then_kodo` |
| 50 | `high_risk_escalation` | `risk_level=high` | `kodo` |

**Fallback (global):** `claude_cli + kodo` — used when no rule matches.

## Routing policy

Policies are loaded from YAML and evaluated in ascending priority order (lower number = checked first). The first rule that matches wins. See `switchboard/lane/policy.py` for the schema and `switchboard/lane/defaults.py` for the built-in policy.

To override routing for a deployment, supply a custom policy YAML to `LaneSelector`.
