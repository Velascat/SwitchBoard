# Troubleshooting

## `GET /health` returns `degraded`

The policy loaded, but validation found routing issues. Inspect `policy_issues` in the response.

## `POST /route` returns `400` or `422`

The submitted payload is not a valid canonical `TaskProposal`.

## `POST /route` returns `503`

Routing policy evaluation failed. Check the configured policy, profiles, and capabilities.
