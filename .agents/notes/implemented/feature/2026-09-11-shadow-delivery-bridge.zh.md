# Agent Note：Shadow 投递桥把已接收工作转发进存活控制器

Status: implemented

[English](2026-09-11-shadow-delivery-bridge.md) | 中文

## Problem

Shadow 路由器把跨根投递持久化为持久的行与回执，但它自身的契约止步于 `received`：裸挂载让每个 controller 的输入对模型不可见，因为把收到的输入写入 controller 会话日志是宿主职责（[路由器决策](../architecture/2026-09-05-shadow-router-project-tools-binding-store.zh.md)点名了这一缺口）。没有转发者，[详细设计承诺的闭环](../../../../docs/detailDesign-part2.zh.md#delivery)——Goal 与验收绑定匹配某次授权 open run 的 `work` 消息会在绑定的 controller 上调度一次 follow-up——永远不会运行，送达的输入堆积成模型永远看不到的 `received` 行。

## Decision

`packages/experimental/shadow-bridge` 是一个宿主侧 function plugin，按必填的 `intervalMs` 节奏轮询 router 的公开读面（`listDeliveries`/`findBinding`），把每一条通过设计自身门禁的 `received` `work` 投递转发出去：绑定不是 `stopping` 或 `stopped`，绑定仍记录着授权 open run，且投递的 Goal 与验收关联等于该 run——因此收到投递之后发生 Goal 切换，上一个 Goal 的消息不会进入 controller 的当前 Goal。转发是绑定 controller 会话解析到的 live agent 上的一次 durable follow-up（`agent.followup`），携带确定性头部（来源投递 id 加 workspace）与受 `followupMaxChars` 约束的逐字投递原文；内容经由 inbox 以 `user/message` 事件进入 controller 会话日志，保持"模型可见必已记录"不变量。messageId 随后记录进本包自己的 `shadow_bridge` 存储域，启动时重建进转发器的内存集合，因此重启不会重复转发。v1 只解析存活 agent，从不确定 `completed`——完成保持 controller 侧事实，为 controller agent 建立存活状态由宿主组合负责（[包 README](../../../../packages/experimental/shadow-bridge/README.zh.md)）。

## Alternatives considered

**用 router 或域事件做事件驱动转发。** 本轮否决：router 的公开读面没有转发钩子，事件意味着在桥不得修改的包里新增 router 侧契约；轮询稳定的读面在不引入新耦合的前提下容忍挂载顺序与重启，代价是至多一个 `intervalMs` 的延迟。

**先标记后发送，追求至多一次。** 否决：标记写入与 follow-up 之间的崩溃会让投递被标记、未转发、悄悄丢失；先发送后标记在同一崩溃窗口接受一条可见重复（相同头部、相同 messageId），这与设计"去重覆盖持久 inbox 输入，绝不覆盖静默"的规则一致。

**让桥创建或恢复缺失的 controller agent。** v1 否决：agent 生命周期归宿主所有，且两个注册表入口都无法收养 router 已创建并持有在会话存储中的 controller 会话，冷恢复需要超出本轮的新生命周期机制；controller 不存活的投递只是等待之后的轮询。

**转发后把投递结算为 `completed`。** 否决：`completed` 是已完成工作的 controller 侧持久事实，转发回执会声称尚未运行的工作已经运行。

## Consequences

送达的 `work` 终于到达模型：绑定的 controller 以 Shadow 输入驱动 turn，router 留下的环在 follow-up 接缝处闭合。代价：转发延迟受轮询节奏而非即时性约束；上述崩溃窗口可能重复一条投递；`note` 投递要等后续轮次；每个部署都必须自行把 controller agent 拉到存活状态，因为桥从不这样做。
