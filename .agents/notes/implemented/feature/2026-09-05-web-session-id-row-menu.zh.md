# Agent Note: Web 会话 ID 行菜单

Status: implemented

[English](2026-09-05-web-session-id-row-menu.md) | 中文

## 问题

2026-09-04 的头部徽章（[已归档](../../archived/feature/2026-09-04-web-session-id-badge.md)）让 `SessionId` 可见，但它以常驻芯片的形式渲染在会话头右上角的工具区。展示要求已变更：ID 不得占用右上角常驻位置；它应放入左侧会话列表中每个会话行已有的操作菜单，按需展开并给出明确的复制流程。

## 决策

展示归 [`dsh-client-ui-workspace`](../../../../packages/client/ui-workspace/README.zh.md) 所有。`SessionNodeItem` 的操作菜单在重命名/分叉/归档之后新增第四项"会话 ID"。选中后打开 `SessionIdDialog`（`src/client/rows/SessionIdDialog.tsx`），一个 `Modal` 原样渲染该行的 `SessionId`——不截断，配合 `word-break` 与 `user-select`，每个字符都可见、可选择。ID 文本本身（渲染为按钮）与明确的复制按钮都通过共享的 `writeClipboard` 助手写入完整值。一行 `role="status"` 报告结果：成功显示本地化的"已复制"；宿主拒绝写入时显示明确的失败文案，绝不伪装成功。复制按钮带 `autoFocus`；对话框通过自身外壳关闭（Escape、遮罩、关闭按钮）。

对话框状态为行内局部（每个 `SessionNodeItem` 自己的 `showId`），每行打开的是绑定自己 ID 的对话框；值读取自实时会话作用域而非缓存历史，因此刷新、切换会话、重启与冷恢复显示的都是该会话持久化时的同一 ID。

`@deepseek-ai/dsh-client-ui-session-id` 整体移除：`cordis.patch.yml` 插件行、`dsh-web-app` 依赖、`tsconfig.base.json` paths 条目、`tsconfig.client.json` reference、模块图目录与 lockfile 全部去掉该包，目录随之删除。全程不铸造、不变换、不复制任何身份：对话框渲染的正是 API 创建、JSONL `SessionHeader` 持久化的同一个 branded `SessionId`。没有 RPC、没有 store、没有会话日志事件，模型可见面由构造保持不变。

### 前身：2026-09-04 头部徽章（已归档）

[已归档的徽章笔记](../../archived/feature/2026-09-04-web-session-id-badge.md) 记录了本决策继承的动机：`SessionId` 此前贯穿全栈——在 `dsh-session` 中 branded、在 `SessionHeader` 中持久化、由每个 Session Controller、SDK 与 ACP wire 帧携带——但 GUI 最初完全没有展示，徽章用一个 `conversation.session.header.utilities` 芯片解决了这一点。徽章的复制语义（完整值、尽力写入、写入未被接受绝不声称成功）原样延续到对话框中。不再成立的是摆放决策：常驻芯片与"ID 不占用右上角常驻空间"的要求冲突。

完整移除之外的其他方案已被考虑并否决：两个表面同时保留会把一个值渲染两次，且被否决的常驻芯片仍然存在；把芯片移入行悬停卡只有悬停发现、没有键盘路径；设置页字段只有已经知道去哪找的人才找得到。放弃的能力是零操作即可见的 ID；只有当需求再次要求 ID 常驻可见时才重新引入常驻芯片——`conversation.session.header.utilities` 这个位置仍在。

## 已考虑的替代方案

**由浏览器根持有、像重命名那样的会话列表级对话框。** 重命名需要跨列表重渲染存活的文本草稿，所以它放在浏览器根。ID 对话框无状态——唯一输入就是该行的 ID——行内局部状态避免了向两个列表主体穿透回调，且不损失任何东西。

**把 ID 渲染进悬停卡。** 一次悬停停留才能触达复制操作，没有到达该值的键盘路径，且卡片的内容集合是固定的；操作菜单才是该行已有的键盘可达动词面。

**复用被移除的包、换一个槽位注册。** 该包存在的意义就是在一个头部槽位渲染一枚芯片；在另一个包的行组件内部新增菜单项跨越了这条缝，槽位机制将只为单组件的包服务。`ui-workspace` 已拥有行菜单与行动词的 locale 键。

## 测试

`tests/session-id-dialog.client.spec.tsx` 钉住：菜单项出现且不打开会话；对话框原样显示完整 ID；ID 文本与明确按钮两条路径都能复制；写入被拒时报告失败文案且绝不出现成功文案；两行显示互不相关的 ID、与选中无关；新字典键在两个语言中都存在。徽章包的测试随其目录一并移除。Web 回放快照不再包含该芯片。`verify-client-ui-i18n` 负责新键的 locale 归属规则。

## 后果

**找到 ID 现在需要两次激活**（行菜单，再对话框），这是移除常驻芯片的接受成本。会话列表重排导致某行卸载时，其打开的对话框一并关闭——与行菜单已有的生命周期一致。

**复制仍是尽力而为。** 同时拒绝异步 Clipboard API 与 `execCommand('copy')` 的宿主会让 ID 保持可选但无法复制，状态行明确陈述失败而不是声称成功。
