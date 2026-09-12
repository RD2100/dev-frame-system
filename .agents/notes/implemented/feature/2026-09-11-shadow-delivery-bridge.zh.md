# Agent Note：Shadow 投递桥把已接收工作转发进存活控制器

Status: implemented

[English](2026-09-11-shadow-delivery-bridge.md) | 中文

## Problem

Shadow 路由器把跨根投递持久化为持久的行与回执，但它自身的契约止步于 `received`：裸挂载让每个 controller 的输入对模型不可见，因为把收到的输入写入 controller 会话日志是宿主职责（[路由器决策](../architecture/2026-09-05-shadow-router-project-tools-binding-store.zh.md)点名了这一缺口）。没有转发者，[详细设计承诺的闭环](../../../../docs/detailDesign-part2.zh.md#delivery)——Goal 与验收绑定匹配某次授权 open run 的 `work` 消息会在绑定的 controller 上调度一次 follow-up——永远不会运行，送达的输入堆积成模型永远看不到的 `received` 行。

## Decision

`packages/experimental/shadow-bridge` 是一个宿主侧 function plugin，从 router 只观察的 `shadow/delivery-received` 事件转发——这是 routing Service Definition 对 `queued` → `received` 唯一转换的信号（[routing 接缝决策](../architecture/2026-09-12-shadow-routing-seam.zh.md)）——并在每个转发单元里重读 router 的公开读面（`listDeliveries`/`findBinding`）。挂载时与 loader 结束后各一次全量对账轮询，加上低频安全网定时器（`intervalMs`），覆盖在监听器窗口之外进入 `received` 的投递。每个单元都通过设计自身的门禁：绑定不是 `stopping` 或 `stopped`，绑定仍记录着授权 open run，且投递的 Goal 与验收关联等于该 run——因此收到投递之后发生 Goal 切换，上一个 Goal 的消息不会进入 controller 的当前 Goal。所有单元——事件驱动或轮询驱动——都在同一条串行化链上、任何继承的 agent-initiator 边界之外运行。转发是绑定 controller 会话解析到的 live agent 上的一次 durable follow-up（`agent.followup`），携带确定性头部（来源投递 id 加 workspace）与受 `followupMaxChars` 约束的逐字投递原文；内容经由 inbox 以 `user/message` 事件进入 controller 会话日志，保持"模型可见必已记录"不变量。messageId 随后记录进本包自己的 `shadow_bridge` 存储域，启动时重建进转发器的内存集合，因此重启不会重复转发。v1 只解析存活 agent，从不确定 `completed`——完成保持 controller 侧事实，为 controller agent 建立存活状态由宿主组合负责（[包 README](../../../../packages/experimental/shadow-bridge/README.zh.md)）。

## Alternatives considered

**只靠事件转发、去掉轮询。** 否决：晚于转换挂载的监听器——桥在 router 恢复 queued 行之后才挂载的启动、或监听器尚未注册的重启——永远看不到那次转换；对账轮询与安全网才是让恰好一次转发在挂载顺序与重启之下成立的部分。安全网节奏保持必填、无默认：合适的节奏因部署而异——事件承载实时转换，节奏只为"错过的工作至多等多久"定价。

**先标记后发送，追求至多一次。** 否决：标记写入与 follow-up 之间的崩溃会让投递被标记、未转发、悄悄丢失；先发送后标记在同一崩溃窗口接受一条可见重复（相同头部、相同 messageId），这与设计"去重覆盖持久 inbox 输入，绝不覆盖静默"的规则一致。

**让桥创建或恢复缺失的 controller agent。** v1 否决：agent 生命周期归宿主所有，且两个注册表入口都无法收养 router 已创建并持有在会话存储中的 controller 会话，冷恢复需要超出本轮的新生命周期机制；controller 不存活的投递只是等待之后的单元。

**转发后把投递结算为 `completed`。** 否决：`completed` 是已完成工作的 controller 侧持久事实，转发回执会声称尚未运行的工作已经运行。

## Consequences

送达的 `work` 终于到达模型：绑定的 controller 以 Shadow 输入驱动 turn，router 留下的环在 follow-up 接缝处闭合。实时转换经由事件转发。代价：事件路径错过的工作要等一次对账轮询或安全网；上述崩溃窗口可能重复一条投递；`note` 投递要等后续轮次；每个部署都必须自行把 controller agent 拉到存活状态，因为桥从不这样做。
