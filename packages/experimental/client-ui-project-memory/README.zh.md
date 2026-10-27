---
description: "记忆库能力中心标签页：浏览、搜索、预览只读 Obsidian 记忆库，复制绝对路径，并在对话中引用文件。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-project-memory

[English](README.md) | 中文

## 概要

`dsh-experimental-client-ui-project-memory` 为只读 Obsidian 记忆库（由 [project-memory](../project-memory/README.zh.md) 提供）在能力中心增加一个「记忆库」标签页。它挂载生成的 `ctx.remote.library` 命名空间，展示记忆库可用状态与文件数、列出可访问文件、按名称和内容搜索，并预览文件及其绝对路径。预览可以复制路径，或向当前对话草稿追加 `@vault:<absolutePath>` 引用。未配置 Vault 的部署会说明记忆库不可用，并隐藏浏览控件。Vault 严格只读：页面从不追加、编辑或写入库内容。本包作为可选客户端插件发布，通过公开的键控插槽加入能力中心。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [进一步探索](#further-exploration)
- [模型体验](#model-experience)
- [已知限制与后续工作](#known-limitations-and-deferred-work)
- [开发说明](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 安装到 DSH Web profile

[DevFrame profile 层](../devframe-profile/README.zh.md) 已挂载 Host 记忆服务与本浏览器入口。手工组合时，在 Host 侧挂载 `@deepseek-ai/dsh-experimental-project-memory`，在 Web 侧挂载本包；包根在 headless 组合中惰性，Web loader 通过 `dsh.client` manifest 选择其 `/client` 导出。本客户端可选使用能力中心插槽，即使未安装中心提供方也能保持独立加载。

### 你得到什么

- 能力中心中的「记忆库」标签页，用于访问已配置的 Vault。
- 一次快照读取得到记忆库可用状态与可访问文件数，并提供显式刷新动作。
- Vault 根下的文件列表，逐文件预览读取返回文件内容与其真实绝对磁盘路径。
- 按文件名与内容搜索的搜索框，每个命中带有限界摘要。
- 预览面板可复制绝对路径到剪贴板，并可在当前对话中引用文件（`@vault:<absolutePath>`）。
- 部署未配置 Vault 目录时呈现诚实的空态——无无效控件、无虚构清单。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

浏览器入口（`src/client/index.ts`）从 `@deepseek-ai/dsh-experimental-project-memory/remote` 导入生成的 Library Remote 产物并委托给 [`mountLibraryUi`](src/client/mount.ts)。挂载注册英文与中文 `library` 字典，并通过 `capabilities.center.tab` 注册 key 为 `library` 的页面；类型导入会加载该 slot 声明，不会在运行时导入清单功能。它在 `ctx.remote.library`（view/list/read/search）之上构造 face，并创建用于对话操作的 `LibraryReferenceController`。页面挂载时读取快照，用户可以显式刷新。搜索结果与文件列表分开展示；请求序号会丢弃过期回复和卸载后的回复。预览面板为纯展示组件（`LibraryPane`），与有状态的 `LibraryCard` 分离，使 client 测试能直接覆盖各分支。引用控制器从 `sessions.list` 读取当前会话、解析其会话作用域，并通过 `conversation.input` 追加到既有草稿；它从不创建或切换会话，没有可接收引用的会话时会显示本地化提示。

| 文件 | 职责 |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | 浏览器入口与生成的 Remote 绑定 |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote 挂载、locale 注册与能力中心标签页生命周期 |
| [`src/client/LibraryCard.tsx`](src/client/LibraryCard.tsx) | 有状态卡片与纯展示组件 `LibraryPane` |
| [`src/client/reference.ts`](src/client/reference.ts) | 追加草稿的对话引用（从不创建会话） |
| [`src/client/locales.ts`](src/client/locales.ts) | `library` locale 命名空间与中英文字典 |
| [`src/index.ts`](src/index.ts) | 面向 profile 组合的惰性 Host 侧包入口 |
| — | 不发布运行时 invariant 伴生；卡片是 Host Remote 快照的纯消费者。 |

</details>

-----

<a id="further-exploration"></a>
## 进一步探索

- [project-memory 核心](../project-memory/README.zh.md) — 有界 Obsidian 记忆服务与 Host Remote 拥有方。
- [DevFrame profile](../devframe-profile/README.zh.md) — 更大范围栈的可选源码组合。
- [实验性包](../README.zh.md) — 孵化状态与发布排除。

-----

<a id="model-experience"></a>
## 模型体验

### 库管理页

#### 模型看到什么

页面本身仅浏览器侧，不注册工具或提示词片段。引用动作在当前对话中暂存普通用户可见的草稿文本（`@vault:<absolutePath>`）；用户提交该草稿后走正常对话路径。会话内对记忆库的模型工具仍是模型读取被引用文件的可见表面。

#### Token 影响

打开、浏览、搜索或引用不会自动发起请求。已提交的暂存引用像普通用户提示词一样贡献其可见文本。

#### KV 缓存影响

入口不贡献工具或 schema 内容。任何缓存影响来自用户提交的提示词文本，遵循正常对话行为。

## 已知限制与后续工作

<a id="known-limitations-and-deferred-work"></a>

- **只读 Vault** — 页面浏览、预览、搜索、复制路径与引用文件；按设计从不追加、编辑或写入库内容。
- **无最近访问 / Vault 选择 UI** — 页面只操作部署配置的 Vault；选择或切换 Vault 不在范围内。
- **追加草稿而非自动提交** — 引用落在输入框，用户提交才发送。没有当前会话作用域时，动作给出提示且不做任何改动。
- **无实时订阅** — 快照在挂载与刷新时读取；页面外的文件变化在下一次读取时可见。
- **可选提供方** — 同时挂载本包和能力中心外壳后才显示“记忆库”页面；未配置 Vault 时，Host Remote 仍会诚实报告不可用状态。

<a id="dev-note"></a>
### 开发说明

<details>
<summary>维护者工作上下文——点击展开</summary>

暂无。

</details>
