# Agent Note: 从行操作菜单直接复制 Session ID

Status: implemented

[English](2026-09-05-web-session-id-direct-copy.md) | 中文

## 问题

行操作菜单需要服务于只需要持久 Session ID 的调用者，而不能为此创建第二个导航表面。对话框增加一次操作，并让复制这个唯一目标依赖临时界面的打开。

行菜单的位置与身份归属仍由[行菜单 Note](2026-09-05-web-session-id-row-menu.zh.md)定义；本 Note 负责复制交互。

## 决策

`dsh-client-ui-workspace` 保留每条 Session 行已有操作菜单中的 Session ID 操作，并通过共享的 `writeClipboard` 助手直接复制该行的 branded `SessionId`。普通会话行和 Agent 树中的每一行使用同一套直接复制行为。

选中该操作后菜单关闭，不打开对话框。短暂 Toast 报告宿主接受写入或明确报告失败；写入被拒时绝不显示成功消息。每行同一时间只允许一个剪贴板请求；行卸载后到达的异步结果会被忽略。

`SessionIdDialog` 及其样式表已移除。描述对话框的 locale 条目已移除；菜单、成功与失败文案仍由 `ui-workspace` 所有。

不会铸造、变换或复制身份。复制的值就是 API 创建并持久化在会话 header 中的同一个 `SessionId`。

## 已考虑的替代方案

**保留对话框复制流程。** 拒绝：它增加一次操作，并为只需写入剪贴板的动作创建临时界面。

**静默复制，不报告结果。** 拒绝：宿主可能同时拒绝两种剪贴板路径，因此用户需要看到写入成功与尝试失败的区别。

**在每条行标题旁增加独立复制按钮。** 拒绝：它占用常驻行空间，并重复已经由行操作菜单所有的动词。

## 后果

常用路径变为一次菜单操作，会话列表保持在原位置。成功或失败通过短暂 Toast 呈现，而不是对话框。复制仍是尽力而为，因为浏览器权限与宿主剪贴板支持不由插件控制。

## 验证

`pnpm exec vitest run packages/client/ui-workspace/tests/session-id-copy.client.spec.tsx packages/client/ui-workspace/tests/agent-tree-rows.client.spec.tsx` 覆盖两种行类型的直接复制、不导航、不打开对话框、成功反馈与写入被拒。浏览器验证前使用 `pnpm --filter @deepseek-ai/dsh-client-ui-workspace bundle` 重新构建生成的客户端 bundle。
