---
description: "持有代理工作追加式证据台账的 Cordis 服务：任务/Goal 绑定回执、提交回执与验证快照，均绑定到共享工作身份。"
kind: "package-reference"
---

# @deepseek-ai/dsh-experimental-agent-evidence

[English](README.md) | 中文

## 概述

`dsh-experimental-agent-evidence` 挂载 `ctx.agentEvidence`，在 `agent_evidence` 存储域上记录并查询代理工作的追加式溯源台账的 Cordis 服务：任务/Goal 绑定回执（单任务视角的 DevFrame goal-result 绑定元组）、提交回执（commit 对象名、改动路径、工作起点源输入摘要）与验证快照（命令、退出码、产物路径——非零退出码原样记录）。台账只存溯源：验收判定留在 Goal 绑定与任务状态里，因此这里不存在另一个验收数据库。回执在启动时原样恢复。本包同时导出诚实的 DevFrame 证据生产者（`AgentEvidenceJournal`）：它以真实子进程执行面逐字执行存储的 approved 必需检查并把真实结果追加为 `devframe/verification` 记录，将审查决定记录为 `devframe/review` 记录——两者都经 schema 校验的 DevFrame Session journal。

## 目录

- [使用本包](#use-this-package)
- [理解实现](#understand-the-implementation)
- [模型体验](#model-experience)
- [已知限制与延期工作](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

在存储栈旁挂载本服务；它硬注入 `ctx.storageDomain`，存储后端缺失即在激活时失败。

```yaml
- name: '@deepseek-ai/dsh-storage'
- name: '@deepseek-ai/dsh-storage-json'
- name: '@deepseek-ai/dsh-storage-domain'
- name: '@deepseek-ai/dsh-experimental-agent-evidence'
```

### 记录并读取证据轨迹

每次记录调用经持久化 schema 校验并返回冻结回执；查询按记录顺序返回追加式轨迹。

```ts
import type {
  AgentEvidenceLedger, SubmissionRequest, TaskGoalBindingRequest, VerificationRequest,
} from '@deepseek-ai/dsh-experimental-agent-evidence'

async function recordEvidence(
  ctx: { agentEvidence: AgentEvidenceLedger },
  binding: TaskGoalBindingRequest,
  submission: Omit<SubmissionRequest, 'taskId'>,
  verification: Omit<VerificationRequest, 'taskId'>,
) {
  await ctx.agentEvidence.recordTaskGoalBinding(binding)
  await ctx.agentEvidence.recordSubmission({ ...submission, taskId: binding.taskId })
  await ctx.agentEvidence.recordVerification({ ...verification, taskId: binding.taskId })
  return {
    trail: ctx.agentEvidence.byTask(binding.taskId),
    bindings: ctx.agentEvidence.bindingsByGoal(binding.controllerSessionId, binding.goalId),
  }
}
```

畸形回执以 `AGENT_EVIDENCE_INVALID_RECEIPT` 大声失败；存储拒绝以 `AGENT_EVIDENCE_PERSISTENCE` 呈现。

### 记录 DevFrame 验证与审查证据

记录任务输出证据时，宿主向两个 journal 方法提供最新任务交付的 `deliveryId`，并以其 `deliveryResultBinding` 作为 `binding`。journal 保留交付引用；DevFrame 投影检查当前 Goal、最新交付和输出身份。原始 Goal 输入保持不变。省略 `deliveryId` 仍会记录整个 Goal 的证据，但不能替代集成所要求的任务交付证据。

journal 生产者是宿主组合的 plain class（非插件挂载）：以 Session 持久化回调与审查者角色权威构造，在验证与审查完成的时刻调用两个 record 方法。

```ts
import { AgentEvidenceJournal } from '@deepseek-ai/dsh-experimental-agent-evidence'
import type {
  AgentEvidenceJournalOptions, ReviewEvidenceRequest, VerificationEvidenceRequest,
} from '@deepseek-ai/dsh-experimental-agent-evidence'

async function recordJournalEvidence(
  options: AgentEvidenceJournalOptions,
  verificationRequest: VerificationEvidenceRequest,
  reviewRequest: Omit<ReviewEvidenceRequest, 'session' | 'binding'>,
) {
  // The host supplies native Session flushing and reviewer role authority.
  const journal = new AgentEvidenceJournal(options)
  // Execute the approved checks resolved from the stored digest.
  const verification = await journal.recordVerification(verificationRequest)
  // Cross-authorize the reviewer Session before appending its decision.
  const review = await journal.recordReview({
    ...reviewRequest, session: verificationRequest.session, binding: verificationRequest.binding,
  })
  return { verification, review }
}
```

生产者记录证据，不判定完成。存储失败在任何事件写入前以既有 `RequiredChecksError` 错误码（`REQUIRED_CHECKS_CONFIG_NOT_FOUND`、`REQUIRED_CHECKS_INVALID_CONFIG`）传播；门拒绝以 `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` 呈现且不闩锁；持久化失败以 `DevFramePersistenceError` 呈现并闩锁该 Session 的 journal。每条记录在落账前都经持久化 `devframe/verification`/`devframe/review` schema 校验。

-----

<a id="understand-the-implementation"></a>
## 理解实现

<details>
<summary>Implementation internals — click to expand</summary>

本节解释设计决策并指向实现代码；可观察行为已在 [Use this package](#use-this-package) 完整覆盖。

### 设计决策

- **复用身份，而非重新声明。** 绑定回执携带 DevFrame goal-result 绑定词汇——`ControllerSessionId`、`GoalId`、`AcceptanceHash`、`SourceFingerprint`、`WorkspaceId`——直接从实验 DevFrame 包导入，使证据解析到派发与完成已使用的同一工作身份。
- **只存溯源。** 台账不持验收判定：失败的验证快照是记录在案的事实，验收决策留在 Goal 绑定（DevFrame）与任务状态（project-controller）里。这正是"不另建验收数据库"的原因。
- **持久边界由 schema 负责品牌化。** 记录时用与存储域恢复校验相同的 zod schema 解析每条回执，品牌施加与校验共用一个定义；存储拒绝以 `AGENT_EVIDENCE_PERSISTENCE` 带原始原因呈现。
- **追加式轨迹。** 在新 Goal 修订下重录绑定即追加回执；任何回执都不会被重写或删除。`byTask` 与 `bindingsByGoal` 按记录顺序返回完整轨迹。

### Source map

| File | Role |
|---|---|
| [`src/ledger.ts`](src/ledger.ts) | `ctx.agentEvidence` 服务：记录、查询、冷恢复 |
| [`src/spec.ts`](src/spec.ts) | `agent_evidence` 域声明与 zod 回执 schema |
| [`src/types.ts`](src/types.ts) | 建立在共享工作身份上的回执记录类型 |
| [`src/ids.ts`](src/ids.ts) | `EvidenceReceiptId` 与 `CommitSha` 品牌工厂 |
| [`src/errors.ts`](src/errors.ts) | `AgentEvidenceError` 及其稳定错误码联合 |
| [`src/check-runner.ts`](src/check-runner.ts) | 必需检查的参考子进程执行面 |
| [`src/journal.ts`](src/journal.ts) | 建立在 Session journal 上的 DevFrame 证据生产者 |
| [`src/index.ts`](src/index.ts) | 包入口与默认导出 |

### Invariant

不发布运行时 invariant 伴随物：回执是追加式单表行、无跨表派生，JSON 后端拒绝同一单元的第二个活动句柄，查询读的是写入所填充的同批进程内映射，因此不存在可能分叉的独立观察。

</details>

-----

<a id="model-experience"></a>
## 模型体验

### 代理证据台账

#### What the model sees

没有任何内容到达模型请求。本包不注册工具与提示词段落，也不新增事件类型；`AgentEvidenceJournal` 生产者向所属控制器 Session 日志追加 DevFrame 证据记录——`devframe/verification` 与 `devframe/review`，既有 DevFrame 词汇。该日志是宿主侧 durable 记录：从不进入模型请求，因此没有请求字段携带本包数据。

#### Token effect

对每次请求的直接 token 影响为零。

#### KV Cache effect

与实时请求无关：本包不触碰请求前缀，因此不可能使提供方缓存复用失效。

<a id="known-limitations-and-deferred-work"></a>
## 已知限制与延期工作

这些限制界定了台账在何种场景下不适用或需要特别运维关注。它们是当前包约束，不是任务清单。

- **回执是受信溯源，不是已核实事实** —— 改动路径与产物路径按调用方所报记录；台账不检查仓库来确认它们。
- **台账不校验任务或 Goal 的存在性** —— 回执引用调用方提供的 id；引用完整性由项目控制器与 Goal 绑定负责。
- **轨迹无界增长** —— 回执从不重写或修剪；长期运行的部署会在三张表中累积行。
- **无有界输出捕获** —— 执行面仅以退出码判定结果且不捕获 stdout/stderr（从不产生 `outputRef`）；有界日志捕获与产物落盘归 toolface 切片。
- **生产者记录证据，不判定完成** —— 两个 record 方法只写入诚实记录；准入合取（指纹→检查→审查）归 DevFrame controller。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>Working context for maintainers — click to expand</summary>

None.

</details>
