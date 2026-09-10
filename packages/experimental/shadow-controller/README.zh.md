---
description: "Shadow 路由器聚合状态与面板写入面的 Remote 拥有者，供宿主状态面板调用。"
kind: "package"
---

# @deepseek-ai/dsh-experimental-shadow-controller

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-controller` 是[影子路由器](../shadow-router/README.zh.md)聚合状态与面板写入面的 Remote 拥有者。它以一个诚实的读取 `readStatus()`——是否挂载了影子路由器、宿主组合指定了哪个控制者会话、该会话是否在线、授权根目录，以及打开项目的行——和三个写入 `openProject(path)`、`sendToController(workspaceId, text)`、`releaseProject(workspaceId)` 支撑生成的 `ctx.remote.shadow` 命名空间。每个写入都委托给影子路由器的宿主桥，因此校验、调用者门禁（以指定 Shadow 的授权运行）、重放与投递通道都仍是路由器自己的；控制器只为每次操作铸造一个新的请求 id。本服务绝不唤醒模型。正式发布排除本包，只能从源码 checkout 使用。

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

### 驱动面板写入

```ts
await ctx.remote.shadow.openProject({ path: 'D:/projects/alpha' }) // ProjectOpenResult
await ctx.remote.shadow.sendToController({ workspaceId, text: 'ship the release' }) // ProjectSendResult
await ctx.remote.shadow.releaseProject({ workspaceId }) // ProjectStopResult, status 'stopped'
```

失败以 `{ ok: false, error: { code, message } }` 解析，并逐字携带路由器自己的拒绝理由——未授权根、路径不存在、项目已关闭——因此界面显示服务的原因而不是编造一个。没有挂载路由器时，读取保持诚实（`mounted: false`），每个写入都大声失败。

### 你会得到什么

- `ctx.shadowController` 服务与诚实的 `readStatus()` 方法、三个写入面。
- 生成的 `@deepseek-ai/dsh-experimental-shadow-controller/remote` Client 产物，以及携带 `ShadowStatusView` 与写入词汇的 `./types` 子路径。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

`ShadowController` 以服务键 `shadowController`、Remote 命名空间 `shadow` 继承 `TypertRemoteService`。每个方法都由 `@Remote` 修饰；typert 生成器在 `lib/` 下产出宿主 face 与 Client contribution。实现调用 `ctx.get('shadowRouter')`——可选服务读取，不做声明注入。`readStatus()` 把路由器的快照与 `mounted` 事实一起逐字投影；写入以每次操作铸造的 `randomUUID()` 请求 id 调用 `openProjectForHost`、`sendToProjectForHost` 与 `releaseProjectForHost`，因为每次面板操作都是一个新意图。

| 文件 | 职责 |
|---|---|
| [`src/index.ts`](src/index.ts) | `ShadowController` 服务：读取与三个 `@Remote` 写入面 |
| [`src/types.ts`](src/types.ts) | Client 安全的 `ShadowStatusView` 与写入词汇（仅类型） |
| [`lib/typert.host.js`](lib/typert.host.js) | 生成的宿主 FaceModel 与严格结果编解码器 |
| [`lib/typert.remote-client.js`](lib/typert.remote-client.js) | 生成的 Client contribution，挂载 `ctx.remote.shadow` |
| — | 不发布运行时 invariant 伴生；每个方法都是路由器状态的投影或委托，路由器自身套件已覆盖。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [影子路由器](../shadow-router/README.zh.md)——本控制器暴露的指定控制者域、投递通道与宿主写入桥。
- [Shadow Web 入口](../client-ui-shadow-entry/README.zh.md)——读写此命名空间的常驻侧栏面板。
- [实验包](../README.zh.md)——孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

无。该服务是宿主面，绝不被模型调用；不新增提示词、工具或 schema 内容。

#### KV Cache 效应

无——控制器不贡献任何模型可见内容。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **写入以指定 Shadow 的授权运行**——写入桥运行与模型面工具相同的受门禁流程，因此指定会话缺失或不在线的部署会以诚实消息拒绝所有写入，而不是绕过门禁。
- **解除是停止语义**——被解除的项目落在 `stopped` 并随行保持可见；重新打开会被路由器拒绝（`SHADOW_PROJECT_STOPPED`），因为重启遵循宿主恢复策略。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### Dev Note

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
