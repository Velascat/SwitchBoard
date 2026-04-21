# Phase 8 — Advanced Capabilities

Phase 8 expands what decisions can be made without making them opaque.  Every
new routing dimension is deterministic, observable in logs, and operator-controlled.

```
Request
  │
  ▼
PolicyEngine → (profile, rule)           # unchanged
  │
  ▼
ExperimentRouter (Phase 8)               # A/B split → maybe redirect + record
  │
  ▼
AdjustmentStore (Phase 7)                # adaptive demote → maybe redirect + record
  │
  ▼
Eligibility check (Phase 3 + Phase 8)    # tools / long-context / structured-output
  │   if ineligible →
  │     ProfileScorer (Phase 8)          # multi-factor scoring: cost × quality × latency
  ▼
CapabilityRegistry → downstream_model
  │
  ▼
SelectionResult (cost_estimate, ab_*, scored_profiles, …)
```

---

## What Changed

| Area | Before | After |
|------|--------|-------|
| Task types | code \| planning \| summarization \| chat | + `analysis` |
| Structured output | Not tracked | `requires_structured_output` + eligibility filter |
| Cost awareness | `cost_tier` stored but unused | `cost_estimate` in every decision trace |
| A/B experiments | Not supported | `ExperimentRouter` + policy.yaml `experiments:` |
| Eligibility fallback | Fixed preference order | Multi-factor `ProfileScorer` |
| Decision trace | 7 fields | + `cost_estimate`, `ab_experiment`, `ab_bucket`, `scored_profiles` |

---

## 1. Task Classification

### New `analysis` task type

Detection order: `code → analysis → planning → summarization → chat`

Triggers on phrases like:

```
analyze / analyse / analysis of
evaluate / compare and contrast / pros and cons
trade-offs / root cause / investigate / diagnose / assess / examine
```

### Structured output detection

`requires_structured_output: bool` is set to `True` when the request includes:

```json
"response_format": {"type": "json_object"}
"response_format": {"type": "json_schema", "json_schema": {...}}
```

This triggers eligibility filtering: profiles where `supports_structured_output: false` (e.g. `local`) are automatically rejected and a fallback profile is selected.

---

## 2. Cost Awareness

### Profile metadata

Every profile in `profiles.yaml` now declares:

```yaml
profiles:
  capable:
    cost_tier: high       # low | medium | high  (qualitative)
    cost_weight: 10.0     # precise relative cost (Phase 8; overrides tier in scorer)
    quality_tier: high
    latency_tier: medium
    supports_structured_output: true
```

### Cost estimate in decision trace

Every `DecisionRecord` includes `cost_estimate: float | None` — the `cost_weight`
of the selected profile (falls back to tier conversion if `cost_weight` is absent).

```python
# Tier → cost_estimate mapping (fallback when cost_weight absent)
"low"    → 1.0
"medium" → 5.0
"high"   → 10.0
```

---

## 3. A/B Experiments

### Configuration

Add an `experiments:` section to `config/policy.yaml`:

```yaml
experiments:
  - name: capable_vs_fast_chat
    profile_a: capable       # control (majority)
    profile_b: fast          # treatment
    split_percent: 10        # 10% of matching requests go to 'fast'
    enabled: true
    applies_to_rules:        # empty = all rules
      - default_short_request
```

### How it works

1. Policy selects `capable`.
2. `ExperimentRouter` checks if any experiment has `profile_a = "capable"`.
3. If a matching experiment is found, the request ID is hashed (SHA-256) with
   the experiment name to produce a stable 0–99 integer.
4. Values `< split_percent` → bucket **B** (treatment, `profile_b` used).
5. Values `≥ split_percent` → bucket **A** (control, original profile kept).

Assignment is **deterministic**: the same `request_id` always maps to the same bucket.

### Decision trace

```json
{
  "ab_experiment": "capable_vs_fast_chat",
  "ab_bucket": "B",
  "rule_name": "experiment:capable_vs_fast_chat",
  "profile_name": "fast"
}
```

### Constraints

- `force_profile` rules are **never** intercepted by experiments.
- Disabled experiments (`enabled: false`) are silently ignored.
- `applies_to_rules: []` means the experiment applies to all non-force rules.

---

## 4. Multi-Factor Profile Scoring

When a profile is ineligible (or demoted) and the selector needs to choose
an alternative, `ProfileScorer` ranks all eligible candidates by a weighted
score rather than a fixed preference order.

### Scoring dimensions

| Dimension | Source | Lower tier → |
|-----------|--------|-------------|
| `cost_score` | `cost_tier` in profiles.yaml | cheaper is better (score = 1 − tier) |
| `quality_score` | `quality_tier` in profiles.yaml | higher quality is better |
| `latency_score` | `latency_tier` in profiles.yaml | lower latency is better |

```
total_score = w_cost × cost_score + w_quality × quality_score + w_latency × latency_score
```

### Context-driven weights

| Context signal | Effect |
|----------------|--------|
| default (none) | quality=4, cost=1, latency=1 — quality dominates |
| `cost_sensitivity: high` | cost=4, quality=1, latency=1 — prefers cheapest |
| `cost_sensitivity: low` | cost=0.5, quality=3, latency=1 |
| `latency_sensitivity: high` | latency=6, quality=4, cost=1 — latency dominates |
| `latency_sensitivity: low` | latency=0.5 |

### Trace

When scoring is applied, `scored_profiles` in the decision record lists all
candidates and their scores:

```json
"scored_profiles": [
  {"profile": "fast", "cost_score": 1.0, "quality_score": 0.5, "latency_score": 1.0, "total_score": 5.5},
  {"profile": "capable", "cost_score": 0.0, "quality_score": 1.0, "latency_score": 0.5, "total_score": 4.5}
]
```

---

## 5. Structured Output Eligibility

Profiles must declare `supports_structured_output: true/false` in `profiles.yaml`.

The eligibility check now has three filters:

| Requirement | Profile field checked | Rejection reason |
|-------------|----------------------|-----------------|
| `requires_tools` | `supports_tools` | "profile does not support tool use" |
| `requires_long_context` | `max_context_tokens < 16 000` | "context window too small" |
| `requires_structured_output` | `supports_structured_output` | "profile does not support structured output" |

---

## 6. Decision Trace Fields (Phase 8)

Every `DecisionRecord` now includes:

| Field | Type | Description |
|-------|------|-------------|
| `cost_estimate` | `float \| None` | Relative cost weight of selected profile |
| `ab_experiment` | `str \| None` | Experiment name if A/B routing applied |
| `ab_bucket` | `str \| None` | `"A"` (control) or `"B"` (treatment) |
| `scored_profiles` | `list[dict] \| None` | Scorer output when eligibility fallback ran |

These appear in `GET /admin/decisions/recent` and `GET /admin/decisions/{request_id}`.

---

## 7. Configuration Reference

### profiles.yaml — new Phase 8 fields

```yaml
profiles:
  <name>:
    supports_structured_output: true   # bool, default true
    cost_weight: 1.0                   # float, precise relative cost
    quality_tier: medium               # low | medium | high
```

`cost_weight` takes precedence over `cost_tier` in the scorer.  If absent, the
scorer converts `cost_tier` (low=1.0, medium=5.0, high=10.0).

### policy.yaml — experiments section

```yaml
experiments:
  - name: <unique_name>
    profile_a: <control_profile>
    profile_b: <treatment_profile>
    split_percent: <0–100>
    enabled: true
    applies_to_rules: []               # empty = all; list = restrict to named rules
```

---

## 8. Current Limitations

- **Experiments loaded at startup.** `ExperimentRouter` is initialised from the
  policy store during `lifespan()`.  Adding or modifying experiments requires a
  service restart (or a future hot-reload endpoint).
- **`promote` adjustment still not acted on.** Phase 7's promote signal is recorded
  but does not affect routing.  Phase 8 scoring provides an alternative mechanism
  via `quality_tier`.
- **Scorer uses static profile metadata only.** The scorer does not incorporate
  live signal data from the decision log.  For latency-based scoring using
  historical P50/P95, combine with Phase 7 `SignalAggregator`.
