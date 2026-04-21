# Writing Policy Rules

Policy rules live in `config/policy.yaml`. They are evaluated on every request to decide which model profile to use.

---

## File structure

```yaml
version: "1"
fallback_profile: "default"

rules:
  - name: my_rule
    priority: 50
    select_profile: capable
    description: Optional explanation.
    when:
      <condition_key>: <value>

experiments: []
```

### Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | no | Schema version. Currently `"1"`. |
| `fallback_profile` | string | yes | Profile used when no rule matches. |
| `rules` | list | yes | Ordered list of rule objects. |
| `experiments` | list | no | A/B experiment definitions. Empty by default. |

---

## Rule fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique identifier used in logs and decision records. Duplicate names cause a startup error. |
| `priority` | integer | no | Evaluation order. Lower = evaluated first. Default: `100`. |
| `select_profile` | string | yes | The profile name to select when this rule matches. |
| `when` | dict | no | Key/value pairs that must all match. Empty = always matches. |
| `description` | string | no | Human-readable explanation. |

---

## Rule evaluation order

1. Rules are sorted by `priority` ascending (lowest first).
2. All `when` conditions must match (logical AND).
3. First matching rule is used — remaining rules are skipped.
4. If `X-SwitchBoard-Profile` header is present, all rules are skipped.
5. If no rule matches, `fallback_profile` is used with `rule_name = "fallback"`.

After a rule matches, these checks still apply in order:
- **A/B experiment**: the matched profile may be redirected to a treatment profile
- **Adaptive routing**: demoted profiles are bypassed for an alternative
- **Eligibility**: profiles that cannot meet capability requirements are skipped
- **Scoring**: remaining eligible profiles are ranked by quality/cost/latency

---

## Condition keys

### Task and content

| Key | Type | Description |
|-----|------|-------------|
| `task_type` | string or list | Inferred task: `"code"`, `"analysis"`, `"planning"`, `"summarization"`, `"chat"` |
| `complexity` | string or list | `"low"` (≤500 tokens, ≤3 msgs), `"medium"` (≤3k tokens, ≤8 msgs), `"high"` (>3k tokens, >8 msgs, or tools present) |
| `stream` | boolean | Whether the caller requested SSE streaming |
| `tools_present` | boolean | Whether the request includes a `tools` array |
| `requires_tools` | boolean | Same as `tools_present` — alias used by the eligibility check |
| `requires_long_context` | boolean | `true` when estimated tokens > 6,000 |
| `requires_structured_output` | boolean | `true` when `response_format.type` is `json_object` or `json_schema` |

### Token counts

| Key | Semantics |
|-----|-----------|
| `min_estimated_tokens` | `estimated_tokens >= value` |
| `max_estimated_tokens` | `estimated_tokens <= value` |
| `min_max_tokens` | requested output tokens `>= value` |
| `max_max_tokens` | requested output tokens `<= value` |

### Caller signals

| Key | Source | Example |
|-----|--------|---------|
| `model_hint` | `model` field in request body | `model_hint: ["capable", "gpt-4o"]` |
| `priority` | `X-SwitchBoard-Priority` header | `priority: "high"` |
| `tenant_id` | `X-SwitchBoard-Tenant-ID` header | `tenant_id: "acme"` |
| `cost_sensitivity` | `X-SwitchBoard-Cost-Sensitivity` header | `cost_sensitivity: "high"` or `cost_sensitivity: "low"` |
| `latency_sensitivity` | `X-SwitchBoard-Latency-Sensitivity` header | `latency_sensitivity: "high"` or `latency_sensitivity: "low"` |

### List values ("any of")

When a condition value is a list, it matches if the context attribute equals **any** element:

```yaml
when:
  task_type: ["code", "planning"]
  model_hint: ["gpt-4o", "capable", "claude-3-5-sonnet"]
```

---

## A/B experiments

Experiments are defined alongside rules and intercept matching traffic after rule evaluation.

```yaml
experiments:
  - name: capable_vs_fast_chat
    profile_a: fast          # control — majority of traffic
    profile_b: capable       # treatment — split_percent % of traffic
    split_percent: 10
    enabled: true
    applies_to_rules:
      - default_short_request   # only intercept this rule; empty = all rules
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique identifier recorded in decision logs. |
| `profile_a` | string | yes | Control profile. Must differ from `profile_b`. |
| `profile_b` | string | yes | Treatment profile. |
| `split_percent` | integer | yes | Percentage routed to `profile_b` (0–100). |
| `enabled` | boolean | no | Set to `false` to pause without removing the config. Default: `true`. |
| `applies_to_rules` | list | no | Restrict to specific rule names. Empty = all rules. |

Assignment is deterministic: the same `X-Request-ID` always lands in the same bucket.

---

## Example rules

### Route code tasks to the capable model

```yaml
- name: coding_task
  priority: 35
  select_profile: capable
  when:
    task_type: "code"
```

### Route large context to capable

```yaml
- name: large_context
  priority: 50
  select_profile: capable
  when:
    min_estimated_tokens: 4096
```

### Keep cost-sensitive short requests on the fast model

```yaml
- name: cost_sensitive
  priority: 65
  select_profile: fast
  when:
    cost_sensitivity: "high"
    complexity: ["low", "medium"]
```

### Route a specific tenant to local

```yaml
- name: tenant_batch_local
  priority: 25
  select_profile: local
  when:
    tenant_id: "internal-batch"
    priority: "low"
```

### Catch-all fast path

```yaml
- name: default_short
  priority: 100
  select_profile: fast
  when:
    max_estimated_tokens: 4096
```

---

## Troubleshooting

Check `GET /admin/decisions/recent` to see which rule triggered for recent requests.
Each decision record includes `rule_name` — if it shows `"fallback"`, no rule matched.

See [troubleshooting.md](troubleshooting.md) for more.
