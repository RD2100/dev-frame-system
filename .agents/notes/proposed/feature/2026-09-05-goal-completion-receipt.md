# Agent Note: Goal completion receipts with evidence

Status: proposed

English | [中文](2026-09-05-goal-completion-receipt.zh.md)

## Problem

A completion claim today ends at the `complete` phase change: the durable `goal/change` log records that a caller marked the goal complete, but nothing about what verified the outcome. Consumers that audit finished goals — the DevFrame controller binding and the evaluator-backed certification policy deferred in the [goal package README](../../../../packages/goal/goal/README.md#known-limitations-and-deferred-work) — cannot distinguish an evidenced completion from a bare one. The repo-wide rule that model-visible input must be reconstructable from the session log also cuts here: completion evidence a later goal round should reason about has no durable record to be reconstructed from.

## Proposal

Record a completion receipt as a third member of the existing `goal/change` payload union (`GoalReceiptChangeMeta`, `operation: 'receipt'`) instead of a new session event type. The receipt names the exact goal revision it acknowledges with compare-and-set identity and carries a non-empty evidence array; each entry is `{ kind, summary, at, ref? }`:

- `kind` — a stable lower-kebab-case classification of the evidence (`test-run`, `command`, `log`, …), following the `GoalBlockReason.code` pattern so the set can grow without a format change.
- `summary` — a non-empty trimmed one-line result digest shown to humans and models.
- `at` — epoch milliseconds when the evidence was captured; caller-owned and validated, not defaulted.
- `ref` — optional durable location of the full record (test file, log path, or session event reference). A verification command is its own entry (or part of a summary), not a dedicated field; the minimal shape keeps one kind per entry.

`GoalService.recordReceipt(agent, ref, evidence)` validates `ref` against the current goal (`GOAL_STALE_REVISION` / `GOAL_NOT_FOUND` otherwise) and requires the current phase to be `complete` (`GOAL_INVALID_TRANSITION` otherwise). The receipt annotates the revision without advancing it: refs held by the completing caller stay valid, and the receipt is not a lifecycle mutation. Duplicate receipts for one revision are allowed; the log is an append-only receipt stream and deduplication is a consumer concern.

The strict fold accepts a receipt only when it references the current goal at its exact revision, that goal is `complete`, and `recordedAt` does not precede the goal's `updatedAt`; receipts mutate no fold state, so `lastRef`, `updatedAt`, and the checkpointed projection state are unchanged and the `goal` projection `stateVersion` stays at 6. Empty evidence arrays are rejected (`GOAL_INVALID_EVIDENCE`): an evidence-free receipt is indistinguishable from the bare `complete` event it would follow and would let a completion claim pass without any recorded verification.

### Format and compatibility

No `SESSION_FORMAT_VERSION` bump. The version mechanism bumps only structural changes — header shape, event envelope, core event semantics, the surface mechanism — while ordinary vocabulary growth never bumps; this change grows the payload vocabulary of one existing plugin-owned event type. A reader built before the receipt variant fails loud, not wrong: the strict goal decoder rejects the unknown operation and the projection latches a replay failure with a diagnostic, the same contained refusal an unknown required event produces. `GOAL_CHANGE_VERSION` stays at 1 because every version-1 snapshot and tombstone shape is unchanged and the receipt is additive within the same decoder. `recordReceipt` is a service method only (`block` precedent): no `@Remote` export, no wire-catalog change, and remote exposure is deferred until a remote consumer exists.

### Model-visible ⟺ recorded

The receipt enters the log as the `goal/change` event, so any future component that renders it to the model is reconstructable from the log. This slice adds no model-visible input: no tool, prompt, or continuation-context change.

## Alternatives considered

**A new `goal/receipt` session event type.** Rejected: it adds a `KNOWN_SESSION_EVENT_TYPES` entry, forces a fresh ignorable-classification decision for a non-surface event, and duplicates decode/fold plumbing that `goal/change` already owns, without any consumer needing a distinct event identity.

**A revision-advancing snapshot mutation.** Rejected: bumping the revision at receipt time invalidates every `GoalRef` the completing caller holds, couples evidence recording to lifecycle state, and requires a new phase-preserving snapshot transition in the fold for no consumer need.

**Evidence in a sidecar store instead of the session log.** Rejected: it breaks model-visible ⟺ recorded, and fork, resume, and replay would lose or diverge from the receipt-to-goal association.

**Allowing an empty evidence array.** Rejected: it makes the receipt semantically empty and unenforceable as a verification record; requiring at least one entry is the contract that makes a receipt worth auditing.

## Acceptance criteria

- `recordReceipt` commits a `goal/change` receipt event, emits the contained `goal/changed` notification with `operation: 'receipt'`, and returns the committed receipt; `create` → `complete` → `recordReceipt` → full fold replay leaves the current goal, revision, `roundsStarted`, and `seenGoalIds` exactly as after `complete`.
- Stale or missing refs, non-complete phases, and empty or malformed evidence fail with the named `GoalError` codes before any append.
- Fold-level replay rejects receipts that lack a current goal, reference another goal or revision, target a non-complete phase, precede the goal's `updatedAt`, or carry malformed shapes — each as a strict replay failure, not a silent skip.
- `pnpm exec vitest run packages/goal` and `pnpm run typecheck` pass; the goal subsystem page (both languages), the package README contract, and the generated Cordis catalog stay fresh under `pnpm run test:docs`.

## Risks

Pre-receipt readers that replay a receipt-bearing log latch a goal-projection failure at that record (goal access rejects with the diagnostic until the log is repaired); other projections and the raw log continue to work, which is the accepted degradation for payload growth inside one event type. Evidence summaries are caller-asserted text — the receipt records claims with the same integrity-detection stance as block reasons, not independent verification. Receipt timestamps are monotonic only against the goal's `updatedAt`, not across successive receipts, because receipts retain no fold state. Deferred with this slice: the DevFrame `GoalBinding` latest-receipt reference (needs a `NativeGoalPort` receipt observation plus a projection-state home), wire exposure of `recordReceipt`, and any model-visible rendering of receipts.
