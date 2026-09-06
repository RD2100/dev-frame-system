# Agent Note: /goal-complete Host Command Surface

Status: implemented

English | [中文](2026-09-06-command-goal-binding-host-command-surface.zh.md)

## Problem

The [completion admission production seam](2026-09-06-goal-completion-admission-seam.md) made the three-predicate admission product-reachable at the controller face, but nothing dispatched it from a human surface: a host operator could not say "complete this goal now, through the admission", and the composition a controller needs — which workspace, which worktree, which required-checks store — had no owner. That note explicitly deferred the completion receipt through `GoalService.recordReceipt` and any host-level interception to a "host command surface slice". Without that slice the admission stayed reachable only from tests, and a goal a human judged done could not be completed under the verified evidence chain.

## Decision

The private experimental package `packages/experimental/command-goal-binding` mounts a function plugin whose service registers the human command `/goal-complete` into `ctx.commands` and the devframe projection unit in one activation, so the command and the state it reads are activation-atomic. The handler reads that projection for the invoking session, takes the latest verification evidence attributed to the current goal, and takes the latest review record without a goal pre-filter: review attribution is enforced structurally by `GoalBindingController.complete`, which fails closed on a foreign review, so the reader does not duplicate the check. A pre-check of the composition-held binding store keeps "no binding" a stable data error, the worktree path resolves explicitly from the command line or the configured `workspaceRoot`, and the declared digest resolves against the composition-held required-checks store. The handler then dispatches `GoalBindingController.complete`; an admitted completion records one `completion-admission` receipt through `GoalService.recordReceipt` — closing the deferred receipt slice — while every rejection renders as a stage-named data error that never exposes goal identities. Structural `GoalBindingError`, `SourceFingerprintError`, and `RequiredChecksError` propagate unchanged and fail dispatch. The admission's evaluation order, fail-closed semantics, and complete hot-path async contract are untouched; goal, commands, devframe, and core/session sources carry zero changes.

## Alternatives considered

**A model-facing goal tool instead of a human command.** A model tool would return the completion decision to the model, while the admission exists to make completion human-authorized; the still-active [required-checks wiring proposal](../../proposed/architecture/2026-09-06-required-checks-wiring.md) keeps the model-facing tool surface and deeper verdict journaling open separately.

**Pre-filtering reviews by goal in the projection read.** A filtered read would make a foreign latest review invisible instead of failing loudly; the structural propagation is the fail-closed direction and the test matrix pins it.

**Declaring a Context service key for the composition.** The composition is a private experimental service, so it registers through the Service base and callers read it by reflection; a declared Context merge would spend public catalog surface on a wave-scoped seam.

**Catching structural errors into data errors.** `RequiredChecksError`, `SourceFingerprintError`, and `GoalBindingError` indicate miscomposition, an unusable worktree, or tampering — not user input; converting them to command text would soften fail-closed behavior at exactly the wrong boundary.

## Consequences

- The human completion verb is product-reachable end to end: command dispatch, projection read, controller admission, native compare-and-set complete, durable receipt.
- Receipt journaling through `GoalService.recordReceipt` now belongs to this slice; verdict journaling beyond the receipt and the model-facing tool surface remain with the still-active proposed note.
- Evidence producers remain deferred: the composition's tests append role-policy, goal-binding, verification, and review records directly, and a host without producers receives the stable no-evidence error.
- Binding and required-checks stores are process-local memory defaults; durable stores are future work.
