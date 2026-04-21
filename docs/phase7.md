# Phase 7 — Adaptive Policy

Phase 7 adds an evidence-driven adaptive layer that improves routing decisions
using observed signals — without ML, without hidden state, and without removing
operator control.

```
DecisionLogger (ring buffer)
         │
         ▼
 SignalAggregator → ProfileSignals (per profile)
         │
         ▼
 AdjustmentEngine → PolicyAdjustment (demote | neutral | promote)
         │
         ▼
  AdjustmentStore (cache + operator controls)
         │
         ▼
     Selector ── adaptive check between policy (step 1) and eligibility (step 2)
```

---

## What Changed

| Area | Before | After |
|------|--------|-------|
| Routing decisions | Static policy only | Static policy + adaptive adjustment |
| Signal source | None | In-memory decision ring buffer |
| Adjustment logic | N/A | Explicit rules in `AdjustmentEngine` |
| Operator control | N/A | Enable / disable / reset / refresh via admin API |
| Decision trace | No adjustment fields | `adjustment_applied`, `adjustment_reason` |
| Admin API | 3 endpoints | 3 + 5 adaptive endpoints |

---

## Components

### SignalAggregator

`src/switchboard/services/signal_aggregator.py`

Aggregates a list of `DecisionRecord`s into per-profile `ProfileSignals`:

```python
@dataclass
class ProfileSignals:
    profile: str
    total_requests: int
    error_count: int
    # computed properties:
    error_rate: float
    mean_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
```

Only successful requests contribute latency samples.

### AdjustmentEngine

`src/switchboard/services/adjustment_engine.py`

Derives one `PolicyAdjustment` per profile using explicit, priority-ordered rules:

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | `error_rate ≥ 40%` AND `total ≥ 5` | `demote` |
| 2 | `mean_latency ≥ 8 000 ms` AND `total ≥ 5` | `demote` |
| 3 | `error_rate ≤ 2%` AND `total ≥ 20` | `promote` |
| — | Otherwise | `neutral` |

```python
@dataclass
class PolicyAdjustment:
    profile: str
    action: str   # "demote" | "neutral" | "promote"
    reason: str   # human-readable derivation explanation
```

Thresholds are named constants (`_DEMOTE_ERROR_RATE`, `_DEMOTE_LATENCY_MS`, etc.).

### AdjustmentStore

`src/switchboard/services/adjustment_store.py`

Caches non-neutral adjustments and provides operator controls:

```python
store = AdjustmentStore(ttl_seconds=300.0)  # default 5-minute TTL

# Refresh from a window of records
store.refresh(decision_logger.last_n(200))

# Lazy refresh — only if TTL expired
store.maybe_refresh(decision_logger.last_n(200))

# Operator controls
store.enable()
store.disable()
store.reset()          # clears all adjustments → all profiles neutral

# Query
adj = store.get_adjustment("capable")  # PolicyAdjustment | None
state = store.get_state()              # AdjustmentStoreState snapshot
```

Only `demote` and `promote` adjustments are stored; neutral profiles are not kept
(implicit neutral is the default).

### Selector (updated)

`src/switchboard/services/selector.py`

The adaptive check runs between step 1 (policy) and step 2 (eligibility):

```
1. PolicyEngine.select_profile(context) → (profile_name, rule_name)
1.5 IF adjustment_store.enabled AND rule_name != "force_profile":
      adj = adjustment_store.get_adjustment(profile_name)
      IF adj.action == "demote":
        alternative = _find_non_demoted_profile(profile_name)
        IF alternative found:
          profile_name = alternative
          rule_name = "adaptive_demote"
          adjustment_applied = True
          adjustment_reason = adj.reason
2. Eligibility check
3. CapabilityRegistry → downstream_model
4. Return SelectionResult (with adjustment_applied / adjustment_reason)
```

`force_profile` rules bypass the adaptive check entirely — operator overrides
always win.

The `_find_non_demoted_profile` helper iterates `_FALLBACK_PREFERENCE`
(`capable → fast → default → local`) then any remaining registered profiles,
skipping the demoted profile and any others that are also demoted.
If no alternative exists, the original profile is kept (fail-open).

---

## Decision Trace

Every `DecisionRecord` and `SelectionResult` now carries:

```python
adjustment_applied: bool = False       # True when adaptive redirection occurred
adjustment_reason: str | None = None   # Why the adjustment was applied
```

These appear in:
- `GET /admin/decisions/recent`
- `GET /admin/decisions/{request_id}`

---

## Admin API

### Inspect state

```bash
GET /admin/adaptive
```

```json
{
  "enabled": true,
  "adjustment_count": 1,
  "demoted_profiles": ["capable"],
  "promoted_profiles": [],
  "adjustments": [
    {
      "profile": "capable",
      "action": "demote",
      "reason": "error rate 45% over 10 requests exceeds threshold (40%)"
    }
  ],
  "last_refresh": "2026-04-20T12:00:00+00:00",
  "window_size": 200
}
```

### Operator controls

```bash
# Enable / disable without clearing data
POST /admin/adaptive/enable
POST /admin/adaptive/disable

# Clear all adjustments → all profiles return to neutral
POST /admin/adaptive/reset

# Force recomputation from last N decision records
POST /admin/adaptive/refresh?n=200
```

All control endpoints return the updated `AdaptiveStateResponse`.

---

## Wiring

`AdjustmentStore` is created in `lifespan()` with default settings and injected
into both `Selector` and `app.state`:

```python
# app.py (lifespan)
adjustment_store = AdjustmentStore()
selector = Selector(policy_engine, capability_registry, profile_store, adjustment_store)
app.state.adjustment_store = adjustment_store
```

To trigger a refresh on a live instance:

```bash
# After traffic has accumulated:
curl -X POST http://localhost:20401/admin/adaptive/refresh?n=200
curl http://localhost:20401/admin/adaptive
```

---

## Current Limitations

- **No auto-refresh.** Adjustments are recomputed only when an operator calls
  `POST /admin/adaptive/refresh` or when `maybe_refresh()` TTL elapses.
  The selector does not call `maybe_refresh()` on every request; operators
  must trigger refreshes explicitly or integrate a background task.
- **`promote` action is recorded but has no routing effect.** Phase 7 only acts
  on `demote`. Promote is tracked for future use (e.g. raising a profile's
  weight in multi-candidate selection).
- **In-memory only.** Adjustments are lost on restart. They will be recomputed
  after the next `refresh` call once enough traffic has been observed.
