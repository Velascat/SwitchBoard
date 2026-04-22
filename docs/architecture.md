# SwitchBoard Architecture

SwitchBoard is now a selector-only service.

## Runtime boundary

```text
TaskProposal -> SwitchBoard -> LaneDecision
```

- SwitchBoard accepts canonical `TaskProposal` input.
- It evaluates lane-routing policy.
- It returns a canonical `LaneDecision`.
- It can also return a full routing plan with fallback and escalation candidates.

## Live API

- `GET /health`
- `POST /route`
- `POST /route-plan`

See [README.md](../README.md) and [docs/routing.md](routing.md) for the current routing model.
