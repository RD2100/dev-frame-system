---
description: "Web 会话 ID 徽标：会话头部工具区的会话 ID 芯片，支持一键复制；面向会话身份体验的用户与维护者。"
kind: "package-reference"
---

# @deepseek-ai/dsh-client-ui-session-id

English | [中文](README.md)

## 概述

本包渲染 Web GUI 的会话 ID 徽标：会话头部工具区中的一枚芯片，显示当前会话的 ID 并支持一键复制。该 ID 与核心会话存储创建并持久化的 branded `SessionId` 是同一个值——本包只把它呈现给人，不拥有任何自己的身份。芯片在视觉上截断过长 ID，复制按钮始终把完整值写入剪贴板，ID 文本本身保持可选中。

## 目录

- [使用本包](#使用本包)
- [理解实现](#理解实现)
- [延伸阅读](#延伸阅读)
- [模型体验](#模型体验)
- [已知限制与延后工作](#已知限制与延后工作)

-----

<a id="使用本包"></a>
## 使用本包

把本插件挂载到 Web 客户端旁；徽标随后出现在每个有 ID 的会话的会话头部工具区，位于会话日志下载动作之前。点击复制按钮把完整 ID 写入剪贴板并显示一秒成功状态；写入被拒（权限拒绝、非安全上下文）时保留复制入口而不谎报成功。没有会话 ID 时（空白会话 Hero）不渲染任何内容。

复制出的 ID 在所有接受会话 ID 的位置都能寻址该会话：会话列表搜索、历史读取、ACP 与 SDK 的会话寻址，以及持久化日志文件名。

-----

<a id="理解实现"></a>
## 理解实现

<details>
<summary>实现细节 — 点击展开</summary>

本包向 `dsh-client-ui-conversation` 声明的 `conversation.session.header.utilities` 列表贡献一个条目（`session-id-badge`，order `-10`），并通过标准会话作用域的 `sessionId` prop 读取 ID——无 RPC、无 store。复制反馈使用 `dsh-client-ui-primitives` 的共享 `writeClipboard` 助手，优先走异步 Clipboard API，回退到 `execCommand('copy')`。复制动作全部是用户可见行为：会话日志不记录它，ID 本身来自 Session Controller 的 wire，因此没有任何模型可见面变化。

</details>

-----

<a id="延伸阅读"></a>
## 延伸阅读

当徽标不够用、需要理解身份本身时阅读这些页面。

- [Session 子系统](../../../docs/subsystems/session.md) — 拥有 `SessionId`、其 branded 类型与 `SessionHeader` 持久化。
- [dsh-client-ui-jobs](../ui-jobs/README.zh.md) — 本包遵循的会话头部动作的姊妹模式。
- [dsh-client-ui-conversation](../ui-conversation/README.zh.md) — 声明徽标占用的头部工具区槽位。

-----

<a id="模型体验"></a>
## 模型体验

无。徽标仅用于呈现：它渲染 Session Controller 已经下发的 wire 数据，不向会话日志写入任何内容，不增加工具，也不改变提示词。

-----

<a id="已知限制与延后工作"></a>
## 已知限制与延后工作

- 徽标只显示 ID；重命名会话或加入工作区都不会改变它，因为 `SessionId` 设计上不可变。
- 非安全浏览器上下文回退到 `execCommand('copy')`；两条路径都被拒绝的宿主中 ID 仍可选中，但无法复制。
