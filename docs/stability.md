# Stability

Stable:

- `GET /health`
- `POST /route`
- `POST /route-plan`
- Canonical `TaskProposal -> LaneDecision` routing

Not part of the product surface:

- Provider proxy endpoints
- 9router health semantics
- OpenAI-compatible `/v1/chat/completions` forwarding
