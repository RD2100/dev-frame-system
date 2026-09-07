# Project task controller

English | [中文](project-controller.zh.md)

The project-controller subsystem owns the project task board: it moves tasks through the shared `TaskState` order, requires a reason, a next action, and a wake condition for every `blocked` or `failed` move, bounds the number of concurrently `developing` tasks through a validated `maxActiveTasks` config (default 2), runs the DevFrame project lifecycle, and gates main-tree integration behind a controller-only merge marker. Task records persist through the `project_tasks` storage domain and are restored verbatim on start; the lifecycle itself is process-local run state that a fresh process opens explicitly with `startProject`. The [package README](../../packages/experimental/project-controller/README.md) owns the mount configuration and the model experience.

## Service surface

`ctx.projectController` is the board owner. Its core operations:

- Lifecycle — `startProject`, `requestStop`, `confirmQuiescence`, `completeStop`, plus the `needs_attention` and `ambiguous` side states via `markNeedsAttention` and `markAmbiguous`.
- Task moves — `createTask`, `assign`, `startDevelopment`, `beginReview`, `submit`, `requestMainTreeMerge`, `integrate`, `complete`, with `block`, `fail`, and `resume` as the recovery triple path; every move returns the updated record and an illegal move fails loud instead of rewriting state.
- Queries — `find`, `byState`, and `list` answer from the board restored at start.

## Contracts

Every failure carries a stable `PROJECT_CONTROLLER_*` code on `ProjectControllerError` (illegal transition, concurrency exceeded, marker invalid, not controller, quiescence incomplete, task exists or unknown, admission closed, invalid config or detail, persistence). The board lives in the `project_tasks` [storage domain](storage.md) and is a write-through projection of one domain table rebuilt on start. `maxActiveTasks` is enforced exactly where a task would enter `developing`; leaving development frees the slot. Dispatch-path moves require `admission_open`; recording moves (`block`, `fail`, `complete`) stay available while the project has not stopped, so a stop can still record why work ended. The merge gate mints a single-use, process-local marker only for a session whose binding carries the `controller` role, and `integrate` validates the marker before the state check, so a consumed marker reports `MARKER_INVALID` even when the task has already moved on; markers are never restored across restarts.

## Boundaries

The merge gate verifies the caller's role against [session identity bindings](session-identity.md), and submission provenance is recorded by the [agent evidence ledger](agent-evidence.md). The dispatch-path admission requirement builds on the [agent reliability service](agent-reliability.md). The shared `TaskRecord`, `TaskState`, and `PluginId` types belong to the [project-contracts package](../../packages/experimental/project-contracts/README.md). The lifecycle bounds task states, not live model requests — the request ceiling stays the deployment's account-level constraint.

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxprojectcontroller--projectcontroller"></a>

### `ctx.projectController` — `ProjectController`

The project controller: task board, dispatch budget, lifecycle, and merge gate.

```ts cordis-catalog
/**
 * Open project admission after a fresh boot or a completed stop.
 * @returns the new lifecycle state.
 */
startProject(): ProjectLifecycleState

/**
 * Begin the stop: admission closes and in-flight work must drain.
 * @returns the new lifecycle state.
 */
requestStop(): ProjectLifecycleState

/**
 * Confirm quiescence: every task must be out of in-flight work.
 * @returns the new lifecycle state.
 */
confirmQuiescence(): ProjectLifecycleState

/**
 * Complete the stop after the writer-release commit.
 * @returns the new lifecycle state.
 */
completeStop(): ProjectLifecycleState

/**
 * Record that the project needs host attention.
 * @returns the new lifecycle state.
 */
markNeedsAttention(): ProjectLifecycleState

/**
 * Record that the project's durable state cannot be interpreted right now.
 * @returns the new lifecycle state.
 */
markAmbiguous(): ProjectLifecycleState

/**
 * Add one task in the `planned` state.
 * @param request - Task identity, plugin scope, and title.
 * @param options - Host authority guard at the serialized write boundary.
 * @returns the stored record.
 */
async createTask( request: { readonly taskId: TaskId; readonly pluginId: PluginId; readonly title: string }, options: TaskMutationOptions = {}, ): Promise<TaskRecord>

/**
 * Assign a planned task to a session.
 * @param taskId - Task to move.
 * @param assigneeSessionId - Session bound to execute the task.
 * @param options - Host authority guard at the serialized write boundary.
 * @returns the updated record.
 */
async assign(taskId: TaskId, assigneeSessionId: SessionId, options: TaskMutationOptions = {}): Promise<TaskRecord>

/**
 * Move an assigned task into development, consuming one dispatch slot.
 * @param taskId - Task to move.
 * @param options - Host authority guard at the serialized write boundary.
 * @returns the updated record.
 */
async startDevelopment(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord>

/**
 * Move a developing task into lead review.
 * @param taskId - Task to move.
 * @param options - Host authority guard at the serialized write boundary.
 * @returns the updated record.
 */
async beginReview(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord>

/**
 * Submit a reviewed task for integration.
 * @param taskId - Task to move.
 * @param options - Host authority guard at the serialized write boundary.
 * @returns the updated record.
 */
async submit(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord>

/**
 * Return a reviewed task for correction after an explicit negative review.
 * @param taskId - Reviewing task to return to its assigned Worker.
 * @param options - Host authority guard at the serialized write boundary.
 * @returns Task in developing, consuming one development slot.
 */
async returnToDevelopment(taskId: TaskId, options: TaskMutationOptions = {}): Promise<TaskRecord>

/**
 * Mint a main-tree merge marker for a submitted task. Only a session whose
 * binding carries the `controller` role may trigger the merge; the marker
 * is single-use and process-local.
 * @param callerSessionId - Session requesting the merge.
 * @param taskId - Task to merge.
 * @param request - Exact Git inputs and the host-owned approved-checks store.
 * @returns the marker to hand to {@link ProjectController.integrate}.
 */
async requestMainTreeMerge( callerSessionId: SessionId, taskId: TaskId, request: MainTreeMergeRequest, ): Promise<MainTreeMergeMarker>

/**
 * Execute the admitted fast-forward once, then record integration only after observing the exact clean target.
 * @param taskId - Task to move; the marker must name it.
 * @param marker - The marker minted by {@link ProjectController.requestMainTreeMerge}.
 * @returns the updated record.
 */
async integrate(taskId: TaskId, marker: MainTreeMergeMarker): Promise<TaskRecord>

/**
 * Reconcile a durable intent after interruption without issuing another Git merge.
 * @param callerSessionId - The same controller that admitted the original operation.
 * @param taskId - Task whose retained intent is being reconciled.
 * @param options - Explicit deployment process limits for read-only Git observations.
 * @returns The actual Git observation; only `applied` advances the task board.
 */
async reconcileMainTreeIntegration( callerSessionId: SessionId, taskId: TaskId, options: IntegrationGitOptions, ): Promise<IntegrationGitObservation>

/**
 * Complete an integrated task.
 * @param taskId - Task to move.
 * @returns the updated record.
 */
async complete(taskId: TaskId): Promise<TaskRecord>

/**
 * Block a task from any active state; the recovery triple is mandatory.
 * @param taskId - Task to move.
 * @param detail - Reason, next action, and wake condition.
 * @returns the updated record.
 */
async block(taskId: TaskId, detail: TaskBlockDetail): Promise<TaskRecord>

/**
 * Fail a task from any active state; the recovery triple is mandatory.
 * @param taskId - Task to move.
 * @param detail - Reason, next action, and wake condition.
 * @returns the updated record.
 */
async fail(taskId: TaskId, detail: TaskBlockDetail): Promise<TaskRecord>

/**
 * Resume a blocked or failed task back into dispatch through `assigned`;
 * the recovery triple is cleared on the way out.
 * @param taskId - Task to move.
 * @param assigneeSessionId - Replacement assignee; omitted, the previous one is kept.
 * @returns the updated record.
 */
async resume(taskId: TaskId, assigneeSessionId?: SessionId): Promise<TaskRecord>

/**
 * Charge one granted-and-billed model request against the project's
 * cumulative budget. The request that fills the last budget slot is
 * admitted; any further charge is rejected until the deployment raises
 * `requestBudget`. Concurrent charges from racing controller/child sessions
 * serialize on the controller's write chain, so a full budget admits
 * exactly one of them, and the charge persists before the receipt returns —
 * a retry or a process restart never resets usage.
 * @returns the receipt with the cumulative charged count, the configured
 *   budget, and the remaining allowance after this charge.
 * @throws {@link ProjectControllerError} with
 *   `PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED` when every budget unit is
 *   already spent, `PROJECT_CONTROLLER_ADMISSION_CLOSED` when the project
 *   lifecycle is not admitting dispatch work, or
 *   `PROJECT_CONTROLLER_PERSISTENCE` when the usage write failed.
 */
async chargeModelRequest(): Promise<RequestChargeReceipt>

/**
 * Read the request-budget accounting without charging.
 * @returns the configured budget, the cumulative charged count, and the
 *   remaining allowance (clamped at zero once exhausted).
 */
requestBudgetUsage(): { readonly requestBudget: number readonly chargedRequests: number readonly remainingRequests: number }

/**
 * Read one task from the restored board.
 * @param taskId - Task identity selecting the record.
 * @returns the record, or `undefined` when the task does not exist.
 */
find(taskId: TaskId): TaskRecord | undefined

/**
 * Read every task carrying one state.
 * @param state - State to filter by.
 * @returns the matching records in stable (createdAt, taskId) order.
 */
byState(state: TaskState): readonly TaskRecord[]

/**
 * Read the whole board in stable (createdAt, taskId) order.
 * @returns all restored or written records.
 */
list(): readonly TaskRecord[]
```

Types: [IntegrationGitObservation](../../packages/experimental/project-controller/README.md) · [IntegrationGitOptions](../../packages/experimental/project-controller/README.md) · [MainTreeMergeRequest](../../packages/experimental/project-controller/README.md) · [SessionId](core.md) · [TaskMutationOptions](../../packages/experimental/project-controller/README.md)

Source: [`packages/experimental/project-controller/src/controller.ts`](../../packages/experimental/project-controller/src/controller.ts)
<!-- END GENERATED cordis-surface -->
