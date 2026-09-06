# Agent Note: Goal Completion Admission Production Seam

Status: implemented

English | [中文](2026-09-06-goal-completion-admission-seam.zh.md)

## Problem

`evaluateCompletionAdmission` shipped as a pure evaluation face with no production caller: nothing in the runtime conjuncted the three predicates — fingerprint match, required-checks coverage, authorized review — so their rejection power was test-pinned but not product-reachable. A DevFrame-bound Goal could reach the native Goal lifecycle's complete mutation with no completion-evidence check at all, which is the exact "source changed after review" and "weakened required checks" hazard the face exists to reject. The [required-checks wiring proposal](../../proposed/architecture/2026-09-06-required-checks-wiring.md) registered this production assembly as deferred; that proposal stays active for the host tool surface and verdict journaling, and this note owns the first slice that closes the controller-level gap.

## Decision

`GoalBindingController.complete(identity, request)` in `packages/experimental/devframe/src/controller/goal-binding.ts` is the production call point where the admission conjunction gates the native Goal lifecycle's complete mutation. The attempt resolves the binding by exact identity, closes admission for its whole duration, validates that the native Goal is still this binding's Goal, not behind the bound revision, and not already complete, and requires the review evidence to be attributed to the completing Goal (Goal id, controller Session, workspace). The three predicates then evaluate in their fixed evidence-chain order against the durable binding's own recorded fingerprint — never a caller claim. A rejection returns as data with the native Goal untouched, and continuing work requires a human-authorized `resume`. An admission performs the native complete at the current revision and persists the binding at the revision the service returned.

The `NativeGoalPort` seam gains the required `complete(ref)` verb, and `GoalServicePort` is the port's first production implementation: every verb delegates to the resolved `ctx.goals` service on the exact live Agent the port binds, and native rejections propagate unchanged. The model-facing `update_goal` completion path and the native Goal service contract are unchanged.

## Alternatives considered

**Evaluate inside the native Goal service or the `update_goal` tool.** Release packages cannot depend on experimental packages, and the generic Goal lifecycle carries no DevFrame evidence; both placements would either invert the dependency rule or force every Goal completion to present DevFrame evidence. The controller seam keeps the evaluation at the identity owner.

**Optional port verb with a runtime rejection.** An optional `complete` would let a half-wired port compile and only fail at call time; the required verb moves the unwired failure to type-checking, matching the `DevFrameSessionJournal` review-gate precedent of failing at construction rather than inventing a softer runtime path.

**Host-level interceptor around `ctx.goals.complete`.** A global service wrapper would observe bound-Goal completions from every path, but it changes global composition for all Goal consumers; intercepting belongs to the host command surface slice, which also owns journaling the verdict.

**Fingerprint claimed by the caller.** Taking the fingerprint from the request would let the caller assert the tree state; the controller reads it from the durable binding, so the recorded claim stays the authority side of the comparison.

## Consequences

- The three-predicate rejection power is product-reachable through the controller face; the evaluation order, the hot-path async contract, and the pure evaluation face are unchanged.
- Admission closes for the whole completion attempt and a rejected attempt leaves it closed: the evaluation runs real git subprocesses and must not race admitted model steps, and a broken evidence chain does not keep admitting work without human re-authorization.
- The binding's `goalRevision` advances to the completed revision while `ProjectBindingRecord.lifecycle` keeps its current vocabulary — the native Goal phase owns the completed state, and the lifecycle vocabulary still has no terminal completion value.
- Evidence attribution is enforced on the identity triple (Goal, controller Session, workspace); deeper tuple matching (revision, snapshot, task ids) stays with the host composition, which attributes the evidence it records.
- The verdict is returned to the caller and not journaled; recording it, or a completion receipt through `GoalService.recordReceipt`, stays with the host command surface slice.
