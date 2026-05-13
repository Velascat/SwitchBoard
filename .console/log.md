
- Remove OC contracts dependency (2026-05-08, on fix/remove-oc-contracts-dependency): X2 surfaced that SB imported `LaneDecision`, `TaskProposal`, and routing enums from `operations_center.contracts` — a backwards dependency (OC routes_through SB, not the reverse). Fix: created `switchboard/contracts/` module owning `TaskProposal`, `LaneDecision`, `enums`, and supporting value objects. Wire format unchanged (same Pydantic field names). Updated 6 src files and 7 test files. 301 tests pass; X2: 0 findings.

## 2026-05-08 — Wire pre-commit hook

Added .hooks/pre-commit (log.md enforcement) and set core.hooksPath = .hooks.
Pre-push Custodian guard was already present; now both hooks are active.

- X1 cross-repo config wired (2026-05-08, on `chore/x1-cross-repo-config`): Added `audit.cross_repo.platform_manifest_repo: ../PlatformManifest` to `.custodian/config.yaml`. X1 live-run: 0 legacy-name findings.

- DC4 Architecture section (2026-05-08, on `fix/dc4-architecture-section`): Custodian DC4 (native) flagged the README missing an Architecture H2 (Quick Start was already present). Added a brief Architecture section above Execution Lanes summarising SwitchBoard as a thin policy boundary with config-driven lane selection.

## 2026-05-08 — M1: CHANGELOG.md stub (Keep-a-Changelog format)

Added a minimal CHANGELOG.md so M1 (and M5 format check) pass.

## 2026-05-08 — DC8: Move Quick start before Architecture


## 2026-05-08 — Custodian round: SB clean (42 → 0)


## 2026-05-08 — CI regression guard

Added .github/workflows/custodian-audit.yml + .hooks/pre-push.
Both run `custodian-multi --fail-on-findings`. CI is the source of
truth; pre-push catches regressions before they hit GitHub.


## 2026-05-08 — D11 exclusions (admin CRUD trio + strategy pattern)


## 2026-05-10 — GitHub username migration

- Updated repo-owned references from the previous GitHub username to `ProtocolWarden` after the account rename.
- Scope: license headers, GitHub URLs, workflow install commands, manifests, dependency URLs, examples, and local owner defaults where present.

## 2026-05-10 — Custodian pre-push command resolution

- Updated the pre-push guard to prefer system `custodian-multi`, with repo venv and sibling Custodian venv fallbacks.

## 2026-05-10 — GitHub Pages owner URL migration

- Updated the MkDocs `site_url` from the old GitHub Pages owner URL to `https://protocolwarden.github.io/SwitchBoard/`.

## 2026-05-13 — Custodian audit cleanup (phase 1)

- RUFF: fixed import sorting (I001) and modernised str+Enum to StrEnum (UP042) across contracts/enums.py and api/routes_routing.py, adapters/cxrp_mapper.py, contracts/common.py, contracts/proposal.py, contracts/routing.py, lane/catalog_advisor.py.

## 2026-05-13 — Contracts test coverage (custodian audit phase 2)

- Added per-module contract tests in `test/unit/switchboard/contracts/`: `test_enums.py` (7), `test_common.py` (13), `test_proposal.py` (7), `test_routing.py` (6) — 33 tests total, all pass.
- Added `test/unit/switchboard/__init__.py` and `test/unit/switchboard/contracts/__init__.py` (empty).
- Removed old consolidated `test/unit/test_contracts.py`.
- Updated `.custodian/config.yaml`: removed contracts/ from T1/T6/T7 exclusions; updated deferred-test comments.
- custodian audit: 0 T1/T6/T7 findings (1 pre-existing RUFF path ghost unrelated to this change).
