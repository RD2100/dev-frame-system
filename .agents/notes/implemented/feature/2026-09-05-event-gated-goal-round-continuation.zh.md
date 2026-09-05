# Agent Note: Event-gated goal round continuation

Status: implemented

[English](2026-09-05-event-gated-goal-round-continuation.md) | 中文

## Problem

同会话 goal-round 驱动器此前无条件调度下一轮：持有 active 且已启用续行、仍有容量 goal 的 agent，每次 idle 沿都会预留并排队一条新的 `<goal_round>` 提示词。在编排型会话里，模型把工作委托给后台子代理后结束轮次、再无其他待办；驱动器立即烧掉下一轮，模型只能回答"正在等待事件"，循环往复——每次 idle 消耗一次完整模型请求，直到某次结算恰好落进来才可能有进展。浪费随上下文规模与委托深度放大。

## Decision

驱动器现在用事件预算 `eventPending` 门控每次预留。预算按 agent 生命周期记录在驱动器状态内（`packages/goal/goal-round-driver/src/index.ts`）：三处来源授予、一处消费、预留路径检查：

- 非 goal 消息插入 agent 的 `next-turn` inbox 队列时授予预算（待处理的用户输入、插件注入、子代理结算通知、定时投递——包括不唤醒 agent 的 quiet 消息）。
- 当前视图为 active 且 armed 的 `goal/changed` 边沿授予预算，保持 create/edit/resume 在下一次 idle 轮进的既有行为。
- 刚结算的活动**不是**已准入 goal 轮的 `agent/status` idle 沿授予预算，覆盖不携带 inbox 消息即打开 turn 的唤醒（后台任务完成、steered turn）。
- 预留的 Round 准入（其 goal 来源的 `user/message`）时消耗预算。
- `drive()` 的预留路径在无预算时于渲染提示词之前直接返回。该检查位于 Round 上限 block 之后，因此上限耗尽的 goal 仍立即记录 `round-limit` blocker，与事件无关。

挂起不产生任何持久状态：goal 保持 active 且 armed，下一事件经既有的唤醒 → turn → idle 沿 → `requestDrive` 链条自动恢复。仓库中所有事件源都满足授予契约（每次结算、完成唤醒或定时投递要么插入 inbox 消息、要么打开 turn）。

## Alternatives considered

- **等待期间 pause/resume 持久 goal phase。** 拒绝：pause 会把 `paused` phase 写入会话日志并停用激活；在事件上自动 re-arm 会破坏"驱动器绝不自行复活 goal"的成文边界——激活会因纯调度原因在 UI 与日志中来回翻转。
- **按 idle 周期性 disarm/re-arm 进程内激活。** 因同样的激活语义原因拒绝：`armed` 当前表示由人工或工具授权、持续到生命周期事件为止的续行边沿；按 idle 翻转会在侵蚀该语义的同时给每个观察该状态的消费者增加扰动。
- **在预留点查询活跃后台工作（运行中的子代理、任务、定时器）。** 本切片拒绝：需要新的跨包服务缝隙（子代理 continuation manager、`dsh-tool-jobs`、`dsh-schedule`），且仍覆盖不了"模型自己想要下一轮"的情形；事件预算不需要新缝隙，并涵盖同样情形——上述各表面的产出都作为事件送达。

## Consequences

门控针对的浪费消失：结算后无事件待办的 Round 不排队任何内容，多轮推进现在要求轮间存在事件。代价是刻意的：若模型持续在无待处理事件时结束轮次，goal 在输入、结算或唤醒到达前不会推进——预期模型在当轮内继续工作、把工作交给后台（其结算即事件）、安排定时唤醒，或在完成时 complete、pause 或 block 该 goal（README 已知限制一节已记载）。门控信任上述投递契约；未来若出现既不插入消息也不打开 turn 的事件源，会在下一事件前停滞。goal 状态机不变量未受影响：`roundsStarted` 仍只在 goal 轮准入时推进，blocker 代码与阻塞阈值保持与事件无关，竞态防护、持久性检查点与 fail-closed teardown 均未改变。

## Related

驱动器原有的竞态与生命周期理由：[same-session goal round driver](2026-07-19-same-session-goal-round-driver.zh.md)。
