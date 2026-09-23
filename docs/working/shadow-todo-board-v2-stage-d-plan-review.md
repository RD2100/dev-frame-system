---
title: Shadow Todo 看板 v2 — 阶段 D 计划评审意见（汇总 r2）
owner: shadow
status: review-done-r2
date: 2026-09-21
reviewed: docs/working/shadow-todo-board-v2-stage-d-plan.md（draft-plan-r1）
based-on: docs/working/shadow-todo-board-v2-stage-d-plan.md（draft-plan-r1）、docs/working/shadow-todo-board-v2-delivery-chain-diagnosis.md（根因）、docs/working/shadow-todo-board-v2-stage-c-plan.md（r2）、docs/working/shadow-todo-board-v2-stage-c-plan-review.md（评审范式）
review-standard: 只读、逐行亲验源码、不采信二手转述、P0/P1/P2 分级
---

# Shadow Todo 看板 v2 — 阶段 D 计划评审意见（r2 合并稿）

- 评审对象:`docs/working/shadow-todo-board-v2-stage-d-plan.md`(draft-plan-r1,D-1 宿主侧 controller provisioner + D-2 规划上下文 + 真实 e2e)
- 评审方式:只读,不改任何源码 / 不 commit / 不重跑套件。计划引用的每一处源码位置均实际打开文件核对,不采信计划自述或根因文档的二手转述。
- 本稿说明:r1 已覆盖 D-1 全部关键技术假设并亲验;r2 聚焦 D-2(worktree 绑定、goal 上下文)源码可行性做行级亲验,并对 r1 的 P0(open 入口分裂)与 resume 事件顺序做了复核。合并后结论见下。
- **结论:有条件通过(P0×4、P1×6、P2×7)。**
  - D-1 技术内核(resume 签名、resume 触发 `agent/created`、agent-hierarchy 角色工具注入、空 setup 不丢 cwd、bridge 60s 安全网)全部亲验成立;**但 provisioner 落点漏了对话入口**(P0-1,r1 提出、本轮复核确认)。
  - D-2 的三处"最小方案"按现描述**在现有 API 下不成立**,不是"补满足前置"那么轻:worktree 不能登记项目根(P0-2)、agentBindings 拒绝二次改绑(P0-3)、goal binding 无 host 侧轻建立通道(P0-4)。建议 D-2 goal 条直接 deferred;worktree 条按真建 linked worktree 的规范模式重做。
  - 4a 通过线站得住,但"投递状态从 received 前进"措辞错误(P1-3)。

---

## A. 逐条核对表(计划断言 ↔ 源码实际 ↔ 判定)

### A-1 投递链根因(计划 §1 / 根因文档)

| # | 计划/根因断言 | 源码实际(file:line + 摘录) | 判定 |
|---|---|---|---|
| 1 | forwarder.ts:171-174 只转 live agent;桥从不创建/恢复 | `shadow-bridge/src/forwarder.ts:171-174`:`const agent = this.deps.agents.get(binding.controllerSessionId)` 紧接注释 `// v1 forwards to live controllers only…the bridge never creates or resumes one.` 再 `if (agent === undefined) return` | **符合(逐字命中)** |
| 2 | 既存 received 投递由 60s 安全网轮询自动转发,无需重发 | `forwarder.ts:121-128` poll 遍历 `router.listDeliveries()`,过滤 `state==='received' && mode==='work'` 后逐个 serialize;触发周期由桌面 `intervalMs` 决定 | **符合** |
| 3 | README.zh.md:112 / :124 明示边界与扩展方向 | `shadow-bridge/README.zh.md:112`:"…从不创建、恢复或收养 agent;宿主从未使之 live 的 controller 永远收不到它的投递,投递保持 received";:124:"…以及一个在保留会话上拉起 controller agent 的宿主侧 provisioner——这三者本桥都刻意不拥有" | **符合(逐字命中)** |
| 4 | router completeProvisioning 只 sessions.create + bind,不 resume | `shadow-router/src/service.ts`:`createControllerSession`:1126-1140 内 `sessions.create(..., { meta:{ cwd: record.canonicalPath, agentPreset } })`(:1129-1131);`completeProvisioning`:1143-1153 内 `agentBindings.bind({ agentId: record.controllerSessionId, role: 'controller' })`(:1145)。全程无 agents.resume | **符合** |
| 5 | shadow-controller openProject(index.ts:130-133)不 resume | `shadow-controller/src/index.ts:131-133`:仅 `return await this.requireRouter().openProjectForHost({...})` | **符合** |
| 6 | 全仓无宿主 resume controller 代码;agent-hierarchy 只恢复 worker/lead | `agent-hierarchy/src/service.ts:268` 的 agents.resume 在 createChildAgentSerial(:178-283)内,仅对 reserved child 恢复 | **符合** |

### A-2 D-1 方案(计划 §2.1)

| # | 计划断言 | 源码实际 | 判定 |
|---|---|---|---|
| 7 | resume API 签名 `{ resumeSessionId, agentOptions, setup }` | `packages/core/agent/src/index.ts:132-149` ResumeAgentOptions 四字段一致;agent-hierarchy 恢复路径 `service.ts:268-273` 同款调用 | **符合** |
| 8 | setup 空/最小不缺 cwd;cwd/preset 已在 session 创建时写入 | ResumeAgentOptions 无 meta 字段;cwd/agentPreset 在 service.ts:1130 写入 header,resume 走 persistence.prepare 恢复 header(agent-loop :748-767,r1 亲验) | **符合** |
| 9 | **resume 是否触发 `agent/created`(角色策略注入时机)** | `agent-loop/tests/resume.spec.ts:350-359` 断言 resume 顺序含 `agent/created`;agent-hierarchy `service.ts:93-97` 全局 `ctx.on('agent/created')` → 查 `agentBindings.find(agent.id)` → `installRestriction`(:306-311)→ `agent.ctx.tools.restrict({ allow: [...policy.inheritedTools] })`。provisioning 期已绑 controller 角色(A-1#4),故注入必然发生 | **符合(本轮复核确认)** |
| 10 | agentOptions 复用 agentDefaultModel.currentSelection()(shadow-agent.ts:295-299 同款);缺失 fail-loud | `shadow-agent.ts:295-299` get + fail-loud + currentSelection();:300-304 组装 `{provider, model, reasoningEffort}` | **符合** |
| 11 | project_task 全局注册;controller inheritedTools 含 project_task/project_integrate/worktree_* | `task-consumer.ts:29` `ctx.tools.register(defineTool({name:'project_task'}))`;桌面 `development-project.ts:161-163` controller inheritedTools 确含 `project_task, project_integrate, worktree_create/list/prune/remove/status, create_goal/get_goal/update_goal`。execute 内 `authority()`:60-63 调 resolveControllerAuthority(:62) | **符合**(注意:是 allow-list,白名单外工具不可见) |
| 12 | 幂等判 live 与 forwarder 同一 registry | 同一 AgentRegistry 单例 | **符合** |
| 13 | resume 失败记 binding needs_attention/logger | `markNeedsAttention` 是 shadow-router **private**(service.ts:1156-1163);抽象 ShadowRouter 公开面无此方法 | **偏差 → P1-1** |
| 14 | **openProject 是"面板与对话共用的唯一打开入口"** | **实际两条**:①面板走 `index.ts:132` @Remote;②对话里 Shadow LLM 调 `shadow_open_project` 工具(`shadow-tools.ts:126`)**直接** `router.openProjectForHost(...)`,绕过 @Remote。本轮亲验 shadow-tools.ts:126 确认 | **错误 → P0-1** |

### A-3 D-2 规划上下文(计划 §2.2,本轮重点亲验)

| # | 计划断言 | 源码实际 | 判定 |
|---|---|---|---|
| 15 | resolveControllerAuthority 要求 bind 带 worktreeId/worktreePath 且等于 session cwd | `start-authority.ts:79-81`;cwd 为**字符串精确相等**(非 realpath) | **符合** |
| 16 | authority 还要求 devframe state 有 admission_open goal binding 且 taskIds 含 taskId | `start-authority.ts:82-87`:`state?.bindings.at(-1)`,要求 lifecycle==='admission_open'、`goal.controllerSessionId===root.sessionId`、`goal.taskIds.some(id===taskId)` | **符合** |
| 17 | host open run 的 goal(service.ts:688-692)只写 goalId/acceptanceHash,无 taskIds | `establishHostOpenRun`:688-692 → `setActiveGoal(...'host-run-<rev>', 'open-run-<rev>')`(:761-771 只写 binding row 的 activeGoalId/activeAcceptanceHash) | **对 shadow row 符合**(但与 D-2 所需对象是两套,见 #21) |
| 18 | **D-2 item 1:"controller 的 worktree 即项目根(非 git worktree 语义)"** | **不成立**:① authority 除 #15 外还要求 registry row 存在且 `row.path===root.worktreePath`、`String(row.lockedBy)===String(root.sessionId)`、`String(row.workspaceId)===String(goal.workspaceId)`(`start-authority.ts:88-91`),计划只写了前半;② worktreeRegistry `create` 明确"path must not collide with the owner workspace directory"(`worktree-registry/src/registry.ts:64-66`);`reconcile.adoptUnregistered` 注释"The repository's main worktree is never reported as unregistered"(:139-140);无登记任意已存在路径的 API——项目根永远落不成 row;③ 规范模式是真建 linked worktree:`create({workspaceId, path})` → `bind(tree.id, WorktreeLockHolder(sessionId))` → session cwd = tree.path(`project-controller/tests/fixtures/integration-snapshot.ts:54-61`) | **不成立 → P0-2** |
| 19 | **agentBindings 可"补注册"worktree** | `session-identity/src/registry.ts:260-267`:已存在且内容不同的记录二次 bind 抛 `SESSION_IDENTITY_ALREADY_BOUND`;`sameRecord`(:111-121)比较含 worktreeId/worktreePath/branch。当前 controller 已以无 worktree 字段 bind 过,事后补必炸;无 update/rebind 方法 | **不成立 → P0-3**:worktree 必须折进首次 bind |
| 20 | DevFrame goal binding 由 /devframe-start 建立 | 属实,但代价远高于计划暗示:binding 经 `landGoalBinding(journal, session, binding)` 落进 controller 会话日志(`command-goal-binding/src/composition.ts:383-384、490`),projection fold 日志事件后 `state.bindings.at(-1)` 才非空;`GoalBindingController.start` 需 native goal create + human authorization confirmation + sourceFingerprint + snapshot + required checks 真实执行(`devframe/src/controller/goal-binding.ts:604-643`;StartGoalRequest:349-357) | **属实但非轻路径** |
| 21 | **"host 在 open 时以 goals 服务建立 open goal binding,并让投递 taskId 落入 taskIds"** | **无现成 seam**:authority 读的是 `ctx.sessionProjections.stateOf(controllerSession,'devframe')` 的 fold 结果(start-authority.ts:82),不是 shadow-router 的 activeGoalId——两套对象;桌面 config taskIds 已固定 `['devframe-goal']`(`development-project.ts:151`;`command-goal-binding/src/config.ts:48/87` 要求非空唯一),v2 单任务下 taskId 就是 devframe-goal,真正缺的是 admission_open binding 事件本身 | **不成立 → P0-4** |

### A-4 验收分级与桌面组合

| # | 计划断言 | 源码实际 | 判定 |
|---|---|---|---|
| 22 | 桌面组合:shadow-router + bridge intervalMs 60000 + project-controller/consumer/task-consumer/delivery-consumer + agent-hierarchy | `development-project.ts:130-133`(router,controllerProfile 'standard');:139-143(bridge intervalMs:60000);:183-221(project-controller + consumer + task-consumer + delivery-consumer);:159-170(agent-hierarchy roleToolPolicies);:144-158(command-goal-binding taskIds:['devframe-goal']) | **符合** |
| 23 | 4a:会话落 followup + 投递状态从 received 前进;4b 依赖 D-2 | 转发门 `forwardableDelivery` 仅要求 binding 非 stopping/stopped 且 activeGoalId/activeAcceptanceHash 齐备一致;host open 已写这两值,故 resume 后 60s poll 必然转发——**4a 只需 D-1**。但 delivery 状态机仅 `queued/received/completed/cancelled`(`shadow-router/src/spec.ts:72`),无 forwarded;bridge 转发只写自己的 marker 表,router 行保持 received,直到 `completeDelivery`(service.ts:791-806);`README.zh.md:113` 明示"已转发的投递保持 received" | **前半符合;"状态前进"措辞错误 → P1-3** |
| 24 | 组合测试已有"手动 agents.resume 模拟宿主职责"骨架 | `shadow-bridge/tests/composition.spec.ts:274-277、330-333` 两处 `agents.resume({resumeSessionId, agentOptions:{provider:'mock',model:'mock'}})`(无 setup);用例正是 open→run→restart→手动 resume→send→followup 落盘闭环 | **符合** |
| 25 | **4a 观测手段可执行性(本轮只读实跑)** | 本机 python 3.14.7 + zstandard 0.25.0;实测解压 `C:\Users\25313\.dsh\sessions\--D-dsh-devframe--\shadow-935c5f7a-1e50-4bb4-a0c3-9438883fc3a3\session.jsonl.zstd`(311B),`RECORD_COUNT=4`,type 依次 `session`/`permission/preset`/`sandbox/mode`/`approval/policy`——与根因文档"4 条基础记录"逐字一致。followup 落盘形态:forwarder.ts:176 → text.ts:20 头 `` `[Shadow delivery ${messageId} for workspace ${workspaceId}]` `` → createUserMessage → `type=user/message`(composition.spec:262 已断言同款)。D-1 落地后该文件应 4→5 条 | **可观测手段真的可执行**;复核看 (a) 该 zstd 增一条含 `[Shadow delivery …]` 的 `user/message`、(b) bridge marker 表记 messageId;**router 投递行仍 received,不以前进为信号**(见 P1-3) |

---

## B. 可行性结论

**B-1 D-1 在真实桌面组合下足以让 followup 落盘吗?** 技术内核成立(resume 恢复 header、resume emit agent/created、角色工具白名单注入、bridge 60s 安全网、转发门不依赖 plan 成功)。**唯一阻断是落点**:真实 e2e(人对 Shadow 说话 → Shadow 调 shadow_open_project)走 shadow-tools.ts:126,不经 index.ts:132。只在 @Remote openProject 加 provisioner = 真实场景 controller 永远不 live,4a 跑不出来。→ P0-1。

**B-2 resume 是否触发角色策略注入?** 是,本轮复核确认(resume.spec.ts:350-359 + agent-hierarchy service.ts:93-97/306-311)。

**B-3 setup 空会让 controller 缺 cwd/预设而启动失败吗?** 不会。cwd/agentPreset='standard' 来自创建时写入的 header,session-identity 的 bindPreparedSession 也强制 `worktree.worktreePath === session.header.cwd`(registry.ts:233-235)。唯一边角:fresh 同进程 open 后立即 resume 的 lazy persistence(r1 记 composition.spec.ts:318-321 曾显式 ensureMaterialized),需按 shadow-agent.ensureOnce 模式覆盖。→ P1-2。

**B-4 D-2 最小方案成立吗?有没有更轻路径?** 不成立,三处都是 API 级阻断:
1. worktree 不能登记项目根(P0-2)。真实最小实现 = 真建一个 linked worktree(worktreeRegistry.create)→ 锁给 controller session(worktreeRegistry.bind)→ controller 会话 cwd 指向该 worktree 路径 → 首次 bind 即带 worktree 字段(P0-3)。这比计划想象的重(连带改 createControllerSession 的 cwd 与 provisioning 顺序),但有 integration-snapshot.ts:54-61 规范模式可抄。
2. goal binding 无 host 侧轻路径(P0-4):admission_open binding 只能经 /devframe-start 等价流程在 controller fiber 产出并落 journal,该流程要求 human authorization 等重前置;host open 无法替代。taskIds 在 v2 单任务下已固定 ['devframe-goal'],不是要改的点。
→ **推荐:D-2 goal 条按 §6 直接 deferred;worktree 条若 4b 需要则按真建 linked worktree 重做,否则随 goal 条一起 deferred。**

**B-5 4a 通过线站得住吗?** 站得住。它只要求 live agent + followup 落盘,不要求 controller 成功 plan(controller 尝试 plan 时 resolveControllerAuthority 抛错是预期,不影响消息落盘这一事实)。观测措辞按 P1-3 修正后可复核。

---

## C. P0 / P1 / P2 清单

### P0(阻断,4 条)

1. **provisioner 落点漏了对话入口。** 计划 §2.1 只挂 `index.ts:132` 的 @Remote openProject;对话侧 `shadow_open_project`(shadow-tools.ts:126)直接调 `router.openProjectForHost(...)`。修订:把 `ensureControllerAgent(binding/result)` 抽成包内共享私有方法,index.ts:132 与 shadow-tools.ts:126 两处 openProjectForHost 返回后都调用(一处实现、两处复用)。
2. **D-2 item 1"worktree 即项目根"在现有 API 下不成立。** worktreeRegistry.create 拒绝 owner workspace 目录冲突(registry.ts:64-66),reconcile 永不登记主工作树(:139-140),无任意路径登记面;authority 还要求 row.lockedBy===controllerSessionId 且 row.workspaceId===goal.workspaceId(start-authority.ts:88-91)。须改为真建 linked worktree 的规范模式,并把 controller 会话 cwd 指向它。
3. **agentBindings 无改绑通道。** 已存在且内容不同的记录二次 bind 抛 SESSION_IDENTITY_ALREADY_BOUND(session-identity/src/registry.ts:260-267)。worktree 字段必须折进 completeProvisioning 的首次 bind(service.ts:1145),且其前先完成 worktreeRegistry.create+lock;"provisioner 中补注册"的写法会炸。
4. **D-2 item 2"host 以 goals 服务建立 open goal binding"无现成 seam。** authority 读的是 controller 会话日志 fold 出的 devframe projection(start-authority.ts:82),binding 事件只由 /devframe-start 等价流程经 landGoalBinding 落 journal(composition.ts:383-384/490),该流程要求 human authorization confirmation、sourceFingerprint+snapshot、required checks 真实执行。shadow-router 的 activeGoalId 是另一套对象。taskIds 已固定 ['devframe-goal']。建议此条直接 deferred。

### P1(执行前必须修订,6 条)

1. **needs_attention 无公开接缝。** markNeedsAttention 是 private(service.ts:1156),抽象 ShadowRouter 无公开面。计划须二选一:provisioner 只 logger,或先在 shadow-routing 抽象层加公开方法(如 markBindingNeedsAttention)。
2. **fresh open→resume 的 lazy persistence 风险。** composition.spec.ts:318-321 曾显式 ensureMaterialized;计划应写明 provisioner 参照 shadow-agent.ensureOnce 的"resume 失败且磁盘无此 session 才降级"模式,并在 host.spec 与组合用例覆盖 fresh open→resume。
3. **4a 观测措辞错误:投递行不会离开 received。** 状态机无 forwarded(spec.ts:72),转发后 router 行仍 received,completed 要等 completeDelivery(service.ts:791-806;README.zh.md:113)。正确观测:(a) controller 会话 session.jsonl(.zstd)出现 user/message 含 [Shadow delivery …];(b) bridge marker 表出现该 messageId;(c) router 行仍 received。
4. **组合测试须覆盖对话入口 open。** 鉴于 P0-1,组合/host 用例必须覆盖经 shadow_open_project(对话面)open 后 provisioner 仍触发的分支。
5. **幂等/重启收敛补显式断言。** host.spec 用例清单加:已 live 再 open→不重复 resume;binding 非 ready→跳过;resume 失败后再次 open→可重试且不破坏既有 received 投递。per-file 100% 门会要求这些分支。
6. **实现前置核查。** (a) 宿主 composition 里 ctx.worktreeRegistry provider 是否真可解析——桌面 links 有该包(development-project.ts:327)但 provider 实现挂在哪个 profile,D-2 开工前须验证;(b) D-1 新增私有方法不进 @Remote,无需 gen:typert;若改 openProject Remote 签名才需;(c) 动 development-project.ts 后须重跑 buildDevFrameDeploymentPatch(:389)并重建 host/client bundle。

### P2(收尾时做,7 条)

1. 行号小偏差见 D 节。
2. 计划 §3.4 的 gen:typert 注明"仅当新增/改 Remote 契约时才需重跑"。
3. §2.1"resume 恢复 header"补证据落点(service.ts:1130 写 cwd/agentPreset;ResumeAgentOptions 无 meta,header 即唯一来源;session-identity registry.ts:233-235 同样强制 worktreePath===cwd)。
4. §6 显式写明"4a 通过线 + D-2 deferred"的验收结论,避免评审/验收时再争。
5. §2.1 与桥协作补"最坏等待 intervalMs=60s"(README.zh.md:116),e2e 观察窗口留足。
6. readStatus/board 暴露 controller live 状态为可选;若做,注意 live 是运行期事实不在 binding 行里,需另起只读字段,别误塞进 binding 投影。
7. §7 deferred 清单补记"D-2 goal 上下文无 host 侧轻路径、仅经 /devframe-start 重流程可达",避免下一轮重复调研。

---

## D. 行号偏差清单

| 计划引用 | 实际 | 偏差 |
|---|---|---|
| "completeProvisioning(service.ts:1126-1153)只 sessions.create + bind" | createControllerSession :1126-1140(含 :1129-1131 sessions.create);completeProvisioning :1143-1153(含 :1145 bind) | 区间覆盖两者,方法边界建议写明 |
| "agentBindings.bind(service.ts:1145)" | :1145 | 精确命中 |
| "agentDefaultModel.currentSelection()(shadow-agent.ts:295-299 同款)" | lookup+currentSelection :295-299;组装 agentOptions :300-304 | 构造段下挪 1 行,语义无差 |
| "task-consumer.ts:29 全局注册;:59-62 校验点" | 注册 :29;authority 闭包 :60-63,实调 :62 | 基本命中 |
| "development-project.ts:160-163 inheritedTools" | config: :160、roleToolPolicies: :161、controller: :162、inheritedTools: :163 | controller 块实际 :162-163 |
| "openProject(index.ts:130-133)" | :130-133 | 精确命中 |
| "start-authority.ts:77-87" | resolveControllerAuthority :70-93;live 检查 :77;bind worktree :78-81;goal :82-87;worktree row 锁定 :88-91(计划漏引) | 区间命中,建议补 :88-91 |
| "host open run goal(service.ts:688-692)" | establishHostOpenRun :688-692;setActiveGoal :761-771 | 精确命中 |
| "forwarder.ts:171-174" / "README.zh.md:112/124" | 逐字命中 | 无偏差 |

---

## 终审

阶段 D 计划的投递链根因判断与 D-1 技术内核经两轮亲验全部成立:D-1 的三个最关键假设——(a) agents.resume 签名与 setup 语义、(b) resume 确实 emit `agent/created` 从而触发 agent-hierarchy 角色工具注入、(c) 空 setup 不丢 cwd/preset——均有源码硬证据。4a 作为通过线技术上站得住。

**但有两组必须修订的硬阻断:**
1. **P0-1(D-1 落点)**:真实对话入口 shadow_open_project(shadow-tools.ts:126)绕过 @Remote openProject,provisioner 只挂 index.ts:132 = 真实 e2e 仍跑不出来。
2. **P0-2/3/4(D-2 三处 API 级阻断)**:worktree 不能登记项目根(create 拒绝 owner 目录、reconcile 不收主工作树、authority 还要 lockedBy+workspaceId 双匹配);agentBindings 拒绝二次改绑;goal binding 无 host 侧轻建立通道(只能走 /devframe-start 重流程落 journal)。这三处不是"实现时先读接口再定"的小事,而是"最小方案按现描述不成立"。

修订建议:P0-1 必修(两处 open 共用 ensureControllerAgent);P0-2/3 视 4b 是否本轮要做而定,要做就按真建 linked worktree + 首次 bind 带 worktree 重做,不做则随 P0-4 一起按 §6 降级 deferred;6 条 P1(needs_attention 接缝、lazy persistence、4a 观测措辞、对话入口测试、幂等用例、前置核查)执行前落实;P2 收尾处理。

## 执行回注（2026-09-24）

阶段 D 已按上述 P0 修订实现：shadow-router 在首次 Agent factory setup 中预配并锁定 linked worktree，`bindPreparedSession` 一次写入 controller role 与 worktree 字段；command-goal-binding 通过 host-owned `shadowGoalProvisioner` 在 controller Session 上落 `admission_open` Goal binding、`devframe-goal` task id 和真实 verification。离线验收为 shadow-router host bridge 13/13、shadow-bridge composition 合并 20/20、command-goal-binding real composition 21/21，两包 TypeScript 检查通过。

原评审把 D-2 列为 deferred 的结论只适用于评审时的缺口；当前仍未执行真实桌面 host 重建与 Shadow 对话 e2e，因此桌面 4a/4b 保留为发布前门槛。
