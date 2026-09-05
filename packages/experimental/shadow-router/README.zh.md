---
description: "Cordis 服务：在多个独立项目根之间路由用户意图——持久的控制器绑定存储、以 received 与 completed 两种状态持久化的跨根投递，以及只对 Shadow 开放的四个模型可见项目工具。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-router

[English](README.md) | 中文

## Summary

`dsh-experimental-shadow-router` 挂载 `ctx.shadowRouter`，是插件化代理层级的 Shadow 侧路由器。它在自己的 `shadow_router` 存储域（组合 storages 根下的 JSON 文档）中为每个工作区保存一条控制器绑定；为每个项目创建带精确 `cwd` 元数据的独立控制器根会话；把每条跨根投递持久化两次——发送方的 `queued` 意图与目标已接受的 `received` 输入——并将 `completed` 作为一个独立的持久状态；且只向宿主指定为 Shadow 的那一个代理作用域安装四个项目工具（`project_open`、`project_send`、`project_status`、`project_stop`）。停止按项目隔离：其他绑定、它们的控制器与队列都不受影响。本包是私有的实验性宿主侧服务；它不注册提示词分区与会话事件，TypeScript 与 Python SDK 投影不受影响。

## Table of Contents

- [Use this package](#use-this-package)
- [Understand the implementation](#understand-the-implementation)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

在已经挂载存储栈、会话存储、工作区注册表与会话身份绑定注册表的组合中挂载本服务；它硬注入 `ctx.sessions`、`ctx.storageDomain`、`ctx.workspaceRegistry` 与 `ctx.agentBindings`，任一缺失即在激活时报错。

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
  config:
    root: dshHomePath('storages')
- name: '@deepseek-ai/dsh-storage-domain'
  config:
    backend: json
- name: '@deepseek-ai/dsh-session'
- name: '@deepseek-ai/dsh-workspace'
- name: '@deepseek-ai/dsh-experimental-session-identity'
- name: '@deepseek-ai/dsh-experimental-shadow-router'
  config:
    authorizedRoots: [dshHomePath('projects')]
```

### Config

| 字段 | 默认值 | 含义 |
|---|---|---|
| `authorizedRoots` | `[]` | 项目根允许位于其下的绝对目录。为空表示任何项目都无法打开（fail-closed）。 |
| `controllerProfile` | `'devframe'` | 每条绑定固定的 profile 键；已绑定到其他 profile 的绑定会被拒绝。 |
| `maxPendingDeliveries` | `16` | 每个项目 `queued` 投递的上限；队列已满时，新输入在接受前即被拒绝。 |
| `maxMessageChars` | `20000` | 单条投递文本的长度上限。 |
| `statusPageSize` | `20` | `project_status` 每页项目与投递的最大条数。 |

### Designate the Shadow and call the tools

`markShadow(agent)` 只把四个工具装进该代理的作用域，其他作用域一个都解析不到。宿主调用与工具相同的 Service 方法，外加模型永远接触不到的宿主专用缝：`setActiveGoal` 为项目授权一次运行，`completeDelivery` 结清 received 投递，`confirmProjectStopped` 收尾一次停止，`recoverDeliveries` 在重启时收敛中断的行。

```ts
const shadow = ctx.agentLoop.create(SessionId('session-shadow'), { provider: 'mock', model: 'mock' })
ctx.shadowRouter.markShadow(shadow)

const open = await ctx.shadowRouter.openProject(shadow, { path: projectRoot, requestId: 'open-1' })
await ctx.shadowRouter.setActiveGoal(open.workspaceId, goalId, acceptanceHash)
const receipt = await ctx.shadowRouter.sendToProject(shadow, {
  workspaceId: open.workspaceId, bindingRevision: open.bindingRevision,
  goalId, acceptanceHash, requestId: 'send-1', mode: 'work', text: '…',
})
```

-----

<a id="understand-the-implementation"></a>
## Understand the implementation

<details>
<summary>实现内部——点击展开</summary>

本节解释特性背后的设计决策并指向实现它们的代码；可观察行为已在 [Use this package](#use-this-package) 完整覆盖。

### Design decisions

- **每个项目一条 provisioning 状态机。** `reserving → provisioning → ready` 在每一步动作前先持久化，任何时点崩溃都会留下一条后续 open 或宿主 reconcile 可收敛的行：保留的会话 id 绝不二次铸造，创建失败把行滚到可见的 `failed`，cwd 不匹配则停为 `needs_attention` 而不是出现第二个写入者。
- **两次写入的投递，三个持久状态。** `sendToProject` 先把发送方意图持久化为 `queued`，再把目标已接受的输入标记为 `received`；`completed` 是由宿主另行结清的控制器侧事实，回执绝不声称工作已执行。`queued → received` 与 `received → completed` 是仅有的前进转移；被取消的 queued 行连同原因保持可见。
- **请求重放日志。** 每次 open/send/stop 都以调用方的 `requestId` 为键保存规范化输入哈希与结果，因此响应中断后的重试会重放已存结果而不是重复执行，同一 id 携带不同输入则响亮失败（`SHADOW_REQUEST_CONFLICT`）。
- **复用注册表事实，而非邮箱语义。** 路由复用工作区注册表的规范路径事实（`fs.realpath` 规范、别名折叠、按段的重叠检查）；有意不复用 agent-team 邮箱的成员校验，因为 Shadow 的目标由绑定存储授权，而非团队成员身份。
- **单项目停止隔离。** 停止只取消该绑定的 `queued` 投递（连同 `project-stopped` 原因保持可见），把绑定停为 `stopping`，其他绑定、控制器会话与队列一律不动；已接受的投递在随后的停止中依然存活。

### Source map

| 文件 | 角色 |
|---|---|
| [`src/service.ts`](src/service.ts) | `ctx.shadowRouter` 服务：绑定生命周期、投递持久化、重放、状态、宿主缝 |
| [`src/tools.ts`](src/tools.ts) | 四个项目工具及其 Shadow 作用域安装 |
| [`src/spec.ts`](src/spec.ts) | `shadow_router` 域规格：bindings、deliveries、requests 三张表 |
| [`src/ids.ts`](src/ids.ts) | 请求、消息与验收哈希的品牌化 id |
| [`src/errors.ts`](src/errors.ts) | `ShadowRouterError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 包入口与默认导出 |

### Invariant

未发布运行时不变量伴生包：内存索引是单张域表的 write-through 投影并在启动时由其重建，且 JSON 后端拒绝同一存储单元上的第二个存活句柄，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## Model Experience

### Shadow project tools

#### What the model sees

被指定的 Shadow 作用域恰好多出四个工具。`project_open` 把一个已授权的既有目录解析为工作区与控制器根；`project_send` 投递一条有界的 `work`/`note` 消息并返回绝不声称已完成的 `received` 回执；`project_status` 读取单个项目或有界分页，包括逐条投递状态与阻塞原因；`project_stop` 精确停止一个项目并报告 stopping 直到宿主确认。失败返回结构化 `SHADOW_*` 错误码（过期 revision、未知工作区、未授权调用方、超长文本、队列已满），绝不暴露原始存储错误。

#### Token effect

四个工具的模式常驻 Shadow 作用域的工具列表，每次请求都在；每次工具调用追加一轮结果，规模受投递与状态分页上限约束。

#### KV Cache effect

工具模式只声明一次且字节稳定，因此第一次项目调用之前的请求前缀可复用供应商缓存；每次调用的结果追加在其后，不会使共享前缀失效。

## Known Limitations and Deferred Work

这些限制界定了路由器何时不适配或需要特别的运维注意。它们是当前包约束，不是任务清单。

- **没有 UI 状态集** —— 面向客户端的项目状态投影（队列卡片、停止确认）是独立的关注点，不属于本包。
- **投递呈现是宿主侧职责** —— 路由器负责持久化与回执；把 received 输入写入控制器会话日志由宿主组合完成，因此裸挂载不会产生任何模型可见内容。
- **`authorizedRoots` 为空则什么都打不开** —— fail-closed 默认是有意的；组合必须显式声明它服务的根。
- **每个存储根一个存活进程** —— JSON 后端拒绝同一存储单元上的第二个存活句柄，因此对同一根启动第二个路由进程会响亮失败而不是竞态。

<a id="dev-note"></a>
### Dev Note

<details>
<summary>维护者工作上下文——点击展开</summary>

无。

</details>
