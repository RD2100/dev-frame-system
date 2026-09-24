# 项目任务控制器

[English](project-controller.md) | 中文

项目控制器子系统持有项目任务板：让任务沿共享的 `TaskState` 顺序流转，每次 `blocked` 或 `failed` 流转都要求原因、下一步动作与唤醒条件，经校验的 `maxActiveTasks` 配置约束同时处于 `developing` 的任务数（默认 2），运行 DevFrame 项目生命周期，并把主树集成关在仅控制器可铸造的合并标记之后。任务记录经 `project_tasks` 存储域持久化并在启动时原样恢复；生命周期本身是进程本地运行状态，由新进程用 `startProject` 显式打开。[包 README](../../packages/experimental/project-controller/README.zh.md) 负责挂载配置与模型体验。

## 服务面

`ctx.projectController` 是任务板所有者。核心操作：

- 生命周期 — `startProject`、`requestStop`、`confirmQuiescence`、`completeStop`，另有经 `markNeedsAttention` 与 `markAmbiguous` 的 `needs_attention` 与 `ambiguous` 侧状态。
- 任务流转 — `createTask`、`assign`、`startDevelopment`、`beginReview`、`submit`、`requestMainTreeMerge`、`integrate`、`complete`，以 `block`、`fail`、`resume` 作为恢复三元组路径；每次流转返回更新后的记录，非法流转大声失败而不是重写状态。
- 查询 — `find`、`byState`、`list` 从启动时恢复的任务板作答。

## 约定要点

每次失败都在 `ProjectControllerError` 上携带稳定的 `PROJECT_CONTROLLER_*` 代码（非法流转、并发超限、标记无效、非控制器、未完全停稳、任务已存在或未知、准入关闭、无效配置或详情、持久化失败）。任务板位于 [存储域](storage.zh.md) `project_tasks`，是启动时由单张域表重建的 write-through 投影。`maxActiveTasks` 恰好在任务将进入 `developing` 的位置强制执行；离开开发（`beginReview`）即释放名额。派发路径流转要求 `admission_open`；记录型流转（`block`、`fail`、`complete`）在项目未停止前始终可用，因此停止仍能记录工作为何结束。合并门只为绑定携带 `controller` 角色的会话铸造单次使用、进程本地的标记，且 `integrate` 先校验标记再检查状态，因此已消费的标记即使任务已流转也会报告 `MARKER_INVALID`；标记跨重启永不恢复。

## 子系统边界

合并门对照[会话身份绑定](session-identity.zh.md)校验调用方角色，提交溯源由[代理证据账本](agent-evidence.zh.md)记录。派发路径的准入要求建立在[代理可靠性服务](agent-reliability.zh.md)之上。共享的 `TaskRecord`、`TaskState`、`PluginId` 类型属于 [project-contracts 包](../../packages/experimental/project-contracts/README.zh.md)。生命周期约束的是任务状态，不是活跃模型请求——请求上限仍是部署的账户级约束。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxprojectcontroller--projectcontroller"></a>

### `ctx.projectController` — `ProjectController`

The project controller: task board, dispatch budget, lifecycle, and merge gate.

```ts cordis-catalog
/**
 * Read the durable integration receipts owned by one controller Session.
 * @param controllerSessionId - Controller whose completion reads these receipts.
 * @returns Detached receipts, including unfinished integration attempts.
 */
integrationReceipts(controllerSessionId: SessionId): readonly MainTreeIntegrationRecord[]

/**
 * Require the live root controller to retain its registered integration target.
 * @param agent - Exact invoking Agent.
 * @param targetPath - Target persisted in the integration receipts.
 * @param workspaceId - Workspace authorized by the current Goal.
 */
assertCompletionOwner(agent: Agent, targetPath: string, workspaceId: WorkspaceId): void

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
 * Execute the admitted integration once in its prepared mode, then record integration only after observing the exact clean target.
 * @param taskId - Task to move; the marker must name it.
 * @param marker - The marker minted by {@link ProjectController.requestMainTreeMerge}.
 * @returns the updated record.
 */
async integrate(taskId: TaskId, marker: MainTreeMergeMarker): Promise<TaskRecord>

/**
 * Reconcile a durable intent after interruption without issuing another Git merge.
 * An applied receipt pins the recorded head exactly; a prepared intent whose
 * Git already applied repairs recording from the observed merge commit.
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
 * Reserve one model sending attempt against the project's
 * cumulative budget. The request that fills the last budget slot is
 * admitted; any further charge is rejected until the deployment raises
 * `requestBudget`. Concurrent charges from racing controller/child sessions
 * serialize on the controller's write chain, so a full budget admits
 * exactly one of them, and the charge persists before the receipt returns —
 * a retry or a process restart never resets usage. A reservation does not
 * prove supplier billing and is not refunded after cancellation. An uncertain
 * storage write closes further charging until the service is reloaded.
 * @param options - Host authority guard checked inside the charge queue.
 * @returns the receipt with the cumulative charged count, the configured
 *   budget, and the remaining allowance after this charge.
 * @throws {@link ProjectControllerError} with
 *   `PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED` when every budget unit is
 *   already spent, `PROJECT_CONTROLLER_ADMISSION_CLOSED` when the project
 *   lifecycle is not admitting dispatch work, or
 *   `PROJECT_CONTROLLER_PERSISTENCE` when the usage write failed.
 */
async chargeModelRequest(options?: TaskMutationOptions): Promise<RequestChargeReceipt>

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

Types: [Agent](core.zh.md) · [IntegrationGitObservation](../../packages/experimental/project-controller/README.zh.md) · [IntegrationGitOptions](../../packages/experimental/project-controller/README.zh.md) · [MainTreeIntegrationRecord](../../packages/experimental/project-controller/README.zh.md) · [MainTreeMergeRequest](../../packages/experimental/project-controller/README.zh.md) · [SessionId](core.zh.md) · [TaskMutationOptions](../../packages/experimental/project-controller/README.zh.md) · [WorkspaceId](workspace.zh.md)

Source: [`packages/experimental/project-controller/src/controller.ts`](../../packages/experimental/project-controller/src/controller.ts)

<a id="ctxprojectdeliveryregistry--projectdeliveryregistry"></a>

### `ctx.projectDeliveryRegistry` — `ProjectDeliveryRegistry`

Host-updatable delivery registry (`ctx.projectDeliveryRegistry`): the runtime source of approved checksets and commit scopes the delivery tools read at call time. Seeded from deployment config; the host registers each task's approved checkset and commit scope at approval time, so plan-time registration and delivery-time reads can never race. Idempotent: a re-registration replaces the previous entry, unregistering an absent task is a no-op.

```ts cordis-catalog
/**
 * Register or replace the delivery configuration of one task.
 * @param taskId - The task being approved.
 * @param registration - Approved checkset digest and optional commit scope.
 */
registerTask(taskId: TaskId, registration: TaskDeliveryRegistration): void

/**
 * Drop the delivery configuration of one task.
 * @param taskId - The task whose delivery configuration is removed.
 */
unregisterTask(taskId: TaskId): void
```

Source: [`packages/experimental/project-controller/src/delivery-consumer.ts`](../../packages/experimental/project-controller/src/delivery-consumer.ts)
<!-- END GENERATED cordis-surface -->
