# Production Promotion Criteria

> Status: DRAFT — criteria definition only, NOT promotion authorization.
> Meeting these criteria does NOT automatically authorize production promotion.
> Production promotion still requires a separate GPT-accepted authorization pack.

## P0: Test Health

- [ ] Full smoke test passes 2 consecutive runs (no intermittent failures)
- [ ] Core state tests: all pass, 0 failures
- [ ] E2E evidence tests: all pass, 0 failures
- [ ] Documentation staleness check: CLEAN (0 stale patterns)

## P0: Broader Real-Chain Testing

- [ ] B1 Multi-Pack Replay: accepted (history replay across all decision types)
- [ ] B2 Multi-Agent Chain: accepted (authorization → execution → review → route → closure)
- [ ] B3 Bounded Real-Chain Dry Run: accepted (real submission, capture, decision parse, route update, no production)

## P0: Evidence Integrity

- [ ] All evidence packs: manifest-zip-hash consistency verified
- [ ] VALIDATION_RESULT.json: passed for all recent packs
- [ ] No hash_failures, missing_from_zip, or extra_in_zip in any recent pack

## P0: Route / Ledger Consistency

- [ ] CURRENT_ROUTE.json: all blocked items = false (as expected)
- [ ] DECISION_LEDGER.jsonl: all entries consistent with POST_REVIEW_ROUTE
- [ ] No review_unverified or RID mismatch entries in recent history
- [ ] TRANSITION_LOG.jsonl: consistent with ledger decisions

## P1: Rollback Readiness

- [ ] ROLLBACK_PLAN.md: exists and reviewed
- [ ] Rollback dry-run: tabletop exercise completed
- [ ] Evidence preservation: confirmed for all historical packs

## P1: Monitoring Readiness

- [ ] MONITORING_PLAN.md: exists and reviewed
- [ ] Smoke test #0 (staleness): integrated and passing
- [ ] Readiness score tool: operational

## P1: Human Override Readiness

- [ ] HUMAN_OVERRIDE_PROTOCOL.md: exists and reviewed
- [ ] Manual intervention paths: documented for review_unverified, human_required, blocked

## P2: Open Gap Threshold

- [ ] P0 open gaps: 0
- [ ] P1 open gaps: all have defined remediation plans
- [ ] P2 open gaps: tracked in readiness heatmap

## Explicit Non-Automatic Rule

```
Meeting ALL of the above criteria is necessary but NOT sufficient for production promotion.
Production promotion REQUIRES a separate, explicit GPT-accepted authorization pack.
No agent (Claude, Codex, OpenCode) may self-declare production promotion.
The readiness_score tool is diagnostic only and does not authorize promotion.
```

## Current Assessment (2026-06-04)

| Criteria Group | Status |
|---------------|--------|
| Test Health | PASS (smoke 4/4, 717 tests) |
| Broader Real-Chain | NOT STARTED (B1/B2/B3 pending) |
| Evidence Integrity | PASS |
| Route/Ledger Consistency | PASS |
| Rollback Readiness | PASS (doc exists) |
| Monitoring Readiness | PASS (doc exists) |
| Human Override | PASS (doc exists) |
| Open Gap Threshold | 5 open (P0×2, P1×2, P2×1) |
| Production Promotion | BLOCKED |
