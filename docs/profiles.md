# Profiles

Profiles are named routing abstractions used by policy. They do not imply a provider proxy hop.

Typical fields:

- `downstream_model`: backend/model identifier used after route selection
- `description`: human-readable purpose
- `tags`: capability tags
- `cost_tier`, `latency_tier`, `quality_tier`: ranking metadata
