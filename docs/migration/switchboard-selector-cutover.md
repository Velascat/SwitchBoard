# SwitchBoard Selector Cutover

- Default FastAPI runtime now exposes selector endpoints instead of provider-proxy endpoints.
- `/health` now reports selector readiness and policy validity only.
- `/route` accepts canonical `TaskProposal` input and returns `LaneDecision`.
- `/route-plan` returns the full routing plan.
- Legacy proxy modules were removed from the default shipped runtime and test surface.
