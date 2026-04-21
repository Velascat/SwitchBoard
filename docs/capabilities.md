# Capability Registry

`config/capabilities.yaml` is the single place where abstract **profile names** are bound to concrete **downstream model identifiers** sent to 9router, and where per-model capability metadata is declared.

---

## Why a separate registry?

- **Decoupling**: Policy rules reference profile names (`capable`, `fast`), not model strings (`gpt-4o`). When a new model is released, you update one line — not every rule.
- **Capability enforcement**: The Selector uses model metadata to skip profiles that cannot satisfy a request (e.g. a model that does not support structured output when the caller set `response_format`).
- **Auditability**: One file shows all model bindings; easy to review in PRs.

---

## File structure

```yaml
version: "1"

# Per-model capability metadata
models:
  <model_identifier>:
    supports_tools: true
    supports_streaming: true
    supports_long_context: true
    quality: medium       # low | medium | high
    cost_tier: low        # low | medium | high

# Profile → downstream model binding
profiles:
  <profile_name>:
    downstream_model: <model_string_sent_to_9router>
    provider_hint: <optional_9router_provider_hint>
```

### `models` section

Describes the capabilities of each downstream model. SwitchBoard uses this to enforce capability requirements.

| Field | Type | Description |
|-------|------|-------------|
| `supports_tools` | boolean | Whether the model reliably handles function calling. |
| `supports_streaming` | boolean | Whether the model supports SSE streaming responses. |
| `supports_long_context` | boolean | Whether the model has a large context window (> 32k tokens). |
| `quality` | string | Relative quality tier: `low`, `medium`, or `high`. |
| `cost_tier` | string | Relative cost tier: `low`, `medium`, or `high`. |

### `profiles` section

Binds each profile name to a downstream model string and optional provider hint.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `downstream_model` | string | yes | Exact model identifier forwarded to 9router in the `model` field. |
| `provider_hint` | string | no | Optional hint to 9router about which provider to prefer. |

---

## Resolution flow

```
Selector.select(context)
  │
  ├─► PolicyEngine  → profile_name = "capable"
  │
  ├─► (eligibility check: does this profile meet the request's requirements?)
  │     - requires_tools? → supports_tools must be true
  │     - requires_structured_output? → supports_structured_output in profiles.yaml must be true
  │
  └─► CapabilityRegistry.resolve_profile("capable")
        │
        └─► body["model"] = "gpt-4o"
              └─► 9router → OpenAI API
```

---

## Example

```yaml
version: "1"

models:
  gpt-4o-mini:
    supports_tools: true
    supports_streaming: true
    supports_long_context: true
    quality: medium
    cost_tier: low

  gpt-4o:
    supports_tools: true
    supports_streaming: true
    supports_long_context: true
    quality: high
    cost_tier: high

  llama3:
    supports_tools: false
    supports_streaming: true
    supports_long_context: false
    quality: medium
    cost_tier: low

profiles:
  fast:
    downstream_model: gpt-4o-mini
    provider_hint: openai

  capable:
    downstream_model: gpt-4o
    provider_hint: openai

  local:
    downstream_model: llama3
    provider_hint: ollama

  default:
    downstream_model: gpt-4o-mini
    provider_hint: openai
```

---

## Switching models

To move all `capable` requests from `gpt-4o` to `claude-3-5-sonnet`:

1. Add the model to the `models:` section:

   ```yaml
   claude-3-5-sonnet:
     supports_tools: true
     supports_streaming: true
     supports_long_context: true
     quality: high
     cost_tier: high
   ```

2. Update the profile binding:

   ```yaml
   profiles:
     capable:
       downstream_model: claude-3-5-sonnet
       provider_hint: anthropic
   ```

3. Restart SwitchBoard. No policy or profile changes needed.

---

## Error behaviour

If the policy engine selects a profile that is not present in the `profiles:` section of `capabilities.yaml`, the Selector raises a `KeyError`. This is caught by the route handler and returned as a structured `503 routing_error` response:

```json
{"error": {"type": "routing_error", "code": "no_eligible_profile", ...}}
```

To prevent this, ensure every profile referenced in `policy.yaml` (including `fallback_profile` and experiment profiles) has an entry in `capabilities.yaml`. The config validator at startup logs a warning for any unknown profile references.
