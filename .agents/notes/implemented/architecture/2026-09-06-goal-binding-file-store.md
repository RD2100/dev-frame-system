# Agent Note: File-Backed Goal Binding Store

Status: implemented

English | [中文](2026-09-06-goal-binding-file-store.zh.md)

## Problem

The [file-backed required-checks store](2026-09-06-required-checks-file-store.md) made the checks predicate restart-safe, but the composition-held `GoalBindingStore` remained process-local memory: a restart dropped every goal binding, so a host that had bound goals to worktrees could not dispatch `/goal-complete` against them until re-binding by hand. The binding store was the last restart-fragile input of the completion admission's evidence chain.

## Decision

`FileGoalBindingStore` implements the existing four-method `GoalBindingStore` interface over a JSON ledger at a `Config`-provided path, mirroring the required-checks file-store contract wholesale: strict versioned envelope, wholesale re-validation on every read, integrity failures surfaced through the existing `GOAL_BINDING_PERSISTENCE` error family (no new code), same-directory temp-plus-rename publishing, idempotent re-save, and refusal to repair a corrupt ledger. Inherited rulings carry over unchanged — no fsync, no multi-writer locks, no directory creation, no prune, single-writer last-write-wins — and the restart bar is the instance-rebuild test matrix: write, reconstruct the store instance in-process, read back equal. The store ships as an injectable alternative implementation behind the unchanged interface; the composition's injection point picks the implementation, and the four-method surface and every consumer carry zero semantic change.

## Alternatives considered

**A bespoke durability contract for bindings.** Diverging from the required-checks precedent would create two ledger dialects in one package; the mirrored contract keeps one integrity vocabulary.

**Wiring the durable store as the composition default now.** The injection point accepts the implementation; making it the profile default is a deployment decision for the owner wave, as with the checks store.

**Repairing or migrating older ledger shapes.** The pre-release stance rejects compatibility shims; a foreign or corrupt envelope fails loud instead of being silently upgraded.

## Consequences

- A host configuring the binding ledger path keeps goal bindings across restarts; the admission's binding input is no longer memory-bound.
- All ledger stores in the package now share one envelope, validation, and error family, so operators reason about them once.
- Concurrency, fsync, and prune remain recorded inherited rulings, not silently assumed properties.
