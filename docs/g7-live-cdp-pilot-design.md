# G7 Bounded Live CDP Mechanical Pilot — Design

## Phase: G7 (Mechanical CDP Verification Only)

G7 verifies the CDP pipeline mechanically: connect, locate target, inject payload, produce trace. No GPT reply capture. No parsed judgment. No accepted/blocked verdict.

## Split Strategy

| Phase | Target | Purpose |
|-------|--------|---------|
| G7 (this) | CDP page mechanics | Verify bridge can connect/upload/paste/send |
| G8/G7B | New clean GPT conversation | Real GPT reply + capture + parse |

## Authorization Chain

G7-DESIGN (current) → G7-AUTH → G7-EXECUTION → G7-CLOSURE

G7-AUTH requires GPT acceptance before execution.

## Auth Pack (max 5 files)

1. G7_SCOPE.md — mechanical CDP pilot only, 1 bounded payload, max 3 retries, no state mutation
2. G7_SAFETY_ATTESTATION.md — safety_flag=True, no cookies/session, no CURRENT_STATE mutation
3. G7_TEST_PAYLOAD.md — short synthetic payload, no private data
4. G7_EXPECTED_RESULT.md — CDP connect OK, target found, payload inserted, mechanical result
5. PACK_MANIFEST.md — lists the 4 files above

## Closure Pack (max 5 files)

1. G7_MECHANICAL_RESULT.md — what happened, trace summary
2. CDP_TRACE.json — structured trace of CDP operations
3. PAYLOAD_PROOF.sha256 — hash of submitted payload
4. SAFETY_CHECK.md — no state mutation, no guard removal, no evidence cleanup
5. TEST_OUTPUT.txt — 36/36 tests PASS

## Closure Iteration Policy

Max 2 iterations. If v2 still blocked but CDP mechanical evidence is consistent → accept_with_evidence_limitation.

## Safety Boundaries

- No CURRENT_STATE/CURRENT_ROUTE/DECISION_LEDGER mutation
- No guard removal (guard_removal_approved: false)
- No evidence cleanup (evidence_cleanup_approved: false)
- No cookies/session/browser profile access
- No real user data in test payload
