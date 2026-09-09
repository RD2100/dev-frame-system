---
description: "Shadow 路由器聚合状态的只读 Remote 拥有者，供宿主状态面板调用。"
kind: "package"
---

# @deepseek-ai/dsh-experimental-shadow-controller

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-controller` 是[影子路由器](../shadow-router/README.zh.md)聚合状态的只读 Remote 拥有者。它以一个方法 `readStatus()` 支撑生成的 `ctx.remote.shadow` 命名空间，回答部署的真实事实：是否挂载了影子路由器、宿主组合指定了哪个控制者会话、该会话是否在线、授权根目录，以及持久化的绑定行。读取绝不修改路由器状态，也不会唤醒模型。正式发布排除本包，只能从源码 checkout 使用。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与推迟事项](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 从浏览器界面读取状态

把本服务挂载在[影子路由器](../shadow-router/README.zh.md)提供者旁边（[DevFrame profile 层](../devframe-profile/README.zh.md)已这样做），然后调用生成的命名空间：

```ts
const result = await ctx.remote.shadow.readStatus()
if (!result.ok) return
// result.value: { mounted, shadowSessionId?, shadowLive, authorizedRoots, bindings }
```

`mounted: false` 表示此部署没有组合影子路由器；`mounted: true` 而 `shadowSessionId` 缺失表示路由器存在但宿主尚未指定控制者。两者都是诚实的未启用回答，绝不伪装在线。

### 你会得到什么

- `ctx.shadowController` 服务与只读的 `readStatus()` 方法。
- 生成的 `@deepseek-ai/dsh-experimental-shadow-controller/remote` Client 产物，以及携带 `ShadowStatusView` 的 `./types` 子路径。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

`ShadowController` 以服务键 `shadowController`、Remote 命名空间 `shadow` 继承 `TypertRemoteService`。`readStatus()` 由 `@Remote` 修饰；typert 生成器在 `lib/` 下产出宿主 face 与 Client contribution。实现调用 `ctx.get('shadowRouter')`——可选服务读取，不做声明注入——并把路由器的 `readStatus()` 与 `mounted` 事实一起逐字投影。

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | `ShadowController` 服务与唯一的 `@Remote readStatus()` 方法 |
| [`src/types.ts`](src/types.ts) | Client 安全的 `ShadowStatusView` 词汇（仅类型） |
| [`lib/typert.host.js`](lib/typert.host.js) | 生成的宿主 FaceModel 与严格结果编解码器 |
| [`lib/typert.remote-client.js`](lib/typert.remote-client.js) | 生成的 Client contribution，挂载 `ctx.remote.shadow` |
| — | 不发布运行时 invariant 伴生；该读取是路由器状态的纯投影，路由器自身套件已覆盖。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [影子路由器](../shadow-router/README.zh.md)——本控制器投影的指定控制者域与绑定索引。
- [Shadow Web 入口](../client-ui-shadow-entry/README.zh.md)——读取此命名空间的常驻侧栏卡片。
- [实验包](../README.zh.md)——孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

无。该服务只读、宿主面、绝不被模型调用；不新增提示词、工具或 schema 内容。

#### KV Cache 效应

无——控制器不贡献任何模型可见内容。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **只读是构造决定的**——控制器不暴露任何写入面；变更仍由影子路由器自己的宿主侧 API 拥有。未来的状态操作（例如从 Web 请求停止）需要先做明确的写入面决策。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### Dev Note

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
