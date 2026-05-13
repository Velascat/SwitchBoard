# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
"""CatalogAdvisor — validate a LaneDecision against an ExecutorCatalog.

After LaneSelector picks (lane, backend), the advisor checks the catalog
for problems the routing policy doesn't know about:

  - the chosen backend isn't classified ``adapter_only`` or
    ``adapter_plus_wrapper`` (warns: ``fork_required`` / ``upstream_patch_pending``)
  - the chosen backend doesn't advertise required capabilities
  - the chosen backend doesn't support the runtime kind the caller asked for

The advisor is non-mutating: it returns advisories. The caller (route
endpoint, audit) decides whether to surface, log, or override.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from switchboard.contracts import LaneDecision
from switchboard.ports.executor_catalog import ExecutorCatalog


class AdvisoryLevel(StrEnum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class CatalogAdvisory:
    level: AdvisoryLevel
    code: str
    message: str


def advise(
    *,
    catalog: ExecutorCatalog,
    decision: LaneDecision,
    required_capabilities: Iterable[str] | None = None,
    requested_runtime_kind: str | None = None,
) -> list[CatalogAdvisory]:
    """Return a list of advisories for this decision against the catalog.

    Empty list = catalog confirms the decision is safe to dispatch.
    """
    out: list[CatalogAdvisory] = []
    backend = decision.selected_backend.value

    # Outcome check.
    forks = set(catalog.backends_by_outcome(outcome="fork_required"))
    pending = set(catalog.backends_by_outcome(outcome="upstream_patch_pending"))
    wrappers = set(catalog.backends_by_outcome(outcome="adapter_plus_wrapper"))
    only = set(catalog.backends_by_outcome(outcome="adapter_only"))

    if backend in forks:
        out.append(CatalogAdvisory(
            level=AdvisoryLevel.BLOCK,
            code="BACKEND_FORK_REQUIRED",
            message=f"backend={backend!r} is classified fork_required; do not dispatch",
        ))
    elif backend in pending:
        out.append(CatalogAdvisory(
            level=AdvisoryLevel.WARN,
            code="BACKEND_UPSTREAM_PATCH_PENDING",
            message=f"backend={backend!r} is classified upstream_patch_pending; "
                    "dispatch is conditional on catalog policy",
        ))
    elif backend in wrappers:
        out.append(CatalogAdvisory(
            level=AdvisoryLevel.INFO,
            code="BACKEND_ADAPTER_PLUS_WRAPPER",
            message=f"backend={backend!r} requires the wrapper layer; OC binder must translate",
        ))
    elif backend not in only:
        out.append(CatalogAdvisory(
            level=AdvisoryLevel.WARN,
            code="BACKEND_NOT_IN_CATALOG",
            message=f"backend={backend!r} is not present in the executor catalog",
        ))

    # Capability check.
    if required_capabilities:
        cap_supporting = set(catalog.backends_supporting_capabilities(
            required_capabilities=required_capabilities,
        ))
        if backend not in cap_supporting:
            out.append(CatalogAdvisory(
                level=AdvisoryLevel.BLOCK,
                code="BACKEND_MISSING_CAPABILITIES",
                message=f"backend={backend!r} does not advertise required "
                        f"capabilities {sorted(required_capabilities)}",
            ))

    # Runtime check.
    if requested_runtime_kind is not None:
        rt_supporting = set(catalog.backends_supporting_runtime(
            runtime_kind=requested_runtime_kind,
        ))
        if backend not in rt_supporting:
            out.append(CatalogAdvisory(
                level=AdvisoryLevel.BLOCK,
                code="BACKEND_MISSING_RUNTIME",
                message=f"backend={backend!r} does not support runtime "
                        f"kind={requested_runtime_kind!r}",
            ))

    return out
