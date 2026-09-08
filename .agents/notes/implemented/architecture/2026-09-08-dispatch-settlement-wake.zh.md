# Agent Note: 派发结算通知唤醒父会话

Status: implemented

[English](2026-09-08-dispatch-settlement-wake.md) | 中文

## 问题

`agent_dispatch` 复用既有 child 时从不投递新指令；被派发的 child 完成一轮真实回合后也从不告知父会话：没有其他待决事件的 lead 控制器在 worker 交付后继续沉睡，多任务链卡在评审阶段。复用 child 还会静默地什么都不重派，调用方无法让已结算的 child 继续工作。

## 决策

派发服务在每个存活的已派发 child 上挂载结算监听，冷恢复的 child 也一样。当 child 自身日志记录到终态的 `turn/end`——completed、error 或 aborted 皆可：监听有意不过滤原因，因为以失败收场的回合也必须唤醒链条——且该记录持久刷写成功后，监听以父会话下一普通回合（`followup()`）的形式向父会话投递类型化的 `dispatch-settled` 通知：空闲父会话立即开启回合，忙碌父会话在在途回合结束后立刻认领。不使用 steer——steer 的消息瞄准回合可能永远到不了的步骤边界，通知会因此搁浅。

去重分层。每个存活 child 一份同步获取的声明集合阻止并发监听重复投递；它以确切 Agent 实例为键，独立 Context 复用同一 session id 时各持各的声明。父会话的持久事实——已落日志的通知，或仍停在其 inbox 的排队通知——阻止重挂载后的重复投递。被扣留的投递释放声明，在下一个 idle 边缘重试。

`followup: true` 派发参数配合 prompt，现在把明确的续作指令投给该任务既有 child，并拒绝盲目的 followup；不带 prompt 的 followup 同样拒绝而非静默降级；全新派发绝不排队 followup，不带该字段的复用行为与从前完全一致。不带 prompt 的恢复保持无副作用。

## 已考虑的替代方案

- 父会话轮询 child 日志把父耦合到子代持久化，并在每个回合边界成倍增加日志读取。
- 进程内字符串键（如 `childId|turnIdentity`）跨宿主泄漏：独立 Context 复用 session id 与日志序号，一个 Context 的声明会吞掉另一个的通知。
- 在服务内存里记录「已通知」在重启后丢失账目；父会话的持久账本才是唯一重启安全的权威。

## 后果

父会话在真实 child 结算时自行醒来，无需任何脚本化再提示；调用方也能显式续作已结算的 child。每次结算都会开启父会话一个回合，请求预算必须覆盖唤醒驱动的请求。通知投递失败只记日志并放弃：child 绝不会为重试通知而被扣留，child 自身日志无论如何都是持久记录。

[手工编写的 SDK 场景](../../../../snapshots/sdk/dispatch-settlement-followup/snapshot.yml) 使用脚本化模型响应运行真实的派发、层级、工作树注册表和持久化服务。它将两次 child 结算与父会话通知的身份对应核验，并向同一个 child 投递一次明确请求的 followup。完整提示词序列均被固定，包括父会话变化后的请求头和 child 自己的提示词。这些无需密钥的证据不证明真实模型任务验收通过。
