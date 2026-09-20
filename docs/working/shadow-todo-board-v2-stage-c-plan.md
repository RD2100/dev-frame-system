---
title: Shadow Todo 看板 v2 — 阶段 C 实施计划（修订 2）
owner: shadow
status: draft-plan-r2
date: 2026-09-20
previous:
  - docs/working/shadow-todo-board-v2-plan.zh.md（总计划 r3，§2C 为阶段 C 设计）
  - docs/working/shadow-todo-board-v2-stage-b-review.md（阶段 B 验收通过；P1-1 commitPaths 为阶段 C 集成前置）
  - docs/working/shadow-todo-board-v2-stage-c-plan.md（r1 计划，四路评审）
  - docs/working/shadow-todo-board-v2-stage-c-plan-review.md（评审：有条件通过，P0×0、P1×12、P2×9）
---

# Shadow Todo 看板 v2 — 阶段 C 实施计划（修订 2）

> 本版在 r1 基础上**全部落实评审 12 条 P1**（readBoard 改 async、commitPaths 指错文件修正、ui-conversation 依赖声明、branch 采集复用 worktreeRegistry.status、shadowSessionId 接线闭环、label thunk、验收截图、blocked 重新批准、#21 deferred、mounted:false/shadowRouter 缺失测试补列、spec 归属），并吸收 P2-1/2/3/4/5/6/7/9（P2-8 为执行时注意事项，写入 §6）。

## 0. 目标与范围

把阶段 B 打通的任务状态机（HITL 门 + 预配链）变成**用户可见的六列看板**：host 侧新增 `shadow.readBoard()` Remote（**异步**），client 侧新增 BoardView（六列投影 + 批准/打回/重新批准动作 + 等待标记），并解决阶段 B 验收 P1-1 的 commitPaths 闭环，使首轮端到端（plan→approve→develop→deliver→review→integrate）能真正跑通。

**改动包**（3 个 + 1 个部署文件）：

| 包/文件 | 改动 |
|---|---|
| `packages/experimental/shadow-controller` | types.ts 增 `ShadowBoardSnapshot`；index.ts 增 `@Remote async readBoard()` |
| `packages/experimental/project-controller` | delivery-consumer Config 增 `defaultCommitPaths`（Q-C1） |
| `packages/experimental/client-ui-shadow-entry` | BoardView + ShadowBoardController + mount 注册 + locales + **package.json 补 ui-conversation 依赖（P1-3）** |
| `apps/desktop/scripts/development-project.ts` | patch 增 delivery-consumer `defaultCommitPaths`（首轮验收任务固定产出） |

---

## 1. 决策

### Q-C1 commitPaths 闭环（阶段 B 验收 P1-1，必解）

**问题**：approveTask 的 `commitPaths` 来自 request（**`packages/experimental/shadow-controller/src/types.ts:88`**，`readonly commitPaths?: readonly string[]`；**不改 project-contracts**，该包 :88 是 TaskRecord.pluginId）；而 deliver 要求 worktree 干净（delivery-consumer.ts:215 `git('status','--porcelain=v1','--untracked-files=all') !== ''` → throw :216）。若永远不 pin，worker 产出后 `project_commit` 恒拒（commit-consumer.ts:303-306），交付永远无法走完。首轮全链路 e2e 必须 pin。

**证据（已核实）**：
- commit scope 是**精确路径集合**：commit-consumer.ts:307 `new Set(scope)` + :308 精确 `has()` 匹配，非目录前缀。
- `normalizeCommitPaths` 拒绝空、绝对路径、`''`/`'.'`/`'..'`/`.git` 段、超 64 条/超长（commit-consumer.ts:174-192），scope 至少一个路径。
- `requirePathsInWorktree` 对 model 请求的每个路径要求**已存在的文件**且在 worktree 内（:203-223）——model 侧按文件提交。
- approveTask 无法在批准时枚举 worker 未来产出（index.ts:210-213 注释原意，fail-closed 语义属实）。

**决策（方案 A，评审确认可行）**：delivery-consumer Config 新增可选 `defaultCommitPaths?: string[]`（z.object 未 `.strict()`，新增可选键不拒绝既有部署 YAML，先例 `commitPathsByTask?` :96/:104）；`ProjectDeliveryRegistry` 接口（:54-69）新增 `readonly defaultCommitPaths?: readonly string[]`；approveTask 注册时（index.ts:214-217 三元处）`commitPaths = request.commitPaths ?? registry.defaultCommitPaths`——两者皆无则保持 fail-closed（行为与现状逐字节一致）。apply 时（registry 字面量 :552-567）对默认值经 `normalizeCommitPaths` 归一化（空数组 fail-loud，对齐 commit-consumer.ts:175 语义；normalizeCommitPaths 已 export 且已 import）。

**职责差异（P2-3 补注）**：既有 `commitPathsByTask` 是 **apply 期静态 seed**（按 taskId 精确键控，首轮静态 goal-binding 的 taskId 可用）；新增 `defaultCommitPaths` 是 **approve 期兜底**（approveTask 动态注册时 `??` 合并）。静态 seed 与动态注册二者取其一即可，本阶段优先用动态注册路径走通首轮，静态 seed 保持现状不动。

**桌面首轮取值**：首轮 e2e 的验收任务由用例固定产出（如"修改 `packages/experimental/project-controller/src/index.ts` 增加一行注释"），`defaultCommitPaths` 配置为该文件相对路径；更通用的"task→路径"映射记入 §3 偏离（与总计划 §7 多轮任务机制同列，deferred）。

**方案 B（不采纳首轮）**：commit scope 放宽为前缀匹配——动 commit-consumer 语义与既有测试（commit-consumer.spec.ts 26 条），超出阶段 C 范围，记录为后续候选。

### Q-C2 readBoard 契约

`ShadowBoardSnapshot`（types.ts 新增）：

```ts
export interface ShadowBoardSnapshot {
  /** Whether this deployment mounts a projectController at all. */
  readonly mounted: boolean
  /** Workspace binding digest from shadowRouter.listBindings(). */
  readonly bindings: readonly ShadowBoardBinding[]
  /** Whole board in stable (createdAt, taskId) order. */
  readonly tasks: readonly ShadowBoardTask[]
}

export interface ShadowBoardBinding {
  readonly workspaceId: string
  readonly state: string
  /** Required in the binding record; keep as string (P2-5 收窄). */
  readonly controllerSessionId: string
}

export interface ShadowBoardTask {
  readonly taskId: string
  readonly pluginId: string
  readonly title: string
  readonly state: string
  readonly blockedReason?: string
  readonly nextAction?: string
  readonly wakeCondition?: string
  readonly createdAt: string
  readonly updatedAt: string
  /** Host-derived readiness of a planned task to start; planned tasks only. */
  readonly startReady?: boolean
  /** Current branch of the worker worktree; assigned/developing only, failure → null. */
  readonly branch?: string | null
}
```

- **签名：`@Remote async readBoard(): Promise<ShadowBoardSnapshot>`**（P1-1：branch 采集走异步 API；同包所有异步 Remote 均显式 async/Promise）。
- `mounted: false` 时返回空 bindings/tasks（降级而非 fail-loud，对齐 Q2/r2 P2-7 决策：UI 显示 disabled 态）。**依赖服务不齐（agentBindings/workspaceRegistry 等缺）时 startReady 全 false，而非 mounted:false**（P2-6 注释语义）。
- 数据来源：`ctx.projectController.list()`（controller.ts:891-894，稳定 createdAt/taskId 序）+ `ctx.shadowRouter.listBindings()`（抽象接口在 `packages/experimental/shadow-routing/src/service.ts:243`，实现在 `packages/experimental/shadow-router/src/service.ts:880`；P2-4 补全包名）。`ctx.get('shadowRouter')` 缺失 → bindings 空数组（mounted 仍按 projectController 判定）。
- **startReady 派生**：对每个 `planned` 任务调用 `resolveTaskStartAuthority(ctx, controllerAgent, taskId, () => false)`（start-authority.ts:105-110 **同步纯读**，无副作用；:77 controllerAgent 缺失/离线 throw）——成功 → `true`，异常捕获 → `false`（只读派生，不推进状态）。
- **branch 采集（P1-4 修订）**：对 `assigned`/`developing` 任务，**复用 `ctx.worktreeRegistry.status(worktreeId)` 实时只读 API**（worktree-registry/src/registry.ts:109，返回 `{ branch }`；Worktree 行另带创建时 branch 快照 :79-99），**不自造 git 子进程、不自管缓存**——status() 是仓库一等只读查询，符合 prefer-maintained-over-hand-rolling；失败（registry 缺失/任务无 worktree）降级 `null`。链路：`TaskRecord.worktreeId` → `ctx.worktreeRegistry.status(worktreeId)`。
- task→workspace 归属：TaskRecord 无 workspaceId 字段（project-contracts/types.ts:84-107），v2 桌面为单 workspace；任务归属展示用绑定摘要推导（第一个 ready binding 的 workspaceId），跨 scope 聚合保持 deferred（总计划 Q2）。

### Q-C3 看板 UI 结构

- **BoardView.tsx**：props = `PropsRuntime<'conversation.view'> & InjectFace<BoardViewFace> & PropsLocale<'shadow'>`（对齐 ChatView 模式，ui-chat/contract/slots.ts:150-155；本包 ShadowCard.tsx:30-31 已有同形先例）。
  - 六列投影：planned→Backlog / assigned→To confirm / developing→Building / reviewing→To review / submitted→Submitted / integrated+completed→Done；blocked/failed 独立行（带 blockedReason/nextAction/wakeCondition）。
  - 卡片：标题、workspace 标签、状态时间（updatedAt 相对显示）、blockedReason、building 卡 live 行（branch + updatedAt，回应 r2 P1-4）。
  - **planned 卡片主 CTA"批准开工"**（唯一主 CTA）+ 打回按钮（弹 note 输入框 → rejectTask）+ **blocked 卡片"重新批准"按钮（P1-8）**。
  - 按钮态：`startReady=false` 置灰；批准 RPC 往返期间 disabled；失败 toast + 原地重试。
  - **黄底等待标记**：planned 待批 >30min 或 developing 无进展 >30min（updatedAt 阈值，回应 P1-1/#15 最低兑现）。
  - **渲染层每帧自检（P1-5 接线闭环）**：`sessionId === shadowSessionId` 才渲染，否则 `return null`；**shadowSessionId 数据源 = BoardViewFace 增 `hooks.status`（复用 mount.ts:49 同一 ShadowStatusController 实例及其 store.view.shadowSessionId），不另开数据通道**。
  - 视觉：蓝白体系、模块聚合、单一主 CTA、统计收敛；沿用 ShadowCard.module.css 样式语言；全部文案走 locale。
- **ShadowBoardController**（shadow-store.ts）：复用 ShadowStatusController 模式（createSnapshotStore + 最新读胜出）；BoardView 挂载时启动 **5s 轮询**（setInterval，卸载清理），失败保留上次快照 + error。
- **mount.ts**：`ctx.slots.inject('conversation.view', ...)` 注册 id `'board'`（order 10，**label 为 thunk（P1-6）：`const t = ctx.locale.bind(NS)` 后 `label: () => t('board.tab')`**，对齐 ui-chat apply.ts:76/99 先例，locale 变更时 roster 重算）；`ctx.slots.inject('conversation.session.header.actions', ...)` 注册 id `'shadow-board-toggle'`（order 30）。
  - **切换接线（已定案，走候选路径①）**：注册 conversation.view 后 tab 由 header 自动渲染（ConversationSession.tsx:146 `selectView(viewTab.id)`，roster 订阅插槽变更 apply.ts:121-160，tabs>1 才显示 :137——注册 'board' 后自动出现第 2 个 tab）。header.actions 条目拿不到 header 的 injected selectView（renderSlot('conversation.session.header.actions', {}) 不传 owner props，:130；selectView 只注入 header 槽体 apply.ts:261-268）。**board-toggle 切换项复用/抽取 mount.ts:64-75 的 onOpenConversation 逻辑（打开 Shadow 会话，P2-9：不复制两份），作为看板入口补充而非必需**。
- **package.json（P1-3）**：dsh.client.inject 与 peerDependencies、devDependencies **三处补** `@deepseek-ai/dsh-client-ui-conversation`（`PropsRuntime<'conversation.view'>` 类型合并与运行期装配都需要它；缺则 hygiene 门拦）。
- **locales.ts**：新增 `board.*` 全量 key（zh/en），无硬编码中文（v1 硬伤 #2）。

### Q-C4 blocked 任务恢复（P1-8）

**决策：阶段 C 补"重新批准"= approveTask 接受 `blocked` 状态**（总计划 §4.3 要求打回后可重新批准；现 approveTask 仅接受 planned，index.ts:200）。

- 执行时第一步**验证 controller.assign 的 from-state 是否允许 blocked → assigned**（controller.ts:915 `requireTransition`）；若允许，approveTask 条件放宽为 `state === 'planned' || state === 'blocked'`，走既有 assign + startDevelopment 链（重新批准语义 = resume）；若不允许，则按总计划 Q1 补 `shadow.resumeTask` RPC（blocked → assigned → startDevelopment）或按 controller 既有语义确认迁移路径。
- UI：blocked 卡片渲染"重新批准"按钮（复用 approve 主 CTA 视觉与 disabled 语义），点击即走上述路径。
- 测试：blocked → 重新批准 → developing 状态断言（host + view）。

---

## 2. 阶段划分与改动清单

### 阶段 C-1：host 侧 readBoard（shadow-controller）

1. `types.ts`：新增 `ShadowBoardSnapshot` / `ShadowBoardBinding` / `ShadowBoardTask`（Q-C2），随 index.ts 导出。
2. `index.ts`：新增 `@Remote async readBoard(): Promise<ShadowBoardSnapshot>`：
   - `ctx.get('projectController')` 缺失 → `{ mounted: false, bindings: [], tasks: [] }`。
   - `ctx.get('shadowRouter')` 缺失 → bindings 空数组（mounted 仍按 projectController 判定）。
   - tasks 直映 `projectController.list()`；planned 派生 startReady（try/catch，依赖服务不齐 → false）；assigned/developing 采集 branch（`worktreeRegistry.status(worktreeId)`，失败/无 worktree → null）。
   - 无状态推进、无副作用（只读），boardNotify 不参与。
3. 测试（shadow-controller.host.spec.ts 增补，扩展现有 spec）：
   - mounted:false 降级（无 projectController）。
   - **shadowRouter 缺失降级（P1-11）**：projectController 在、shadowRouter 缺 → mounted:true 且 bindings 空。
   - 任务全量投影 + stable 序。
   - startReady：预配完整 → true；缺 worker/lead/worktree → false。
   - branch：developing 任务经 status() 成功采集；status 失败 → null；assigned 无 worktree → null。

### 阶段 C-2：commitPaths 闭环（project-controller + shadow-controller + 部署）

1. `delivery-consumer.ts`：
   - Config 增 `defaultCommitPaths?: string[]`；z.object 加 `defaultCommitPaths: z.array(z.string()).optional()`。
   - `ProjectDeliveryRegistry` 接口增 `readonly defaultCommitPaths?: readonly string[]`。
   - apply：`defaultCommitPaths` 经 `normalizeCommitPaths` 归一化后注入 registry（空数组 fail-loud）。
2. `shadow-controller/index.ts` approveTask（:214-217 三元处）：`commitPaths: request.commitPaths ?? registry.defaultCommitPaths`（类型上 `readonly string[] | undefined`；仍可能 undefined → 注册仅 checkset，保持 fail-closed）。
3. `development-project.ts` patch（:206-217 config 块）：`project-controller-delivery-consumer` config 增 `defaultCommitPaths: ['<首轮验收任务固定产出文件相对路径>']`（占位，验收用例确定后填实）。
4. 测试：
   - delivery-consumer：config 带 defaultCommitPaths → registry.defaultCommitPaths 暴露且归一化；非法值（空数组/越界路径）fail-loud；**缺省 → registry.defaultCommitPaths 为 undefined、行为不变（P2-2 成对保护既有 host.spec.ts:291 断言）**。
   - approveTask：request 无 commitPaths 时注册用 registry 默认值（mock registry）。
   - development-project.spec.ts：patch 断言含 defaultCommitPaths 行（现 spec :181 仅断言 id 行，纯增量）。

### 阶段 C-3：client 侧看板（client-ui-shadow-entry）

1. `package.json`（P1-3）：dsh.client.inject + peerDependencies + devDependencies 补 `@deepseek-ai/dsh-client-ui-conversation`。
2. `shadow-store.ts`：`ShadowBoardController`（复用 ShadowStatusController 模式；5s 轮询由 view 驱动，store 本身只暴露 refresh + snapshot）。
3. `BoardView.tsx` + `BoardView.module.css`：六列投影、卡片、主 CTA/打回/重新批准、按钮态、黄底等待、live 行、自检 null（hooks.status 数据源）、loading/error/重试、5s 轮询生命周期。
4. `slots.ts`：`BoardViewFace`（hooks.board + **hooks.status（P1-5）** + approve/reject/refresh verbs）。
5. `mount.ts`：注册 conversation.view（id board，label thunk）+ conversation.session.header.actions（id shadow-board-toggle，复用 onOpenConversation，P2-9 抽取不复制）。
6. `locales.ts`：`board.*` zh/en 全量 key。
7. 测试（**扩展现有 spec，不新建 board-* spec，P1-12**；组件 spec 头 `// @vitest-environment jsdom`；5s 轮询/移列用 `vi.useFakeTimers`，本包现无先例，先跑通一个 fake-timer 用例再铺开，P2-8）：
   - `shadow-presenter.client.spec.ts` 扩展：六列投影、blocked/failed 独立行、超时黄底标记、startReady 置灰、**mounted:false → disabled 展示模型（P1-10）**、自检 null 分支（presenter 纯函数 toEqual）。
   - `shadow-store.client.spec.ts` 扩展：快照胜出语义、5s 轮询调度（fake timer）、失败保留旧快照。
   - `shadow-card.client.spec.tsx` 或新组件 spec 扩展：批准点击 → approve RPC 调用形态（workspaceId/taskId）；往返 disabled；批准后 5s 移列断言（fake timer）；打回弹 note → rejectTask(reason)；blocked 卡重新批准 → resume 路径；失败 toast + 原地重试。

---

## 3. 已知偏离 / deferred（本阶段显式记录）

- **#21 repairLimit 看板显示（P1-9）**：总计划 §4.6 点名要求"repairLimit 撞限时显示已回退次数+末次失败命令"；Snapshot/TaskRecord 均无此字段，数据源在 evidence 域，**本阶段记 deferred 到阶段 D**（building 卡 live 行先以 branch+updatedAt 兑现，总计划 §4.6 #16 部分）。
- 通用 task→commit 路径映射（多轮任务）：deferred，与总计划 §7 同列；本阶段以 `defaultCommitPaths` + 固定产出验收任务闭环。
- 跨 workspace 聚合：v2 桌面单 workspace，deferred（总计划 Q2）。
- `test:snapshot` keyless 场景（总计划 §4 验收 5）：录制需真实 key，执行时先查 `DEEPSEEK_API_KEY` 可用性；不可用则补 presenter 快照断言覆盖并记录偏离。
- **点名用例归属（P2-7）**：#13（building 杀进程恢复）、#19（并发/中止）、#20（Windows 冒烟）、#11（配置 fail-loud）均**不属阶段 C**——#13/#19 属集成验收（阶段 D/e2e）、#20 属阶段 B 预配链冒烟（已验收范围）、#11 属阶段 B（已验收）；阶段 C 验收不重复执行。
- **验收 9 真实界面截图（P1-7）**：**本阶段执行（不 deferred）**——桌面端启动后 Web UI（127.0.0.1:3080）截图验证看板视图与操作，见 §4.5。

## 4. 验收标准

1. host：`shadow-controller` tsc + 单测全绿（含新增 readBoard 用例）；`project-controller` 全量测试回归无破坏（含"未注册拒 deliver"既有路径与 defaultCommitPaths 成对用例）。
2. client：`client-ui-shadow-entry` tsc + 扩展后的 presenter/store/view 测试全绿；per-file 100% 覆盖门保持。
3. 部署：development-project.spec.ts 断言 defaultCommitPaths 行存在；桌面启动日志无 project-controller 相关错误。
4. 端到端（一次全链路）：Shadow 给 controller 派活 → plan（planned）→ 看板出现卡片 → 批准开工 → developing → commit（defaultCommitPaths 生效）→ deliver → review → integrate；每步状态看板正确投影；**blocked 打回后"重新批准"恢复路径**（Q-C4）。
5. **真实界面验证（P1-7）**：桌面端启动后 Web UI（127.0.0.1:3080）截图验证看板六列视图与批准/打回操作。
6. UI 规范：六列正确、单一主 CTA、蓝白视觉、zh/en locale 无硬编码、loading/失败/禁用/黄底等待态齐全。
7. 仓库门：改动包 `pnpm run typecheck` / `pnpm run lint` / `pnpm run test` 通过。

## 5. 风险与依赖

| 风险 | 缓解 |
|---|---|
| defaultCommitPaths 静态配置与动态 task 产出错位 | 首轮验收任务固定产出文件；通用映射记偏离 deferred |
| Q-C4 blocked→assigned 迁移合法性未知 | 执行时第一步验证 controller.assign from-state；不合法则补 resume RPC（总计划 Q1 路径） |
| worktreeRegistry.status() 调用面与既有测试不一致 | 执行时对照 registry.ts:101-115 签名与既有调用先例；降级 null 分支必测 |
| startReady 派生对每个 planned 任务跑 authority | 桌面 maxActiveTasks=2，规模可忽略；只读无副作用 |
| 新增 ui-conversation 依赖的 hygiene/peer 检查 | package.json 三处同步声明，跑 hygiene 确认 |

## 6. 执行注意事项（P2-8）

- 新组件/测试文件放 `client-ui-shadow-entry/tests/`；组件 spec 头加 `// @vitest-environment jsdom`。
- fake-timer 先跑通一个用例再铺开（本包现无先例）。
- board-toggle 复用/抽取 mount.ts:64-75 onOpenConversation 逻辑，不复制两份（P2-9）。
- register label 一律 thunk（P2-1 行号已修：approveTask fail-closed 注释在 index.ts:210-213）。
