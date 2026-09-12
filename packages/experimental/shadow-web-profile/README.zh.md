---
description: "把常驻 Shadow 入口卡片加进源码 checkout 的 Web profile，与 Shadow 状态控制器并排。"
kind: "package-bundle"
---

# @deepseek-ai/dsh-experimental-shadow-web-profile

[English](README.md) | 中文

## 概述

`dsh-experimental-shadow-web-profile` 是 [Shadow 入口卡片](../client-ui-shadow-entry/README.zh.md)的私有 Web 层。加在 `@deepseek-ai/dsh-web-app` 之后即可挂载常驻侧栏入口。卡片读取 `shadow` Remote 命名空间，所以请在同时挂载[影子控制器](../shadow-controller/README.zh.md)宿主行的组合旁应用本层——[DevFrame profile 层](../devframe-profile/README.zh.md)把该行放在其 shadow-router 行旁边。没有路由器的组合中卡片仍会挂载并读取诚实的未挂载状态。正式发布排除本包，只能从源码 checkout 使用。

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

### 安装到 profile

从本仓库 checkout，把 Web Shadow 层加进已初始化、且组合中带有 DevFrame（或等价影子控制器）层的 `web` profile：

```sh
pnpm dsh plugin --profile web add ./packages/experimental/shadow-web-profile
```

用 `dsh plugin --profile web remove @deepseek-ai/dsh-experimental-shadow-web-profile` 移除本包会去掉卡片，组合的其余部分保持不变。

### 你会得到什么

侧栏页脚在设置按钮上方获得常驻 Shadow 入口。[`@deepseek-ai/dsh-experimental-client-ui-shadow-entry`](../client-ui-shadow-entry/README.zh.md) 拥有浏览器行为，并挂载用于读取状态的生成 Remote 命名空间。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现细节——点击展开</summary>

本包的运行时内容是 [`cordis.patch.yml`](cordis.patch.yml)。加在 `dsh-web-app` 之后，它唯一的 `insert` 条目为 `@deepseek-ai/dsh-experimental-client-ui-shadow-entry` 添加 `ui-shadow-entry` 行。插入的 Client 插件拥有生成的 Remote 组装与入口卡片；这个静态 bundle 不持有可变状态，也不安装运行时 invariant。

| 文件 | 职责 |
|---|---|
| [`cordis.patch.yml`](cordis.patch.yml) | 含 `ui-shadow-entry` 行的有序 Web 补丁 |
| [`src/index.ts`](src/index.ts) | 空模块入口；补丁即运行时内容 |
| — | 不发布运行时 invariant 伴生；本包只携带静态 profile 补丁。Remote 组装与入口卡片拥有各自的激活要求。 |

</details>

-----

<a id="further-exploration"></a>
## 延伸阅读

- [实验包](../README.zh.md)——孵化状态与发布排除。
- [Shadow Web 入口](../client-ui-shadow-entry/README.zh.md)——本层挂载的卡片。
- [DevFrame profile 层](../devframe-profile/README.zh.md)——携带 shadow-router 与 shadow-controller 行的宿主组合。
- [Web bundle](../../bundle/web-app/README.zh.md)——本补丁扩展的稳定浏览器层。

-----

<a id="model-experience"></a>
## 模型体验

### Shadow Web 补丁层

#### 模型看到什么

没有任何内容到达模型请求。本包是静态 Web 补丁：它唯一的 `cordis.patch.yml` insert 行挂载常驻浏览器入口卡片，bundle 自身不注册工具、提示词段落或会话事件；Shadow 域没有面向模型的面。

#### Token 影响

对每次请求的直接 token 影响为零。

#### KV Cache 影响

与实时请求无关：本 bundle 不贡献提示词、工具或 schema 内容，因此不可能使提供方缓存复用失效。

## 已知限制与推迟事项

<a id="known-limitations-and-deferred-work"></a>

- **有序组合**——`dsh-base`、`dsh-web-app`、影子控制器宿主层（DevFrame profile 或等价层）与本包必须保持该顺序。
- **仅限源码 checkout**——正式 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

无。

</details>
