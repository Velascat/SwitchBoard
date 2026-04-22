# SwitchBoard API

SwitchBoard is selector-only.

## `GET /health`

Returns local selector readiness and policy validity.

## `POST /route`

Accepts a canonical `TaskProposal` and returns a canonical `LaneDecision`.

## `POST /route-plan`

Accepts a canonical `TaskProposal` and returns the primary route plus fallback and escalation candidates.
