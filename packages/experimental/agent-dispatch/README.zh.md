---
description: "横跨 agent-hierarchy 引擎的宿主派发入口（ctx.agentDispatch）：经层级授权的 lead 创建，带权威 worktree 行校验、单写锁与 agent_dispatch 消费工具。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-dispatch

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-dispatch` 是横跨 [agent-hierarchy 引擎](../agent-hierarchy/README.zh.md)的宿主侧派发入口。服务定义向组合层调用方暴露 `ctx.agentDispatch.createChildAgent(parent, request, options)`；引擎拥有子 agent 身份与生命周期，本适配器自身绝不实现创建。在引擎调用前，适配器以权威注册表行校验请求：已注册的 worktree id、存在的目录、path/branch 匹配，以及该 workspace 的锁占有着（`status` 只回报 `directoryExists/branch/clean`；path 与 `lockedBy` 来自 `worktreeRegistry.list`）。它复用引擎的批准范围契约（`config.leadPluginScopes[creator.agentId]`）——适配器不复刻角色 policy，引擎拒绝原样透传。装配在入口内部完成：preset `composeFrom(parent.ctx)`、由子 session id 持有的 `worktreeRegistry.bind` 单写锁，然后是引擎的 `bindPreparedSession`；可选 `prompt` 仅在引擎发布之后经 `child.agent.followup` 送达。调用方提供的 `setup` 在装配片之后运行，不得用来供给装配本身。同一包也是 Consumer，暴露 `agent_dispatch` 工具。本包为实验性私有包：不入任何发布 bundle，契约可变。

## 目录

- [何时使用](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与待办](#known-limitations-and-deferred-work)
- [开发注记](#dev-note)

-----

<a id="use-this-package"></a>
## 何时使用

当组合层需要把层级的角色规则转化为被派发的子 agent 时使用本包——controller 把任务交给 lead，lead 在其批准范围内配备 worker。当调用方想要绕过注册表校验的裸引擎创建、或部署尚未预配 lead 身份时跳过；引擎自身的 `createChildAgent` 仍是本入口所委托的权威。

### 使用时机

每次派发需要四个决定，全部在引擎运行前校验：子 agent 的 `role`（controller 派 lead，lead 派 worker）、其拥有的 `taskId`（一任务至多一个被派子 agent）、其工作的 `pluginId` 范围、其将持有的 `worktreeId`。重试中的任务传 `retry: true`——或之前返回的子 agent id——复用既有子 agent 且不重投其简报。被派子 agent 的 worktree 锁终生绑定该子 agent；中断创建经引擎的 `recoverChildAgent` 语义恢复（typed `SessionPersistenceNotFoundError` 按原 id 恢复；损坏与取消不 fallback），适配器只新增持久身份查询——身份复用绝不重投 prompt。

<a id="understand-the-implementation"></a>
## 理解实现

Service 挂载于插件 fiber，接缝随插件存亡（构造上即 HMR 安全）。`AgentDispatchError` 错误码：`DISPATCH_WORKTREE_UNREGISTERED`、`DISPATCH_WORKTREE_MISMATCH`、`DISPATCH_PARENT_UNBOUND`、`DISPATCH_HIERARCHY_DENIED`。引擎拒绝（角色、范围、深度、去重）以其自身类型化错误透传。`DispatchAgentOptions` 是适配器 options 面：四个引擎 `CreateChildAgentOptions` 字段按键显式透传，外加用于权威行校验的必填 `workspaceId` 与可选 `prompt`。per-task 门把身份判断、引擎创建/恢复与首次投递串行进一个原子跨度，因此同任务并发请求恰产生一个子 agent 与一份简报。

不发布运行时 invariant 伴随物：适配器承诺的每一项保证（worktree 注册、path/branch 匹配、锁排他、范围批准）都从它所调用的同一批权威注册表行与引擎求值推导，拒绝在其调用返回的 `AgentDispatchError` 面上可观察，因此不存在可能分叉的独立观察。

<a id="model-experience"></a>
## 模型体验

### 系统提示词

#### 模型看到什么

本插件注册范围内的每个父请求都会收到以下固定指导。

##### Agent 派发指导

```markdown
The agent dispatch tool is the daily delegation entry over the agent hierarchy. The controller dispatches a lead per task onto its own registered worktree; the lead dispatches workers inside the plugin scopes approved for it in the deployment's leadPluginScopes. Every dispatch binds the worktree's single-writer lock to the new child for its whole life. A retried task reuses the existing child (retry: true) — never re-brief a running child.
```

#### Token 影响

插件激活期间每请求小额固定指导成本。

#### KV Cache 影响

插件范围与指导文本不变时前缀稳定。激活或卸载可能使本提示词节的复用失效。

### 工具 schema

#### 模型看到什么

生成的[工具目录](../../../docs/tool-catalog.md#deepseek-aidsh-experimental-agent-dispatch)中的 `agent_dispatch` 条目拥有 schema；消费面未在其之外增加字段。

#### Token 影响

每派发回合小额固定成本：一次工具调用加一份点名所建子 agent 或拒绝原因的结果。

#### KV Cache 影响

每派发回合仅追加；本包不改写更早的请求 token。

<a id="known-limitations-and-deferred-work"></a>
## 已知限制与待办

- 证据状态：真实 Loader 组合套件证明工具注册与 controller/lead/worker 可见性面；真实模型回合证明 service 面与一次真实派发回合（worker 工件）。shipped opt-in overlay 已接线——其候选 profile 验证（显式 `--patch`、隔离 HOME）是剩余验收步骤。
- 中断创建的恢复复用引擎的 `recoverChildAgent` 语义；适配器只新增持久身份查询，身份复用绝不重投 prompt。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点开查看</summary>

开放方向：被派子 agent 终态的持久确认；编排域接管后的 worker 侧修复环回送路径；lead 指派消费已在 devframe 包落地。

</details>
