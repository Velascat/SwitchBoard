# SwitchBoard

SwitchBoard is the selector layer in the platform:

```text
ControlPlane -> TaskProposal -> SwitchBoard -> LaneDecision
```

It evaluates routing policy and returns a canonical lane decision. It does not proxy provider traffic, execute backends, or depend on 9router.

## Core docs

- [Quickstart](quickstart.md)
- [Configuration](configuration.md)
- [API](api.md)
- [Architecture](architecture.md)
- [Routing](routing.md)
- [Policies](policies.md)
- [Profiles](profiles.md)
- [Capabilities](capabilities.md)
- [Observability](observability.md)
- [Troubleshooting](troubleshooting.md)
- [Roadmap](roadmap.md)
