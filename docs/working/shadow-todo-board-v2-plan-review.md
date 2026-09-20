# Shadow Todo 看板 v2 实施计划 — 独立第三方评审意见

- 待审计划：`docs/working/shadow-todo-board-v2-plan.zh.md`
- 对照基线：`docs/working/shadow-todo-board-review.md`（v1 三方审核 22 条硬伤）、`docs/working/shadow-todo-board-handoff-v2.zh.md`
- 评审方式：两名独立评审员分别核对（A）计划全部源码断言 vs 真实源码、（B）22 条硬伤覆盖度与可执行性；P0 两条经评审组复核原码确认。
- 评审日期：2026-09-20
- **结论：打回。** 计划方向（路线 3：接 project-controller 核心件）正确，P0 级源码事实错误 2 处，P1 必须修 7 处，不可直接进入实施。修改后需重新送审。

---

## P0 — 阻断执行（必须改对才能开工）

### P0-1　Q3「空 checkset 可注册」前提与源码直接冲突，且改动面漏了关键文件

- 计划声称：空 checkset（`version: 1, checks: []`）可作为种子注册，deliver 时空循环即过（Q3）。
- 源码事实：`packages/experimental/devframe/src/required-checks.ts:84-90`
  ```ts
  export const requiredChecksConfigSchema = z.object({
    version: z.literal(1),
    checks: z.array(requiredCheckSchema).min(1).refine(/* checkId 唯一 */),
  }).strict()
  ```
  `:86` 的 **`.min(1)`** 使 `{version:1, checks:[]}` 在 `decodeRequiredChecksConfig`（:138-151）处直接抛 `REQUIRED_CHECKS_INVALID_CONFIG`；而 file-store 每次持久化读都对每条 registration 跑该校验（`required-checks-file-store.ts:105`）。**空 checkset 在物理上无法落账**。
- 影响：按计划现状实施，host 注册空 checkset 后第一次读 ledger 就炸；deliver 仍会被拒。
- 计划改动面遗漏：Q3 只列「改 delivery-consumer.ts + 注册面定义」，**未提 required-checks.ts 本身要放宽 `min(1)`**。这是跨包契约改动——现有 `development-project.ts:152-158` 的 command-goal-binding 用的是非空 git-diff-check，放宽 schema 会改变整个 devframe 包的校验语义，必须补 invalid/valid 用例。
- 修法：二选一并在计划里写明——(a) 把 schema 放宽为 `min(0)` 并补一对用例；或 (b) 放弃空 checkset 路线，给每个看板 task 种子一个最小非空 check（如 `git-diff-check`）。无论哪条，都要把 required-checks.ts 列入改动文件清单与验收。

### P0-2　Q1 approveTask 直调 `assign`/`startDevelopment`，绕过 task-consumer 的全部前置断言与 router 写面闸门

- 计划声称：approveTask RPC 内联 `assign→startDevelopment→followup`，步骤 3 只查「存在 role=worker 且 taskId/pluginId 匹配的 binding，无则 fail-loud」。
- 源码事实：
  - 一整套安全前置**只在工具层**：`task-consumer.ts:88-102` 要求「恰一个 worker + lead 存在且 parentSessionId=root + worker/lead agent 在线且 cwd 对齐各自 worktree + 两个 `lockedBy` 分别为 worker/lead session + `new Set([target,source,reviewer]).size===3`（三个独立 worktree）」。
  - 而 `controller.ts:400-408 assign` 与 `:416-431 startDevelopment` 只做 `requireTransition` + `requireAdmissionOpen` + `maxActiveTasks` 并发预算，**不复刻上述任何一条断言**。
  - 结论：approveTask 若按计划直调这两个方法，worktree 未建、worker/lead 未绑、写锁未占齐时照样能把任务推进到 developing——这正是 task-consumer 工具层原本要挡住的非法态。
- 次生问题（与 v1 硬伤 #17 同类）：`shadow-controller/src/index.ts:8-11` 文件头约定「所有 project 写面 delegate 到 shadow-router 的 `*ForHost` gated bridge」（caller gate / 回放 / 投递都在 router 侧）。approveTask 直调 projectController 是新写面，**绕过了这套 gate**，必须自证 caller 是 designated Shadow authority——否则 v1 #17「Shadow 自批绕过 gate」的边界在新 RPC 上重现。
- 修法：计划须在 Q1 明确 approveTask 复用 task-consumer 的前置断言（抽成可复用的 host-side 校验函数，或直接走经 host authority guard 包装的入口），并补上 caller 闸门设计，不能只查「worker binding 有无」。

---

## P1 — 必须修（不解决会留执行缺口或违背审核结论）

### P1-1　v1 硬伤 #15（超时软告警）被整体 deferred，违反 review 最低交付要求
- review #15 明确要求「v2 至少加一个软告警（超 N% 黄底）」。计划 §0 表（line 22）与 §7（line 169）把软告警连同花超停机一起 deferred，痛点④在 v2 内 0 交付。这是有意识地偏离审核意见，送审须显式标注「已知不接 #15」，而不是藏在 deferred 列表里。

### P1-2　v1 硬伤 #18（Chief 何时开 todo 的触发规则）全文缺失
- review #18 要求给「查询解释类直接答、交付物类才开 todo」的触发规则 + 正反例。计划只讲 controller 侧 plan→派工，**通篇无任何 Shadow/Chief 系统提示词改动**，也无触发规则与示例。

### P1-3　Goal 创建路径半定义
- 阶段 B 第 1 点只写「验证 `/devframe-start` 可创建 goal 进入 admission_open」——这是验证动作不是操作路径。谁触发（用户/Shadow/controller 自动）、新看板 task 如何被现有 `taskIds:['devframe-goal']` 接纳、每次派活落同一 Goal 还是新建、单 Goal 复用策略，全部没讲。而 task-consumer 硬前置正是「task 必须在当前 open Goal 的 taskIds 内 + admission_open」（task-consumer.ts:67-72），整个闭环入口卡在这里。须补一节「Goal 生命周期」。

### P1-4　worker worktree node_modules 策略「或」未定 + 无 owner + 首次引导未定义
- 阶段 B 第 4 点写「`pnpm install --frozen-lockfile` **或**依赖镜像」未拍板；「worker 启动脚本」由谁产出无人负责；干净 worktree 首次 install（content-store 硬链接在本仓是否真生效、失败兜底）未定义。须定死一种策略并指定 owner，把「首次空 worktree 引导」写进预配冒烟。

### P1-5　agent_dispatch / devframe 所在插件的挂载行未列入 patch
- 阶段 A 把 `agent_dispatch`/`worktree_*` 写进 controller face，但 `buildDevFrameDeploymentPatch` 的 rows 只列了 project-controller 四个 row，**没列「提供 agent_dispatch 工具的那个插件/consumer row」是否进 patch、是否进 devframeLinks**。工具名写进 face ≠ 工具所在插件已挂载。
- 附带：delivery-consumer 从 `@deepseek-ai/dsh-experimental-devframe` 导入 `FileRequiredChecksConfigStore`/`RequiredChecksDigest`（delivery-consumer.ts:16-22），当前 devframeLinks（development-project.ts:246-272）只链了 `devframe-profile`，**未单独链 `devframe` 包**，计划阶段 A 也未提。须按 disposable node_modules 解析方式确认是否需要显式 link。

### P1-6　Q3「host 在 task 被 plan 时自动注册」的触发钩子未定义，存在时序竞态
- plan 是 controller agent 的一次模型工具调用，不是 host 事件；host 凭什么信号在「刚 plan、还没 deliver」之间截获并注册？若 deliver 先于注册触发，会被 delivery-consumer.ts:207 的 `'Task has no host-approved checkset'` 直接拒掉。须定死 projectController 哪个生命周期钩子/事件负责注册，并用一条单测锁住 plan→注册→deliver 的先后。

### P1-7　验收 2/3/4 无 recorded-session 场景，点名硬例未进测试
- AGENTS.md 测试策略要求「每处 model-/协议-/产品可见变更更新一个 keyless 录像场景」，计划 §6 只字未提 `test:snapshot`。
- 验收 2（全链路闭环）/3（HITL 语义）/4（model-visible）全是「人工走一遍/人翻日志」；v1 点名的硬骨头——#13 building 中途杀进程恢复、#19 两条并发（cancel 时 worker bash 在跑 / building 中 controller stop-rebind）、#20 原生 Windows 阻塞冒烟——无一进验收或测试清单。
- 「蓝白视觉/loading 态齐全」应换成 presenter 快照断言。

---

## P2 — 建议（不阻断，但送审前顺手修）

- **P2-1　行号/语义误植（delivery-consumer）**：真正拒 deliver 在 `delivery-consumer.ts:207`（显式 `throw new Error('Task has no host-approved checkset')`），`:208` 才是 brand parse；计划引的 `:334` 实为 `project_evidence` 只读工具的 `?? null` 容错分支（后续 :383 返回 `stale_verification`），不是拒 deliver 点。结论方向对，引用要修。
- **P2-2　§7 误引硬伤编号**：line 172 把 cancelTodo 无处调用标为「v1 硬伤 #6」，实为 **#4**；#6 是「一 workspace 一 binding 并发假设」。
- **P2-3　行号小偏差**：task-consumer 实际区间 :79-120（计划写 :59-119）；shadow-routing `findBinding` 在 service.ts:237、`listBindings` 在 :243（计划把 :237 指给 listBindings）；`ProjectStatusEntry.controllerSessionId` 在 types.ts:201。结论不受影响，但证据要对齐。
- **P2-4　P1/P2 硬伤「方向覆盖、点名用例未进验收」**：#11（配置加载期 fail-loud：lead 身份/leadPluginScope/worktree 可写性）、#16（building 卡片 live 行：当前 branch/最近命令）、#19（两条并发用例）、#20（windows-blocking 冒烟）、#21（repairLimit:3 无依据、不区分抖动与真缺陷）均如此——补进验收/测试即可。
- **P2-5　审批竞态未提**：按钮 disabled 与 5s readBoard 轮询的竞态（点批准后 5s 内又轮询到旧态）、Q1 fail-loud 与 B 阶段「模型预配在批准前」的 UI 时序（预配未完成时按钮该置灰还是点了报错）未约定。建议加「批准后 5s 内卡片移入 Building」的可观察断言。
- **P2-6　「仅 Shadow 会话渲染」是组件级自检，不是插槽级过滤**：`conversation.view` 与 `conversation.session.header.actions` 均为 `scope:'session'` 的 list 插槽（slot-catalog.ts:1271-1327 / :1079-1136），插槽本身不按 session 过滤；BoardView 必须在**渲染层每帧**用 `sessionId === shadowSessionId` 自检并对其他会话 return null，否则所有会话都会多一个 board tab/header 按钮。
- **P2-7　readBoard 对 projectController 未挂载需 fail-loud/降级**：ShadowController 现有惯例是 `ctx.get(...)` 可选取服务（index.ts:91），新 RPC 不能假设 projectController 一定在 host context 挂载。
- **P2-8　#5/#9/#10 靠架构变更隐含解决，缺收口句**：#5（多轮回退/打回理由）、#9（不建新存储域故免 SCHEMA_VERSION）方向上被 project-controller 吸收，但计划未点号、未说明落在哪；#10（执行面 allowlist）全文未出现 allowlist 字样，应补一句「Shadow 本身不新增工具、其 allowlist 不动，controller/lead/worker 三个 face 的显式工具面即为本架构的 allowlist」。

---

## 已核对为属实、无需改动的断言

- task-consumer `start()` 四项前置（live root controller / 恰一 worker / lead+三 worktree 写锁 / open Goal）与行号范围属实（task-consumer.ts:59-120）。
- `buildDevFrameDeploymentPatch` 当前 rows 确无 project-controller/agent_dispatch/worktree 注册面，agent-hierarchy `roleToolPolicies` 确为窄列表（development-project.ts:109-192）。
- shadow-controller 以 `TypertRemoteService` + `@Remote` 方法 + types.ts 请求/结果类型暴露面，新增 readBoard/approveTask/rejectTask 与现有六方法同构，模式可行（注意 P0-2 的写面闸门问题）。
- `ShadowBindingRecord.controllerSessionId` 字段存在（types.ts:56），`findBinding`/`listBindings` 返回类型均带该字段。
- 两插槽均为 list、可追加（slot-catalog.ts）。

## 复评要点（修改后请逐条回应本文件）

1. P0-1、P0-2 的修法选型（空 check schema 放宽 vs 种子最小非空 check；approveTask 如何复用 task-consumer 断言与 router gate）。
2. P1-1/P1-2 是「本轮就做」还是「显式记录已知偏离」——二选一，不要藏在 deferred。
3. P1-3 至 P1-7 的缺口是否各补了一节或一行可执行定义。
4. 验收是否补齐 keyless recorded-session 场景与 #13/#19/#20 三条点名用例。
