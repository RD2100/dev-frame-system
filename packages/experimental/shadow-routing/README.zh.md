---
description: "Shadow 路由缝的 Service Definition（ctx.shadowRouter）：抽象路由契约、路由词汇与 shadow/delivery-received 事件——不含 Provider、工具与存储。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-shadow-routing

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-routing` 是 shadow 路由能力缝的 Service Definition：它声明 `ctx.shadowRouter` 上下文键、抽象 `ShadowRouter` 服务契约，以及 shadow 家族所有成员共同编译的词汇——品牌化的请求、消息与验收哈希 id；控制器绑定、投递与请求记录类型及其 provisioning 与投递状态机；有界的请求/回执形态；稳定的 `ShadowRouterError` 及其 `SHADOW_*` 错误码联合；以及一条投递持久进入 `received` 时发出的 `shadow/delivery-received` 观察型事件。本包没有实现、没有模型可见工具、也没有存储：Service Provider 是 `@deepseek-ai/dsh-experimental-shadow-router`，而 Consumer（shadow 桥与控制器）只依赖本包。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

任何为 shadow 路由标注类型、消费或实现契约的代码都从本包导入词汇；需要路由器本身的组合再挂载 Provider 包。

### 不经 Provider 直接消费契约

测试、宿主桥与 Remote 属主从本包导入抽象 `ShadowRouter` 类型、记录形态与品牌工厂，而不是从 Provider 导入，因此它们永远不会加载实现：

```ts
import type { ShadowRouter, ShadowDeliveryRecord } from '@deepseek-ai/dsh-experimental-shadow-routing'

function forwardable(delivery: ShadowDeliveryRecord, router: ShadowRouter): boolean {
  const binding = router.findBinding(delivery.workspaceId)
  return binding !== undefined
    && binding.state === 'ready'
    && delivery.state === 'received'
    && delivery.goalId === binding.activeGoalId
}
```

品牌工厂在边界处校验：`ShadowRequestId`、`ShadowMessageId` 与 `AcceptanceHash` 为有界 token 加品牌，遇到其他输入即抛出 `SHADOW_INVALID_REQUEST` 码的 `ShadowRouterError`。

### 实现契约

Service Provider 继承 `ShadowRouter`，实现全部抽象方法，并作为插件加载——它注册为 `ctx.shadowRouter`（每个上下文一个实现；加载第二个会抛错，这是 cordis 标准的重复服务行为）。Provider 同时拥有 `static Config` 及其默认值与 `ShadowRouterConfig` 类型——插件自己的 config 类型必须住在自己的包里。随仓发布的 Provider 是 `@deepseek-ai/dsh-experimental-shadow-router`。

### 通过事件响应投递

`shadow/delivery-received` 是一条观察型 typed 事件：Provider 在一条 queued 投递的持久目标接受写入提交之后发出它，携带工作区 id 与进入 `received` 时的冻结记录快照。它在发送路径与把 queued 行收敛为 `received` 的恢复路径上都会发出；事件绝不重放，在转移之后才挂载的监听者（或进程重启后）改经 Provider 的读取面对账。监听者失败会被包含并记录日志，绝不会使路由操作失败。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

本节解释缝背后的设计决策并指向实现它们的代码；可观察行为已在[使用本包](#use-this-package)中完整覆盖。

### 设计概念

这条缝存在的意义是把 shadow 家族的词汇放进一个无属主的位置：抽象类与词汇随契约变化，Provider 随持久化、provisioning 或工具化变化。它沿用 `dsh-subprocess` / `dsh-shell` 的 Service Definition 模板——抽象类加类型，除品牌校验与事件派发外没有运行时行为——并且拥有带逐监听者包含的事件派发，使一个损坏的 Consumer 无法让路由操作失败。

### 源码地图

| 文件 | 角色 |
|---|---|
| [`src/service.ts`](src/service.ts) | 抽象 `ShadowRouter`、`ctx.shadowRouter` 扩增、`shadow/delivery-received` 事件与带包含的 emit 助手 |
| [`src/types.ts`](src/types.ts) | 词汇：记录、状态机与请求/回执形态 |
| [`src/ids.ts`](src/ids.ts) | 品牌化的请求、消息与验收哈希 id 工厂及其边界校验 |
| [`src/errors.ts`](src/errors.ts) | `ShadowRouterError` 及其稳定错误码联合 |
| [`src/index.ts`](src/index.ts) | 包入口与默认导出 |
| — | 不发布运行时不变量伴生包：本缝不拥有状态，因此不存在可能分叉的受有关系。 |

</details>

-----

<a id="model-experience"></a>
## 模型体验

无，因为 Service Definition 自身不注册任何工具、提示词分区或模型可见请求内容；四个项目工具与全部模型可见效果由 Provider 负责。

#### KV Cache 影响

无直接失效；工具模式对请求前缀的影响由 Provider 包负责，本包的声明从不进入模型请求。

## 已知限制与延期工作

<a id="known-limitations-and-deferred-work"></a>

这些限制界定了本缝何时不适配、或把工作留给 Provider 与 Consumer。它们是当前包约束，不是任务清单。

- **本包不发布 Provider** —— 只挂载本包的组合没有 `ctx.shadowRouter`；持久化、provisioning 与工具白名单由 Service Provider（`@deepseek-ai/dsh-experimental-shadow-router`）负责。
- **事件只观察、绝不重放** —— 在转移之后（或进程重启后）才挂载的 Consumer 经 Provider 的读取面对账；本缝不提供投递事件历史。
- **私有实验性契约** —— 词汇可以变更且不带支持承诺，shadow 家族之外不应导入它。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者工作上下文——点击展开</summary>

无。

</details>
