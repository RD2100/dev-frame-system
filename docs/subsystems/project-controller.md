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
 * @returns the stored record.
 */
async createTask(request: { readonly taskId: TaskId; readonly pluginId: PluginId; readonly title: string }): Promise<TaskRecord>

/**
 * Assign a planned task to a session.
 * @param taskId - Task to move.
 * @param assigneeSessionId - Session bound to execute the task.
 * @returns the updated record.
 */
async assign(taskId: TaskId, assigneeSessionId: SessionId): Promise<TaskRecord>

/**
 * Move an assigned task into development, consuming one dispatch slot.
 * @param taskId - Task to move.
 * @returns the updated record.
 */
async startDevelopment(taskId: TaskId): Promise<TaskRecord>

/**
 * Move a developing task into lead review.
 * @param taskId - Task to move.
 * @returns the updated record.
 */
async beginReview(taskId: TaskId): Promise<TaskRecord>

/**
 * Submit a reviewed task for integration.
 * @param taskId - Task to move.
 * @returns the updated record.
 */
async submit(taskId: TaskId): Promise<TaskRecord>

/**
 * Mint a main-tree merge marker for a submitted task. Only a session whose
 * binding carries the `controller` role may trigger the merge; the marker
 * is single-use and process-local.
 * @param callerSessionId - Session requesting the merge.
 * @param taskId - Task to merge.
 * @returns the marker to hand to {@link ProjectController.integrate}.
 */
async requestMainTreeMerge(callerSessionId: SessionId, taskId: TaskId): Promise<MainTreeMergeMarker>

/**
 * Consume one merge marker and move the task to `integrated`.
 * @param taskId - Task to move; the marker must name it.
 * @param marker - The marker minted by {@link ProjectController.requestMainTreeMerge}.
 * @returns the updated record.
 */
async integrate(taskId: TaskId, marker: MainTreeMergeMarker): Promise<TaskRecord>

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

Types: [SessionId](core.md)

Source: [`packages/experimental/project-controller/src/controller.ts`](../../packages/experimental/project-controller/src/controller.ts)
<!-- END GENERATED cordis-surface -->
