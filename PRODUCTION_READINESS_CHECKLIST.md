# Production Readiness Checklist

## Accepted Capabilities
- bounded guarded review pipeline: CLOSED
- Claude/Codex interchangeable: ACCEPTED
- OpenCode bounded executor: VERIFIED
- limited broader real-chain execution: ACCEPTED (680 tests: 472 core + 216 e2e)
- Runbook/Ledger hardening: ACCEPTED

## Pre-Production Checks
- [ ] All tests pass (680 tests: 472 core + 216 e2e)
- [ ] GPT review authorization active
- [ ] CDP submission functional
- [ ] AUTHORIZED_GPT_CONVERSATION.json valid

## Human Approvals Required
- [ ] Production promotion (BLOCKED)
- [ ] Hardcoded driver replacement (BLOCKED)
- [ ] Guard removal (BLOCKED)
- [ ] Evidence cleanup (BLOCKED)

## Monitoring
- review_unverified rate
- CDP failure rate
- Route anomalies

## Rollback
- Evidence preserved
- Safe automation stop
- Failed execution recovery

## Failure Handling
- HUMAN_REQUIRED on boundary violations
- FAIL_CLOSED on unverified reviews
