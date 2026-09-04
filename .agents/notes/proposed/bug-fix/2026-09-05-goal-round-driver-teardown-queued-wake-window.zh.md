# Agent Note: Goal-round-driver teardown discards the not-yet-admitted queued round

Status: proposed

[English](2026-09-05-goal-round-driver-teardown-queued-wake-window.md) | 中文

## Problem

goal-round 预留可能停在 agent inbox 中而 `agent.status` 仍报告 `idle`。`Agent.followup()` 在 agent 无法开启 turn 时会先插入消息并扣住（latch）唤醒——当前即 host 发起的 `runMaintenance()` 任务。已入队的 round 一直保持 pending，直到 maintenance 结束后，被扣住的唤醒才把它重放进一个 turn。

driver 的 teardown 只在 agent 报告 `running` 时才发出 `cancel({ kind: 'parent' })`。观察到 maintenance 窗口的卸载两个停止分支都不会走：预留留在队列中，driver 的 `agent/pre-step` 有效性栅栏随监听器一并移除，被扣住的唤醒在插件卸载之后重放——goal round 的模型请求在完全没有任何预留检查的情况下运行。durable goal 保持 disarmed，但该 round 在重放折叠中消耗了它的轮次编号，并且无栅栏地到达了模型。

## Proposal

在 driver 的 teardown 中，当预留存在且 agent 未在运行时，改用 `Agent.inbox.remove(attempt.messageId)` 从 inbox 中恰好移除该预留 round 的消息，而不是让它留在队列里。只移除 round 自己的消息，因此无关的 pending 输入保持其队列位置，被扣住的唤醒之后只重放进该输入；消息已消失的唤醒会打开一个无模型调用的空 turn 边界。移除失败（该丢弃会追加持久化 splice）只记录日志，不使整个 teardown 失败，与现有 `disarm()` 的容灾方式一致。

running 分支保持现状：以 `parent` cause 取消并等待 `whenIdle()`。

## Alternatives considered

**在 idle 分支同样等待 `whenIdle()`。** 否决：idle 读数可能在 host 自己的 maintenance 任务运行期间保持，等待它会把插件卸载时间拉长到该任务的时长。被丢弃的 round 不会留下属于 driver 的工作：唤醒只重放进剩余输入，或打开一个不花费模型调用的空边界。

**无论 phase 一律不带 `keepInbox` 取消。** 否决：`cancel()` 清空整个 inbox，会丢弃恰好处于 pending 的无关人类或插件输入；缺陷只涉及 driver 自己的预留。

**让 disposal 等到被扣住的唤醒重放后再取消。** 否决：这会让插件的监听器跨越一个时长无界的 maintenance 任务继续安装，而且 round 仍是被取消而非被持久化撤回；移除预留会立即释放唤醒。

**把该窗口当作不可达并维持现状。** 否决：maintenance 是 driver 无法控制的 host 持有 phase，而恰在重放的 round 运行时 pre-step 栅栏已经消失，失败是静默的。

## Acceptance criteria

- 在预留因被扣住的唤醒而留在队列中时进行 disposal，产生一条持久化的 canceled inbox splice、无模型请求、无已准入的 goal-round `user/message`，且在 agent 达到 quiescence 后观察 goal 保持 active 且 disarmed。
- 同一场景中存在无关的非唤醒 pending 输入（对 next-step 的 `inject()`）时，模型仍只收到该输入；goal-round 提示永不进入请求，且该输入不因 teardown 被丢弃。
- 现有 teardown 测试（running round 被取消并等待；已入队 round 被观察）保持通过。

## Risks

- 该丢弃会在 teardown 期间追加一条持久化 inbox splice；此处的持久化失败被容纳为一条警告并使 round 留在队列中，与修复前该失败模式的行为一致。
- 已被 claim 或 admit 的预留不受影响：`remove()` 找不到 pending 消息并返回 false，running 分支继续取消并等待。
- host 通过 idle agent 上的 `keepInbox` 取消刻意保留的已入队输入，在 host 之后唤醒 agent 时仍可能在卸载后运行；撤回 driver 预留无法覆盖 host 选择保留的输入，也没有 driver 栅栏可以复查它。
