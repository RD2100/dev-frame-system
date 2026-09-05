# P-sched 切片一设计笔记：goal 自动继续的事件门控

配套定位清单：[location.md](location.md)。范围：只改 goal 自动继续的触发面，不动子代理事件通知，不动 agent-loop。

## 1. 问题

`goal-round-driver` 在每次 agent 转入 idle 且 goal 为 active+armed 且有余量时，无条件预留并排队下一轮 `<goal_round>` 提示词（`drive()` 的预留分支）。总控场景中模型把工作委托给后台子代理后结束轮次，driver 立即烧掉下一轮：模型只能回答"等待事件"，随后再次 idle、再次烧轮——无事件/无就绪任务时每轮一个模型请求的空转。

## 2. 方案：eventPending 信号（ contained，全部在 driver 包内）

DriverState 增加进程内布尔 `eventPending`："自上一 admitted 轮以来是否有外部事件到达"。三处来源、一处消费、一处检查：

- **来源 A — 待处理输入插入**（`agent/inbox/inserted`，现有 listener）：非本轮预留的 message 进入 `nextTurn` 时置 true（覆盖用户消息、插件注入、子代理结算通知、schedule 到期投递；quiet 无唤醒的挂起输入也计入）。
- **来源 B — 激活边沿**（`goal/changed` listener）：变更后视图为 active+armed 时置 true（覆盖 create / edit / resume——保持三者现状即"变更后 idle 必排一轮"）。
- **来源 C — 外部轮次结算**（`agent/status` idle 沿）：刚结算的活动**不是**刚准入的 goal 轮（`attempt?.phase !== 'admitted'`）时置 true。覆盖无消息唤醒（tool-bash/tool-jobs 后台完成唤醒）、steer 唤醒轮、任何外来 turn。goal 轮自身结算（attempt 已 admitted）不置位——这是抑制空转的关键路径。
- **消费 — 轮准入**（`session/event` `user/message` 命中 `attempt.messageId`）：置 false。一个事件预算换一轮。
- **检查 — 预留裁决点**（`drive()`，位于 round-cap block 检查**之后**、渲染预留之前）：`!eventPending` → 直接 return。goal 保持 active+armed，无持久状态变化，无新请求；下一事件经"唤醒 → turn → idle 沿 → requestDrive"既有链条自动恢复。

### 挂起语义与 resume 复用

"挂起"不引入新状态：goal 停留在 armed，挂起只体现为 driver 本轮不预留（`eventPending=false`）。resume（人工授权）经来源 B 重新授予预算；任何外部事件经 A/C 重新授予。无需触碰 pause/resume 的持久 phase。

## 3. 可复用的既有原语（不新造）

| 原语 | 位置 | 用途 |
|---|---|---|
| armed/disarmed 激活（进程内） | `packages/goal/goal` `GoalService.disarm/resume` | 挂起期间授权保持，不闪断 |
| pause/resume（持久 phase） | 同上 | 仅人工/模型显式使用；门控不碰（自动 re-arm 会破坏"driver 从不自行复活"边界） |
| inbox 唤醒/挂起队列 | `packages/core/agent-loop` `send/followup/steer/inject`、latched wake | 事件到达 → turn → idle 沿的既有恢复链 |
| 子代理结算注入 | `packages/subagent/subagent` continuation manager（结算唤醒父代理、注入 notice） | 来源 A/C 的事件供给方 |
| 后台任务完成唤醒 | `packages/jobs/tool-jobs`（`completionDelivery: wakeup/quiet`）、`packages/shell/tool-bash` 后台任务 | 来源 C |
| 定时唤醒 | `packages/schedule/schedule` runtime（到期项以消息投递） | 来源 A |
| 串行 driver 合并 | `requestDrive` 的 `requested` 合并循环 | 门控检查点天然复用 |

## 4. 不变量核对（不可破坏项）

- **goal 状态机**：无新 phase、无新持久事件；`goal/change` 仍只在 `GoalService.commit` 发射。轮次准入走 projection fold（`fold.ts` `applyGoalEvent`），不发射 `goal/changed`——门控不会被准入自身 nullify（已核实）。
- **roundsStarted 计数**：推进点不变（仅 admitted goal-source `user/message`）；门控只减少预留次数，不改计数语义。
- **blocked / min-round 语义**：round-cap 的 `block('round-limit')` 在门控检查**之前**执行——到顶即阻塞，与事件无关，行为不变。`tool-goal` 的 `blockedAfterConsecutiveRounds` 与 authority 链不触碰。
- **竞态栅栏**：`validReservation` 双检、stale/competing/revision fence、checkpoint 失败 disarm、teardown fail-closed 全部保持；门控只在不预留时提前 return，不新增绕过路径。checkpoint（durability barrier）仍在门控之前执行，已结算轮的持久化不受挂起影响。
- **激活边界**：mount 时对既有 agent 一律 disarm、resume/fork 后不自行复活——不变。

## 5. 改动面与风险

改动面：`packages/goal/goal-round-driver/src/index.ts`（一个状态字段 + 四个 listener 各一行级改动 + 预留裁决点一处）+ README 行为描述 + 该包测试。无跨包接口变化，无 agent-loop / session 循环改动 → **contained**，可实现。

风险与语义后果（如实陈述）：

1. **无事件连续多轮被抑制是行为变更**：模型若以"多轮独立推进、轮间无外部事件"的方式使用 goal，现在会在轮间挂起等待。缓解：模型应在完成时 complete/pause/block，需要未来续跑时用 schedule 安排唤醒，或把工作交给后台子代理（其结算即事件）。README 同步更新。
2. **事件丢失即静默停滞**：门控信任"每个事件要么插入 inbox 要么打开 turn"。已核对现有事件源均满足；若未来出现既不插入也不唤醒的事件源，会挂起至下一事件。
3. **来源 C 的粒度是"非 goal 轮的任意 idle 沿"**：罕见的外来活动（如一次性维护后唤醒）也会授予一轮预算——与今日"任意 idle 即预留"相比只减不增，不构成回归。

## 6. 测试计划

- 重写两个"无事件连跑多轮"用例（`admits exact numbered rounds…`、`reserves the next round only after…`）：轮间插入一次用户消息事件。
- 新增：无事件挂起（断言不发起第二请求、goal 仍 armed）+ 事件到达后恢复（用户消息 → 下一轮）。
- 既有单轮/错误/disarm/teardown 用例应全部保持通过（create/resume/edit 边沿授予预算，行为不变）。
