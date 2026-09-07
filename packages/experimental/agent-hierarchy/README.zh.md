---
description: "插件化代理层级的三态角色策略、创建入口守卫、插件范围校验与冷恢复。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-hierarchy

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-hierarchy` 挂载 `ctx.agentHierarchy`——插件化代理层级的策略服务。它把角色策略统一为 `controller` / `lead` / `worker` 三态（退役 `reviewer` 的 deny 语义并入 lead 与 worker 两面），在根工具注册表上安装一个 monotonic pre-execute 守卫，覆盖一切可创建 Agent 的入口——委托 seam（spawn/fork）、Team spawn/任务控制类工具，以及宿主声明的其他创建面——对照宿主获批集合校验 lead 委托的插件范围，在 seam 的 `SubagentDepthError` 之外以绝对委托深度预算 2 作为第二条独立拒绝路径，并在冷恢复时从持久绑定注册表重建角色与每代理限制。守卫在每次执行时从 `ctx.agentBindings` 实时解析角色，激活之后写入或恢复的绑定立即生效；无角色绑定的会话触达任何受控工具即 fail closed，拒绝原因指明缺角色。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在同时挂载了 agent 注册表与工具注册表的组合中、于 session-identity 注册表之后挂载本服务；它硬注入 `ctx.agentBindings`、`ctx.tools` 与 `ctx.agents`，任一缺失即在激活时失败。

```yaml
- name: '@deepseek-ai/dsh-experimental-session-identity'
- name: '@deepseek-ai/dsh-experimental-agent-hierarchy'
  config:
    roleToolPolicies:
      controller: { inheritedTools: ['project_read', 'subagent', 'send_message'] }
      lead: { inheritedTools: ['project_read', 'subagent', 'send_message'] }
      worker: { inheritedTools: ['project_read', 'send_message'] }
    leadPluginScopes:
      lead-1: ['plugin-a']
```

### 角色策略

每个角色保留其 `inheritedTools` 列表点名的全局工具（空列表对该角色拒绝所有全局工具），外加宿主可选的 `denyScopedTools` 扩充。本包叠加自己固定的 deny 面：lead 失去 Team spawn/任务控制类工具，worker 失去一切可创建 Agent 的工具。`send_message` 对 worker 有意保留——它是向 lead 汇报的授权通道。无角色绑定的会话调用任何受控工具即被拒绝并指明 `missing role`；未绑定会话仍可执行非受控工具。

### Lead 插件范围

lead 通过 spawn/fork 工具委托时，必须携带落在宿主配置 `leadPluginScopes[<agentId>]` 获批集合内的 `pluginId` 绑定。未列入配置的 lead、无插件范围绑定的 lead、越界范围，一律 fail closed 拒绝。深度 2 的会话无论绑定何种角色，只要尝试委托即被深度预算拒绝，与角色面无关。

### 程序化创建

工具执行由守卫自动覆盖。一切非工具创建入口（宿主服务、SDK 桥）必须在子代理存在之前调用 `ctx.agentHierarchy.evaluateCreation(creatorRecord, intent)`；它对 P00 `CreationIntent` 施行同一策略。

求值器仅允许总控创建组长，拒绝创建另一个总控或 Worker；组长只能在获批的插件范围内创建 Worker。返回允许决定不会创建或绑定 Agent：调用方必须在执行创建之前落实该决定。

`createChildAgent(parent, request, options)` 校验活跃父 Agent、角色、深度、任务及工作树归属，然后在 Agent 工厂的 setup 阶段持久化绑定，之后才发布 Agent。调用方提供已通过注册表校验的工作树，以及装配所需 preset 的 setup。同一父会话和任务的相同重试返回活跃子 Agent；冲突请求和已被占用的工作树会被拒绝。已保留的子 Agent 不可用时必须显式恢复。此方法激活 Agent，但不发送提示词。宿主可以预先分配 SessionID，以配置组长获准使用的插件范围。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释特性背后的设计决策并指向实现它们的代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计决策

- **守卫是权威，限制只是纵深防御。** 角色、deny 面、深度与范围在每次执行时从活动绑定注册表与精确 agent 身份解析，因此陈旧或未绑定身份永远借不到记录。每代理的 inherited 限制只收窄提示词可见性；它在首次执法时惰性安装、经 `agent/created` 作用于已绑定代理、由 init 时的冷恢复扫描重建，并随代理处置解除。
- **双保险深度。** 委托 seam 以 `SubagentDepthError` 拒绝超出 `maxDepth` 的子代理；本包守卫独立拒绝一切来自深度 2 的委托。预算是固定安全不变量，不是配置字段。
- **无需注册表事件的冷恢复。** 绑定注册表持久化记录但不发事件，因此服务从三条路径重建：对已恢复且代理仍活的记录做 init 扫描、对激活后创建的代理挂 `agent/created` 监听，以及守卫的按执行查找——后者根本不需要事件。
- **装载时 fail loud，执法时 fail closed。** 配置在构造时一次性校验；守卫拒绝是普通原因字符串，指明角色、缺角色、范围或深度。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/service.ts`](src/service.ts) | `ctx.agentHierarchy` 服务：守卫安装、监听、冷恢复扫描、处置 |
| [`src/guard.ts`](src/guard.ts) | 覆盖身份、角色、深度与范围的 monotonic pre-execute 守卫 |
| [`src/policy.ts`](src/policy.ts) | 三角色查找表、deny 面与深度预算 |
| [`src/creation.ts`](src/creation.ts) | 面向 `CreationIntent` 的程序化创建面求值器 |
| [`src/config.ts`](src/config.ts) | zod 校验的宿主配置 |
| [`src/errors.ts`](src/errors.ts) | `AgentHierarchyError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 包入口与默认导出 |

### 不变式

不发布运行时 invariant 伴随物：每一条拒绝都在执行时从唯一的绑定注册表与活动 agent 注册表推导，守卫是唯一的执法权威——已安装的限制只是同一配置的投影，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 角色策略与创建守卫

#### 模型看到什么

被拒绝的工具调用返回 pre-execution 错误结果并指明原因——绑定的 `controller` / `lead` / `worker` 角色、`missing role`、插件范围或深度预算——工具体从不执行，任何 post-execute 监听都无法翻案。被 inherited allow 面限制掉的工具从提示词消失，表现为未知工具。

#### Token 影响

无固定每请求开销。inherited allow 面会缩小角色的工具清单，为受影响代理减少提示词 token；惰性安装的限制从下一请求起改变工具清单。

#### KV Cache 影响

限制在两次请求之间安装或解除会改变受影响代理的工具提示词前缀，从而破坏该代理下一次请求的 provider 缓存复用。守卫与拒绝从不触碰请求内容。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制界定了本服务何时不适配或需要特别运维关注。它们是当前包约束，不是任务清单。

- **仅覆盖工具面。** 守卫覆盖模型可见的工具执行；程序化创建入口必须自行调用 `evaluateCreation`。自动的 SDK 面拦截推迟到出现消费方波次再定义。
- **绑定写入不发事件。** 新绑定代理的限制在其首次受守卫执行或下一次公告时安装，而非 bind 时；执法从不过迟，因为守卫实时读取角色。
- **无 unbind。** 记录是持久事实；已处置代理的陈旧身份由身份校验拒绝而非记录移除，角色的生命周期移除路径尚不存在。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

devframe 的 `RolePolicy`（controller/worker/reviewer）是本包取代的部署；其迁移属于后续波次，本包不 import devframe。深度预算与 `DEVFRAME_DELEGATION_DEPTH_BUDGET` 有意一致；seam 自身的 `SubagentDepthError` 路径保持为第一拒绝半。

</details>
