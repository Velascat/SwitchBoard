# SwitchBoard Documentation

Index for the `docs/` tree. The README covers what SwitchBoard is and the
execution-lane model; this directory holds API reference, configuration
detail, runtime behaviour, and historical migration notes.

## Get started

- [quickstart.md](quickstart.md) — Install, configure, start, smoke-test.
- [index.md](index.md) — Doc-set landing page (legacy; kept for inbound links).

## Architecture

- [architecture.md](architecture.md) — Internal structure, layers, data flow.
- [request-flow.md](request-flow.md) — Lifecycle of a routing request from
  ingress to `LaneDecision`.

## Configuration

- [configuration.md](configuration.md) — Config keys and environment variables.
- [policies.md](policies.md) — Routing policy schema and evaluation order.
- [routing.md](routing.md) — Routing algorithm in depth.
- [routing-examples.md](routing-examples.md) — Worked examples of policy outcomes.
- [lanes.md](lanes.md) — Per-lane behaviour: claude_cli, codex_cli, aider_local.

## API

- [api.md](api.md) — HTTP surface: endpoints, request/response shapes, errors.

## Operate

- [observability.md](observability.md) — Logs, metrics, decision audit trail.
- [stability.md](stability.md) — Adaptive demotion behaviour and tuning.
- [troubleshooting.md](troubleshooting.md) — Common failures and how to diagnose.

## Roadmap

- [roadmap.md](roadmap.md) — Planned work, out-of-scope items.

## Migration

- [migration/switchboard-selector-cutover.md](migration/switchboard-selector-cutover.md) —
  Selector-cutover historical notes.
