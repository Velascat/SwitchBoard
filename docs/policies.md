# Writing Policy Rules

Policy rules live in `config/policy.yaml`.  They are evaluated on every request
to decide which model profile to use.

---

## File Structure

```yaml
version: "1"
fallback_profile: "default"

rules:
  - name: my_rule
    priority: 50
    profile: capable
    description: Optional explanation.
    conditions:
      <condition_key>: <value>
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | no | Schema version. Currently `"1"`. |
| `fallback_profile` | string | yes | Profile to use when no rule matches. |
| `rules` | list | yes | Ordered list of rule objects. |

---

## Rule Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique identifier used in logs and decision records. |
| `priority` | integer | no | Evaluation order. Lower = evaluated first. Default: `100`. |
| `profile` | string | yes | The profile name to select when this rule matches. |
| `conditions` | dict | no | Key/value pairs that must all match. Empty = always matches. |
| `description` | string | no | Human-readable explanation. |

---

## Rule Evaluation Order

1. Rules are sorted by `priority` in ascending order (lowest number first).
2. For each rule, **all** conditions must match (logical AND).
3. The first matching rule is used — subsequent rules are not evaluated.
4. If `X-SwitchBoard-Profile` header is present, all rules are skipped.
5. If no rule matches, `fallback_profile` is used with `rule_name = "fallback"`.

---

## Condition Keys

### Direct Context Attributes

These keys map directly to fields on `SelectionContext`:

| Key | Type | Example |
|-----|------|---------|
| `stream` | boolean | `stream: true` |
| `tools_present` | boolean | `tools_present: true` |
| `model_hint` | string or list | `model_hint: "capable"` or `model_hint: ["gpt-4o", "capable"]` |
| `priority` | string or list | `priority: "high"` |
| `tenant_id` | string or list | `tenant_id: ["acme", "initech"]` |

### Numeric Range Conditions

| Key | Semantics | Example |
|-----|-----------|---------|
| `min_estimated_tokens` | `estimated_tokens >= value` | `min_estimated_tokens: 4096` |
| `max_estimated_tokens` | `estimated_tokens <= value` | `max_estimated_tokens: 512` |
| `min_max_tokens` | `max_tokens >= value` (if set) | `min_max_tokens: 2048` |
| `max_max_tokens` | `max_tokens <= value` (if set) | `max_max_tokens: 256` |

### List Values ("Any Of")

When a condition value is a YAML list, the condition matches if the context
attribute equals **any** element of the list:

```yaml
conditions:
  model_hint: ["gpt-4o", "capable", "claude-3-5-sonnet"]
```

---

## Example Rules

### Route all tool-use requests to the capable model

```yaml
- name: tool_use
  priority: 30
  profile: capable
  conditions:
    tools_present: true
```

### Route large context requests to capable

```yaml
- name: large_context
  priority: 50
  profile: capable
  conditions:
    min_estimated_tokens: 4096
```

### Route specific tenant to local model

```yaml
- name: tenant_internal_local
  priority: 25
  profile: local
  conditions:
    tenant_id: "internal-batch"
    priority: "low"
```

### Catch-all fast path for short requests

```yaml
- name: default_short
  priority: 100
  profile: fast
  conditions:
    max_estimated_tokens: 4096
```

---

## Reloading Policy

The policy is loaded once at startup and cached.  To reload without restarting:
- Call `PolicyEngine.reload()` via the admin API (future feature).
- Restart the SwitchBoard process.

---

## Troubleshooting

Check `GET /admin/decisions/recent` to see which rule triggered for recent requests.
Each decision record includes `rule_name` — if it shows `"fallback"`, no rule matched.
