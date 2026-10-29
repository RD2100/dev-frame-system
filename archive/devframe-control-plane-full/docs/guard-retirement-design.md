# Guard Retirement-After-Replacement Design

## Status

- guard_removal_approved: false (permanently blocked)
- This design defines retirement AFTER replacement, not direct removal

## Principle

A guard should only be retired when a stronger replacement is in place and verified. Never remove a guard without its replacement passing the same safety checks.

## Current Guards (submission_guard.py)

| Function | Purpose | Replacement Candidate |
|----------|---------|----------------------|
| pre_submit_gate | Pre-CDP dedup + cooldown | Control Plane state machine invariant |
| record_submission_result | Post-CDP logging | Pipeline runner ledger writer |
| check_before_submit | Pre-flight check | Pipeline schema validation |
| record_submission | Low-level log write | Structured evidence builder |
| get_submission_summary | Diagnostic | Doctor check |

## Replacement Criteria

A replacement must:
1. Provide equivalent or stronger safety guarantee
2. Pass the same test suite (currently 43 tests)
3. Be verified in dry-run mode before production use
4. Have a rollback path to the original guard
5. Not weaken fail-closed behavior

## Retirement Process

1. Design replacement (this document)
2. Implement replacement behind feature flag
3. Shadow-run replacement alongside original
4. Verify parity (same inputs, same outputs)
5. Switch to replacement with original as fallback
6. Only then: retire original guard

## Current State

No guard retirement has occurred. All guards are active. guard_removal_approved remains false.
