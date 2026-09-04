# Agent Note: Goal completion receipts with evidence

Status: proposed

[English](2026-09-05-goal-completion-receipt.md) | 中文

## Problem

完成声明目前止步于 `complete` phase 变更：持久的 `goal/change` 日志只记录了"调用方将 goal 标记为完成"，却没有记录结果是被什么验证的。审计已完成 goal 的消费方——DevFrame 控制器绑定，以及 [goal 包 README](../../../../packages/goal/goal/README.zh.md#known-limitations-and-deferred-work) 中推迟的评估器认证策略——无法区分"有证据的完成"与"裸完成"。仓库级规则"模型可见 ⟺ 已记录"在这里同样成立：后续 goal round 需要推理的完成证据没有可供重建的持久记录。

## Proposal

完成回执作为既有 `goal/change` 载荷 union 的第三个成员（`GoalReceiptChangeMeta`，`operation: 'receipt'`）记录，而不是新增会话事件类型。回执以 compare-and-set 身份指明其确认的确切 goal revision，并携带非空的 evidence 数组；每条为 `{ kind, summary, at, ref? }`：

- `kind`——证据的稳定 lower-kebab-case 分类（`test-run`、`command`、`log`……），沿用 `GoalBlockReason.code` 模式，使集合可以在不改变格式的情况下扩展。
- `summary`——非空、已 trim 的单行结果摘要，面向人类与模型。
- `at`——证据捕获时间的 epoch 毫秒；由调用方提供并校验，不做默认。
- `ref`——可选的完整记录的持久位置（测试文件、日志路径或会话事件引用）。验证命令本身就是一条证据（或 summary 的一部分），不是专门字段；最小形状保持每条证据一个 kind。

`GoalService.recordReceipt(agent, ref, evidence)` 用当前 goal 校验 `ref`（否则 `GOAL_STALE_REVISION` / `GOAL_NOT_FOUND`），并要求当前 phase 为 `complete`（否则 `GOAL_INVALID_TRANSITION`）。回执是对该 revision 的标注，不推进 revision：完成方持有的 ref 保持有效，回执也不是生命周期变更。同一 revision 允许多条回执；日志是追加式回执流，去重是消费方的关注点。

严格折叠只在回执引用当前 goal 的确切 revision、该 goal 为 `complete`、且 `recordedAt` 不早于该 goal 的 `updatedAt` 时接受；回执不改变任何折叠状态，因此 `lastRef`、`updatedAt` 与检查点中的投影状态均不变，`goal` 投影的 `stateVersion` 仍为 6。空 evidence 数组被拒绝（`GOAL_INVALID_EVIDENCE`）：没有证据的回执与它所跟随的裸 `complete` 事件无法区分，会让完成声明在没有任何已记录验证的情况下通过。

### 格式与兼容

不 bump `SESSION_FORMAT_VERSION`。版本机制只对结构性变更 bump——header 形状、事件信封、核心事件语义、surface 机制——而普通的词汇增长从不 bump；本变更扩展的是一个既有插件自有事件类型的载荷词汇。在回执变体之前构建的读取方会响亮失败而非误读：严格 goal 解码器拒绝未知 operation，投影将一次重放失败留存并给出诊断，与未知必需事件产生的受控拒绝一致。`GOAL_CHANGE_VERSION` 保持 1，因为所有 version-1 快照与 tombstone 形状均未变，回执是在同一解码器内的追加。`recordReceipt` 本切片仅为服务方法（`block` 先例）：无 `@Remote` 导出、无 wire 目录变更，远程暴露推迟到出现远程消费方。

### 模型可见 ⟺ 已记录

回执以 `goal/change` 事件进入日志，因此未来任何向模型呈现它的组件都可以从日志重建。本切片不新增模型可见输入：不改工具、提示词或续行上下文。

## Alternatives considered

**新增 `goal/receipt` 会话事件类型。** 否决：它增加一个 `KNOWN_SESSION_EVENT_TYPES` 条目，为一个非 surface 事件引入新的 ignorable 分类决策，并复制 `goal/change` 已拥有的解码/折叠管线，而没有任何消费方需要独立的事件身份。

**推进 revision 的快照变更。** 否决：回执时推进 revision 会使完成方持有的每个 `GoalRef` 失效，把证据记录耦合进生命周期状态，并要求折叠新增一个保持 phase 的快照转换，没有消费方需要。

**证据存放在会话日志之外的旁路存储。** 否决：它破坏模型可见 ⟺ 已记录，且 fork、resume 与重放会丢失或偏离回执与 goal 的关联。

**允许空 evidence 数组。** 否决：它使回执在语义上为空、无法作为验证记录执行；要求至少一条证据，正是让回执值得审计的契约。

## Acceptance criteria

- `recordReceipt` 提交一条 `goal/change` 回执事件，发出受控的 `goal/changed` 通知（`operation: 'receipt'`），并返回已提交的回执；`create` → `complete` → `recordReceipt` → 全量折叠重放后，当前 goal、revision、`roundsStarted` 与 `seenGoalIds` 与 `complete` 之后完全一致。
- 过期或缺失的 ref、非 complete 的 phase、空或畸形的 evidence 都在追加之前以具名 `GoalError` code 失败。
- 折叠层重放拒绝缺少当前 goal、引用其他 goal 或 revision、目标 phase 非 complete、早于该 goal `updatedAt`、或形状畸形的回执——每项都是严格重放失败，而不是静默跳过。
- `pnpm exec vitest run packages/goal` 与 `pnpm run typecheck` 绿；goal 子系统页（双语）、包 README 契约与生成的 Cordis 目录在 `pnpm run test:docs` 下保持新鲜。

## Risks

在回执出现前构建的读取方重放含回执日志时，会在该记录处留存一次 goal 投影失败（goal 访问带诊断拒绝，直到日志被修复）；其余投影与原始日志继续可用，这是单一事件类型内载荷增长的既定降级。证据 summary 是调用方声明的文本——回执以与 block reason 相同的完整性检测立场记录声明，而非独立验证。回执时间戳只相对 goal 的 `updatedAt` 单调，不跨连续回执单调，因为回执不保留折叠状态。本切片一并推迟：DevFrame `GoalBinding` 的最近回执引用（需要 `NativeGoalPort` 的回执观察加投影状态归宿）、`recordReceipt` 的 wire 暴露，以及回执的任何模型可见呈现。
