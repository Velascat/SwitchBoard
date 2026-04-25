## Summary

<!-- One or two sentences describing what this PR does and why. -->

## Changes

<!-- Bullet list of what changed. -->

-

## Selector Boundary Checklist

- [ ] No execution logic introduced (SwitchBoard selects lanes only)
- [ ] No direct adapter or backend calls
- [ ] Output is still a `LaneDecision`
- [ ] Business logic stays in `services/`, not in `api/` route handlers

## Testing

- [ ] Tests pass: `.venv/bin/pytest -q`
- [ ] Linter passes: `.venv/bin/ruff check src test`
- [ ] New routing logic covered by tests

## Related Issues

<!-- Closes #N or References #N -->

## Notes for Reviewer

<!-- Anything non-obvious: edge cases, config changes, policy behavior, follow-up items. -->
