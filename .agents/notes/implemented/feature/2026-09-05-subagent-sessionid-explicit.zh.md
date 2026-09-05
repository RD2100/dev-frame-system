# Agent Note: 委派工具面上显式化 SessionID

Status: implemented

[English](2026-09-05-subagent-sessionid-explicit.md) | 中文

## 问题

可继续 subagent 的持久身份就是它的会话：continuation manager 把每个 `childId` 品牌化为 `SessionId`，会话 header 携带 `parentSession`/`origin`/`delegationDepth`，面向模型的工具返回的也是同一个值。但面上把它标注为 agent id：`subagent` 结果字段叫 `subagentId`，`list_agents` 行叫 `id`，`send_message`/`interrupt_agent` 写的是 "agent id"。模型与用户面上没有任何地方把这个值称为 SessionID，于是不允许伪造会话标识的编排消费者即使拿到了真实值，也只能把子 Agent 身份记录为 unavailable。

## 决策

面向模型的委派面把持久会话身份命名为 `sessionId`，并在渲染文本中标注 SessionID：

- continuable `subagent` 结果字段为 `sessionId`（渲染为 `started continuable subagent; SessionID …`）；
- `list_agents` 条目携带 `sessionId`（渲染为 `SessionID=…`），服务层 `SubagentListEntry.id` 保持不变；
- `send_message` 与 `interrupt_agent` 把自己的 `agent_id` 参数描述为 SessionID。

一次性前台结果保留 `runId`：一次性 child 不可继续，其结算句柄是 run 身份而非会话地址；一次性后台 child 同理保留 job id。

## 已考虑的替代方案

- 保留 `subagentId` 并在文档中说明它就是会话 id。拒绝：标签歧义正是缺陷本身；把 "agent id" 值复制进 SessionID 列而没有类型诚实的字段，只会重现身份不可得的空洞。
- 为工具引入独立的 agent 身份命名空间。拒绝：工具值本来就是会话 id；第二套身份体系会成倍增加路由键，与 subagent 服务的单一持久身份设计冲突。

## 后果

模型与用户面现在把持久子身份称为 SessionID，编排消费者因此无需第二套身份命名空间即可记录并路由子会话。服务层 `ContinuableStart.childId` 与 `SubagentListEntry.id` 保持原名，`send_message`/`interrupt_agent` 保留 `agent_id` 参数名但将其描述为 SessionID。已录制会话快照夹具仍期望更名前的字段与描述文本，在其录制输出刷新之前 `test:snapshot`/`test:web` 在该差异上保持红。

## 验证

`pnpm exec vitest run packages/subagent`（769 测试）覆盖更名后的字段、渲染文本与 send_message/interrupt_agent 描述；`pnpm run verify-tool-catalog` 从源重新生成工具目录；`pnpm run verify-translation-pairing` 保持双语目录与本 Note 配对一致。已录制会话快照套件仍为 CI 信号，本次工具描述变更在其覆盖范围内。
