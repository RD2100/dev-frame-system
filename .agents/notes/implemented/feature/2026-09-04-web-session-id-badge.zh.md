# Agent Note：Web 会话 ID 徽标

Status: implemented

[English](2026-09-04-web-session-id-badge.md) | 中文

## 问题

`SessionId` 在整条链路上都是完备的——在 [`dsh-session`](../../../../packages/core/session/README.md) 中 branded，随 `SessionHeader` 持久化，由每个 Session Controller、SDK 和 ACP wire 帧携带，并且就是浏览器自己的会话作用域键——但 Web GUI 从未把它显示给人。头部只渲染显示标题，因此报告 bug、对照 JSONL 日志或通过 SDK 寻址会话的用户，没有任何产品内途径知道自己看到的是哪个会话。

## 决策

[`@deepseek-ai/dsh-client-ui-session-id`](../../../../packages/client/ui-session-id/README.zh.md) 向 [`dsh-client-ui-conversation`](../../../../packages/client/ui-conversation/README.zh.md) 已声明的 `conversation.session.header.utilities` 列表注册一个 `session-id-badge` 条目（order `-10`，位于下载动作之前）。芯片以等宽字体逐字渲染标准会话作用域的 `sessionId` prop，视觉上截断过长 ID，并通过共享的 `writeClipboard` 助手复制完整值，附带一秒成功状态。没有会话 ID（空白会话 Hero）时不渲染任何内容。

本次改动在任何位置都不铸造、不变换、不复制身份。徽标显示的 ID 与 API 创建、header 持久化、wire 下发的是同一个值；本包不增加 RPC、store 或会话日志事件，因此模型可见面在构造上保持不变。

单功能包形态遵循姊妹头部动作（[`ui-jobs`](../../../../packages/client/ui-jobs/README.zh.md)、会话日志下载条目）：自有 locale 命名空间（`session-id`，zh 为事实源）、惰性 node half，以及 `dsh-web-app` 中的一行 `dsh.client` manifest。

## 已考虑的替代方案

**在每个侧边栏会话行显示 ID。** 列表是标题树；每行都放 ID 在树的密度下是噪音，而且用户进入对话后它仍然消失。从打开会话的头部复制已经覆盖真实需求。

**占用 `header.lineage` 单席位或直接扩展 `ConversationSessionHeader`。** 两者都把会话核心渲染与一个呈现功能耦合，会迫使 `ui-conversation` 增长一个它并不拥有的 locale 命名空间。工具区列表的存在正是为了这种右对齐的每会话信息。

**设置页字段。** 只有已经知道去哪里找的人才能发现；这个值属于正在查看会话的那个表面。

## 测试

browser-plugin spec 针对真实 `SlotRegistry` 注册（fiber 拆除证明 HMR 安全移除）并钉住字典；组件 spec 钉住逐字 ID 渲染、完整值复制、一秒反馈窗口、写入被拒时的无操作，以及无 ID 时的 null 渲染。`verify-client-ui-i18n` 拥有 locale 路由规则。

## 后果

**头部增加一个常驻元素。** 从不需要 ID 的会话也会渲染这枚芯片；截断与安静样式是被接受的成本。若实践中读作噪音，隐藏到既有详情入口之后只是呈现层改动。

**复制是尽力而为。** 同时拒绝异步 Clipboard API 与 `execCommand('copy')` 的宿主中，ID 仍可选中但无法复制，且 UI 不得谎报成功——反馈状态只在写入被接受后出现。

**Fork 与 resume 的身份自证。** fork 出的子会话显示自己的 ID，resume 的会话显示其持久化时的同一 ID，因为徽标读取的是活跃作用域而非缓存历史。
