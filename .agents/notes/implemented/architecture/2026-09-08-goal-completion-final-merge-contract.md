# Agent Note: Goal completion anchors at the final merged result

Status: implemented

English | [中文](2026-09-08-goal-completion-final-merge-contract.zh.md)

## Problem

Goal completion and the final merge were disconnected contracts. The completion admission verified the live worktree against the fingerprint recorded when the Goal started, and consumed whatever review the session log held latest. After `project_integrate` merged the bound tasks' reviewed work into the controller worktree, the tree had moved past that initial fingerprint: the honest merged state could never complete against it, and pointing completion at a stale tree admitted without covering the merged result at all. Nothing tied completion to the integration domain's applied receipts, and a per-task review could stand in for a final-merge review.

## Decision

Completion gains an explicit final-merge lane beside the existing conjunction. `CompleteGoalRequest.finalIntegration` carries the durable evidence: one applied integration receipt per bound task, the whole-Goal verification whose binding holds the merged tree's fingerprint, and the whole-Goal review. The evidence shapes already supported this — `deliveryId` absent marks whole-Goal records, distinct from any per-task evidence bound to one delivery. A new final-integration stage validates the contract before the regular conjunction runs: the receipts must cover exactly the binding's task set, both records must be whole-Goal, they must carry the same work tuple, and the final review's Session must differ from every bound task's delivering worker.

The fingerprint stage re-anchors honestly. In the final-merge lane the admission recomputes the live worktree against the merged-tree fingerprint the whole-Goal verification carries — never against the binding's initial start claim, and the binding record itself is never rewritten; the initial fingerprint stays the start authorization, and the final state is anchored through evidence. The submitted review must be the contract's review, and the submitted checks digest must be the contract verification's, so no caller evidence rides alongside unconnected. The plain lane is unchanged: without the contract, completion anchors at the initial fingerprint exactly as before, which on a moved tree now provably rejects instead of silently passing.

`selectGoalCompletionIntegration` in project-controller is the honest constructor: it reads only the durable integration rows and the session projection's whole-Goal records, requires every bound task's receipt to be applied, and fails loud naming the missing gate. Evidence quality failures — a non-passing review, a worker-issued review, a stale fingerprint — stay with the admission as rejections, not throws.

## Alternatives considered

**Rewriting the binding's fingerprint after integration.** A silent rebind would make the old admission pass unchanged while laundering the authorization source; the contract instead re-anchors through validated evidence and leaves the binding untouched.

**Reusing the per-task lead reviews as the final gate.** Those reviews judged each Worker's branch before integration; none of them examined the merged result. The whole-Goal shape (`deliveryId` absent) plus worker-independence makes the substitution structurally impossible.

**Requiring the final-merge evidence unconditionally.** Every Goal binding has task ids, so a hard requirement would break every existing plain completion until callers were rewired; the lane is opt-in by evidence, and the plain lane's moved-tree rejection already refuses the initial claim against the final state.

## Consequences

The devframe suite pins the positive path (completes at the merged fingerprint, native Goal completes, stored claim untouched), the worker-review refusal, the delivery-bound masquerade refusal, the coverage refusal, the phantom-fingerprint rejection against the live recompute, the plain lane's moved-tree rejection, and the evidence-identity guard. The project-controller suite pins contract selection from applied receipts and whole-Goal evidence and every named absence. The command face's rejection renderer gained the final-integration case its closed union requires.
