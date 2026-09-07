---
description: "持久化代理绑定记录、冷恢复它们，并以准确 cwd 与血缘元数据创建原生 Session 的 Cordis 服务。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-session-identity

[English](README.md) | 中文

## 概述

`dsh-experimental-session-identity` 挂载 `ctx.agentBindings`——插件化代理层级的持久绑定注册表。它把每个代理的一条 `AgentBindingRecord` 保存在自己的 `session_identity` 存储域（组合 storages 根目录下的 JSON 文档）中；以准确的 `cwd`、`parentSession`、`delegationDepth` 头元数据创建原生 Session，并把宿主 SessionID、父会话与工作树在一次持久写入中写进绑定记录；绑定由其他入口（spawn、fork、Team spawn、SDK）已创建的代理；并在启动时冷恢复全部绑定。查询从进程内索引作答；域表保持为唯一持久权威。本包是私有实验性宿主侧服务：不注册工具、提示词段落或会话事件，因此 TypeScript 与 Python SDK 投影不受影响。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在已经挂载会话存储与存储栈的组合中挂载本服务；它硬注入 `ctx.sessions` 与 `ctx.storageDomain`，任一缺失即在激活时失败。

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: dshHomePath('storages')
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-session'
- name: '@deepseek-ai/dsh-experimental-session-identity'
```

### 创建带绑定的会话

`createBoundSession` 创建独立 Session，而非活跃 Agent。父会话必须存在；子代理深度从父头部推导（`父深度 + 1`），调用方也可显式传入 `delegationDepth`。

```ts
import type { Context } from '@deepseek-ai/cordis'
import type { Session } from '@deepseek-ai/dsh-session'
import type { BoundWorktree } from '@deepseek-ai/dsh-experimental-session-identity'
import { PluginId } from '@deepseek-ai/dsh-experimental-project-contracts'

declare const ctx: Context
declare const controllerSession: Session
declare const worktree: BoundWorktree

const { session, record } = await ctx.agentBindings.createBoundSession({
  cwd: worktree.worktreePath,
  role: 'lead',
  parentSessionId: controllerSession.id,
  pluginId: PluginId('agent-reliability'),
  worktree,
})
```

### 绑定、查询与恢复

`bind` 登记由其他入口创建的代理；完全相同的重绑是幂等的，冲突的重绑大声失败。`find`、`byRole`、`list` 从启动时恢复的索引作答，冷进程无须回放会话即可看到全部绑定。

在 Agent 工厂的 setup 中，使用 `bindPreparedSession(agentCtx.agent.session, request)` 在发布前持久化绑定。工厂拥有 Session 的创建和销毁生命周期；再次调用工厂不能接管独立的活跃 Session。身份和父子关系从准备中的 Session 推导。如果后续 setup 或发布失败，绑定会保留供显式恢复，不会静默创建替代 Agent。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本节解释设计决策并指向实现代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计决策

- **每条绑定一次持久写入。** 创建先校验角色、父引用、深度与工作树绑定，然后创建会话并把完整记录一次性写入——宿主 SessionID、父会话与工作树一起——而不是分阶段写入残缺事实。
- **写穿索引。** 每次变更先等待域表写入，再把记录镜像进查询索引；启动时按 (createdAt, agentId) 顺序从域表重建索引，因此重启与恢复无须回放。
- **无会话事件。** 绑定记录是永远不会到达模型请求的宿主侧层级元数据；其持久性由本包自己的存储域承担，因此 `SessionEventMap` 不新增成员，两侧 SDK 投影都不变。
- **幂等重绑。** `bind` 比较除 `createdAt` 外的所有身份字段——时间戳归首次写入所有——并以稳定的 `SESSION_IDENTITY_ALREADY_BOUND` 错误码拒绝冲突绑定。

### 源码地图

| 文件 | 职责 |
|---|---|
| [`src/registry.ts`](src/registry.ts) | `ctx.agentBindings` 服务：创建入口、bind、查询、冷恢复 |
| [`src/spec.ts`](src/spec.ts) | `session_identity` 域声明与绑定到共享契约类型的 zod 记录 schema |
| [`src/errors.ts`](src/errors.ts) | `SessionIdentityError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 包入口与默认导出 |

### 不变式

不发布运行时 invariant 伴随物：查询索引是一张域表的写穿投影，并在启动时从它重建；JSON 后端拒绝同一单元的第二个活动句柄，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 绑定注册表

#### 模型看到什么

没有任何内容。本包不注册工具、提示词段落或会话事件——任何 `AgentBindingRecord` 值都不会到达模型请求——因此没有请求字段携带其数据。

#### Token 影响

对每次请求的直接 token 影响为零。

#### KV Cache 影响

与实时请求无关：本包不触碰请求前缀，因此不可能使提供方缓存复用失效。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制界定了注册表在何种场景下不适用或需要特别运维关注。它们是当前包约束，不是任务清单。

- **`bind` 要求活动的本地会话** —— 代理 id 必须能在会话存储中解析，因此由远端 provider 服务的代理暂时无法绑定；远端绑定形状推迟到出现真实消费方再做。
- **无 unbind** —— 绑定记录是没有移除操作的持久事实；离开层级的代理保留其记录，生命周期移除推迟到消费方需要时再做。
- **绑定写入失败会留下活动的未绑定会话** —— 会话在记录写入之前创建，因此写入路径上的存储失败表现为响亮的 `SESSION_IDENTITY_PERSISTENCE` 错误，由调用方负责会话的清理。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
