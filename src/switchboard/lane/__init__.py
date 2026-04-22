"""
lane — proposal-to-lane routing.

This sub-package contains the LaneSelector service, routing policy models,
decision explanation types, default policy configuration, and the Phase 9
fallback/escalation routing plan infrastructure.

Entry points:
    from switchboard.lane.engine import LaneSelector
    from switchboard.lane.planner import DecisionPlanner
    from switchboard.lane.routing import RoutingPlan, RouteCandidate, CostClass, CapabilityClass
"""
