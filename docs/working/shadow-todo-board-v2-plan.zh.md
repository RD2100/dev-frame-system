---
title: Shadow Todo 看板 v2 实施计划（修订 3）
owner: shadow
status: draft-plan-r3
date: 2026-09-20
previous:
  - docs/working/shadow-todo-board-v2-plan.zh.md（v1 计划，评审打回）
  - docs/working/shadow-todo-board-v2-plan-review.md（r1 评审：P0×2、P1×7、P2×8）
  - docs/working/shadow-todo-board-v2-plan-review-r2.md（r2 复评：5 条 P1 收尾）
  - docs/working/shadow-todo-board-handoff-v2.zh.md
  - docs/working/shadow-todo-board-review.md（v1 三方 22 条硬伤）
---

# Shadow Todo 看板 v2 实施计划（修订 3）

> 本版在修订 2 基础上补齐 r2 复评的 5 条 P1 窄口（§3 回应表 r2 列）：cwd 归一化、beforePersist 接线、typert caller 鉴权证据、#16 数据契约、Goal 冷启动主路径。r1 两条 P0 与 7 条 P1 已在修订 2 改对并经 r2 复核成立。

## 0. 目标与范围

把桌面端 Shadow 从"对话 + 自由派活"升级为**任务看板驱动的多 agent 工作台**，兑现用户 5 痛点：

| 痛点 | v2 承接 |
|---|---|
| ① 改完先给工单等批 | 块 2 HITL gate（plan → planned → 用户批准 → start） |
| ② 干完有质检 | project-controller 的 lead `project_review` 独立审查（接核心件） |
| ③ 动手前问你 | 同 HITL gate（不批准不动手） |
| ④ 花超自己停 | 真正的 token 花超依赖 request-budget，**本版显式记录为已知偏离、deferred**；本轮交付最低兑现：看板对停留待批/开发超阈值的卡片做黄底等待标记（回应 v1 硬伤 #15 的最低要求，见 §2 阶段 C） |
| ⑤ 进度看得见 | 块 3 六列看板 UI（conversation surface 新视图） |

**路线（已拍板）**：接 project-controller 核心件（task 状态机 + worktree + review + integrate），不接 requiredChecks 审批账本与 request-budget。

## 1. 五个未决问题的决策（修订版）

### Q1 HITL gate：plan 后停在 planned，用户批准走什么 RPC？

**决策：在 shadow-controller 包新增 host-plane Remote RPC（`shadow.approveTask` / `shadow.rejectTask`）。approveTask 复用从 task-consumer 抽取的 start 前置断言（单一真值源），不再直调裸 `assign`/`startDevelopment`。**

- 依据（源码）：`project_task start` 的 authority（task-consumer.ts:59-120）绑定 `exec.agent`——必须是实际 live 的 root controller，host 按钮没有 agent 执行上下文，无法复用工具面。`controller.ts:400-431` 的 `assign`/`startDevelopment` **只做状态迁移 + admission_open + 并发预算，不复刻任何前置断言**——直调会把 worktree/写锁/绑定未就绪的任务非法推进 developing（评审 P0-2 复核确认）。
- **抽取**：把 task-consumer 的 `authority()`（:59-78：live root controller / open Goal 且 taskIds 含之 / controller worktree 写锁；:80 是 `const initial = authority()` 调用点）与 start 前置（:88-102：恰一 worker + lead parent 链 + 三独立 worktree + 双写锁 + agent 在线且 cwd 对齐）抽为 project-controller 包内可复用的 `resolveTaskStartAuthority(ctx, controllerAgent, taskId)`，返回签名；工具层与 host RPC 共用，两处行为一致。
- `shadow.approveTask(workspaceId, taskId)` 语义：
  1. `ctx.shadowRouter.findBinding(workspaceId)`：要求 state `ready`，取 `controllerSessionId`；经 agentBindings 解析出 live controller agent（`ctx.agents.get(...)` 校验在线且 session 匹配），无则 fail-loud。
  2. `ctx.projectController.find(taskId)`：要求 state === `planned`（非 planned fail-loud；HITL gate 是唯一进入 start 的路径）。
  3. 调 `resolveTaskStartAuthority(ctx, controllerAgent, taskId)`——预配未完成（无 worker/lead、worktree 未建、写锁未占齐、goal 未 open）在此 fail-loud，**不推进状态**。
  4. 注册 delivery 配置：`registerTask(taskId, { digest, commitPaths })`（Q3，注册与 start 同处完成，消除时序竞态，见 P1-6）。
  5. `projectController.assign(taskId, worker.sessionId, { beforePersist: () => reCheck() })` → `startDevelopment(taskId, ..., { beforePersist: () => reCheck() })`（对齐 controller.ts:400 签名：首参 taskId，次参 worker session），其中 `reCheck` = 重调 `resolveTaskStartAuthority` 比对签名（复用抽取的 unchanged 漂移复检语义）——**必须传 beforePersist**：task-consumer 把并发漂移复检咬在写边界靠的是 `assign/startDevelopment(..., { beforePersist: unchanged })`（task-consumer.ts:113/:116），不传则 approveTask 只有调用前一次性 check，enqueue 内、persist 前的漂移无防护（r2 P1-2）。
  6. `workerAgent.followup(briefing)`。
  7. 成功后向 designated Shadow session `postMessage` 结构化消息（块 4）。
- **caller gate（回应 r2 P1-3 / v1 硬伤 #17）**：approveTask 是 **host-plane 人类动作**（看板按钮），Shadow 模型不持有任何批准工具（shadowAllowlistGuard 只装四个工具、白名单不动，模型面无 approve 入口）。**关于 typert 通道的 caller 鉴权，源码证据如下**：现有 Remote 六方法（index.ts:109-161）方法体内**均无 caller 身份校验**——openProject/sendToController 靠 router 的 host bridge（`openProjectForHost`，其 caller gate 由 router 持有）；postMessage 靠 conversation host。typert Remote 方法签名只有 request 参数（index.ts:110/122/137/149/159），不注入调用者身份，**因此 approveTask 无法在方法体内做"调用者会话"校验**（那是伪校验）。等价防护 = **下游 authority 门**：approveTask 的 authority（`resolveTaskStartAuthority`：live controller agent / goal admission_open 且 taskId 在列 / 三 worktree 写锁 / 恰一 worker+lead 绑定）只能由 host 预配链 + 真实批准后的状态满足，任何未授权调用（模型或其他会话）都在 authority fail-closed。威胁边界与 openProject/postMessage 一致（renderer 为受信 host UI 面、模型工具面无入口）。**增强验证动作**：若执行时发现 typert 上下文暴露 currentSession，approveTask 开头叠加 `currentSession === shadowSessionId` 断言（一行成本，非阻塞）。单测补：模型工具白名单断言无 approve 工具；authority 失败路径全抛错。
- `shadow.rejectTask(workspaceId, taskId, reason)`：planned → `block({ blockedReason, nextAction, wakeCondition })`（BLOCKABLE_STATES 含 planned，controller.ts:131）。看板显示 blocked + 理由 + "重新批准"（`resume` → assigned → startDevelopment）。
- **实现备注（平台能力缺口，r3 建议 5）**：authority 门防"未就绪任务被推进"，但不区分"人类 vs 其他 host 组件"。真正 caller 级鉴权需 typert 传输层提供可信 caller 身份，协议层当前无此机制（r3 已协议层核实：InvocationDescriptor 仅注入 signal，无 caller wire 字段）；此缺口在实现备注留一句，待平台补齐后再加，不阻断本方案。
- **超时未批**：任务**停在 planned 不自动放行**（默认拒，安全侧），看板黄底高亮待批列（P1-1）。
- 改动面：`packages/experimental/project-controller`（抽取 authority + delivery 注册面）、`packages/experimental/shadow-controller`（Remote + types）、配套单测。

### Q2 跨 workspace 聚合：Shadow 怎么读多个 controller 的 task list？

**决策：v2 聚合"当前 host context 内已挂载的 projectController 服务"，桌面 = 单 workspace。跨 plugin scope 聚合 deferred。**

- 事实：`project_tasks` 存储域按 TaskId 键控、TaskRecord 无 workspaceId 字段（spec.ts:99-110）；多项目 = 多 plugin scope = 独立 service 实例，跨 scope 无直接聚合 API。
- 数据面：新 Remote `shadow.readBoard()` 组合 `ctx.projectController.list()` + `ctx.shadowRouter.listBindings()`。**projectController 未挂载时降级**：返回 `mounted: false` + 空 board（沿用 ShadowController 现有 `ctx.get()` 可选取模式，index.ts:91；回应 P2-7）。
- UI 按 workspace 分组投影；多 scope 聚合列为 deferred。

### Q3 requiredChecks：运行时按 task 注册唯一一条 check（静态 seed 为空），不改 devframe schema

**决策：放弃"空 checkset"路线（r1 P0-1 复核：`required-checks.ts:86` 是 `checks: z.array(...).min(1)`，空集在 schema 边界即抛 `REQUIRED_CHECKS_INVALID_CONFIG`，且 file-store 每次读账都全校验，物理上落不了账）。改为静态 `requiredChecksByTask: {}`，运行时按 task 注册唯一一条最小非空 check：`git diff --check`，`cwd` = 该 task 的 worker worktree 路径。**（术语统一：静态 seed 为空 map；运行时每个 task 注册恰好一条 check，二者不冲突，r2 P2-1）

- 依据（源码）：
  - `delivery-consumer.ts:211`：approved check 的 `cwd` 必须 realpath 等于 worker worktree，否则拒 deliver → checkset 配置天然**按 worker worktree 注册**，digest 随 cwd 变，注册必须发生在 worktree 已建之后（预配链内）。
  - `delivery-consumer.ts:206-207`：`requiredChecksByTask[taskId]` 无条目 → `throw 'Task has no host-approved checkset'`（真正拒点在 :207；:334 是 `project_evidence` 的 `?? null` 容错分支，不拒 deliver）。
  - `delivery-consumer.ts:266-267`：check 以 `check.cwd` 为工作目录执行（execFileAsync）。
- **动态注册面**：delivery-consumer 的 `requiredChecksByTask`/`commitPathsByTask` 从"config 静态直读"改为"config 种子 + host 可更新 registry"：新 `ctx.projectDeliveryRegistry`（或 consumer 内可变 map + 注册 API）提供 `registerTask(taskId, { digest, commitPaths })` / `unregisterTask(taskId)`（幂等），工具执行时读 live 值。**未注册 task 依旧拒 deliver（保持 fail-closed）**。
- 注册内容（**r2 P1-1：cwd 必须先 realpath 归一化**）：digest 算法对**字面量 cwd 字符串**哈希（required-checks.ts:309 `JSON.stringify({ checkId, executable, arguments, cwd })`），而 delivery-consumer:211 运行时比较的是 `realpathNormalize` 后的值；本仓 worktree 走 junction（development-project.ts:71 `symlinkSync(..., 'junction')`），同一物理 worktree 以不同字面路径注册会算出两个 digest、deliver 判 stale。因此 host 在 `store.save` / 算 digest / 注册**之前**，先对 worker worktree 路径做 `realpathNormalize(cwd)`，对齐 :211 比较语义。digest = `requiredChecksDigest({ version: 1, checks: [{ checkId: 'git-diff-check', executable: 'git', arguments: ['diff', '--check'], cwd: <realpathNormalize(worker worktree path)> }] })`（先 `store.save(config)` 落账再注册 digest）；commitPaths = 该 task 允许提交的仓库相对路径（阶段 B 预配链定义默认：worker worktree 内的受控子路径，执行时确认）。
- `git diff --check` 在干净已提交 worktree 上恒 exit 0，语义真实（拦截空白错误）、代价可忽略；verification 记录该 digest，review/integrate 的 approved-checks 校验通过；**reviewer 直接看 diff** 由 review 工具天然支持（findings 任意）。
- 改动面：`packages/experimental/devframe` **不动**；`packages/experimental/project-controller/src/delivery-consumer.ts`（注册面 + live 读取）；配套测试（未注册拒 deliver、注册后通过、digest 随 cwd 变化）。

### Q4 controllerSessionId 从哪个 binding row 读？

**决策：`ctx.shadowRouter.findBinding(workspaceId)?.controllerSessionId`**（service.ts:237；`listBindings` 在 :243；`ProjectStatusEntry.controllerSessionId` 在 types.ts:201，三者等价来源）。

- 静态 patch 在 prepare 时 binding 尚不存在 → request-budget-consumer 的 config 无法预填 → **路线 3 不接 request-budget 的判断成立**（将来接需 host 动态配置通道，deferred）。
- v2 里 controllerSessionId 只出现在 readBoard 快照与 approveTask 解析，不写入任何静态 patch。

### Q5 看板 UI 放在 conversation surface 哪里？

**决策：新注册 `conversation.view` 列表插槽项（id `board`）+ `conversation.session.header.actions` 切换项；BoardView 在渲染层每帧自检只对 designated Shadow 会话渲染（插槽本身不按 session 过滤，回应 P2-6）。**

- 依据（源码）：`conversation.view` 是 session 级 list 插槽（slot-catalog.ts:1271-1327，现有 occupant chat/trajectory）；`conversation.session.header.actions` 为 list 插槽（:1079-1136）。均**不按 session 过滤**——BoardView 必须 `sessionId === shadowSessionId` 时渲染、否则 return null。
- 客户端数据流：新 Remote `shadow.readBoard()` → client SnapshotStore（复用 ShadowStatusController 模式）→ BoardView。
- 视觉：蓝白体系、单一主 CTA（批准开工）、模块聚合、统计收敛；全部文案走 locale dictionary（zh/en）；loading 态、失败 toast + 原地重试、批准 RPC 往返期间按钮 disabled、**批准后 5s 内卡片移入 Building 的可观察断言**（P2-5）；预配未就绪的 planned 卡片"批准开工"置灰（readBoard 携带 startReady 标志，由 host 侧只读 authority 检查派生，不改状态）。

## 2. 阶段划分与改动清单

### 阶段 A：composition 接线（块 1）

文件：`apps/desktop/scripts/development-project.ts`

1. **devframeLinks 增加**（:246-272 列表）：
   - `['@deepseek-ai/dsh-experimental-project-controller', 'packages/experimental/project-controller']`
   - `['@deepseek-ai/dsh-experimental-agent-evidence', 'packages/experimental/agent-evidence']`（delivery/review/integrate 的持久化证据依赖）
   - `['@deepseek-ai/dsh-experimental-devframe', 'packages/experimental/devframe']`（delivery-consumer 运行时 import `FileRequiredChecksConfigStore`/`RequiredChecksDigest`，delivery-consumer.ts:16-22；桌面 disposable project 用显式 junction 模式，必须确认解析，回应 P1-5）
   - `['@deepseek-ai/dsh-experimental-project-contracts', 'packages/experimental/project-contracts']`（TaskId/PluginId/TaskRecord brand 类型来源，执行时按解析验证加/不加）
   - **agent-dispatch**：devframe-profile bundle 已 insert 其 row（agent_dispatch 工具提供者），桌面 patch 不删则仍在；阶段 A 验证其挂载生效，必要时在 patch 显式 restate（回应 P1-5）。
2. **`buildDevFrameDeploymentPatch` 增加 rows**（参照 shadow-loop 示例，删 request-budget-consumer）：
   - `project-controller`（service）：`maxActiveTasks: 2`、`requestBudget: 64`
   - `project-controller-consumer`（project_integrate）：`requiredChecksPath: !!js dshHomePath('required-checks.json')`、`gitExecutable: git`、`gitTimeoutMs: 60000`、`gitMaxOutputBytes: 10485760`
   - `project-controller-task-consumer`（project_task）：无 config
   - `project-controller-delivery-consumer`：`repairLimit: 3`、`requiredChecksPath`、`requiredChecksByTask: {}`（**静态 seed 为空**，运行时按 task 注册唯一一条 git-diff-check，Q3）、`commitPathsByTask: {}`、git/check 限额（checkTimeoutMs 600000 / checkMaxOutputBytes 1048576）
   - **不接**：request-budget-consumer（Q4）
3. **agent-hierarchy row 扩展工具面**（桌面 patch restate 会整体替换 devframe-profile 的 row，必须在此补全；回应 P1-5 的"工具名进 face ≠ 插件已挂载"——插件挂载见上条，本条只保证工具对角色可见）：
   - controller += `project_task`, `project_integrate`, `agent_dispatch`, `worktree_create`, `worktree_list`, `worktree_prune`, `worktree_remove`, `worktree_status`, `create_goal`, `get_goal`, `update_goal`（Goal 生命周期模型驱动，P1-3）
   - lead += `agent_dispatch`, `project_evidence`, `project_review`
   - worker += `project_deliver`, `project_commit`
   - `leadPluginScopes`：配置 lead 身份 → 插件 scope（v2 固定单 pluginId `devframe-goal`；预配链确认后定值）
4. `development-project.spec.ts` 补 patch 内容断言（新 rows 存在、request-budget 不存在、faces 含新增工具）。

### 阶段 B：HITL gate + 预配链 + Goal 生命周期（块 2）

**关键前提（源码已证）**：`project_task start` 要求 ①task 在当前 open Goal 的 taskIds 内且 lifecycle admission_open ②live root controller binding + controller worktree 写锁 ③恰一 worker + lead binding + 三独立 worktree 双写锁（task-consumer.ts:59-120）。桌面 dev 环境目前全无 → 块 2 = HITL 状态 + **打通预配链与 Goal 生命周期**。

**Goal 生命周期（回应 r1 P1-3 + r2 P1-5）**：
- 每个 workspace 常驻一个 Goal，进入 `admission_open`。**冷启动触发者定案（r2 P1-5，不留冒烟临场挑）**：
  - **主路径（host 驱动）**：host 在 workspace binding 首次进入 `ready` 时，向 controller session `followup` 一条 `/devframe-start`（默认 objective 常量文本，如"DevFrame workspace 常驻开发目标"；命令语法执行冒烟确认），由 controller 会话完成 goal 创建。
  - **fallback（controller 自主）**：触发条件 = followup 后 host 轮询 `sessionProjections` 超时（60s）仍未达 `admission_open`，或命令在 controller face 不可用；此时 controller agent 用 `create_goal` 自主创建。
  - 主路径优先的理由：确定性高、可测试（host 可轮询断言）、不依赖模型自主性；fallback 保底闭环入口不阻塞。
- **新 task 接纳**：taskIds 精确匹配（task-consumer.ts:71 `goal.taskIds.some(id => String(id) === String(taskId))`），静态 config 只含 `['devframe-goal']` → 每个新看板 task 派发前，controller 先 `update_goal` 把 taskId 追加进当前 goal 的 taskIds，再 `project_task plan`。
- **单 Goal 复用策略**：常驻一个 Goal、taskIds 动态追加，不每 task 新建；goal 完成/停止后按 DevFrame 既有语义收尾，下一轮重建。
- 冒烟：plan 前 goal 存在性断言（admission_open + taskIds 含 taskId），不通过则阶段停下修正。

**预配链（模型驱动，与 DevFrame 语义一致）**：
- controller agent 在 `plan` 后、批准前完成：`agent_dispatch` 派 lead（→worker）、`worktree_create` 建 controller/lead/worker 三 worktree 并注册写锁。建 worktree/派 agent 不算"改代码"，不违反"动手前问你"；批准后才真正 start（worker 干活）。
- **worker worktree node_modules（回应 P1-4，定案）**：预配链在 worker worktree 创建后由 **host 预配逻辑（owner）** 执行 `pnpm install --frozen-lockfile --prefer-offline`（全局 content-store 硬链接，本仓为 pnpm workspace 已验证模式）；**失败 fail-loud 阻止 start**；兜底策略：store 不可用时退化为 junction 镜像主项目 node_modules（复用 development-project.ts 的 mirrorDependencyLinks 模式），风险与适用写入文档。Windows 要求（Developer Mode / core.longpaths / MAX_PATH）写入文档，原生 Windows 冒烟（见验收）。
- 备选（host 驱动预配，不推荐）：approve RPC 内 `ctx.agentDispatch.createChildAgent` + worktreeRegistry.create/bind——重且与模型循环冲突。

**HITL RPC**：按 Q1 实现 `shadow.approveTask` / `shadow.rejectTask`（含抽取的 `resolveTaskStartAuthority` + 注册面调用 + caller gate）。

**注册时序（回应 P1-6，消除竞态）**：delivery 注册**移进 approveTask**（步骤 4），与 start 在同一 host 调用内完成——plan 是模型工具调用、无 host 事件可监听，若在 plan 时注册则存在 deliver 先于注册的竞态；在 approveTask 内注册则注册必然先于任何 deliver。单测锁定"approve → 注册 → start → deliver 成功"与"未 approve 直接 deliver 被拒"两条路径。

### 阶段 C：跨 workspace task board UI（块 3）

文件：`packages/experimental/client-ui-shadow-entry`（+ host 侧 shadow-controller）。

1. host：`ShadowController` 新增 `@Remote readBoard()`（Q2 组合 + projectController 未挂载降级）→ types.ts 增 `ShadowBoardSnapshot`（tasks + bindings 摘要 + `startReady` 每任务标志 + `mounted`；**task 记录含 `branch?: string | null` 与 `lastActivityAt` 字段，回应 r2 P1-4 数据契约**）。采集方式：`branch` = readBoard 对 developing/assigned 任务的 worker worktree 执行只读 `git rev-parse --abbrev-ref HEAD`（失败降级 null，5s 缓存）；`lastActivityAt` 复用 TaskRecord.updatedAt。**"最近命令"无数据源（无命令日志），v2 撤掉该要素**：building 卡片的 live 行用 branch + updatedAt 兑现（对 v1 硬伤 #16 原文的偏离记录在 §4）。
2. client：
   - `shadow-store.ts` 增 `ShadowBoardController` + store（复用现有模式）。
   - 新 `BoardView.tsx`：六列（Backlog=planned / To confirm=assigned / Building=developing / To review=reviewing / Submitted=submitted / Done=integrated+completed；blocked/failed 独立标注列），卡片含标题/工作区/状态时间/blockedReason；planned 卡片 = 单一主 CTA"批准开工"+ 打回（弹 note 输入框，回应 v1 硬伤 C 的 UX）；**黄底等待标记**（planned 待批 >30min 或 developing 无进展 >30min，基于 updatedAt，回应 #15 最低兑现）；5s 轮询；loading/disabled/toast/按钮禁用/批准后 5s 移列断言（P2-5）；`startReady=false` 的卡片批准按钮置灰。
   - **渲染层每帧自检**：`sessionId === shadowSessionId` 才渲染 board view / header action，否则 return null（P2-6）。
   - `mount.ts`：注册 `conversation.view`（id `board`）+ `conversation.session.header.actions`（id `shadow-board-toggle`）。
   - `locales.ts`：zh/en 全量 key（v1 硬伤 #2）。
   - 测试：presenter/store/view 状态快照断言（六列投影、按钮态、locale、超时标记、自检 null 分支）+ host RPC 单测。
3. 视觉规范：蓝白、模块聚合、单一主 CTA、统计收敛；沿用 chat/trajectory 样式语言。

### 阶段 D：model-visible ⟺ logged + Shadow 触发规则（块 4）

- **动作注入**：approve / reject（后续 review 决策）完成后，host 向 **designated Shadow session** `postMessage` 结构化文本（工作区、taskId、标题、decision、时间）；消息走现有会话持久化 → session log 天然记录（model-visible ⟺ logged，无新存储域，回应 v1 硬伤 #8/#9）。
- **Shadow 触发规则（回应 P1-2 / v1 硬伤 #18）**：定位 Shadow 系统提示注入点（执行时确认在 shadow-agent 或桌面会话 preset），加入触发规则：**"用户明确要求改动/交付物才开 todo（plan 工单）；查询、解释、浏览、讨论类直接回答，不开工单。"** 附正例（"帮我修这个 bug"/"写一份周报"→ 开工单）与反例（"这个函数是干嘛的"/"你怎么看这个方案"→ 直接答）。
- **收口句（回应 P2-8）**：v1 硬伤 #5 多轮回退/打回理由由 project-controller `repairLimit`（delivery-consumer config）与 review `changes_required` + blockedReason 承接；#9 不新建存储域（task 持久化在既有 `project_tasks` 域），**无需 SCHEMA_VERSION 变更**；#10 执行面 allowlist：**Shadow 本身不新增工具、shadowAllowlistGuard 不动**，controller/lead/worker 三个 agent-hierarchy face 的显式工具面即为本架构的 allowlist。

## 3. 评审意见回应表（修订 3 逐条回应）

| 评审条目 | 回应 |
|---|---|
| P0-1 空 checkset 被 `.min(1)` 阻断 | **放弃空 checkset**，改种子非空 check（`git diff --check`，cwd=worker worktree），devframe schema 不动；见 Q3/§2B |
| P0-2 approveTask 绕过前置断言与 router gate | 抽取 `resolveTaskStartAuthority` 单一真值源，approveTask 复用全部断言；caller gate = host-plane 人类动作、Shadow 无批准工具、白名单不动；见 Q1 |
| P1-1 #15 软告警 | 本轮交付：看板黄底等待标记（planned/developing 超 30min）；token 花超真正熔断显式记录为已知偏离、deferred；见 §0/§2C |
| P1-2 #18 触发规则 | 新增 §2 阶段 D：Shadow 触发规则 + 正反例 |
| P1-3 Goal 生命周期 | 新增 §2 阶段 B「Goal 生命周期」：常驻 Goal、update_goal 接纳新 taskId、复用策略、冒烟断言 |
| P1-4 node_modules 策略 | 定案：host 预配逻辑 owner + `pnpm install --frozen-lockfile --prefer-offline`，失败 fail-loud，junction 兜底，Windows 要求入文档 |
| P1-5 插件挂载行 | 阶段 A 补 devframe/agent-evidence/project-contracts link + agent-dispatch 挂载验证；faces 扩展与插件挂载分开处理 |
| P1-6 注册时序竞态 | 注册移进 approveTask（与 start 同调用），消除竞态；两条单测锁定 |
| P1-7 验收无 recorded-session/点名用例 | §4 验收补 test:snapshot 场景 + #13/#19/#20 用例 + presenter 快照断言 |
| P2-1 delivery 行号 | 修正为拒点 :207（:334 是 evidence 工具） |
| P2-2 硬伤编号 | cancelTodo 为 v1 硬伤 #4（非 #6） |
| P2-3 行号偏差 | task-consumer :79-120；findBinding :237 / listBindings :243；controllerSessionId types.ts:201 |
| P2-4 点名用例进验收 | #11/#16/#19/#20/#21 补入 §4 |
| P2-5 审批竞态 | 批准后 5s 移列断言；startReady 置灰；预配未就绪点击 fail-loud |
| P2-6 渲染层自检 | BoardView 每帧 `sessionId === shadowSessionId` 否则 return null |
| P2-7 readBoard 降级 | projectController 未挂载返回 `mounted:false` + 空 board |
| P2-8 #5/#9/#10 收口句 | 见 §2 阶段 D「收口句」 |
| **r2 P1-1 cwd 归一化** | Q3 注册内容：host 在 `store.save`/算 digest/注册**之前**先 `realpathNormalize(cwd)`，对齐 delivery-consumer:211 比较语义（junction 下字面路径分叉 digest 已写证据） |
| **r2 P1-2 beforePersist 接线** | Q1 步骤 5：`assign/startDevelopment(..., { beforePersist: () => reCheck() })`，reCheck 重调 authority 比签名，对齐 task-consumer.ts:113/:116 写边界复检 |
| **r2 P1-3 typert caller 鉴权** | Q1 caller gate 段：写明证据（typert 方法签名无 caller、现有六方法均无方法内校验、靠下游 authority）+ approveTask 等价防护 = resolveTaskStartAuthority 门 + 工具面白名单断言 + 增强验证动作（若 typert 暴露 currentSession 则叠加比对） |
| **r2 P1-4 #16 数据契约** | 阶段 C：ShadowBoardSnapshot 加 `branch?` + `lastActivityAt`；采集 = worker worktree 只读 `git rev-parse --abbrev-ref HEAD`（5s 缓存、失败降级 null）；"最近命令"无数据源、撤掉，live 行用 branch+updatedAt 兑现，偏离记录在 §4 |
| **r2 P1-5 Goal 冷启动触发者** | 阶段 B 定案：主路径 = host 在 binding 首次 ready 时 followup `/devframe-start`；fallback = controller `create_goal` 自主创建（触发条件：60s 轮询未达 admission_open 或命令不可用） |
| r2 P2-1 "种子"术语统一 | Q3 标题/阶段 A 统一为"静态 seed 为空 + 运行时按 task 注册唯一一条 check" |
| r2 P2-2 三处"执行时选定"保留为验证动作 | Shadow prompt 注入点 / project-contracts link / agent-dispatch restate 三处接受实施时一行验证定夺 |
| r2 P2-3/P2-4 两处偏离已记录 | #15 用时间阈值黄底替代 token% 黄底（§0/§7 明记）；readBoard 未挂载走 `mounted:false` 降级（Q2/阶段 C 明记，§7 已补记） |
| r2 P2-5 task-consumer 区间 | 维持 :59-120（authority :59-78 + start 前置 :88-102），不再改 |
| r2 P2-6 行号核实 | 已确认（:207/:211/:266/:309/:113/:116 等），采纳 |

## 4. 验收标准

1. **启动**：`D:\dsh-devframe\.desktop-devframe-staging\dsh-client-launch.ps1` 启动无新行加载报错；日志无 project-controller 相关错误。
2. **端到端闭环（一次全链路）**：Shadow 会话给 controller 派活 → controller `update_goal` 接纳 taskId → `project_task plan`（planned）→ 看板出现卡片 → 用户"批准开工" → developing（worker 开工）→ `project_deliver`（git-diff-check 通过）→ lead `project_review` 通过 → controller `project_integrate` → submitted/integrated。每步状态在看板正确投影。
3. **HITL 语义**：不批准则任务停在 planned；打回后 blocked + 看板可见理由；重新批准走 resume；**未 approve 直接 deliver 被拒**（注册时序用例）。
4. **model-visible**：批准/打回后 Shadow 会话出现对应消息（会话日志可查）。
5. **keyless recorded-session（回应 P1-7）**：新增一条 `test:snapshot` 场景（如 `shadow-loop-v2-approve`）覆盖 plan→approve→develop→deliver→review→integrate 的模型可见输出（keyless 重放）；改动的 model-/协议-/产品可见面同步更新既有场景。
6. **点名用例（回应 P2-4）**：
   - #13 building 中途杀进程恢复：集成测试——approve 后杀 controller 进程 → 重启 → task 状态与证据 reconcile 正确、无挂死。
   - #19 并发/中止：v2 无 cancel（已定），改 blocked/failed 语义用例——worker 正在跑时 block → 状态正确 + 看板显示 reason；building 中 controller stop-rebind → blockedReason 暴露而非静默挂起。
   - #20 原生 Windows 冒烟：一条 powershell 冒烟——worktree 预配 + `pnpm install` 在原生 Windows 真跑（含长路径/Developer Mode 检查）。
   - #11 配置 fail-loud：lead 身份/leadPluginScope/worktree 可写性非法配置在加载期报错用例；#16 building 卡片 live 行：显示**当前 branch + updatedAt**（`git rev-parse --abbrev-ref HEAD` 采集，见阶段 C；"最近命令"因无命令日志数据源撤掉，v2 偏离 #16 原文此处明记）；#21 repairLimit 撞上限时看板显示"已回退次数 + 末次失败命令"。
7. **UI 规范**：六列正确、单一主 CTA、蓝白视觉、zh/en locale 无硬编码中文、loading/失败/禁用/黄底等待态齐全；presenter 快照断言覆盖（非人工走查）。
8. **仓库门**：改动包 `pnpm run typecheck`、`pnpm run lint`、`pnpm run test` 通过；project-controller / shadow-controller / client-ui-shadow-entry 改动文件维持 per-file 100% 覆盖门。
9. **真实界面验证**：桌面端启动后 Web UI（127.0.0.1:3080）截图验证看板视图与操作。

## 5. 风险与依赖

| 风险 | 缓解 |
|---|---|
| 预配链 + Goal 生命周期是最大依赖 | 阶段 B 前置冒烟（goal 创建 → plan → 预配 → approve → start），不通过则停下修正 |
| approveTask 抽取 authority 改变 task-consumer 行为面 | 抽取后工具层行为不变（同一函数），project-controller 全测试回归 |
| 动态 delivery 注册改包影响既有测试 | 改后跑 project-controller 全测试；保"未注册拒 deliver"fail-closed 用例 |
| worker worktree pnpm install 失败/慢 | fail-loud 阻止 start；junction 兜底；Windows 冒烟前置 |
| 桌面 agent-hierarchy faces 扩展放宽权限面 | 只加闭环所需工具；review 对照 devframe-profile 基线 |

## 6. 测试与验证方式

- 每个包改动后：`pnpm --filter <pkg> run test` + `pnpm run typecheck` + `pnpm run lint`。
- 模型可见面变更：keyless recorded-session（`pnpm run test:snapshot` 新增/更新场景）。
- 端到端：桌面启动 → Web UI 操作 → 日志核对（shadow-router/bridge/controller 事件链）。
- 提交策略：每完成一个阶段 git commit 一次（用户偏好）；4 个外部插件相关改动不 commit。

## 7. 明确不做 / 显式偏离（deferred）

- **request-budget-consumer / token 花超熔断（痛点 ④）**：**显式记录为已知偏离**——本轮交付最低兑现为看板黄底等待标记（P1-1/#15 部分）；真正熔断需 request-budget 挂载与动态配置通道（Q4），后续。
- 跨 plugin scope 多 workspace 聚合（Q2）。
- requiredChecks 审批账本（Goal binding digest 审批链）。
- cancel 单任务 RPC（task 有 blocked/failed 标记；v1 硬伤 #4 已定，不做）。
- intervalMs 保持 60000 不动（v1 硬伤 #14）。
- devframe required-checks schema 放宽（`min(1)` 保持，P0-1 已改选方案 b）。
- readBoard 在 projectController 未挂载时返回 `mounted:false` + 空 board（降级而非 fail-loud；偏离已记录，Q2/阶段 C，UI 显示 disabled 态而非静默跳过）。
