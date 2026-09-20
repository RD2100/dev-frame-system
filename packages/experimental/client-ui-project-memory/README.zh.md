---
description: "库管理页 Web 入口：浏览、搜索、预览只读 Obsidian 记忆库，复制绝对路径，并在对话中引用文件。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-client-ui-project-memory

[English](README.md) | 中文

## 概要

`dsh-experimental-client-ui-project-memory` 是只读 Obsidian 记忆库（由 [project-memory](../project-memory/README.zh.md) 提供）的常驻 Web 入口。它挂载生成的 `ctx.remote.library` 命名空间，并在 `sidebar.footer.action` 座位注册侧边栏入口（order 25，位于专家中心与影子入口之间）。入口打开的库管理页展示记忆库可用状态与文件数、列出可访问文件、按文件名与内容搜索，并打开预览面板展示文件真实绝对磁盘路径、复制路径动作，以及「引用到对话」动作——向当前对话草稿追加 `@vault:<absolutePath>` 标记。未配置 Vault 的部署保持诚实的空态：页面说明记忆库不可用，不暴露任何无效控件。Vault 严格只读——页面从不追加、编辑或写入库内容。官方发布版不包含此私有包，仅源码检出可用。

## 目录

- [使用本包](#使用本包)
- [理解实现](#理解实现)
- [进一步探索](#进一步探索)
- [模型体验](#模型体验)
- [已知限制与后续工作](#已知限制与后续工作)
- [开发说明](#开发说明)

-----

<a id="使用本包"></a>
## 使用本包

### 装入 DevFrame Web profile

[DevFrame profile 层](../devframe-profile/README.zh.md) 已挂载 Host 记忆服务与本浏览器入口。手工组合时，在 Host 侧挂载 `@deepseek-ai/dsh-experimental-project-memory`，在 Web 侧挂载本包；包根在 headless 组合中惰性，Web loader 通过 `dsh.client` manifest 选择其 `/client` 导出。

### 你得到什么

- 一个常驻侧边栏入口，打开已配置 Vault 的库管理页。
- 一次快照读取得到记忆库可用状态与可访问文件数，并提供显式刷新动作。
- Vault 根下的文件列表，逐文件预览读取返回文件内容与其真实绝对磁盘路径。
- 按文件名与内容搜索的搜索框，每个命中带有限界摘要。
- 预览面板可复制绝对路径到剪贴板，并可在当前对话中引用文件（`@vault:<absolutePath>`）。
- 部署未配置 Vault 目录时呈现诚实的空态——无无效控件、无虚构清单。

-----

<a id="理解实现"></a>
## 理解实现

<details>
<summary>实现内部——点击展开</summary>

浏览器入口（`src/client/index.ts`）从 `@deepseek-ai/dsh-experimental-project-memory/remote` 导入生成的 Library Remote 产物并委托给 [`mountLibraryUi`](src/client/mount.ts)。挂载注册英文与中文 `library` 字典、注入侧边栏入口（id `project-library`，order 25），并在 `ctx.remote.library`（view/list/read/search）之上构造卡片 face，外加用于对话引用的 `LibraryReferenceController`。卡片挂载时读取一次快照，刷新时重新读取。搜索读取与文件列表分离，浏览与搜索不会混淆结果集。预览面板为纯展示组件（`LibraryPane`），与有状态的 `LibraryCard` 分离，使 client 测试能直接覆盖每个分支。引用控制器从 `sessions.list` 读取当前会话、解析其会话作用域，并通过 `conversation.input` 追加到既有草稿——它从不创建或切换会话；没有当前会话作用域时，动作返回本地化提示而非无效控件。

| 文件 | 职责 |
|---|---|
| [`src/client/index.ts`](src/client/index.ts) | 浏览器入口与生成的 Remote 绑定 |
| [`src/client/mount.ts`](src/client/mount.ts) | Remote 挂载、locale 注册与侧边栏贡献生命周期 |
| [`src/client/LibraryCard.tsx`](src/client/LibraryCard.tsx) | 有状态卡片与纯展示组件 `LibraryPane` |
| [`src/client/reference.ts`](src/client/reference.ts) | 追加草稿的对话引用（从不创建会话） |
| [`src/client/locales.ts`](src/client/locales.ts) | `library` locale 命名空间与中英文字典 |
| [`src/index.ts`](src/index.ts) | 面向 profile 组合的惰性 Host 侧包入口 |
| — | 不发布运行时 invariant 伴生；卡片是 Host Remote 快照的纯消费者。 |

</details>

-----

<a id="进一步探索"></a>
## 进一步探索

- [project-memory 核心](../project-memory/README.zh.md) — 有界 Obsidian 记忆服务与 Host Remote 拥有方。
- [DevFrame profile](../devframe-profile/README.zh.md) — 同时挂载 Host 与浏览器行的源码检出 Web 组合。
- [实验性包](../README.zh.md) — 孵化状态与发布排除。

-----

<a id="模型体验"></a>
## 模型体验

### 库管理页

#### 模型看到什么

页面本身仅浏览器侧，不注册工具或提示词片段。引用动作在当前对话中暂存普通用户可见的草稿文本（`@vault:<absolutePath>`）；用户提交该草稿后走正常对话路径。会话内对记忆库的模型工具仍是模型读取被引用文件的可见表面。

#### Token 影响

打开、浏览、搜索或引用不会自动发起请求。已提交的暂存引用像普通用户提示词一样贡献其可见文本。

#### KV 缓存影响

入口不贡献工具或 schema 内容。任何缓存影响来自用户提交的提示词文本，遵循正常对话行为。

## 已知限制与后续工作

<a id="已知限制与后续工作"></a>

- **只读 Vault** — 页面浏览、预览、搜索、复制路径与引用文件；按设计从不追加、编辑或写入库内容。
- **无最近访问 / Vault 选择 UI** — 页面只操作部署配置的 Vault；选择或切换 Vault 不在范围内。
- **追加草稿而非自动提交** — 引用落在输入框，用户提交才发送。没有当前会话作用域时，动作给出提示且不做任何改动。
- **无实时订阅** — 快照在挂载与刷新时读取；页面外的文件变化在下一次读取时可见。
- **仅源码检出** — 官方 CLI、Web、npm 与 Python 发布负载排除此私有包。

<a id="开发说明"></a>
### 开发说明

<details>
<summary>维护者工作上下文——点击展开</summary>

暂无。

</details>
