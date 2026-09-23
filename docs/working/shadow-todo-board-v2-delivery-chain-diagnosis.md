---
title: Shadow Todo 看板 v2 — 真实 e2e 投递链排查结论
owner: shadow
status: diagnosis-complete
date: 2026-09-21
branch: feat/desktop-quality-fixes
related: docs/working/shadow-todo-board-v2-stage-c-plan.md, docs/working/shadow-todo-board-v2-stage-c-review.md
---

# Shadow Todo 看板 v2 — 真实 e2e 投递链排查结论

## 现象

桌面真实 e2e（shadow 对话 → 打开项目 → 投递规划指令 → controller 规划 → 看板出现卡片 → 批准）卡在投递之后：投递 `msg-a66ef910-b70a-48b4-9c7b-39f37ece5226` 状态为 `received`，但 controller 会话 `shadow-935c5f7a-1e50-4bb4-a0c3-9438883fc3a3` 的 `session.jsonl.zstd` 只有 4 条基础记录（session / permission/preset / sandbox/mode / approval/policy），投递消息从未落盘，controller agent 从未运行。

## 排查过程（只读，未改代码）

### 1. 投递链本体工作正常

- `shadow_message_controller` 工具 → `router.sendToProjectForHost` → `sendToProject`：投递先持久化为 `queued`，再持久化为 `received` 并发出 `shadow/delivery-received` 事件（`packages/experimental/shadow-router/src/service.ts:407-495`）。
- 当前投递状态 `received` 证明该链路已完整走到持久化目标接受，binding 也带着授权 open run（否则 send 会以 `SHADOW_GOAL_NOT_AUTHORIZED` 拒绝）。

### 2. 转发器（bridge forwarder）工作正常但有一个前提

- `shadow-bridge` 的 `DeliveryForwarder` 把 `received` 的 work 投递转为 controller 会话上的一条 durable follow-up（`packages/experimental/shadow-bridge/src/forwarder.ts`）。
- **前提**：转发只发给 live agent —— `forwarder.ts:171-174`：

```ts
const agent: Agent | undefined = this.deps.agents.get(binding.controllerSessionId)
// v1 forwards to live controllers only: without a live agent the
// delivery waits for a later unit; the bridge never creates or resumes one.
if (agent === undefined) return
```

- README 明示这一边界（`packages/experimental/shadow-bridge/README.zh.md:112`）：**"仅限 live controller——不做冷恢复——桥通过 live-agent registry 解析绑定的 controller 会话，从不创建、恢复或收养 agent；宿主从未使之 live 的 controller 永远收不到它的投递，投递保持 received 并在 router 中可见。"**

### 3. 没有任何宿主组件把 controller agent 变为 live

| 组件 | 对 controller agent 的处理 | 证据 |
|---|---|---|
| shadow-router | 只 `sessions.create`（会话记录）+ `agentBindings.bind`（角色），**不 resume** | `shadow-router/src/service.ts:1126-1153` |
| shadow-bridge | 刻意不创建/恢复/收养 agent | `forwarder.ts:171-174`、README.zh.md:112 |
| shadow-controller host 面 | `openProject` 只调 `router.openProjectForHost`，不 resume | `shadow-controller/src/index.ts:130-133` |
| agent-hierarchy | 只处理 worker/lead 子 agent 的恢复 | `agent-hierarchy/src/service.ts:206-283` |
| desktop 宿主 | 无 bindings/controller/agent resume 代码 | 全仓 grep `agents.resume|controllerSessionId` 在 apps/ 仅命中 host-process.ts 的 stream 处理 |
| apps/web、apps/cli | 无 controller resume | 同上 |

- README 把这一能力明确列为下一轮扩展（`shadow-bridge/README.zh.md:124`）：**"…以及一个在保留会话上拉起 controller agent 的宿主侧 provisioner——这三者本桥都刻意不拥有。"**

### 4. 即使补上 resume，controller 完整生命周期还缺一环

- `resolveControllerAuthority`（`project-controller/src/start-authority.ts:77-81`）要求 controller 的 agentBindings 记录带 `worktreeId`/`worktreePath`，且 session cwd 与之匹配。
- router 的 `completeProvisioning` 只 bind `{ agentId, role: 'controller' }`，**没有 worktree 绑定**。即 controller 的 "live agent + worktree + 授权" 组装在桌面宿主从未存在。

## 根因结论

**不是投递链 bug，而是宿主侧 controller 生命周期（provisioner）缺失**——这是 v1 设计边界（README 明示"桥不拉起 controller"）叠加"宿主侧 provisioner 尚未实现"的结果。投递不会丢：`received` 行在 router 中持久可见，provisioner 就绪后事件/轮询路径会继续转发；但当前没有任何组件会拉起 controller，所以 e2e 永远停在 `received`。

## 修复方向（建议，待确认后立项）

1. **宿主侧 provisioner（阶段 D 第一项）**：在保留会话上拉起 controller agent，落点建议在 `shadow-controller` host 面 `openProject` 成功后（唯一打开入口，桌面面板与对话都走它），或独立宿主插件：
   - `agents.resume({ resumeSessionId: controllerSessionId, agentOptions, setup })`；
   - `agentOptions`（provider/model）与 controller setup（project-controller consumer 注入）需要明确的来源方案；
   - controller 的 worktree 绑定需要补齐（否则 start authority 不认）；
   - 失败需 fail-loud/可观测，避免静默停在 received。
2. **组合层验证已有覆盖**：`shadow-bridge/tests/composition.spec.ts` 已验证"投递 → received → 转发 → controller 会话落盘"闭环（需手动 `agents.resume` 模拟宿主职责）；本次 278 测试全绿包含该组。
3. **阶段 D 入口**：把 provisioner 需求写入 v2 计划（与已 deferred 的 #21 repairLimit、通用 task→scope 映射并列）。

## 已确认信息（供 provisioner 实现复用）

- 桌面入口：`D:\dsh-devframe\.desktop-devframe-staging\dsh-client-launch.ps1`，日志 `dsh-client-run.log`。
- 当前 binding：workspace `33202c5c-0550-4d7a-b92e-2282590c4529`（cwd D:\dsh-devframe，binding_revision 2），controller 会话 `shadow-935c5f7a-1e50-4bb4-a0c3-9438883fc3a3`（standard profile，cwd 已写入 session meta）。
- 待转发投递：`msg-a66ef910-b70a-48b4-9c7b-39f37ece5226`（mode work，received）。
- controller 会话文件为 zstd 压缩 JSONL：`C:\Users\25313\.dsh\sessions\--D-dsh-devframe--\<id>\session.jsonl.zstd`（`python -c "import zstandard..."` 流式解压）。

## 阶段 D 执行状态（2026-09-24）

阶段 D 已补齐宿主侧 controller provisioner：fresh open 通过 Agent factory 创建 live controller，冷恢复由 boot sweep resume；Git 项目先创建并锁定 sibling linked worktree，再在 setup 中一次写入 controller role 和 worktree binding。command-goal-binding 暴露 host-owned Goal provisioner，在 controller Session 上写入 `admission_open`、`devframe-goal` task id、角色策略和真实 verification，因此 `project_task` 的既有 authority 可以读取完整上下文。

离线证据：shadow-router host bridge 13/13（含真实 Git linked worktree 与 writer lock）、shadow-bridge composition 合并 20/20、command-goal-binding real composition 21/21；两包 TypeScript 检查通过。真实桌面 host bundle 尚未重建，Shadow 对话 4a 投递日志、bridge marker 和 4b 看板卡片仍待发布前 e2e 复核。
