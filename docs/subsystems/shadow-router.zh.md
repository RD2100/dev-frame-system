# Shadow 项目路由

[English](shadow-router.md) | 中文

Shadow 路由子系统是插件化 agent（智能体）层级的 Shadow 侧路由器：在相互独立的项目根之间路由用户意图。它把每个工作区一条控制器绑定保存在自己的 `shadow_router` 存储域中，为每个项目以准确的 `cwd` 元数据预置独立的控制器根会话，把每次跨根投递持久化两次——发送方的 `queued` 意图与目标已接受的 `received` 输入——`completed` 则是另一个独立的持久状态，并把恰好四个项目工具（`project_open`、`project_send`、`project_status`、`project_stop`）安装进宿主指定为 Shadow 的那一个 agent 作用域。停止按项目隔离：其他绑定、它们的控制器与队列都不受影响。[包 README](../../packages/experimental/shadow-router/README.zh.md) 负责挂载配置与模型体验。

## 服务面

`ctx.shadowRouter` 是路由器。核心操作：

- `markShadow` — 只把四个项目工具装进该 agent 的作用域；其他作用域解析不到其中任何一个。
- `openProject`、`sendToProject`、`stopProject`、`projectStatus` — 与四个工具派发到的相同方法：open 把一个已授权的既有目录解析为工作区与控制器根，send 投递一条有界的 `work`/`note` 消息并返回绝不声称已完成的 `received` 回执，status 读取单个项目或有界分页，stop 恰好停止一个项目并在宿主确认前报告 stopping。
- 模型永远触达不了的宿主专属 seam — `setActiveGoal` 为每个项目授权一个进行中的运行，`completeDelivery` 结清一条已接收投递，`confirmProjectStopped` 完成一次停止，`recoverDeliveries` 与 `reconcileProject` 在重启时收敛被中断的行。
- 查询 — `findBinding`、`listBindings`、`listDeliveries` 从启动时恢复的索引作答。

## 约定要点

每次失败都在 `ShadowRouterError` 上返回结构化的 `SHADOW_*` 代码（陈旧修订、未知工作区、未授权调用方、超长文本、队列已满、根缺失或未授权、根重叠、profile 冲突、goal 陈旧或未授权、接收方已关闭、需要关注、项目已停止、请求冲突、无效配置或请求、持久化失败）——绝不是裸存储错误。绑定、投递与回放日志位于 [存储域](storage.zh.md) `shadow_router`（bindings、deliveries、requests 三张表）。预置是每项目的状态机（`reserving → provisioning → ready`），先持久化每一步再执行它，因此任意时刻的崩溃都会留下一行，由后续 open 或宿主 reconcile 收敛。`sendToProject` 先把发送方意图持久化为 `queued`，再把目标已接受的输入标记为 `received`；`completed` 是宿主另行结清的控制器侧事实，且它们是仅有的前进流转——被取消的 queued 行带着原因保持可见。每次 open/send/stop 都以调用方的 `requestId` 为键存储规范化输入哈希与结果，因此重试会重放已存结果，同一 id 携带不同输入则以 `SHADOW_REQUEST_CONFLICT` 大声失败。配置 fail closed：空的 `authorizedRoots` 什么都打不开，配置同时固定 `controllerProfile`、`maxPendingDeliveries`、`maxMessageChars` 与 `statusPageSize`。

## 子系统边界

路由复用 [workspace](workspace.zh.md) 子系统的规范路径事实（`fs.realpath` 规范、别名折叠、感知路径段的重叠检查），但有意不复用 agent 团队的邮箱成员校验——Shadow 目标由绑定存储授权，而不是由[团队成员关系](agent-team.zh.md)授权。它读取的绑定记录记录在[会话身份绑定](session-identity.zh.md)，控制器根经 [session](session.zh.md) 存储预置，`setActiveGoal` 对照运行绑定的 [goal](goal.zh.md) 身份授权。把 received 输入写入控制器的会话日志是宿主组合的职责，因此裸挂载不会收到任何模型可见内容。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxshadowrouter--shadowrouter"></a>

### `ctx.shadowRouter` — `ShadowRouter`

The shadow router: binding store, cross-root delivery, and the Shadow tool whitelist.

```ts cordis-catalog
/**
 * Designate one live agent as the host's Shadow and install the four
 * project tools — and nothing else — into its scope. The host chooses the
 * profile; workers, leads, and reviewers are never marked, and marking is
 * idempotent.
 * @param agent - The live agent the host designates as Shadow.
 */
markShadow(agent: Agent): void

/**
 * Whether one agent is the designated Shadow.
 * @param agent - The agent to check, or `undefined` when the caller has no attached agent.
 * @returns true when the agent is currently designated as the host's Shadow; the predicate also narrows `agent` to `Agent`.
 */
isShadow(agent: Agent | undefined): agent is Agent

/**
 * Open (or resolve) one project: canonicalize and authorize the root, reuse
 * the workspace registry's identity, and converge the controller binding —
 * reserving a controller session id and persisting the in-creation
 * association before the session exists. Repeated opens deduplicate; a
 * request id replayed with different input conflicts.
 * @param caller - The designated Shadow session.
 * @param request - Existing authorized path and stable request id.
 * @returns the controller association.
 */
async openProject(caller: Agent | undefined, request: ProjectOpenRequest): Promise<ProjectOpenResult>

/**
 * Deliver one bounded message to a project's controller. The delivery is
 * persisted twice on purpose: first as the sender intent (`queued`), then as
 * the target-accepted input (`received`). The receipt never claims
 * completion; `completed` is a separate durable state the controller side
 * settles via {@link ShadowRouter.completeDelivery}.
 * @param caller - The designated Shadow session.
 * @param request - Target workspace, asserted revision and work ownership, mode, and text.
 * @returns the delivery receipt.
 */
async sendToProject(caller: Agent | undefined, request: ProjectSendRequest): Promise<ProjectSendResult>

/**
 * Stop one project in isolation: close its receiving, cancel its pending
 * deliveries (kept visible, never dropped), and park the binding in
 * `stopping` until the host confirms quiescence via
 * {@link ShadowRouter.confirmProjectStopped}. Other projects are untouched.
 * @param caller - The designated Shadow session.
 * @param request - Target workspace, asserted revision, and stable request id.
 * @returns the stop receipt.
 */
async stopProject(caller: Agent | undefined, request: ProjectStopRequest): Promise<ProjectStopResult>

/**
 * Read one project or one bounded page of projects. The read never mutates
 * durable state, never appends a session event, and never wakes a model;
 * every row carries the observation instant, and a `received` receipt is
 * reported verbatim instead of being read as completion.
 * @param caller - The designated Shadow session.
 * @param request - Optional workspace id plus bounded page controls.
 * @returns the observed status.
 */
async projectStatus( caller: Agent | undefined, request: { readonly workspaceId?: string; readonly cursor?: number; readonly limit?: number }, ): Promise<ProjectStatusResult>

/**
 * Confirm one `stopping` project quiescent and finish its stop. The host
 * calls this once the project's own work has drained; no model tool does.
 * Already-stopped bindings resolve without writing.
 * @param workspaceId - The project whose stop completes.
 * @returns the stopped binding.
 */
async confirmProjectStopped(workspaceId: WorkspaceId): Promise<ShadowBindingRecord>

/**
 * Record the workspace's authorized open run. Deliveries may only arrive
 * while the asserted Goal/acceptance association matches this record, which
 * is what keeps a previous Goal's message out of the controller's current
 * Goal. The host (controller side) calls this; no model tool reaches it.
 * @param workspaceId - The project to authorize the run for.
 * @param goalId - The authorized Goal.
 * @param acceptanceHash - The authorized acceptance association.
 * @returns the updated binding.
 */
async setActiveGoal(workspaceId: WorkspaceId, goalId: string, acceptanceHash: string): Promise<ShadowBindingRecord>

/**
 * Settle one received delivery as completed. `completed` is a controller
 * side durable fact, distinct from the `received` receipt; the host calls
 * this, and no model tool does. A receiver that is `stopping` or `stopped`
 * cannot settle: the call rejects with `SHADOW_RECEIVER_CLOSED` and the row
 * stays `received`.
 * @param workspaceId - The project the delivery belongs to.
 * @param messageId - The delivery to settle.
 * @returns the updated delivery.
 */
async completeDelivery(workspaceId: WorkspaceId, messageId: ShadowMessageId): Promise<ShadowDeliveryRecord>

/**
 * Converge one workspace's queued deliveries after a restart or a Goal
 * switch: a still-authorized delivery becomes `received`; a stale one is
 * cancelled with a visible reason instead of being forwarded to a Goal it
 * was never bound to.
 * @param workspaceId - One project, or omitted for every project.
 * @returns the converged deliveries.
 */
async recoverDeliveries(workspaceId?: WorkspaceId): Promise<readonly ShadowDeliveryRecord[]>

/**
 * Converge one workspace's provisioning row around its reserved session id:
 * create the reserved session when it is still missing, complete the bind
 * when the session matches, and park mismatches as `needs_attention`. The
 * host calls this after a restart; `project_open` runs it implicitly.
 * @param workspaceId - The project to converge.
 * @returns the converged binding.
 */
async reconcileProject(workspaceId: WorkspaceId): Promise<ShadowBindingRecord>

/**
 * Read one binding from the restored index.
 * @param workspaceId - The project whose binding to read.
 * @returns the binding record, or `undefined` when the workspace has no binding.
 */
findBinding(workspaceId: WorkspaceId): ShadowBindingRecord | undefined

/**
 * Read every binding in stable (createdAt, workspaceId) order.
 * @returns every binding record in the index.
 */
listBindings(): readonly ShadowBindingRecord[]

/**
 * Read every delivery of one project (or all projects), oldest first.
 * @param workspaceId - Limits the result to one project; omit it to read every recorded delivery.
 * @returns the matching delivery records in stable (createdAt, messageId) order.
 */
listDeliveries(workspaceId?: WorkspaceId): readonly ShadowDeliveryRecord[]
```

Types: [Agent](core.zh.md) · [WorkspaceId](workspace.zh.md)

Source: [`packages/experimental/shadow-router/src/service.ts`](../../packages/experimental/shadow-router/src/service.ts)
<!-- END GENERATED cordis-surface -->
