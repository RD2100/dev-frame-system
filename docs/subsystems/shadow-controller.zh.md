# Shadow 控制器

[English](shadow-controller.md) | 中文

Shadow 面板 Remote 面的宿主侧属主：由 Web Shadow 卡片驱动的 `shadow` Remote 命名空间。`ctx.shadowController`（[`ShadowController`](../../packages/experimental/shadow-controller)，Typert Remote 服务）提供如实的聚合状态读取与三个面板写入面，每一条都委托给 shadow router 的宿主桥，并以指定 Shadow 自身的授权运行——校验、调用方门禁、重放与投递通道都由路由器负责，且每次面板动作的 request id 在此铸造，因为每个动作都是一次全新意图。`ctx.shadowAgent`（[`ShadowAgent`](../../packages/experimental/shadow-controller)，同包）是持久的 Shadow 对话宿主：一个作为部署指定 Shadow 的持久代理会话，为人类提供发布与读取的对话面。部署未挂载 shadow router 或对话宿主时控制器仍然注册：读取返回 `mounted: false`，其余动词响亮失败，于是界面渲染出如实的禁用态而不是传输失败。本包是实验性私有包：不随任何发布版交付。

Source: [`packages/experimental/shadow-controller/src/index.ts`](../../packages/experimental/shadow-controller/src/index.ts)

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxshadowagent--shadowagent"></a>

### `ctx.shadowAgent` — `ShadowAgent`

Host service behind the controller's conversation verbs. Registered as `ctx.shadowAgent`; every verb resolves the designated session on demand.

```ts cordis-catalog
/**
 * Resolve the live Shadow agent, creating or restoring the designated
 * session on first use. Memoized; a failure is not memoized, so the next
 * verb retries.
 * @returns the live Shadow agent.
 */
async ensure(): Promise<Agent>

/**
 * Post one human message into the Shadow session. The agent loop claims it
 * and runs the turn; the reply lands on the persisted conversation surface,
 * observable through {@link readConversation}.
 * @param text - Non-empty message text from the human.
 * @returns the accepted message's stable id.
 */
async postMessage(text: string): Promise<{ readonly messageId: string }>

/**
 * Read the Shadow conversation surface, bounded and cursor-addressed.
 * Without `after`, the last up-to-`limit` rows; with `after`, the rows
 * beyond that sequence number. `cursor` is the log length at read time, or
 * the last returned row when the page truncated — poll by passing it back.
 * @param request - Optional cursor and page bound.
 * @returns the page of rows plus the continuation cursor.
 */
async readConversation(request: { readonly after?: number; readonly limit?: number }): Promise<ShadowConversationPage>
```

Types: [Agent](core.zh.md)

Source: [`packages/experimental/shadow-controller/src/shadow-agent.ts`](../../packages/experimental/shadow-controller/src/shadow-agent.ts)

<a id="ctxshadowcontroller--shadowcontroller"></a>

### `ctx.shadowController` — `ShadowController`

Host service backing the generated `ctx.remote.shadow` namespace. The read never mutates router state; every write runs through the router's host bridges under the designated Shadow's authority, and the conversation verbs run through the conversation host's persistent session.

```ts cordis-catalog
/**
 * Read the aggregate Shadow status: mount presence, designation, controller
 * liveness, authorized roots, and open-project rows.
 * @returns the router's snapshot, or the honest `mounted: false` answer when
 *   this deployment composes no shadow router.
 */
@Remote readStatus(): ShadowStatusView

/**
 * Open the project at one path under an authorized root: validate, provision
 * the project's controller session, and persist the controller role.
 * @param request - The project path to open.
 * @returns the controller association.
 */
@Remote async openProject(request: ShadowProjectOpenInput): Promise<ProjectOpenResult>

/**
 * Deliver one `work` message to a project's controller session through the
 * router's delivery channel, with the binding's current revision and
 * authorized open run supplied by the router.
 * @param request - Target workspace and bounded message text.
 * @returns the delivery receipt.
 */
@Remote async sendToController(request: ShadowProjectSendInput): Promise<ProjectSendResult>

/**
 * Release (stop and close) one project: cancel pending deliveries and land
 * the row on `stopped`, staying visible in the panel.
 * @param request - The workspace to release.
 * @returns the stop receipt.
 */
@Remote async releaseProject(request: ShadowProjectReleaseInput): Promise<ProjectStopResult>

/**
 * Post one human message into the designated Shadow session. The session's
 * agent loop claims it and runs the turn; the reply lands on the persisted
 * conversation surface.
 * @param request - The human's message text.
 * @returns the accepted message's stable id.
 */
@Remote async postMessage(request: ShadowConversationPostInput): Promise<ShadowConversationAccepted>

/**
 * Read the Shadow conversation surface, bounded and cursor-addressed.
 * @param request - Optional continuation cursor and page bound.
 * @returns the page of conversation rows plus the continuation cursor.
 */
@Remote async readConversation(request: ShadowConversationReadInput): Promise<ShadowConversationPage>

/**
 * Approve a planned task for development from the board. Resolves the same
 * start authority the `project_task start` tool enforces (live root
 * controller, open Goal admitting the task, exactly one Worker and lead,
 * three independent locked worktrees), persists the host-approved
 * `git diff --check` checkset into the required-checks ledger, registers it
 * with the delivery registry, then assigns and starts development under
 * write-boundary drift re-checks. The Worker receives one briefing; the
 * designated Shadow session receives a structured message (best-effort: a
 * conversation-host failure does not fail an already-admitted start).
 * A task that is neither planned nor blocked, or whose provisioning is
 * incomplete, fails loud without advancing state.
 * @param request - The workspace binding and the planned task id.
 * @returns the task's state after admission.
 */
@Remote async approveTask(request: ShadowApproveTaskInput): Promise<ShadowApproveTaskResult>

/**
 * Reject a planned task from the board: block it with the host reason so
 * the board shows the recovery triple instead of silently dropping the
 * task. Only a planned task may be rejected; anything already started
 * fails loud (recovery of active tasks uses the project tools).
 * @param request - The workspace binding, the planned task id, and the reason.
 * @returns the task's blocked state.
 */
@Remote async rejectTask(request: ShadowRejectTaskInput): Promise<ShadowRejectTaskResult>

/**
 * Read the whole task board: mount presence, the workspace binding digest,
 * and every task folded from the controller's stable (createdAt, taskId)
 * order. The read is side-effect free: `startReady` derives from the same
 * start authority the approve face enforces (any resolution failure or
 * missing authority reads false, so the board greys the approve action
 * without advancing state), and `branch` comes from the worktree registry's
 * live status observation. A deployment without a projectController answers
 * the honest `mounted: false` empty board; a missing shadow router or
 * worktree registry degrades the respective section rather than failing.
 * @returns the board snapshot.
 */
@Remote async readBoard(): Promise<ShadowBoardSnapshot>
```

Source: [`packages/experimental/shadow-controller/src/index.ts`](../../packages/experimental/shadow-controller/src/index.ts)
<!-- END GENERATED cordis-surface -->
