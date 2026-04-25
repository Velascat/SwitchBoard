# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main`  | ✅ Yes     |

Only the current `main` branch receives security fixes.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security issues privately by emailing **coding.projects.1642@proton.me**.

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigations (optional)

You will receive an acknowledgment within 72 hours. We aim to release a fix within 14 days of a confirmed report, depending on severity and complexity.

## Scope

SwitchBoard is a lane-selection API — it receives routing requests and returns a `LaneDecision`. The primary security surface is:

- **Unauthenticated routing manipulation** — forged requests causing incorrect lane selection
- **Policy bypass via routing** — crafting a request that routes to an unintended backend
- **Configuration injection** — malicious lane or backend configuration values
- **Information leakage** — decision responses exposing internal topology

SwitchBoard does **not** execute backends directly. It only selects a lane. Execution security belongs in OperationsCenter.

## Out of Scope

- Vulnerabilities in FastAPI, uvicorn, or other upstream dependencies
- Denial-of-service via high request volume (rate limiting is a deployment concern)
- Issues requiring access to the host network or machine
