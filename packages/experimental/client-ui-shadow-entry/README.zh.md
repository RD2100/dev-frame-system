---
description: "常驻 Web Shadow 入口：触发器经标准对话界面打开影子唯一的常驻对话，管理按钮打开诚实的只读状态下拉。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-shadow-entry

[English](README.md) | 中文

## 概述

`dsh-experimental-client-ui-shadow-entry` 是 [Shadow](../shadow-router/README.zh.md) 的常驻 Web 入口——人类全局、跨项目的界面。它挂载生成的 `ctx.remote.shadow` Remote 命名空间，并向侧栏的 `sidebar.footer.action` 座位——设置按钮上方的页脚堆叠——注册一张卡片。触发器打开影子唯一的常驻对话：部署指定的会话，由主聊天使用的同一个标准对话界面渲染，每次点击进的是同一个对话，从不新建；卡片自身不渲染对话。本入口还会把该指定会话标记为内部会话，因此在入口挂载期间会话列表不会为它渲染任何一行。触发器旁的管理按钮打开只读下拉：真实 Shadow 阶段——未挂载路由器或未指定控制者会话时显示未启用，指定的会话未在线时显示已配置，在线后显示在线——指定会话 id、授权根目录与控制器预设。展开下拉会重读状态，读取失败显示传输错误而不是伪装状态。正式发布排除本包，只能从源码 checkout 使用。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [延伸阅读](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与推迟事项](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 安装到 Web profile

先加[影子控制器宿主层](../shadow-controller/README.zh.md)（[DevFrame profile 层](../devframe-profile/README.zh.md)已携带），再加本包的 [Web 层](../shadow-web-profile/README.zh.md)。触发器通过标准对话界面打开部署指定的会话；卡片在挂载时读取一次 `ctx.remote.shadow.readStatus()`，并在每次展开管理下拉时再读一次，读取失败显示传输错误而不是伪装状态，而每次成功读取都会把指定的 id 登记为内部会话，使会话列表永不为此多出一行。

### 你会得到什么

- 常驻触发器（宽侧栏为图标加标签，窄栏仅图标）。点击它打开影子指定的会话——一个常驻对话，每次都是同一个，由主聊天使用的同一个标准对话界面渲染——且会话列表不为它保留任何一行。
- 触发器旁的管理按钮（宽侧栏）打开 portal 到侧栏旁的只读下拉：诚实的阶段及其未启用阶段的说明文案、指定会话 id、授权根目录（或显式的空态文案），以及控制器预设。宽侧栏中触发器旁的详情行在不展开任何内容时承载同样的诚实文案。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

浏览器入口（`src/client/index.ts`）绑定生成的 Remote contribution 并交给 [`mountShadowEntryUi`](src/client/mount.ts)：先挂载 contribution，再在 `ctx.inject(['remote.shadow', 'slots', 'locale', 'sessions'])` 下注册区域字典与一个 `sidebar.footer.action` 条目（id `shadow-entry`，order 30），其 inject face 携带状态 store 与两个动作：`onRefresh`（直通状态读取）与 `onOpenConversation`——它读取 `shadow/readStatus`，指定的 id 尚未列出时刷新会话列表，再经 `sessions` 客户端契约打开该 id——绝不 `create()`：宿主在启动时经代理路径创建指定会话，该路径不记录 `cwd`，而 `session/create` RPC 拒绝为工作区收编这样的会话（`session/conflict`）。每次成功的状态读取还会经 `sessions.markInternal()` 登记指定的 id，会话浏览器据此不为该会话渲染任何一行：该分类是客户端局部的，会跟随重新部署后的指定变化，并在卸载时撤销。`ShadowStatusController` 在 `createSnapshotStore` 上加了被取代读取守卫：最后发出的读取拥有 store，失败在保留上一份好状态的同时发布错误消息。`presentShadowStatus` 是从快照到卡片模型的纯折叠，`ShadowCard` 负责渲染——组件内没有订阅机制；store 经 inject `hooks` 舱位由渲染器绑定。管理下拉 portal 到 `document.body` 并固定定位于侧栏旁，因为侧栏列裁剪溢出，任何原位表面都无法到达页面区域。

| 文件 | 职责 |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | 浏览器入口，把生成的 Remote 产物绑定到挂载生命周期 |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote 挂载、卡片注册、指定会话分类及其联合回滚 |
| [`src/client/ShadowCard.tsx`](src/client/ShadowCard.tsx) | 打开指定对话的常驻触发器，与管理按钮及其只读下拉 |
| [`src/client/shadow-presenter.ts`](src/client/shadow-presenter.ts) | 纯快照到模型折叠 |
| [`src/client/shadow-store.ts`](src/client/shadow-store.ts) | 快照 store 之上的状态控制器 |
| [`src/client/locales.ts`](src/client/locales.ts) | `shadow` 区域命名空间的英文与中文字典 |
| — | 不发布运行时 invariant 伴生；卡片是控制器快照的纯消费者与读取面的直通。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [Shadow 状态控制器](../shadow-controller/README.zh.md)——本面板读写的 `ctx.remote.shadow` 命名空间。
- [影子路由器](../shadow-router/README.zh.md)——面板背后的指定控制者域与宿主写入桥。
- [实验包](../README.zh.md)——孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

### Shadow 入口卡片

#### 模型看到什么

没有任何内容到达模型请求。卡片是纯浏览器呈现：不注册工具、提示词段落或会话事件，其读取与写入都经生成的 `ctx.remote.shadow` Remote 命名空间运行，该命名空间保持宿主面、从不进入提示词。

#### Token 影响

对每次请求的直接 token 影响为零。

#### KV Cache 影响

与实时请求无关：本入口不贡献提示词、工具或 schema 内容，因此不可能使提供方缓存复用失效。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **刷新是显式的**——卡片在挂载与每次展开管理下拉时读取状态；不订阅变化，长时间停留的页面在下一次展开或菜单点击前可能显示过期阶段。
- **隐藏指定行依赖本入口**——该分类是客户端局部的，存活期与本入口挂载期完全一致，因此未装本包的 Web 客户端或任何非 Web 客户端仍会把指定会话当作普通行列出。
- **打开失败是静默的**——触发器在后台打开指定会话，因此状态读取失败或未指定会话时按钮看起来毫无反应，拒绝只会到达控制台；面向用户的错误呈现仍待补。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
