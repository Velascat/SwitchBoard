---
name: Feature Request
about: Suggest an improvement or new capability
labels: enhancement
assignees: ''
---

## Summary

A one-sentence description of the feature.

## Problem It Solves

What is currently difficult or impossible that this would fix?

## Proposed Solution

How you imagine it working. Include example request/response if relevant:

```json
// TaskProposal input
{}

// LaneDecision output
{}
```

## Selector-Only Check

SwitchBoard only selects a lane — it does not execute backends. Confirm this feature stays within that boundary:

- [ ] No adapter or execution calls introduced
- [ ] Output is still a `LaneDecision`
- [ ] No runtime feedback loops to OperationsCenter

## Alternatives Considered

Other approaches and why you ruled them out.

## Additional Context

Related issues, architecture docs, or prior discussion.
