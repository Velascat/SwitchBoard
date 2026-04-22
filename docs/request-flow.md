# Request Flow

```text
TaskProposal
  -> LaneSelector evaluates policy
  -> LaneDecision returned
  -> DecisionRecord persisted
```

The default HTTP flow is:

1. `POST /route` receives a canonical `TaskProposal`.
2. `LaneSelector` evaluates policy and constraints.
3. SwitchBoard returns `LaneDecision`.
4. Observability records the normalized routing evidence.
