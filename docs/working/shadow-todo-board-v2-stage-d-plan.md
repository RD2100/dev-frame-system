---
title: Shadow Todo 看板 v2 — 阶段 D：宿主侧 controller provisioner 与真实 e2e 补跑
owner: shadow
status: implemented-r3
date: 2026-09-24
branch: feat/desktop-quality-fixes
based-on: docs/working/shadow-todo-board-v2-delivery-chain-diagnosis.md、docs/working/shadow-todo-board-v2-stage-d-plan-review.md（P0×4/P1×6/P2×7，已修订）
---

# 阶段 D：宿主侧 controller provisioner 与真实 e2e 补跑

## 1. 背景与目标

阶段 C 验收通过后,唯一未闭环项是验收 4 的真实 e2e:shadow 对话派活 → controller 规划 → 看板出现卡片 → 批准。排查(见 `shadow-todo-board-v2-delivery-chain-diagnosis.md`)确诊根因:

- 投递链本体正常(投递已持久化 `received`,binding 已带授权 open run);
- **controller agent 从未被任何宿主组件变为 live**:shadow-router 只建会话记录,shadow-bridge v1 刻意不拉起(README.zh.md:112、124),shadow-controller host 面 openProject 不 resume,desktop/web/cli 宿主均无相关代码;
- 转发器(forwarder.ts:171-174)只转 live agent → 投递永远停在 `received`,controller 会话只有 4 条基础记录。

**目标**:实现宿主侧 controller provisioner，并补齐真实规划所需的 linked worktree、首次 controller 绑定和 Goal admission 投影。

**范围声明**:本阶段交付 D-1 provisioner 与 D-2 controller 规划上下文。真实桌面 e2e 仍单独记录为未运行项；离线组合证据覆盖 4a/4b 的实现链路。

## 2. 技术方案

### 2.1 D-1 宿主侧 provisioner(本轮全部交付)

**落点(评审 P0-1 修订)**:`packages/experimental/shadow-router/src/service.ts` 的 `openProjectForHost`(service.ts:668)——它是两条 open 入口的共同收敛点:

| open 入口 | 路径 | 是否经 openProjectForHost |
|---|---|---|
| 面板 @Remote `shadow.openProject` | shadow-controller/index.ts:131-133 → `router.openProjectForHost` | 是 |
| 对话工具 `shadow_open_project` | shadow-tools.ts:124-134 → `router.openProjectForHost` | 是 |

在 `openProjectForHost` 的 `opened.state === 'ready'` 分支(establishHostOpenRun 之后)调用包内私有方法 `ensureControllerLive(binding)`,一处实现、两条入口全覆盖。真实 e2e(人对 Shadow 说话 → Shadow 调 shadow_open_project)由此必然触发。

**ensureControllerLive 语义**:

```
ensureControllerLive(record):
  binding ready 且 activeGoalId 已建立?
  agents.get(record.controllerSessionId) 已 live? → 跳过
  defaultModel = ctx.get('agentDefaultModel') 缺失? → logger fail-loud,不吞
  agents.resume({ resumeSessionId, agentOptions: defaultModel.currentSelection() })
  失败? → logger 记录原因;参照 shadow-agent.ensureOnce 的降级模式:
        仅当磁盘无此 session 时按 fresh 语义处理,否则保持失败可见(评审 P1-2)
```

- **agentOptions**:复用 `ctx.get('agentDefaultModel').currentSelection()`(shadow-agent.ts:295-304 同款;缺失 fail-loud,与 shadow 会话启动一致)。
- **setup**:**不传**(空)。评审亲验:resume 恢复 session 创建时写入 header 的 cwd/agentPreset(service.ts:1129-1131;ResumeAgentOptions 无 meta 字段),不丢 cwd;`project_task`/`project_integrate` 由 consumer 全局注册(task-consumer.ts:29),execute 内 `resolveControllerAuthority` 按 live agent 身份与绑定校验(:59-63);controller 角色可见性由 agent-hierarchy 在 `agent/created`(resume 触发,resume.spec.ts:350-359 实证)时按 roleToolPolicies 注入(agent-hierarchy/service.ts:93-97、306-311;development-project.ts:162-163 controller inheritedTools 含 project_task/project_integrate/worktree_*)。
- **幂等**:agent 已 live 或 binding 非 ready 则跳过;重复 open/重启后 resume 收敛到同一 session。
- **失败处理**:只走 logger(评审 P1-1:markNeedsAttention 是 router private,无公开接缝;本阶段不在 shadow-routing 抽象层新增公开面);投递保持 `received` 可重试,不静默吞错。
- **与桥协作**:resume 成功后,既存 `received` 投递由 bridge 安全网轮询自动转发(desktop 配置 intervalMs:60000);最坏等待一个轮询周期(评审 P2-5,e2e 观察窗口留足 ≥60s)。投递行不会离开 `received`(状态机无 forwarded,spec.ts:72;README.zh.md:113),这不是缺陷。

### 2.2 D-2 controller 规划上下文

Host-side Goal provisioning now supplies the same authority facts that `project_task` reads. `createHostGoalBinding` exposes a `shadowGoalProvisioner` seam; shadow-router passes the live controller, workspace id, and linked worktree path through that seam.

1. **首次 linked worktree 绑定**:shadow-router asks `ctx.worktreeRegistry` for a deterministic sibling checkout, binds it to `WorktreeLockHolder(controllerSessionId)`, and creates the controller Agent in the factory setup. `bindPreparedSession` receives the controller role and worktree tuple before publication, so `agentBindings` never needs a second bind. The session cwd, binding worktree path, registry row, and writer lock are one tuple.
2. **Goal admission**:the host seam computes the linked worktree source fingerprint, stores the configured required checks, starts a `GoalBindingController` with the host-issued authorization, lands the role policy and `devframe/goal-binding` event, and records real verification evidence. The binding uses the v2 task id `devframe-goal`, so `resolveControllerAuthority` observes `admission_open` and admits the task id.
3. **Project lifecycle**:after the Goal projection is durable, the provisioner opens a stopped `projectController`. A missing worktree provider keeps the legacy root-session path for plain-directory harnesses; a mounted provider that cannot create or lock the linked checkout parks the binding as `needs_attention` and does not claim readiness.

## 3. 实施步骤

1. **D-1 实现**:shadow-router 在 `openProjectForHost` 与 boot sweep 统一调用 `ensureControllerLive`;fresh open 通过 `agents.create`，冷恢复通过 `agents.resume`。不新增或修改 @Remote 契约。
2. **D-2 实现**:首次创建时预配 linked worktree，并在 Agent factory setup 内完成 `bindPreparedSession`;command-goal-binding 暴露 `shadowGoalProvisioner`，在 controller Session 上落 `admission_open` Goal、`devframe-goal` task id、角色策略和真实 verification。
3. **相关测试**:shadow-router host bridge 13/13（含真实 Git linked worktree、registry lock、session cwd 和首次绑定）；shadow-bridge composition 与 host bridge 合计 20/20；command-goal-binding real composition 21/21（含 Goal seam）。
4. **类型门**:`pnpm exec tsc -p packages/experimental/shadow-router/tsconfig.json --noEmit` 与 `pnpm exec tsc -p packages/experimental/command-goal-binding/tsconfig.json --noEmit` 均通过。
5. **真实桌面 e2e**:当前工作轮次未启动真实桌面重建和对话派活；4a/4b 的桌面信号仍待桌面宿主重建后确认。
6. **收尾**:计划、评审、诊断和验收结论保留在 `docs/working`，并在 §6 区分离线组合证据与真实桌面证据。

## 4. 改动文件预估

- `packages/experimental/shadow-router/src/service.ts`（controller provisioner、linked worktree 和首次绑定）
- `packages/experimental/command-goal-binding/src/composition.ts`、`src/index.ts`（host Goal provisioner seam）
- 测试:shadow-router host bridges、shadow-bridge composition、command-goal-binding real composition
- 文档:docs/working 阶段 D 计划、评审、诊断与验收结论

## 5. 与既有约束的关系

- **不改 forwarder 的 v1 边界**:桥仍不拉起 agent;provisioner 是宿主侧(router Provider 即宿主进程内服务)新增能力,README 明示的扩展方向。
- **不改 authority 语义**:start-authority 的 worktree/goal 要求保持不变；D-2 通过真实 linked worktree、首次绑定和会话日志 Goal projection 满足这些不变量。
- **不改 @Remote 契约**:openProjectForHost 签名不变,无 gen:typert、无 client 面变化。
- **流程**:计划→评审→实现→离线验收；本文件记录实现状态，真实桌面 e2e 仍是单独门槛。

## 6. 验收 1-6

1. **实现存在性（通过）**:fresh open 和 cold boot sweep 均能拉起 controller；首次 Agent factory setup 写入 controller role 与 linked worktree；host Goal seam 通过真实 source fingerprint、required checks、authorization 和 verification 落 `admission_open`。
2. **离线测试（通过）**:shadow-router host bridge 13/13、shadow-bridge composition 合并 20/20、command-goal-binding real composition 21/21；类型检查两包均通过。
3. **4a 离线证据（通过）**:bridge restart sweep 测试验证 `received` 投递转成 controller Session 的 `[Shadow delivery …]` user message；router delivery 行保持 `received`，符合状态机。
4. **4b 离线证据（通过）**:真实 Git linked worktree 测试验证 registry row、writer lock、session cwd 和 controller binding 一致；Goal seam 测试验证 projection 为 `admission_open` 且 `taskIds` 含 `devframe-goal`。
5. **真实桌面 e2e（未运行）**:尚未重建 desktop host bundle，也未在真实 Shadow 对话中观察 4a 会话日志、bridge marker 或 4b 看板卡片；不能把离线证据写成桌面通过。
6. **评审闭环**:评审指出的 P0 worktree/首次绑定/Goal projection 阻断已落实；D-2 不再列为 deferred，真实桌面 e2e 作为下一条独立发布门槛。

## 7. Deferred(记入但不做)

- 通用 task→scope 映射、#21 repairLimit 完整化(阶段 C 已记);
- 多项目并行 open 的 provisioner 排队/容量控制(现单项目场景不涉及);
- readStatus/board 暴露 controller live 状态(可选;live 是运行期事实不在 binding 行,若做需另起只读字段,勿塞进 binding 投影);
- 真实桌面 host 重建、对话派活与看板验收仍待执行。
