---
title: Shadow Todo 看板 v2 — 阶段 C 实施计划评审意见（汇总）
owner: shadow
status: review-done
date: 2026-09-20
reviewed: docs/working/shadow-todo-board-v2-stage-c-plan.md（draft-plan-r1）
based-on: docs/working/shadow-todo-board-v2-plan.zh.md（总计划 r3）、docs/working/shadow-todo-board-v2-stage-b-review.md（阶段 B 验收通过）
---

# Shadow Todo 看板 v2 — 阶段 C 实施计划评审意见

- 评审对象：`docs/working/shadow-todo-board-v2-stage-c-plan.md`（draft-plan-r1，跨 workspace task board UI + readBoard）
- 评审方式：只读，不改源码 / 不提交 / 不推送。两名以上评审员分四路并行：①Q-C1 commitPaths 方案源码逐行对照；②Q-C2 readBoard 契约源码逐行对照；③Q-C3 UI 插槽与组件模式逐行对照；④测试与验收完备性（读测试源码 + 只读复跑相关套件）。所有计划引用的源码位置均实际打开文件核对，不采信二手转述。
- 评审日期：2026-09-20
- **结论：有条件通过（无 P0 阻断）。** 计划对源码行号/签名/契约的断言绝大多数经亲验准确，三个设计决策（Q-C1 方案 A、Q-C2 readBoard 只读派生、Q-C3 插槽注册）源码上均可落地。但存在 **12 条 P1 须在执行前修订**（含 1 处必须的签名修正、2 处计划未声明的部署/接线缺口、9 处验收与测试设计缺口），P2 收尾项 9 条。修订 P1 后即可进入执行。

---

## 一、逐条核对结果表（计划断言 ↔ 源码实际 ↔ 判定）

### 1. Q-C1 commitPaths 闭环（project-controller / shadow-controller）

| # | 计划断言 | 源码实际 | 判定 |
|---|---|---|---|
| 1 | approveTask 的 commitPaths 来自 request，"types.ts:88 可选" | `ShadowApproveTaskInput.commitPaths?` 实际在 **`packages/experimental/shadow-controller/src/types.ts:88`**（`readonly commitPaths?: readonly string[]`）；project-contracts/types.ts:84-107 是 `TaskRecord`（:88 恰为 `pluginId`） | **文件包名指错**（行号 :88 巧合正确）→ P1-2 |
| 2 | "index.ts:209-212 注释：省略 commitPaths 则 fail-closed" | shadow-controller/src/index.ts **:210-213**，注释原文确认语义 | 行号整体下挪 1 行（P2 登记）；语义属实 |
| 3 | approveTask 方法体 index.ts:193-229，合并点在此区间 | registerTask 展开三元在 **:214-217**（`...(request.commitPaths === undefined ? {} : {commitPaths: request.commitPaths})`），registry 取值 :201-202 | 符合（插入 `?? registry.defaultCommitPaths` 即在此三元） |
| 4 | deliver 要求 worktree 干净：delivery-consumer.ts:215 | :215 `git('status','--porcelain=v1','--untracked-files=all') !== ''` → throw :216 | 符合（写法是 `!== ''`，语义等同） |
| 5 | 未注册 checkset 拒点 delivery-consumer.ts:256-257 | :256-257 `checksByTask.get(...) === undefined → throw 'Task has no host-approved checkset'` | 符合 |
| 6 | register 写入点 :558 | :558 `checksByTask.set(...)`，commitPaths 归一化紧随 :559-561 | 符合 |
| 7 | commit scope 精确路径集合：commit-consumer.ts:307 `new Set(scope)` + :308 `has()` | :307 `const scopeSet = new Set(scope)` / :308 `!scopeSet.has(path)` 过滤 | 符合（确为精确集合匹配，非目录前缀） |
| 8 | 未注册 scope 拒 commit：:303-306 | :303-306 `commitPathsByTask.get(...) === undefined → throw` | 符合 |
| 9 | normalizeCommitPaths 拒绝空/绝对路径/`''`/`'.'`/`'..'`/`.git` 段：:174-192 | :175 空数组抛错；:181-183 空串/超长抛错；:185-187 `isAbsolute || win32.isAbsolute || NUL 字节 || parts 含 ''/'...'/'.'/'..'/'.git'` | 符合（另含 64 条上限 :176-178，比计划描述更严，不影响方案） |
| 10 | requirePathsInWorktree 要求文件已存在且在 worktree 内：:203-223 | lstat ENOENT 抛错 :211-212；非文件（目录）抛错 :217；realpath 前缀逃逸抛错 :218-221 | 符合 |
| 11 | Config z.object 加 `defaultCommitPaths: z.array(z.string()).optional()` | delivery-consumer.ts:99-105 z.object **未 `.strict()`**（仓内需严格的 schema 均显式 `.strict()`）；既有 optional 先例 `commitPathsByTask?`(:96/:104 `z.dict(z.array(z.string()))`) | 符合（新增可选键不拒绝既有部署 YAML） |
| 12 | `ProjectDeliveryRegistry` 接口加 readonly 可选字段 | 现接口 :54-69 仅 ledgerPath/registerTask/unregisterTask；TS 结构类型下可选字段纯增量 | 符合 |
| 13 | apply 时从 config 归一化注入 registry | registry 字面量 :552-567，`ctx.provide('projectDeliveryRegistry', …)` :568；`commitPathsByTask` 经 normalizeCommitPaths 落 Map 先例 :544-551；normalizeCommitPaths 已 export（:174）且 apply 已 import（:25） | 符合（可直接复用；空数组必须 fail-loud 不静默） |
| 14 | 桌面 patch 落点 | development-project.ts:206-217（`- id: project-controller-delivery-consumer`，config 块至 :217） | 符合（config 块内加一行即可） |
| 15 | development-project.spec.ts 新增 config 断言 | 现 spec :181 仅断言含 `'id: project-controller-delivery-consumer'`，未断言任何 config 键；新增断言纯增量 | 符合 |

**可行性结论**：方案 A 三落点（Config 可选字段 / registry 接口字段 / approveTask `??` 兜底）均可无破坏落地；既有 26 条 commit-consumer 用例不依赖"Config 无 defaultCommitPaths"，不破坏。唯一行为变化：两者皆无时仍 fail-closed（registerTask 只收 digest），与现状逐字节一致。

### 2. Q-C2 readBoard 契约（shadow-controller / project-controller / shadow-router）

| # | 计划断言 | 源码实际 | 判定 |
|---|---|---|---|
| 1 | `ctx.projectController.list()`，controller.ts:891-894，稳定 (createdAt, taskId) 序 | :891-894 `list(): readonly TaskRecord[]`，sort `createdAt.localeCompare ‖ taskId` | 符合 |
| 2 | TaskRecord 在 project-contracts/types.ts:84-107，无 workspaceId | 字段：taskId/pluginId/title/state/blockedReason?/nextAction?/wakeCondition?/assigneeSessionId?/worktreeId?/createdAt/updatedAt；**确无 workspaceId、无 branch** | 符合 |
| 3 | 六列+blocked/failed 状态值 | types.ts:33-42 九值全小写齐全（planned/assigned/developing/reviewing/submitted/integrated/completed/blocked/failed），与列映射完全对齐 | 符合 |
| 4 | `shadowRouter.listBindings()` service.ts:243 / `findBinding()` :237 | 指 `shadow-routing/src/service.ts` **抽象接口**（:243/:237）；具体实现在 `shadow-router/src/service.ts:880/872` | 行号正确但缺包名（P2-4） |
| 5 | binding 行含 workspaceId/state/controllerSessionId | `ShadowBindingRecord`（shadow-router/src/spec.ts:43-56）三字段均在；**controllerSessionId 实为必填 SessionId** | 符合（计划宽成 `string\|undefined` 可收窄，P2-5） |
| 6 | `resolveTaskStartAuthority(ctx, controllerAgent, taskId, () => false)`，抛错即不可用 | start-authority.ts:105-110 **同步函数**（非 Promise），返回 `TaskStartAuthority` 对象；:77 controllerAgent 缺失/离线 → throw；其余前置条件（Goal/worker/lead/worktree 锁定）全部 throw | 符合（无需 await；"成功 true/异常 false"派生成立） |
| 7 | 只读无副作用 | 函数体全为读（agentBindings/projectController.find/agents.get/workspaceRegistry.list/worktreeRegistry.list），无 enqueue/assign/start 调用 | 符合 |
| 8 | controller agent 经 binding.controllerSessionId → ctx.agents.get 解析 | shadow-controller/index.ts:199 现有生产代码即此调用，已验收 | 符合（直接复用） |
| 9 | `ctx.worktreeRegistry.list(workspaceId)`，row.path | worktree-registry/src/registry.ts:101 `list(workspaceId)`（**workspaceId 必传，无无参重载**）；Worktree 行含 `path`（types.ts:79-99），另带创建时 `branch` 快照与 `status(worktreeId)` 实时查询 API（:109） | 符合（链路每环字段真实存在） |
| 10 | branch 采集：裸 execFile('git', …)，timeout 5000，windowsHide | project-controller 家族确用 `promisify(execFile)`+windowsHide+timeout（consumer/completion/commit/delivery-consumer 一致），**但统一用 config.gitExecutable 而非硬编码 'git'**；且已有一等只读 API `worktreeRegistry.status()` 直接返回实时 branch | 写法符合家族惯例但可复用既有 API（P1-4）；硬编码 'git' 计划 §3 已登记偏离 |
| 11 | readBoard 同步签名 `@Remote readBoard(): ShadowBoardSnapshot` | 计划 §2 C-1.2 写同步；但 branch 采集 execFile 是异步；同包所有异步 Remote（openProject:125/sendToController:137/approveTask:193）均显式 `async …: Promise<…>`，唯一同步的 readStatus(:105) 不 spawn 子进程 | **签名矛盾 → P1-1（必须改 async）** |
| 12 | ShadowBoardTask 各字段数据来源 | taskId/pluginId/title/state/blockedReason/nextAction/wakeCondition/createdAt/updatedAt 全部直取 TaskRecord 同名字段；startReady 派生自 #6；branch 派生自 #9 | 符合 |

**可行性结论**：readBoard 只读主干（list/listBindings/resolveTaskStartAuthority 同步纯读）成立；startReady 的 try/catch 派生语义与 approveTask 可批准性自洽。**唯一硬伤：签名必须 async**。

### 3. Q-C3 看板 UI（ui-conversation / ui-chat / client-ui-shadow-entry）

| # | 计划断言 | 源码实际 | 判定 |
|---|---|---|---|
| 1 | `conversation.view` 插槽 ui-conversation slots.ts:117 | :117 `kind:'list' scope:'session' owner: ConvViewOwnerProps` | 符合（行号精确） |
| 2 | `conversation.session.header.actions` :105-109 | :105-109；owner 类型 :181-184 注释明言"entries receive no owner-specific values" | 符合 |
| 3 | `ConversationSessionHeaderInjected.selectView` :234-241 | :234-241，:240 `selectView:(view:string)=>void` | 符合 |
| 4 | ConversationSession.tsx:130 `renderSlot(..., {})` 不传 owner props | :130 原文如此；header 的 selectView 只注入 ConversationSessionHeader 槽体自身（apply.ts:261-268），不向下传给 actions 条目 | 符合（计划"actions 条目拿不到 selectView"判断成立） |
| 5 | :146 tab 由 `selectView(viewTab.id)` 渲染；注册后 tab 自动出现 | :146 `onClick={() => selectView(viewTab.id)}`；roster 读 `slots.entries('conversation.view')` 并订阅插槽变更（apply.ts:121-160）；'chat' 已注册（ui-chat apply.ts:94-97），tab 栏仅在 tabs.length>1 渲染（:137）→ 注册 'board' 后自动变 2 条出现 | 符合 |
| 6 | ChatViewSlotProps 模式 ui-chat slots.ts:150-155 | :150-155 `PropsRuntime + PropsRenderSlots + PropsStore + InjectFace + PropsLocale`；本包 ShadowCard.tsx:30-31 已有同形先例（PropsRuntime + InjectFace + PropsLocale，无后两者） | 符合 |
| 7 | 注册 label `t('board.tab')` | register 作用域无组件级 t；现行可编译写法是 `const t = ctx.locale.bind(NS)` 后 `label: () => t(...)`（ui-chat apply.ts:76/99 先例），roster 在 locale 变更时重算 thunk | **措辞须改 thunk → P1-6** |
| 8 | createSnapshotStore + 最新读胜出模式可复用 | shadow-store.ts:23-56 现有 ShadowStatusController 即此模式；mount.ts:49-53 实例化 | 符合 |
| 9 | 自检 `sessionId === shadowSessionId` 数据源 | ShadowStatusView 确含 shadowSessionId（mount.ts:50-51）；**但** Q-C2 的 ShadowBoardSnapshot 无此字段、§2 C-3.3 的 BoardViewInjected 也未接 status store | **接线缺口 → P1-5** |
| 10 | onOpenConversation 语义可复用（候选路径①） | mount.ts:64-75 读 readStatus→校验→sessions.open(sessionId)；slots.ts:16 为 face verb | 符合（候选路径①可落地） |
| 11 | `ctx.uiConversation` 服务面可达（候选路径②） | 真实存在，`binding(sessionId).activate(...)` 可用（assembly.ts:210/82） | 符合（技术可达，建议默认路径①） |
| 12 | BoardView.module.css 沿用 ShadowCard 样式语言 | 同包同 css-modules 声明，PostCSS/打包一致 | 符合 |
| 13 | BoardView 注入 ui-conversation 插槽的依赖声明 | 本包 package.json 的 `dsh.client.inject`（:28-36）与 peerDependencies（:48-61）**均未含** `@deepseek-ai/dsh-client-ui-conversation`；`PropsRuntime<'conversation.view'>` 类型合并与运行期装配都需要它 | **计划未声明 → P1-3** |

**可行性结论**：UI 架构成立——插槽注册机制、tab 自动出现、props/snapshot/locale 模式、jsdom 测试基建全部有源可依。三处 P1（依赖声明、shadowSessionId 接线、label thunk）执行前修订即可。

---

## 二、测试与验收完备性

### 总计划 §4 验收覆盖对照

| 总计划条目 | 阶段 C 计划对应 | 判定 |
|---|---|---|
| §4.2 端到端全链路（plan→approve→develop→deliver→review→integrate 每步投影） | §4.4 等价覆盖 | 已覆盖 |
| §4.3 停 planned / 打回 blocked / 未 approve 拒 deliver | 阶段 B 已验收（本阶段不改此语义） | 不属本阶段 |
| §4.3 重新批准走 resume | 计划全文无 resume RPC、blocked 卡无"重新批准"按钮 | **缺口 → P1-8** |
| §4.5 keyless test:snapshot | §3 偏离已记 fallback（无 key 则补 presenter 快照） | 已覆盖（fallback 自洽） |
| §4.6 #16 building 卡 live 行 branch+updatedAt | Q-C3 卡片 + Q-C2 branch 采集 | 已覆盖 |
| §4.6 #21 repairLimit 显示 | Snapshot/TaskRecord 均无 repairLimit 字段 | **缺口 → P1-9** |
| §4.6 #13/#19/#20/#11 归属 | 计划未逐条标注 | P2-7（补归属表） |
| §4.7 UI 规范 + presenter 快照断言 | §4.5 + board-presenter 纯函数 toEqual | 已覆盖 |
| §4.9 真实界面截图（127.0.0.1:3080） | 计划全文未提、§3 也未记 deferred | **缺口 → P1-7** |
| §4.8 仓库门 + per-file 100% | §4.2/§4.6 | 已覆盖 |

### 测试分支充分性

- host readBoard：mounted:false / 全量投影+稳定序 / startReady 真假两路 / branch 采集成功/失败/5s 缓存——均已列；**漏：shadowRouter 缺失降级分支（步骤 2 设计了、步骤 3 测试清单无）→ P1-11**。
- client 侧：六列投影 / blocked-failed 独立行 / 黄底两阈值 / startReady 置灰 / 自检 null / 批准 RPC 形态 / 往返 disabled / 5s 移列 / 打回 note / 失败重试 / 轮询调度与失败保留——均已列；**漏：mounted:false → disabled 展示模型用例 → P1-10**。
- per-file 100% 门：根 vitest.config.ts include `packages/*/*/src/**`、perFile 100（:362-369），本包仅 `src/client/index.ts` 豁免。该包 tests/ 已有 4 个 spec 34 条全绿，新增 board 用例不会把未测文件首次拉进门——计划判断成立。
- spec 归属：tests/ 已存在 shadow-presenter/shadow-store/shadow-mount/shadow-card 四个 spec；计划另起 `board-presenter.client.spec.ts`/`board-store.client.spec.ts` 与现有同包双 presenter/store spec 并存，归属不明 → **P1-12（建议扩展现有 spec）**。

### 只读复跑基线（未改任何文件）

| 命令（仓库根） | exit | 结果 |
|---|---|---|
| `pnpm exec vitest run packages/experimental/shadow-controller/tests/shadow-controller.host.spec.ts` | 0 | 17/17（1.51s） |
| `pnpm exec vitest run packages/experimental/client-ui-shadow-entry` | 0 | 34/34（4.30s，4 spec） |
| `pnpm exec vitest run apps/desktop/tests/development-project.spec.ts` | 0 | 3/3（0.65s） |

未跑 commit-consumer 全量（阶段 B 已实测 26/26 绿、86s，慢且本计划不改其语义）。

---

## 三、P0 / P1 / P2 意见清单

### P0（阻断）

**无。** 未发现计划断言与源码矛盾到无法实现、或破坏既有测试门的点。

### P1（执行前必须修订，共 12 条）

1. **readBoard 签名必须 async。** 计划 §2 C-1.2 写 `@Remote readBoard(): ShadowBoardSnapshot`（同步），但 branch 采集 execFile 是异步；同包所有异步 Remote 均显式 `async …: Promise<…>`。改为 `async readBoard(): Promise<ShadowBoardSnapshot>`，client 轮询相应 await。
2. **commitPaths 定义文件指错。** `ShadowApproveTaskInput.commitPaths` 在 `shadow-controller/src/types.ts:88`，不在 project-contracts（那里 :88 是 TaskRecord.pluginId）。计划须明确"不改 project-contracts；新增面是 registry.defaultCommitPaths"，按字面改错包。
3. **BoardView 依赖 ui-conversation 包未声明。** client-ui-shadow-entry/package.json 的 dsh.client.inject 与 peerDependencies 均无 `@deepseek-ai/dsh-client-ui-conversation`；按仓库"bare 插件必须出现在 resolver manifest dependencies"规则会被 hygiene 门拦。须在 peer/dev/inject 三处补声明。
4. **branch 采集建议复用既有只读 API。** 仓库已有 `worktreeRegistry.status(worktreeId): Promise<{branch}>`（实时）与 Worktree 行自带创建时 branch 快照，比自造 execFile + 自管 5s 缓存更符合"prefer maintained over hand-rolling"；若坚持裸 git，应与家族一致读 config.gitExecutable 并传 env/signal/maxBuffer，不要硬编码 'git'。
5. **自检 shadowSessionId 接线闭环。** 计划自检 `sessionId === shadowSessionId`，但 ShadowBoardSnapshot 无此字段、BoardViewInjected 也未接 status store。推荐：BoardViewFace 增 `hooks.status: ShadowStatusController.store`（复用 mount.ts:49 同一实例），或把 shadowSessionId 加进 Snapshot。
6. **register label 改 thunk。** `label: t('board.tab')` 在 register 作用域无组件级 t；须 `const t = ctx.locale.bind(NS)` 后 `label: () => t('board.tab')`（ui-chat apply.ts:76/99 先例），否则失去 locale 跟随。
7. **验收 9 真实界面截图缺口。** 总计划 §4.9 要求 Web UI（127.0.0.1:3080）截图验证；阶段 C 恰是 UI 交付物，计划既未做也未记 deferred。二选一：§4 补截图验收，或 §3 明记 deferred 并说明理由。
8. **blocked 卡"重新批准 resume"无 RPC 无 UI。** 总计划 §4.3 要求打回后可重新批准；现 approveTask 仅接受 planned（index.ts:200），无 resume RPC，计划 blocked 卡无对应按钮。须明确：阶段 C 补 resume（或 approveTask 扩展接受 blocked）+ UI，或 §3 明记 deferred 并说明 v2 中 blocked 任务如何恢复。
9. **#21 repairLimit 看板显示无着落。** 总计划 §4.6 点名 #21（repairLimit 撞限时显示"已回退次数+末次失败命令"）；Snapshot/TaskRecord 均无此字段。须补 readBoard 数据携带并在 building 卡展示，或 §3 明记 deferred 到阶段 D。
10. **mounted:false 的 UI 态无测试。** 设计了降级 disabled 态，但 presenter/view 测试清单未列；per-file 100% 门必要求该分支。补一条"空 board/mounted:false → disabled 展示模型"断言。
11. **shadowRouter 缺失降级分支未测。** C-1 步骤 2 设计了该分支，步骤 3 测试清单无。补 host 用例（projectController 在、shadowRouter 缺 → mounted:true 但 bindings 空）。
12. **新增 spec 归属不明。** 建议 board 用例**扩展现有** shadow-presenter/shadow-store spec（coverage 按文件维持 100%），而非新建 `board-*.spec.ts` 与现有同包双 spec 并存；若新建须说明拆分理由。

### P2（收尾时做，共 9 条）

1. 行号小偏差：approveTask 注释 fail-closed 实际 :210-213（计划写 209-212，下挪 1 行）；其余 Q-C1 全部行号精确命中。
2. apply 新增 `if (config.defaultCommitPaths !== undefined)` 分支须补"缺省 → registry 为 undefined、行为不变"用例，与新"有默认值"用例成对保护既有 host.spec.ts:291 断言。
3. 设计补注：Config 已有 `commitPathsByTask`（apply 期静态 seed），与新增 `defaultCommitPaths`（approve 期兜底）职责差异建议一句话点明；首轮 taskId 由静态 goal-binding 决定，走旧字段反而更省代码的取舍值得记录。
4. 行号歧义：service.ts:243/237 指 shadow-routing 包抽象接口，具体实现在 shadow-router/src/service.ts:872/880——补全包名，避免执行时打开错文件。
5. `ShadowBoardBinding.controllerSessionId` 实际是必填 SessionId，计划宽成 `string | undefined` 可直接收窄为 `string`。
6. readBoard 注释写明：依赖服务不齐（agentBindings/workspaceRegistry 等缺）时 startReady 全 false，而非 mounted:false。
7. 总计划点名用例 #13/#19/#20/#11 的归属建议 §3 补一行归属表（均不属阶段 C），避免验收误判。
8. 执行时注意：新 spec 放 client-ui-shadow-entry/tests/；BoardView 组件 spec 头加 `// @vitest-environment jsdom`；5s 轮询/移列用 vi.useFakeTimers，本包现无先例，先跑通一个 fake-timer 用例再铺开。
9. 候选路径①若采用：board-toggle 条目须复用/抽取 mount.ts:64-75 的 onOpenConversation 逻辑（现为 ShadowCardFace 私有闭包），不要复制两份。

---

## 四、终审

阶段 C 计划的源码调研质量高：Q-C1 的 normalizeCommitPaths/scope 精确匹配/fail-closed 三处核心机制断言全部经亲验属实；Q-C2 的 list() 投影、resolveTaskStartAuthority 同步纯读、worktreeRegistry 链路逐环真实存在；Q-C3 的插槽契约行号零偏差、tab 自动出现与 actions 拿不到 selectView 的判断均成立。既有测试基线三路复跑全绿（17/17、34/34、3/3）。

**有条件通过。** P1 共 12 条均为"计划修订"层面的问题（签名、依赖声明、接线闭环、验收对照、测试分支补列），不涉及推翻设计——其中 P1-1（readBoard async）与 P1-2/P1-3（指错文件、漏声明依赖）是必须最先修的三条硬项。P1 全部落实后即可按 §2 阶段划分进入 C-1 → C-2 → C-3 执行；P2 可收尾阶段一并处理。
