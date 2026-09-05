# 代理证据账本

[English](agent-evidence.md) | 中文

代理证据子系统在 `agent_evidence` 存储域上保存 agent（智能体）工作的仅追加溯源台账：任务/Goal 绑定回执（单任务视角的 DevFrame goal-result 绑定元组）、提交回执（commit 对象名、变更路径以及工作起点的源输入摘要）与验证快照（命令、退出码与产物路径——非零退出码按原样记录）。账本只保存溯源：验收留在 Goal 绑定与任务状态处。[包 README](../../packages/experimental/agent-evidence/README.zh.md) 负责挂载配置与模型体验。

## 服务面

`ctx.agentEvidence` 是证据账本。核心操作：

- `recordTaskGoalBinding`、`recordSubmission`、`recordVerification` — 经持久化 schema 校验回执并返回冻结回执。
- `byTask` 与 `bindingsByGoal` — 按记录顺序返回仅追加轨迹；在新 Goal 修订下重新记录绑定会新增一条回执，任何回执都不会被改写或删除。
- 回执在启动时原样恢复。

## 约定要点

每次失败都在 `AgentEvidenceError` 上携带稳定的 `AGENT_EVIDENCE_*` 代码：畸形回执以 `AGENT_EVIDENCE_INVALID_RECEIPT` 大声失败，存储拒绝以 `AGENT_EVIDENCE_PERSISTENCE` 带原始原因呈现。回执保存在 [存储域](storage.zh.md) `agent_evidence` 中；记录时用与域恢复校验相同的 zod schema 解析每条回执。回执类型复用 DevFrame 身份词汇——`ControllerSessionId`、`GoalId`、`AcceptanceHash`、`SourceFingerprint`、`WorkspaceId`——因此证据解析到的正是派发与完成已在使用的同一工作身份。任何回执值都不会到达模型请求，因此不新增会话事件。

## 子系统边界

验收决策留在账本之外：goal 一侧由 [goal 子系统](goal.zh.md) 的 Goal 绑定负责，[项目任务控制器](project-controller.zh.md) 负责任务状态。回执是受信任的溯源，不是经验证的事实——账本不检查仓库来确认变更路径或产物路径，也不校验任务或 Goal 是否存在；引用完整性留给消费方。

<!-- BEGIN GENERATED cordis-surface (gen-cordis-catalog.ts) — do not edit between markers -->

<a id="cordis-surface"></a>

## Cordis API

Generated from source by `scripts/gen-cordis-catalog.ts` (verified fresh by `pnpm run verify-cordis-catalog` in doc-sync; regenerate with `pnpm run gen-cordis-catalog`) — the language sides differ only in locale-specific paired document paths. Signature blocks use a `ts cordis-catalog` fence and keep the original source JSDoc; dispatch modes are defined in the [primer](../cordis-primer.zh.md#dispatch-modes), and the framework-inherited `ctx` API lives in [cordis-api/inherited.md](../cordis-api/inherited.md).

<a id="ctxagentevidence--agentevidenceledger"></a>

### `ctx.agentEvidence` — `AgentEvidenceLedger`

The agent evidence ledger: append-only provenance per task and Goal.

```ts cordis-catalog
/**
 * Record one task/Goal binding receipt tying a task to the Goal that owns
 * its work. Re-recording under a new Goal revision adds a receipt; the
 * trail keeps them all.
 * @param request - The work identity to bind, in DevFrame goal-binding vocabulary.
 * @returns the recorded receipt.
 */
async recordTaskGoalBinding(request: TaskGoalBindingRequest): Promise<TaskGoalBindingReceipt>

/**
 * Record one submission receipt: the commit, the changed paths, and the
 * digest of the inputs the work started from.
 * @param request - The submission facts.
 * @returns the recorded receipt.
 */
async recordSubmission(request: SubmissionRequest): Promise<SubmissionReceipt>

/**
 * Record one verification snapshot: command, exit code, and artifact
 * paths. A non-zero exit code is recorded as-is — the ledger does not
 * judge verification outcomes.
 * @param request - The verification facts.
 * @returns the recorded snapshot.
 */
async recordVerification(request: VerificationRequest): Promise<VerificationSnapshot>

/**
 * Read one task's complete evidence trail.
 * @param taskId - Task selecting the receipts.
 * @returns the three trails, each in recorded order.
 */
byTask(taskId: TaskId): TaskEvidence

/**
 * Read the binding receipts of one Goal on one controller session.
 * @param controllerSessionId - Controller Session that owns the Goal.
 * @param goalId - Goal whose bindings are queried.
 * @returns the matching binding receipts in recorded order.
 */
bindingsByGoal(controllerSessionId: ControllerSessionId, goalId: GoalId): readonly TaskGoalBindingReceipt[]
```

Types: [GoalId](goal.zh.md)

Source: [`packages/experimental/agent-evidence/src/ledger.ts`](../../packages/experimental/agent-evidence/src/ledger.ts)
<!-- END GENERATED cordis-surface -->
