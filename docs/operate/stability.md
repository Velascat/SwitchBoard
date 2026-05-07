# Stability

Stable:

- `GET /health`
- `POST /route`
- `POST /route-plan`
- Canonical `TaskProposal -> LaneDecision` routing

Not part of the product surface:

- Provider proxy endpoints
- OpenAI-compatible `/v1/chat/completions` forwarding
