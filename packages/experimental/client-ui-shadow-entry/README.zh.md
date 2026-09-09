---
description: "常驻 Web Shadow 入口卡片：设置按钮上方的诚实状态，由只读状态控制器支撑。"
kind: "package"
---

# @deepseek-ai/dsh-experimental-client-ui-shadow-entry

[English](README.md) | 中文

## 概述

`dsh-experimental-client-ui-shadow-entry` 是 [Shadow](../shadow-router/README.zh.md) 的常驻 Web 入口。它挂载生成的 `ctx.remote.shadow` Remote 命名空间，并向侧栏的 `sidebar.footer.action` 座位——设置按钮上方的页脚堆叠——注册一张卡片，展示部署的真实 Shadow 状态：未挂载路由器或未指定控制者会话时显示未启用，指定的会话未在线时显示已配置，在线后显示在线。展开的面板列出控制者会话、授权根目录，以及每条持久化绑定的工作区、路径与修订。正式发布排除本包，只能从源码 checkout 使用。

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

### 安装到 Web profile

先加[影子控制器宿主层](../shadow-controller/README.zh.md)（[DevFrame profile 层](../devframe-profile/README.zh.md)已携带），再加本包的 [Web 层](../shadow-web-profile/README.zh.md)。卡片在挂载时读取一次 `ctx.remote.shadow.readStatus()`，并在每次展开面板时再读一次；读取失败显示传输错误，而不是伪装状态。

### 你会得到什么

- 常驻触发器（宽侧栏为图标加标签，窄栏仅图标）与阶段圆点：灰色读取中、琥珀色已配置、绿色在线。
- 触发器上方的固定状态面板：阶段行、未启用阶段的诚实说明文案，以及会话、根目录与绑定事实。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

浏览器入口（`src/client/index.ts`）绑定生成的 Remote contribution 并交给 [`mountShadowEntryUi`](src/client/mount.ts)：先挂载 contribution，再在 `ctx.inject(['remote.shadow', 'slots', 'locale'])` 下注册区域字典与一个 `sidebar.footer.action` 条目（id `shadow-entry`，order 30），其 inject face 携带状态 store 与刷新动作。`ShadowStatusController` 在 `createSnapshotStore` 上加了被取代读取守卫：最后发出的读取拥有 store，失败在保留上一份好视图的同时发布错误消息。`presentShadowStatus` 是从快照到卡片模型的纯折叠，`ShadowCard` 负责渲染——组件内没有订阅机制；store 经 inject `hooks` 舱位由渲染器绑定。

| 文件 | 职责 |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | 浏览器入口，把生成的 Remote 产物绑定到挂载生命周期 |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote 挂载与卡片注册及其联合回滚 |
| [`src/client/ShadowCard.tsx`](src/client/ShadowCard.tsx) | 常驻触发器与状态面板 |
| [`src/client/shadow-presenter.ts`](src/client/shadow-presenter.ts) | 纯快照到模型折叠（阶段、行、区域键） |
| [`src/client/shadow-store.ts`](src/client/shadow-store.ts) | 快照 store 之上的状态控制器 |
| [`src/client/locales.ts`](src/client/locales.ts) | `shadow` 区域命名空间的英文与中文字典 |
| — | 不发布运行时 invariant 伴生；卡片是控制器只读快照的纯消费者。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [Shadow 状态控制器](../shadow-controller/README.zh.md)——本卡片读取的只读 `ctx.remote.shadow` 命名空间。
- [影子路由器](../shadow-router/README.zh.md)——快照背后的指定控制者域。
- [实验包](../README.zh.md)——孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

无。卡片是纯浏览器展示；不新增模型请求内容。

#### KV Cache 效应

无——本入口不贡献提示词、工具或 schema 内容。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **只读卡片**——本入口不暴露 Shadow 操作；启用、指定与停止都在宿主侧。增加动作需要先对控制器做明确的写入面决策。
- **无实时刷新**——卡片在挂载与展开时读取；不订阅绑定变化，长时间展开的面板在下一次展开前可能显示过期修订。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### Dev Note

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
