# Phase 3 — Policy Maturity

Phase 3 makes SwitchBoard's routing decisions meaningfully useful by enriching
the selection context, adding capability eligibility validation, and improving
decision trace quality.

```
Client → SwitchBoard → classify → select (policy + eligibility) → forward → 9router
```

Phase 2 proved a real client can talk to SwitchBoard. Phase 3 proves the routing
decisions feel intentional and operator-tunable rather than arbitrary.

---

## What Changed from Phase 2

| Area | Phase 2 | Phase 3 |
|------|---------|---------|
| Context | token count + explicit headers only | + task_type, complexity, requires_tools, requires_long_context, cost/latency sensitivity |
| Profile metadata | downstream_model + tags | + supports_tools, max_context_tokens actively validated |
| Rules | size + priority headers | + task type, complexity, cost sensitivity |
| Eligibility | none — policy choice always accepted | profiles rejected when incompatible with request requirements |
| Decision log | profile + rule + latency | + context_summary + rejected_profiles + reason |

---

## How Selection Context is Derived

The `RequestClassifier` runs three passes:

### 1. Header pass (trusted, short-circuit)

| Header | Context field | Example |
|--------|---------------|---------|
| `X-SwitchBoard-Profile` | `force_profile` | `capable` |
| `X-SwitchBoard-Priority` | `priority` | `high`, `low` |
| `X-SwitchBoard-Tenant-ID` | `tenant_id` | `acme-corp` |
| `X-SwitchBoard-Cost-Sensitivity` | `cost_sensitivity` | `high` |
| `X-SwitchBoard-Latency-Sensitivity` | `latency_sensitivity` | `high`, `low` |

### 2. Body scalar pass

Extracts `model`, `stream`, `max_tokens`, `temperature`, `tools`.

### 3. Heuristic pass (deterministic, inspectable)

**`task_type`** — scanned from message content (lowercased):

| Detected task | Trigger signals |
|---------------|-----------------|
| `code` | Code fence (` ``` `), "write a function", "implement ", "refactor ", "debug ", "fix the bug" |
| `planning` | "architecture", "design a", "how should i", "system design", "roadmap" |
| `summarization` | "summarize", "summarise", "tldr", "tl;dr", "key points" |
| `chat` | default — nothing above matched |

Detection order: code → planning → summarization → chat. A message asking to
"implement a plan" is classified as `code`, not `planning`.

**`complexity`** — from token count, message depth, and tool use:

| Class | Condition |
|-------|-----------|
| `high` | > 3 000 tokens OR > 8 messages OR tools present |
| `medium` | > 500 tokens OR > 3 messages |
| `low` | everything else |

**`requires_long_context`** — `True` when `estimated_tokens > 6 000`.

**`requires_tools`** — same as `tools_present` (non-empty tools array).

**`latency_sensitivity`** — automatically set to `"high"` when `stream=True`,
unless the caller already specified it via header.

---

## Profile Metadata

`config/profiles.yaml` defines the routing-relevant metadata per profile:

```yaml
fast:
  downstream_model: gpt-4o-mini
  supports_tools: true
  max_context_tokens: 128000
  cost_tier: low
  latency_tier: low
  tags: [general, chat, summarisation, classification]

capable:
  downstream_model: gpt-4o
  supports_tools: true
  max_context_tokens: 128000
  cost_tier: high
  latency_tier: medium
  tags: [reasoning, code, long-context, tool-use, complex]

local:
  downstream_model: llama3
  supports_tools: false
  max_context_tokens: 8192
  cost_tier: low
  latency_tier: medium
  tags: [private, on-premise, low-cost, batch]
```

Fields used for eligibility validation: `supports_tools`, `max_context_tokens`.

---

## How Policy Rules Are Applied

Rules in `config/policy.yaml` are evaluated in ascending `priority` order.
The first rule whose `when` conditions all match the `SelectionContext` wins.

### New Phase 3 condition keys

| Key | Type | Description |
|-----|------|-------------|
| `task_type` | string / list | Matches `context.task_type` |
| `complexity` | string / list | Matches `context.complexity` |
| `requires_tools` | bool | True if tools array present |
| `requires_long_context` | bool | True if estimated_tokens > 6 000 |
| `cost_sensitivity` | string | From `X-SwitchBoard-Cost-Sensitivity` header |
| `latency_sensitivity` | string | From `X-SwitchBoard-Latency-Sensitivity` header |

List values use "any of" semantics:
```yaml
when:
  complexity: ["low", "medium"]   # matches either
```

### Rule table (priority order)

| Priority | Rule | Trigger | Profile |
|----------|------|---------|---------|
| 10 | caller_requests_capable | model_hint in [capable, gpt-4o, …] | capable |
| 11 | caller_requests_local | model_hint in [local, llama3, …] | local |
| 20 | high_priority_tenant | priority = high | capable |
| 30 | tool_use | tools_present = true | capable |
| 35 | coding_task | task_type = code | capable |
| 38 | planning_task | task_type = planning | capable |
| 40 | streaming_short | stream = true AND ≤ 512 tokens | fast |
| 45 | summarization_task | task_type = summarization AND ≤ 3 000 tokens | fast |
| 50 | large_context | estimated_tokens > 4 096 | capable |
| 55 | high_complexity | complexity = high | capable |
| 60 | long_output_requested | max_tokens > 2 048 | capable |
| 65 | cost_sensitive_non_complex | cost_sensitivity = high AND complexity low/medium | fast |
| 70 | low_priority_local | priority = low | local |
| 100 | default_short_request | estimated_tokens ≤ 4 096 | fast |

**Fallback**: `default` (resolves to `gpt-4o-mini`, same as `fast`).

---

## How Eligibility / Rejection Works

After the policy selects a profile, the Selector validates it against the
request's declared requirements:

| Requirement | Check | Rejection reason |
|-------------|-------|-----------------|
| `requires_tools = true` | profile `supports_tools` must be true | "profile does not support tool use" |
| `requires_long_context = true` | profile `max_context_tokens` must be ≥ 16 000 | "profile context window (N tokens) too small for long-context request" |

When a profile is rejected, the Selector tries alternatives in preference order:
`capable → fast → default → local → (other profiles alphabetically)`.

The first eligible candidate is selected with `rule_name = "eligibility_fallback"`.

If nothing is eligible, the original policy choice is used (fail-open) and all
rejections are recorded in the decision log.

**`force_profile` bypasses eligibility.** Header overrides are trusted absolutely.

---

## Tuning Routing Behaviour Through Config

### Make coding requests use a different profile

Edit `config/policy.yaml`:
```yaml
- name: coding_task
  priority: 35
  select_profile: capable   # change this
  when:
    task_type: "code"
```

### Raise the long-context threshold

In `classifier.py`, change `_LONG_CONTEXT_THRESHOLD = 6_000` to your preferred
token count. No rules need updating — `requires_long_context` is derived from this
constant and the eligibility check reads `max_context_tokens` from profiles.yaml.

### Add a new profile tier

1. Add entry to `config/profiles.yaml` with `downstream_model`, `supports_tools`,
   `max_context_tokens`, `cost_tier`, `latency_tier`.
2. Add entry to `config/capabilities.yaml` under both `models:` and `profiles:`.
3. Add rules to `config/policy.yaml` referencing the new profile name.
4. Restart SwitchBoard (or call `POST /admin/reload` if implemented).

### Change the fallback

```yaml
# config/policy.yaml
fallback_profile: "fast"   # instead of "default"
```

---

## Example Decision Traces

### Short chat request

```json
{
  "timestamp": "2026-04-20T18:00:00Z",
  "selected_profile": "fast",
  "downstream_model": "gpt-4o-mini",
  "rule_name": "default_short_request",
  "reason": "rule:default_short_request → profile:fast",
  "context_summary": {
    "task_type": "chat",
    "complexity": "low",
    "estimated_tokens": 12,
    "requires_tools": false,
    "requires_long_context": false,
    "stream": false,
    "cost_sensitivity": null,
    "latency_sensitivity": null
  },
  "rejected_profiles": [],
  "latency_ms": 8.3
}
```

### Coding request

```json
{
  "selected_profile": "capable",
  "downstream_model": "gpt-4o",
  "rule_name": "coding_task",
  "reason": "rule:coding_task → profile:capable",
  "context_summary": {
    "task_type": "code",
    "complexity": "low",
    "estimated_tokens": 18,
    "requires_tools": false,
    "requires_long_context": false
  },
  "rejected_profiles": []
}
```

### Explicit local request with tools (eligibility rejection)

```json
{
  "selected_profile": "capable",
  "downstream_model": "gpt-4o",
  "rule_name": "eligibility_fallback",
  "reason": "rule:eligibility_fallback → profile:capable [rejected: local (profile does not support tool use)]",
  "context_summary": {
    "task_type": "chat",
    "complexity": "high",
    "requires_tools": true,
    "requires_long_context": false
  },
  "rejected_profiles": [
    {"profile": "local", "reason": "profile does not support tool use"}
  ]
}
```

---

## Troubleshooting Surprising Routing Decisions

### Why did this coding request go to fast?

Check `task_type` in the decision log's `context_summary`. If it shows `"chat"`,
the classifier didn't detect any coding keywords. Either the request phrasing
didn't match the keyword list in `classifier.py`, or the coding intent was in a
system message that was too generic.

Add more specific coding phrases to `_CODE_PHRASES` in `classifier.py`, or
use the `X-SwitchBoard-Profile: capable` header to force it.

### Why did a long request land on local?

Check `requires_long_context` in `context_summary`. If it's `false`, the request
was under 6 000 estimated tokens. If it's `true` and local was still selected,
check `rejected_profiles` — local should appear there with a context window reason,
and a fallback profile should have been selected.

If local was selected despite `requires_long_context=true` and no rejection
appears, `profile_store` may not have been injected into the Selector (check
`app.py` wiring).

### How do I make all requests use capable temporarily?

```yaml
# config/policy.yaml — set a catch-all rule at priority 1
rules:
  - name: always_capable
    priority: 1
    select_profile: capable
    when: {}   # no conditions = always matches
```

---

## Current Limitations

- **No adaptive routing.** All rules are static and config-driven. Routing does not
  improve automatically based on latency or quality observations.
- **Task type detection is keyword-based.** It is deterministic and inspectable but
  can misclassify requests with unusual phrasing. Override with `X-SwitchBoard-Profile`
  when the classification is wrong.
- **Token estimation is approximate.** `chars / 4` is a reasonable heuristic but
  not accurate. For precise routing on context window limits, use the
  `X-SwitchBoard-Profile` header or tune `_LONG_CONTEXT_THRESHOLD`.
- **No multi-tenant profile isolation.** All tenants share the same profile set.
- **No streaming token counting.** `latency_ms` in streaming decision records
  measures time-to-last-chunk, not time-to-first-token.
