# Agent Note: Goal completion anchors at the final merged result

Status: implemented

English | [中文](2026-09-08-goal-completion-final-merge-contract.zh.md)

## Problem

Goal completion and the final merge were disconnected contracts. The completion admission verified the live worktree against the fingerprint recorded when the Goal started, and consumed whatever review the session log held latest. After `project_integrate` merged the bound tasks' reviewed work into the controller worktree, the tree had moved past that initial fingerprint: the honest merged state could never complete against it, and pointing completion at a stale tree admitted without covering the merged result at all. Nothing tied completion to the integration domain's applied receipts, and a per-task review could stand in for a final-merge review.

## Decision

Completion gains an explicit final-merge lane beside the existing conjunction. `CompleteGoalRequest.finalIntegration` carries the durable evidence: one applied integration receipt per bound task, the whole-Goal verification whose binding holds the merged tree's fingerprint, and the whole-Goal review. The evidence shapes already supported this — `deliveryId` absent marks whole-Goal records, distinct from any per-task evidence bound to one delivery. A new final-integration stage validates the contract before the regular conjunction runs: the receipts must cover exactly the binding's task set, both records must be whole-Goal, they must carry the same work tuple, and the final review's Session must differ from every bound task's delivering worker.

The fingerprint stage re-anchors honestly. In the final-merge lane the admission recomputes the live worktree against the merged-tree fingerprint the whole-Goal verification carries — never against the binding's initial start claim, and the binding record itself is never rewritten; the initial fingerprint stays the start authorization, and the final state is anchored through evidence. The submitted review must be the contract's review, and the submitted checks digest must be the contract verification's, so no caller evidence rides alongside unconnected. The plain lane is unchanged: without the contract, completion anchors at the initial fingerprint exactly as before, which on a moved tree now provably rejects instead of silently passing.

`selectGoalCompletionIntegration` reads controller-owned durable integration receipts and whole-Goal projection records. Each receipt must cover the current delivery. The Loader command reads these receipts through the existing project controller; a delivery, integration attempt, or merged whole-Goal record requires the final contract even when the receipt service is absent. Projection preserves the complete authorized Goal identity while accepting a separate output fingerprint and snapshot after every bound task delivers. The final contract retains the integration target path. Completion fingerprints that target, rejects a caller-selected copy, and requires its live registered controller and writer lock. A shared journal checkpoint joins prior evidence writes; any later queued write or durability failure invalidates the synchronous guard before native completion.

## Alternatives considered

**Rewriting the binding's fingerprint after integration.** A silent rebind would make the old admission pass unchanged while laundering the authorization source; the contract instead re-anchors through validated evidence and leaves the binding untouched.

**Reusing the per-task lead reviews as the final gate.** Those reviews judged each Worker's branch before integration; none of them examined the merged result. The whole-Goal shape (`deliveryId` absent) plus worker-independence makes the substitution structurally impossible.

**Requiring final-merge evidence before any task delivers.** A Goal may finish entirely on its authorized starting source. The command retains that lane only while no delivery, integration attempt, or merged evidence exists; missing integration wiring cannot exempt delivered work.

## Consequences

The opt-in completion consumer runs host-approved whole-Goal commands in the clean committed controller tree, verifies that all applied heads remain ancestors, and rechecks native Goal identity, writer ownership, receipts, and source around evidence writes. An independent live direct lead reviews that exact verification. Source mutation refuses publication; a nonzero check exit remains failed evidence. Loader tests exercise real Git integration, check execution, independent review, native same-Goal completion, source mutation, and refusal after completion. Upstream Worker delivery fixtures are prepared evidence in this scoped suite; real-provider end-to-end validation remains separate.
