# Agent Note: Required-Checks Wiring and Completion Admission

Status: proposed

English | [中文](2026-09-06-required-checks-wiring.zh.md)

## Problem

The AT1-05 "weakened required checks" rejection variant had no implementation anchor anywhere in the tree: an approved check configuration existed only as an opaque `acceptanceHash`, there was no configuration storage to resolve it against, no durable-schema rule rejected a verification payload whose recorded checks diverged from the approved set, and no admission face combined "checks complete" with the already-shipped review authorization and source-fingerprint verify faces. A completion could therefore claim success while silently dropping or swapping a required check. The design wave (`.agents/devframe/p22/required-checks-design.md`) landed the pure faces — config schema, canonical digest, and the completion-policy evaluator — and registered four gaps; this note owns the wiring wave that closes them.

## Proposal

Close the four registered gaps in `packages/experimental/devframe`:

1. **Configuration storage and the check-configuration component.** A `RequiredChecksConfigStore` interface with a `MemoryRequiredChecksConfigStore` reference implementation registers parsed configs by digest and reloads them through `decodeRequiredChecksConfig` (an unregistered digest fails loud with `REQUIRED_CHECKS_CONFIG_NOT_FOUND`); `acceptanceCheckComponent(config)` names the check-configuration component of the acceptance hash synthesis — it returns the canonical digest and never claims `digest === acceptanceHash`, because the objective component and the full synthesis belong to the host wave.
2. **Durable coverage rule.** The `devframe/verification` event payload now carries a self-declared coverage face `requiredChecks: {config, digest}`; `verificationEventSchema` rejects, at decode time, a payload whose declared digest does not match its own config or whose declared checks are not exactly executed by the recorded checks (same checkId plus the exact command triple). A required check that genuinely ran and failed still decodes as honest failed evidence — the passed verdict belongs to admission, not to the schema.
3. **Completion admission conjunction.** `evaluateCompletionAdmission(request)` in the controller domain conjuncts the three shipped predicates in the evidence-chain order the design fixed: fingerprint match first (`verifySourceFingerprint` anchors which tree the evidence describes), required checks second (`store.load(digest)` plus `evaluateRequiredChecks` anchors what ran versus what was approved), and the authorized review decision last (it anchors who judged; the journal write gate already enforced reviewer authorization before this record existed). Violation reasons route through the existing stable error-code family; structural errors (`SourceFingerprintError`, `RequiredChecksError`) bubble fail-loud. The evaluation is an explicit async call — the hot path stays untouched.
4. **README source map.** The devframe README source map gains the `required-checks.ts` and `source-fingerprint.ts` rows, in both languages.

## Key design

- **Evaluation order is part of the evidence chain.** Fingerprint first (cheapest invalidation: a drifted tree makes every later predicate moot), checks second (depends on the fingerprint verdict and the stored config), review last (consumes the durable, gate-authorized pass decision). Each rejection stage carries its own evidence shape — mismatch both-sides, per-check violations in configuration order, or the review's non-pass decision.
- **The brand boundary holds.** `RequiredChecksDigest` stays a distinct branded type; the wiring never equates it with `AcceptanceHash`. `acceptanceCheckComponent` is a component face only, named so that a future host wave can compose `objective + checkComponent` without re-litigating the identity.
- **Schema and evaluator share one exact-equality implementation.** The durable coverage rule and the completion policy both call `sameRequiredCheckCommand`, so "exactly executed" cannot drift between the layer that decodes and the layer that admits.
- **Honest failed evidence stays decodable.** The coverage rule rejects divergence between the declared and executed check sets, not failure itself; a genuinely failed required check enters the journal as failed evidence and only fails admission.

## Alternatives considered

**Make the schema only carry the digest (config-less self-description).** A digest alone cannot be checked for internal consistency at decode time, and the durable payload would not be auditable without a side-channel config lookup. The self-declared `{config, digest}` pair lets the schema verify the claim itself and keeps the payload self-contained.

**Fold admission into the GoalBindingController lifecycle now.** The design's case-A ruling leaves the production assembly — who calls `evaluateCompletionAdmission` at which lifecycle point, and where the verify result is journaled — to the P23/S4 tool surface. Wiring it into `start` or `resolveResultBinding` this wave would have re-opened the hot-path boundary the design registered.

**Persist configs in a durable store backend now.** The store interface plus a memory reference implementation (the `MemoryGoalBindingStore` precedent) is the honest scope; inventing a JSONL/SQLite backend without a consumer would be speculative infrastructure.

## Acceptance criteria

- A verification payload whose declared digest mismatches its config, or whose declared checks are not exactly executed, fails `verificationEventSchema` decode with a message naming the offending check; a payload with genuinely failed but exactly-executed checks decodes and reads as failed evidence.
- `evaluateCompletionAdmission` rejects at `source-fingerprint`, `required-checks`, or `review` in that fixed order — a request with a bad fingerprint and bad checks rejects at the fingerprint stage — and returns `admitted` with the verified fingerprint only when all three predicates pass; unregistered digests and git failures bubble as their structured errors.
- `acceptanceCheckComponent` returns the canonical digest and the `RequiredChecksDigest` brand remains distinct from `AcceptanceHash`.
- The devframe suite passes (including the rewritten durable-combination cases), package `tsc -b`, the repository build, `verify-export-jsdoc`, `verify-translation-pairing`, `gen-cordis-catalog`, and `verify-persistence-catalog` are all clean.

## Risks

- The production assembly is still unwired: nothing in the shipped runtime calls `evaluateCompletionAdmission` yet — the rejection power is test-pinned, not product-reachable, until the P23/S4 tool surface lands.
- The store is memory-backed only; a process restart loses registered configs, which is acceptable while no durable consumer exists but must be revisited with the first persistent one.
- The self-declared coverage face makes the verification payload larger and duplicates the config inside every event; a future wave may reference a stored config by digest alone once the storage contract stabilizes.
- The objective component of `acceptanceHash` remains unowned; until the host wave composes it, the two faces must not be equated in code or prose.
