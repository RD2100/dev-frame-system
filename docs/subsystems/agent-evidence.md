# Agent evidence ledger

English | [中文](agent-evidence.zh.md)

The agent-evidence subsystem holds the append-only provenance trail of agent work over the `agent_evidence` storage domain: task/Goal binding receipts (the DevFrame goal-result binding tuple for one task), submission receipts (commit object name, changed paths, and the digest of the source inputs the work started from), and verification snapshots (command, exit code, and artifact paths — a non-zero exit code is recorded as-is). The ledger stores provenance only: acceptance stays with the Goal binding and the task states. The [package README](../../packages/experimental/agent-evidence/README.md) owns the mount configuration and the model experience.

## Service surface

`ctx.agentEvidence` is the evidence ledger. Its core operations:

- `recordTaskGoalBinding`, `recordSubmission`, and `recordVerification` — validate the receipt through the durable schema and return the frozen receipt.
- `byTask` and `bindingsByGoal` — serve the append-only trail in recorded order; re-recording a binding under a new Goal revision adds a receipt, and nothing rewrites or deletes one.
- Receipts are restored verbatim on start.

## Contracts

Every failure carries a stable `AGENT_EVIDENCE_*` code on `AgentEvidenceError`: an invalid receipt fails loud with `AGENT_EVIDENCE_INVALID_RECEIPT`, and storage refusals surface as `AGENT_EVIDENCE_PERSISTENCE` with the original cause. Receipts live in the `agent_evidence` [storage domain](storage.md); recording parses each receipt through the same zod schema the domain validates restores with. Receipt types reuse the DevFrame identity vocabulary — `ControllerSessionId`, `GoalId`, `AcceptanceHash`, `SourceFingerprint`, `WorkspaceId` — so evidence resolves to the same work identity dispatch and completion already use. No receipt value ever reaches a model request, so no session events are added.

## Boundaries

Acceptance decisions stay outside the ledger: the Goal binding owns them on the [goal](goal.md) side, and the [project task controller](project-controller.md) owns the task states. Receipts are trusted provenance, not verified truth — the ledger does not inspect the repository to confirm changed paths or artifact paths, and it does not validate task or Goal existence; referential integrity stays with the consumers.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentevidence--agentevidenceledger"></a>

### `ctx.agentEvidence` — `AgentEvidenceLedger`

The agent evidence ledger: append-only provenance per task and Goal.

```ts cordis-catalog
/**
 * Record one task/Goal binding receipt tying a task to the Goal that owns
 * its work. Re-recording under a new Goal revision adds a receipt; the
 * trail keeps them all.
 * @param request - The work identity to bind, in DevFrame goal-binding vocabulary.
 * @returns the recorded receipt.
 */
async recordTaskGoalBinding(request: TaskGoalBindingRequest): Promise<TaskGoalBindingReceipt>

/**
 * Record one submission receipt: the commit, the changed paths, and the
 * digest of the inputs the work started from.
 * @param request - The submission facts.
 * @returns the recorded receipt.
 */
async recordSubmission(request: SubmissionRequest): Promise<SubmissionReceipt>

/**
 * Record one verification snapshot: command, exit code, and artifact
 * paths. A non-zero exit code is recorded as-is — the ledger does not
 * judge verification outcomes.
 * @param request - The verification facts.
 * @returns the recorded snapshot.
 */
async recordVerification(request: VerificationRequest): Promise<VerificationSnapshot>

/**
 * Read one task's complete evidence trail.
 * @param taskId - Task selecting the receipts.
 * @returns the three trails, each in recorded order.
 */
byTask(taskId: TaskId): TaskEvidence

/**
 * Read the binding receipts of one Goal on one controller session.
 * @param controllerSessionId - Controller Session that owns the Goal.
 * @param goalId - Goal whose bindings are queried.
 * @returns the matching binding receipts in recorded order.
 */
bindingsByGoal(controllerSessionId: ControllerSessionId, goalId: GoalId): readonly TaskGoalBindingReceipt[]
```

Types: [GoalId](goal.md)

Source: [`packages/experimental/agent-evidence/src/ledger.ts`](../../packages/experimental/agent-evidence/src/ledger.ts)
<!-- END GENERATED cordis-surface -->
