# P-sched 切片一：goal 自动继续机制定位清单（最终）

状态：定位完成；切片一已实现并提交。设计笔记：[design.md](design.md)。

## 1. 核心实现：goal 自动继续（轮次驱动）

- 包：`packages/goal/goal-round-driver`（`@deepseek-ai/dsh-goal-round-driver`，plugin，inject: agents/goals/sessions；仓库内唯一依赖方 `packages/bundle/base`）
- 入口：`src/index.ts` `apply(ctx)` — 安装自动同会话续跑与竞态栅栏
- 关键函数与职责：
  - `apply()` — 注册全部事件监听（触发面）与 teardown
  - `requestDrive(state)` — 触发合并：置 `requested`，经 `ctx.agents.withoutInitiator` 串行 driver 循环（谁在循环：这里）
  - `drive(state)` — 【决定发起下一模型请求的裁决点】：durability checkpoint → 清理上一 attempt → 读 goal（无 goal / 非 active / 非 armed 即返回）→ round-cap 检查（到顶即 `block('round-limit')`）→ 【切片一新增：`eventPending` 门控，无事件即 return】→ 预留 `roundsStarted+1` → `renderGoalRoundPrompt` → `agent.followup(...)`
  - `ctx.on('agent/status')` idle 沿 — 主触发：每次转 idle 即 `requestDrive`；含 cancelled attempt 的 pause 路径
  - `ctx.on('goal/changed')` — goal 变更触发（checkpoint 义务）
  - `ctx.on('agent/inbox/inserted' | 'claimed' | 'discarded')` — 竞争输入/attempt 生命周期跟踪
  - `ctx.on('agent/pre-step')` + `validReservation()` — 准入栅栏（claim 前后双检 revision/armed/round 连续性）
  - `ctx.on('session/event')` — `user/message` 命中 attempt → admitted；`turn/end` max-tokens/aborted → disarm/cancel
  - `disarm()` / pause 路径 — 错误、取消、teardown 时收回自动续跑授权
- 提示词与不变量：`src/prompt.ts`（保留的 `<goal_round>` 块）、`src/invariant.ts`（goal 轮消息必须逐字匹配包自有提示词）

## 2. 触发链（切片一之前 → 之后）

- 之前：任意 idle 沿 → `agent/status` → `requestDrive` → `drive` → goal active+armed 且有余量 → 无条件 `agent.followup(goal round prompt)` → inbox → pre-step 准入 → 新模型请求。空转缺口即在预留分支。
- 之后：同样链条，但预留前增加事件预算检查；无事件 → 挂起（goal 保持 armed，不发请求）。
- 事件预算来源：非 goal 消息进入 nextTurn；active+armed 的 goal/changed 边沿（create/edit/resume）；结算了非 goal 轮的 idle 沿。消费点：round 准入。

## 3. 相关包与不变量（已核实）

- `packages/goal/goal` — goal 状态机：phase（active/paused/blocked/complete，持久）与 activation（armed/disarmed，进程内）；`goal/changed` 仅由 `GoalService.commit` 发射（create/edit/pause/resume/complete/block/receipt/clear），`disarm()` 纯进程内不发射。
- `roundsStarted` 推进点：`fold.ts` `applyGoalEvent` — 仅 admitted 的 goal-source `user/message`（source.round === roundsStarted+1）推进；**不**发射 `goal/changed`（门控不会被准入自身 nullify）。
- `packages/goal/tool-goal` — 模型工具面与 authority（`blockedAfterConsecutiveRounds` min-round 语义、direct-human/goal-round 二元 authority）；切片一未触碰。
- blocked 语义：`block('round-limit')` 在事件门控检查之前执行，到顶即阻塞，与事件无关。
- 竞态栅栏/checkpoint/teardown fail-closed：全部保持原样。

## 4. 可复用等待/挂起原语（门控实际依赖）

- goal 激活 armed/disarmed（进程内）+ pause/resume（持久，人工/模型显式）— `packages/goal/goal`
- inbox 唤醒与挂起队列（send/followup/steer/inject、latched wake、maintenance）— `packages/core/agent-loop`
- 子代理结算注入与唤醒 — `packages/subagent/subagent`（continuation manager）
- 后台任务完成唤醒（`completionDelivery: wakeup/quiet`）— `packages/jobs/tool-jobs`；`packages/shell/tool-bash` 后台任务
- 定时唤醒投递 — `packages/schedule/schedule`
- 串行 driver 合并循环 — `requestDrive`

## 5. 测试与验收面

- `packages/goal/goal-round-driver/tests/goal-round-driver.spec.ts` — 58 用例全通过（含切片一：重写 2 个无事件连跑用例 + 新增 3 个门控用例：挂起、输入事件恢复、外部轮次恢复）
- `packages/goal/goal-round-driver/tests/invariant.spec.ts` — prompt 不变量，未改动，通过
- `tsc -b packages/goal/goal-round-driver` — 通过
- README 双语 + Agent Note（en/zh/.i18n.yaml）已随行为同步
