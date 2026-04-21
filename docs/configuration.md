# Configuration Guide

SwitchBoard has four configuration surfaces:

| Surface | Where | Hot-reload |
|---------|-------|-----------|
| Environment / service settings | `.env` | No — restart required |
| Routing policy | `config/policy.yaml` | No — restart required |
| Model profiles | `config/profiles.yaml` | No — restart required |
| Capability registry | `config/capabilities.yaml` | No — restart required |

---

## Environment variables (`.env`)

Copy `.env.example` to `.env`. All variables have defaults that work for local development.

```bash
cp .env.example .env
```

### Minimal required changes

For most setups you only need to change one line:

```
ROUTER9_BASE_URL=http://localhost:20128
```

Set this to wherever your 9router instance is running.

### Full reference

```
# Service binding
SWITCHBOARD_HOST=0.0.0.0          # interface to bind; use 127.0.0.1 to restrict to localhost
SWITCHBOARD_PORT=20401             # port SwitchBoard listens on

# Logging
SWITCHBOARD_LOG_LEVEL=info         # debug | info | warning | error | critical

# Config file locations (relative to working directory, or absolute)
SWITCHBOARD_POLICY_PATH=./config/policy.yaml
SWITCHBOARD_PROFILES_PATH=./config/profiles.yaml
SWITCHBOARD_CAPABILITIES_PATH=./config/capabilities.yaml

# Decision log (leave blank to disable)
SWITCHBOARD_DECISION_LOG_PATH=./runtime/decisions.jsonl

# 9router connection
ROUTER9_BASE_URL=http://localhost:20128
ROUTER9_CHAT_COMPLETIONS_PATH=/v1/chat/completions
ROUTER9_TIMEOUT_S=120              # per-attempt timeout in seconds (retries excluded)
```

---

## Routing policy (`config/policy.yaml`)

The policy file defines an ordered list of rules. When a request arrives, SwitchBoard evaluates the rules in ascending `priority` order and uses the first rule whose `when` conditions all match.

### Minimal working policy

```yaml
version: "1"
fallback_profile: "default"

rules:
  - name: capable_for_code
    priority: 10
    select_profile: capable
    when:
      task_type: "code"

  - name: default_fast
    priority: 100
    select_profile: fast
    when: {}
```

### Condition reference

| Condition | Type | Description |
|-----------|------|-------------|
| `task_type` | string or list | `"code"`, `"analysis"`, `"planning"`, `"summarization"`, `"chat"` |
| `complexity` | string | `"low"`, `"medium"`, `"high"` |
| `stream` | boolean | Whether the caller requested SSE streaming |
| `tools_present` | boolean | Whether the request includes a `tools` array |
| `cost_sensitivity` | string | `"high"` — from `X-SwitchBoard-Cost-Sensitivity` header |
| `latency_sensitivity` | string | `"high"` — from `X-SwitchBoard-Latency-Sensitivity` header |
| `priority` | string | `"high"`, `"low"` — from `X-SwitchBoard-Priority` header |
| `model_hint` | string or list | The `model` field sent by the caller |
| `min_estimated_tokens` | integer | Context tokens ≥ value |
| `max_estimated_tokens` | integer | Context tokens ≤ value |
| `min_max_tokens` | integer | Requested output tokens ≥ value |
| `max_max_tokens` | integer | Requested output tokens ≤ value |

List values use "any of" semantics: `task_type: ["code", "planning"]` matches either.

Full schema: [docs/policies.md](policies.md)

---

## Model profiles (`config/profiles.yaml`)

A profile is a named set of capability requirements and preferences. It decouples policy rules from concrete model identifiers — you can change the upstream model without touching the policy.

### Minimal profile definition

```yaml
version: "1"

profiles:
  fast:
    downstream_model: gpt-4o-mini
    tags: [general, chat]

  capable:
    downstream_model: gpt-4o
    tags: [reasoning, code, long-context]
```

### Useful optional fields

```yaml
  fast:
    downstream_model: gpt-4o-mini
    description: Low-latency model for short requests.
    supports_tools: true
    supports_vision: false
    supports_structured_output: true
    cost_tier: low        # low | medium | high
    cost_weight: 1.0      # precise relative cost for multi-factor scoring
    latency_tier: low
    quality_tier: medium  # low | medium | high
```

Full schema: [docs/profiles.md](profiles.md)

---

## Capability registry (`config/capabilities.yaml`)

Describes what each downstream model can do. SwitchBoard uses this to enforce capability requirements — for example, if a request requires structured output and the selected profile's model does not support it, SwitchBoard will look for an alternative profile.

```yaml
version: "1"

models:
  gpt-4o-mini:
    supports_tools: true
    supports_streaming: true
    supports_long_context: true
    quality: medium
    cost_tier: low

profiles:
  fast:
    downstream_model: gpt-4o-mini
    provider_hint: openai
```

The `profiles` section maps profile names to the model identifier they use and the preferred 9router provider hint.

Full schema: [docs/capabilities.md](capabilities.md)

---

## A/B experiments

To split traffic between two profiles, add an experiment to `config/policy.yaml`:

```yaml
experiments:
  - name: capable_vs_fast_chat
    profile_a: fast          # control — receives (100 - split_percent)%
    profile_b: capable       # treatment — receives split_percent%
    split_percent: 10
    enabled: true
    applies_to_rules:
      - default_short_request   # only intercept this rule (empty = all rules)
```

The split is deterministic: the same `request_id` always lands in the same bucket.

---

## Configuration validation

SwitchBoard validates all three config files at startup. If there are errors it aborts immediately and logs each problem. Common validation errors:

- Config file path does not exist
- Duplicate rule names
- Experiment `split_percent` outside 0–100
- Experiment `profile_a` equals `profile_b`

If validation fails, fix the reported error and restart.

---

## Caller-side headers

Callers can influence routing without changing the policy by sending these headers:

| Header | Values | Effect |
|--------|--------|--------|
| `X-SwitchBoard-Priority` | `high`, `low` | Matches `priority` condition in rules |
| `X-SwitchBoard-Cost-Sensitivity` | `high` | Matches `cost_sensitivity` condition |
| `X-SwitchBoard-Latency-Sensitivity` | `high` | Matches `latency_sensitivity` condition |
| `X-SwitchBoard-Tenant-ID` | any string | Matches `tenant_id` condition |
| `X-Request-ID` | any string | Preserved in decision log and error responses |

---

## How requests are classified

The `RequestClassifier` runs on every request before policy evaluation and populates the `SelectionContext` fields that rule conditions match against. All logic is deterministic and keyword-based — no model calls.

### Task type

Detection order (first match wins):

| `task_type` | Triggered by |
|-------------|-------------|
| `code` | Code fence (` ``` `) in any message, or phrases like `"write a function"`, `"refactor"`, `"debug"` |
| `analysis` | Phrases like `"analyze"`, `"compare and contrast"`, `"root cause"`, `"trade-offs"` |
| `planning` | Phrases like `"design a"`, `"architecture"`, `"roadmap"`, `"step by step"` |
| `summarization` | Phrases like `"summarize"`, `"tldr"`, `"key points"` |
| `chat` | Default when nothing else matches |

### Complexity

Computed from token count, message count, and tool use:

| `complexity` | Condition |
|--------------|-----------|
| `high` | estimated tokens > 3,000 **or** more than 8 messages **or** tools array present |
| `medium` | estimated tokens > 500 **or** more than 3 messages |
| `low` | everything else |

### Boolean flags

| Flag | Set when |
|------|----------|
| `requires_long_context` | estimated tokens > 6,000 |
| `requires_tools` | `tools` array is non-empty |
| `requires_structured_output` | `response_format.type` is `json_object` or `json_schema` |

### Automatic latency sensitivity

When `stream: true` and no `X-SwitchBoard-Latency-Sensitivity` header is present, `latency_sensitivity` is automatically set to `"high"`. This makes streaming requests match latency-sensitive rules without requiring callers to set the header explicitly.

### Token estimation

Estimated token count = total character length of all message content strings ÷ 4. This is a rough approximation — it does not account for tokenisation differences between models.
