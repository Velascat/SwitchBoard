# Model Profiles

Profiles are named abstractions that decouple policy rules from specific
downstream model identifiers.  A rule selects a **profile**; the
**capability registry** then resolves that profile to the actual model string
sent to 9router.

---

## Profile File: `config/profiles.yaml`

```yaml
version: "1"

profiles:
  <profile_name>:
    description: "Human-readable description."
    tags: [tag1, tag2]
    preferred_provider: openai
    max_context_tokens: 128000
    supports_tools: true
    supports_vision: false
    cost_tier: low        # low | medium | high
    latency_tier: low     # low | medium | high
```

### Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | no | Human-readable explanation of the profile's purpose. |
| `tags` | list[string] | no | Free-form capability tags for documentation purposes. |
| `preferred_provider` | string | no | Hint to 9router for provider selection (e.g. `openai`, `ollama`). |
| `max_context_tokens` | integer | no | Maximum context window size supported by this profile. |
| `supports_tools` | boolean | no | Whether the underlying model reliably handles function calling. |
| `supports_vision` | boolean | no | Whether the underlying model accepts image inputs. |
| `cost_tier` | string | no | Relative cost indicator: `low`, `medium`, or `high`. |
| `latency_tier` | string | no | Relative latency indicator: `low` (fast), `medium`, or `high`. |

---

## Built-in Profiles

### `fast`

Intended for short, routine requests where latency matters more than capability.

- Low cost, low latency.
- Resolves to `gpt-4o-mini` by default.
- Supports tool use.

### `capable`

Intended for complex tasks: long context, multi-step reasoning, reliable tool use.

- High capability, medium latency, higher cost.
- Resolves to `gpt-4o` by default.
- Supports tool use and vision.

### `local`

Intended for sensitive data (no cloud egress), batch jobs, or cost reduction.

- Runs via Ollama on the local network.
- Resolves to `llama3` by default.
- Limited context window (8k tokens).

### `default`

Used when no policy rule matches.  Identical to `fast` in practice.

---

## Relationship to Capabilities

Profiles themselves do not contain the downstream model string.  That binding
lives in `config/capabilities.yaml` so it can be changed without editing policy
rules or profile definitions.

```
Policy rule → profile_name ──► capabilities.yaml → downstream_model → 9router
```

---

## Adding a New Profile

1. Add an entry to `config/profiles.yaml`:

   ```yaml
   profiles:
     ultra:
       description: "Ultra high quality for critical tasks."
       cost_tier: high
       latency_tier: high
   ```

2. Add the downstream model binding to `config/capabilities.yaml`:

   ```yaml
   profiles:
     ultra:
       downstream_model: o3
       provider_hint: openai
   ```

3. Reference the profile name in a policy rule in `config/policy.yaml`:

   ```yaml
   - name: critical_task
     priority: 5
     profile: ultra
     conditions:
       priority: "critical"
   ```

4. Restart SwitchBoard (or trigger a reload) to pick up the changes.
