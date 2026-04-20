# Capability Registry

The capability registry (`config/capabilities.yaml`) is the single place where
abstract **profile names** are bound to concrete **downstream model identifiers**
that are sent to 9router.

---

## Why a Separate Registry?

- **Decoupling**: Policy rules reference profile names (`capable`, `fast`), not
  model strings (`gpt-4o`, `gpt-4o-mini`).  When OpenAI releases a new model,
  you update one line in `capabilities.yaml` — not every rule that routes to
  that tier.
- **Auditability**: One file shows all model bindings; easy to review in PRs.
- **Runtime swap**: Future hot-reload support will let you change the binding
  without restarting the service.

---

## File Structure

```yaml
version: "1"

profiles:
  <profile_name>:
    downstream_model: <model_string_sent_to_9router>
    provider_hint: <optional_hint>
    notes: <optional_human_notes>
```

### Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `downstream_model` | string | yes | Exact model identifier forwarded to 9router in the `model` field. |
| `provider_hint` | string | no | Optional hint to 9router about which provider to prefer. |
| `notes` | string | no | Human-readable notes about this mapping. |

---

## Resolution Flow

```
Selector.select(context)
  │
  ├─► PolicyEngine.select_profile(context)  → "capable"
  │
  └─► CapabilityRegistry.resolve_profile("capable")  → "gpt-4o"
        │
        └─► body["model"] = "gpt-4o"
              │
              └─► 9router  → OpenAI API
```

---

## Example

```yaml
version: "1"

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

## Switching Models

To move all `capable` requests from `gpt-4o` to `claude-3-5-sonnet`:

```yaml
  capable:
    downstream_model: claude-3-5-sonnet-20241022
    provider_hint: anthropic
```

Restart SwitchBoard.  No policy or profile changes needed.

---

## Error Behaviour

If the policy engine selects a profile that does not exist in the registry:
- The selector logs a warning.
- If the original request included a `model` field (model hint), that value is
  passed through as the downstream model with `rule_name = "passthrough_fallback"`.
- If there is no model hint, a `KeyError` is raised and the client receives a
  `500 Internal Server Error`.

Always ensure every profile referenced in `policy.yaml` has an entry in
`capabilities.yaml`.
