# SwitchBoard Documentation

Index for the `docs/` tree. The README covers what SwitchBoard is and the
execution-lane model; this directory is subgrouped by concern: `routing/`,
`reference/`, `operate/`, `system/`, `history/`.

## Get started

- [quickstart.md](quickstart.md) — Install, configure, start, smoke-test.

## Routing

- [routing/routing.md](routing/routing.md) — Routing algorithm in depth.
- [routing/routing-examples.md](routing/routing-examples.md) — Worked examples
  of policy outcomes.
- [routing/request-flow.md](routing/request-flow.md) — Lifecycle of a routing
  request from ingress to `LaneDecision`.
- [routing/lanes.md](routing/lanes.md) — Per-lane behaviour: claude_cli,
  codex_cli, aider_local.
- [routing/policies.md](routing/policies.md) — Routing policy schema and
  evaluation order.

## Reference

- [reference/api.md](reference/api.md) — HTTP surface: endpoints,
  request/response shapes, errors.
- [reference/configuration.md](reference/configuration.md) — Config keys
  and environment variables.

## Operate

- [operate/observability.md](operate/observability.md) — Logs, metrics,
  decision audit trail.
- [operate/troubleshooting.md](operate/troubleshooting.md) — Common failures
  and how to diagnose.
- [operate/stability.md](operate/stability.md) — Adaptive demotion behaviour
  and tuning.

## System

- [system/architecture.md](system/architecture.md) — Internal structure,
  layers, data flow.
- [system/roadmap.md](system/roadmap.md) — Planned work, out-of-scope items.

## History

- [history/switchboard-selector-cutover.md](history/switchboard-selector-cutover.md) —
  Selector-cutover historical notes.
