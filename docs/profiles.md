# Model Profiles

Profiles are named abstractions that decouple policy rules from specific downstream model identifiers. A rule selects a **profile**; the **capability registry** resolves that profile to the actual model string sent to 9router.

---

## Profile file: `config/profiles.yaml`

```yaml
version: "1"

profiles:
  <profile_name>:
    downstream_model: gpt-4o-mini
    description: "Human-readable description."
    tags: [tag1, tag2]
    preferred_provider: openai
    max_context_tokens: 128000
    supports_tools: true
    supports_vision: false
    supports_structured_output: true
    cost_tier: low
    cost_weight: 1.0
    latency_tier: low
    quality_tier: medium
```

### Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `downstream_model` | string | yes | Concrete model identifier forwarded to 9router. |
| `description` | string | no | Human-readable explanation of the profile's purpose. |
| `tags` | list[string] | no | Free-form capability tags. |
| `preferred_provider` | string | no | Hint to 9router for provider selection (`openai`, `anthropic`, `ollama`, …). |
| `max_context_tokens` | integer | no | Maximum context window supported by this profile. |
| `supports_tools` | boolean | no | Whether the model reliably handles function calling. Default: `true`. |
| `supports_vision` | boolean | no | Whether the model accepts image inputs. Default: `false`. |
| `supports_structured_output` | boolean | no | Whether the model reliably produces JSON output when `response_format` is set. Profiles where this is `false` are excluded when the request requires structured output. Default: `true`. |
| `cost_tier` | string | no | Relative cost: `low`, `medium`, or `high`. Used by the profile scorer when `cost_weight` is absent. |
| `cost_weight` | float | no | Precise relative cost for multi-factor scoring. Overrides `cost_tier`. Higher = more expensive. |
| `latency_tier` | string | no | Relative latency: `low` (fast response), `medium`, or `high` (slow). |
| `quality_tier` | string | no | Relative output quality: `low`, `medium`, or `high`. Used by the profile scorer. |

---

## Multi-factor scoring

When multiple profiles are eligible for a request, `ProfileScorer` ranks them using a weighted combination of quality, cost, and latency tiers.

Default weights: `quality=4.0, cost=1.0, latency=1.0` — quality dominates by default.

Weights shift automatically based on caller signals:

| Header | Value | Effect |
|--------|-------|--------|
| `X-SwitchBoard-Cost-Sensitivity` | `high` | `cost=4.0, quality=1.0` — cost-optimal profile wins |
| `X-SwitchBoard-Cost-Sensitivity` | `low` | `cost=0.5, quality=3.0` — quality preference restored, cost nearly ignored |
| `X-SwitchBoard-Latency-Sensitivity` | `high` | `latency=6.0` — latency dominates over quality and cost |
| `X-SwitchBoard-Latency-Sensitivity` | `low` | `latency=0.5` — latency de-prioritised, quality leads |

When no sensitivity header is set the defaults apply (`quality=4.0, cost=1.0, latency=1.0`).

### Tie-breaking

When multiple profiles score identically, the scorer uses a preference order as a tiebreaker:
`capable` → `fast` → `default` → `local`. Profiles not in this list are ranked after those that are.

---

## Built-in profiles

### `fast`

Low-latency, cost-efficient model for short conversational turns and routine requests.

- `downstream_model: gpt-4o-mini`
- `cost_tier: low`, `cost_weight: 1.0`, `latency_tier: low`, `quality_tier: medium`
- `supports_tools: true`, `supports_structured_output: true`

### `capable`

High-capability model for complex reasoning, long-context tasks, code generation, and tool use.

- `downstream_model: gpt-4o`
- `cost_tier: high`, `cost_weight: 10.0`, `latency_tier: medium`, `quality_tier: high`
- `supports_tools: true`, `supports_vision: true`, `supports_structured_output: true`

### `local`

Locally hosted open-weight model. No data leaves the network. Suitable for sensitive workloads, batch jobs, and cost reduction.

- `downstream_model: llama3`
- `cost_tier: low`, `cost_weight: 0.1`, `latency_tier: medium`, `quality_tier: medium`
- `supports_tools: false`, `supports_structured_output: false`

### `default`

Generic fallback used when no rule matches. Identical to `fast` in practice.

- `downstream_model: gpt-4o-mini`
- `cost_tier: low`, `cost_weight: 1.0`, `quality_tier: medium`

---

## Adding a new profile

1. Add the entry to `config/profiles.yaml`:

   ```yaml
   profiles:
     ultra:
       downstream_model: o3
       description: "Highest quality for critical tasks."
       preferred_provider: openai
       cost_tier: high
       cost_weight: 50.0
       latency_tier: high
       quality_tier: high
       supports_tools: true
       supports_structured_output: true
   ```

2. Add the downstream model binding to `config/capabilities.yaml` under `profiles:`:

   ```yaml
   profiles:
     ultra:
       downstream_model: o3
       provider_hint: openai
   ```

3. Reference the profile in a policy rule:

   ```yaml
   - name: critical_task
     priority: 5
     select_profile: ultra
     when:
       priority: "critical"
   ```

4. Restart SwitchBoard to pick up the changes.
