---
description: V1.4 evjournal 设计（taskId v14-evjournal，P23/S4 evidence/journal producer 波）：devframe/verification 与 devframe/review 证据记录的诚实生产调用点定稿、agent-evidence journal producer 最小切片、写入面与 hostcmd 投影读取面的衔接、测试矩阵、精确文件清单与门禁计划。
---

# V1.4 devframe 证据 journal 生产者设计（agent-evidence producer 切片）

- 基点：worktree `D:/dsh-devframe-v14-evjournal-lead`，分支 `codex/v14-evjournal-lead` @ `24b7db9189`（总控已建、干净；`git rev-parse HEAD` = `24b7db91898b07556c78093f2aa36aa3d8db767b`）。主树 `D:/dsh-devframe` 只读核实（主树工作区存在他人未提交的 `AGENTS.md`/`docs/working/*` 改动，与本波无关：本波基点钉死在已并 main 的 `24b7db9189`，file:line 全部在该基点上核实）。
- 性质：为 GAP-b（`devframe/verification` 与 `devframe/review` 证据记录无生产源，测试即唯一生产者）交付**诚实生产调用点本体**——一个宿主采集落账的生产者（执行 approved 检查 + 记录审查决定），经既有 `DevFrameSessionJournal` 写入会话日志。不建 toolface 包、不加命令/工具动词、不接线 shipped profile（工具面包装归未来 S4 toolface 切片）。
- 落点：`packages/experimental/agent-evidence`（下称本包）。devframe 包**零 diff**。

## 1. 架构核对结论（成立；主树只读 file:line 证据链）

1. **词汇已注册，零 schema 改动**：`devframe/verification` 在原生会话日志词表 `packages/core/session/src/known-event-types.ts:41`；事件类型与 `SessionEventMap` 合并在 `packages/experimental/devframe/src/events.ts:253-276`。`SESSION_FORMAT_VERSION` 不动（无结构格式变化）。
2. **写入面唯一**：`DevFrameSessionJournal.append`（`devframe/src/session-journal.ts:66-166`）——decode（:106）→ review 门交叉授权（:107-111）→ append → flush 闩锁（:116-134）。全树 grep 证实生产调用者为零（仅 `agent-evidence/tests/at105-rejection-matrix.spec.ts:288,325` 与 `devframe/tests/events.spec.ts` 实例化）——这就是 GAP-b。
3. **评审授权缝已就位、明确等接线**：`EvidenceReviewGate`（`agent-evidence/src/review-gate.ts:42-66`，稳定码 `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED`）在结构上满足 `DevFrameReviewGate`（同文件 :8-10 明文 "a composition wires it into `DevFrameSessionJournal` without either package importing the other"）。`.agents/devframe/p22/p05harden-design.md:41`：生产组合接线缺失，"组合落地时必须接线，未接线即构造失败"。
4. **诚实执行契约已钉死**：`RequiredCheckCommand` 精确命令身份（`devframe/src/required-checks.ts:43-56`）与 `sameRequiredCheckCommand` 精确等值（:335-340）；`verificationEventSchema` superRefine 强制载荷自声明覆盖面 digest 自洽且每条声明 check 被**逐字执行**（`devframe/src/events.ts:442-481`）。推论：诚实生产者只有一种——真实执行 stored config 声明的精确命令并如实记录结果；任何旁造载荷在 decode 即拒。
5. **消费面（hostcmd）**：`/goal-complete` 组合从 devframe 投影取证据——`command-goal-binding/src/composition.ts:184-201`（`stateOf(agent.session,'devframe')` → `latestAttributedVerification` :240-249 取 `requiredChecks.coverage.digest` :198 → `latestReview` :256-258 → `CompleteGoalRequest`）；稳定无证据错误 `NO_VERIFICATION_TEXT`/`NO_REVIEW_TEXT`（`command-goal-binding/src/command.ts:33-38`）即 GAP-b 所述"无生产者的宿主只能收到稳定无证据错误"。
6. **写入↔读取衔接**：journal append → 控制器 Session 日志 → `devFrameProjectionDefinition` 折叠（事件折叠 `devframe/src/projection.ts:479`，checkpoint 重放解码 :83；定义的 `init`/`apply` 为公开纯面 :512-521）→ `stateOf` → hostcmd。衔接锚已由 `devframe/tests/events.spec.ts:483-495`（journal + SessionProjectionRegistry → `stateOf`）验证；本波测试用定义公开纯面直接折叠即可证明同一衔接，无需注册表。
7. **残余归属明文**：`agent-evidence/tests/at105-rejection-matrix.spec.ts:29`"残余：生产组合接线归 P23/S4 工具面"；`.agents/devframe/v14-evprod/worker/design.md` GAP1（"evidence/journal producer 切片域……属主波裁定"）；`.agents/devframe/integration/s4-toolface-plan.md` §3 规则 4（模型不可写原始证据，提交/验证事实由宿主从真实进程观测采集后落账）+ §4.3/§4.4（`project_verify`/`project_review` 的宿主职责语义权威）+ §6（toolface 包为未来独立切片）。

**生产调用点定稿**：宿主在"验证完成"时刻调用生产者的 `recordVerification`（store 解析 approved config → 真实子进程逐条精确执行 → 聚合 → `journal.append('devframe/verification')`）；在"审查完成"时刻调用 `recordReview`（`journal.append('devframe/review')`，门在 append 前交叉授权）。两者都过 `DevFrameSessionJournal`——会话日志唯一 schema 校验+落盘路径；写入即投影可折叠（同 schema），hostcmd 读取面由此获得证据。生产者是**证据记录者，不是准入权威**：binding 由宿主解析后传入（S4 plan §3 规则 3 的工作归属三查属调用方），durable schema + 投影重放双层校验结构完整性。

## 2. 最小切片边界

**做**：本包新增两个 src 模块（执行面 + 生产者）、两个 spec、index 导出、双语 README 增量。

**不做（零 diff 纪律）**：
- `packages/experimental/devframe/**` 零 diff（全部经既有子路径导入；`'./src/*'` 深导入在 src 层的先例：`command-goal-binding/src/composition.ts:27-30`）。
- `command-goal-binding`/`shadow-router`/`project-memory` 零 diff。
- 台账三表与 `AgentEvidenceLedger` 零 diff（ledger 保持纯溯源；不镜像 journal 证据——语义分层，见 GAP 2）。
- 不加 `declare module '@deepseek-ai/cordis'` Context merge（生产者是 plain class，宿主组合构造——`GoalBindingController` 同型；这同时保住 gen-cordis-catalog 0 written）。
- 不加任何新依赖（devframe 经既有 peer dep；`node:child_process`/`node:crypto` 内建）；`pnpm-lock.yaml` 零改动。
- 不加新错误码：生产者自身不 throw 新族——store 结构错误传播 `RequiredChecksError` 族，门拒绝传播 `AgentEvidenceError`，持久化失败传播 `DevFramePersistenceError`，载荷结构由 devframe schema decode 拒绝。
- `errors.ts`、`ledger.ts`、`spec.ts`、`types.ts`、`ids.ts`、`review-gate.ts` 零 diff。
- `outputRef` 有界日志捕获缺席（deferred，见 GAP 3）：schema optional、完成 admission 不消费，不削弱任何拒绝路径。

## 3. API 定稿

### 3.1 `src/check-runner.ts`（执行面）

```ts
/** Execute every configured required check; one real result per configured check, in config order. */
export type RequiredChecksExecution =
  (config: DevFrameRequiredChecksConfig) => Promise<readonly DevFrameCheckResult[]>

export interface SubprocessExecutionOptions {
  /** Per-check wall-clock kill guard in ms; defaults to 600_000. */
  readonly timeoutMs?: number
}

export function createSubprocessRequiredChecksExecution(
  options?: SubprocessExecutionOptions,
): RequiredChecksExecution

/** The default reference execution face (10-minute kill guard). */
export const subprocessRequiredChecksExecution: RequiredChecksExecution
```

实现：`promisify(execFile)(check.executable, [...check.arguments], { cwd: check.cwd, timeout, stdio: ['ignore','ignore','ignore'] })`。`stdio: 'ignore'` 是裁定而非疏漏：本波不捕获输出（`outputRef` 缺席），ignore 使 `maxBuffer` 截断语义不进入结果分类——退出码是唯一裁决信号。

**状态映射（逐分支可测）**：
- 进程退出码 0 → `status: 'passed'`，`exitCode: 0`。
- 进程退出码 ≠ 0 → `status: 'failed'`，`exitCode` 如实。
- `error.killed === true`（timeout 击杀）→ `status: 'timed_out'`，无 `exitCode`。
- 其余拒绝（ENOENT/EACCES/signal 死亡等无退出码情形）→ `status: 'unknown'`，无 `exitCode`。
- `durationMs` = 调用前后 `Date.now()` 差（≥0）。`cancelled`/`skipped` 不由参考执行面产出（属有取消流宿主的词表）。
- 每条结果的 `checkId/executable/arguments/cwd` **逐字回显自 config**（覆盖规则的前提），config 序输出，不重试、不修补——失败证据诚实入账。

### 3.2 `src/journal.ts`（生产者）

```ts
export interface AgentEvidenceJournalOptions {
  /** Native `ctx.sessions.flush`-compatible durability callback. */
  readonly flush: DevFrameFlush
  /** SessionId-keyed reviewer role authority; wired into the journal's review gate. */
  readonly reviewerDirectory: EvidenceReviewerDirectory
  /** Execution face for required checks; defaults to `subprocessRequiredChecksExecution`. */
  readonly execution?: RequiredChecksExecution
}

export interface VerificationEvidenceRequest {
  /** Controller Session whose log the devframe projection folds. */
  readonly session: Session
  /** Complete work identity the evidence attributes to (host-resolved). */
  readonly binding: GoalResultBinding
  /** Canonical digest of the approved configuration, registered in the store at approval time. */
  readonly requiredChecksDigest: RequiredChecksDigest
  /** Configuration store resolving the digest to the stored approved checklist. */
  readonly requiredChecksStore: RequiredChecksConfigStore
}

export interface ReviewEvidenceRequest {
  readonly session: Session
  readonly binding: GoalResultBinding
  /** Exact reviewer Session identity; cross-authorized by the gate before append. */
  readonly reviewerSessionId: SessionId
  /** Role-policy revision active during review. */
  readonly policyVersion: string
  readonly decision: 'pass' | 'changes_required'
  readonly findings: readonly DevFrameReviewFinding[]
}

export class AgentEvidenceJournal {
  constructor(options: AgentEvidenceJournalOptions)
  async recordVerification(request: VerificationEvidenceRequest): Promise<DevFrameVerificationEventData>
  async recordReview(request: ReviewEvidenceRequest): Promise<DevFrameReviewEventData>
}
```

构造即接线：内部 `new DevFrameSessionJournal(options.flush, new EvidenceReviewGate(options.reviewerDirectory))`——评审门为必填构造项（p05harden"未接线即构造失败"），不存在绕过路径。

**`recordVerification` 流程**：
1. `config = await request.requiredChecksStore.load(request.requiredChecksDigest)` —— `REQUIRED_CHECKS_CONFIG_NOT_FOUND`/`REQUIRED_CHECKS_INVALID_CONFIG`/`REQUIRED_CHECKS_STORE_CORRUPT` 原样传播，**零事件**。
2. `checks = await execution(config)` —— 精确执行每条声明 check（执行集 = 声明集，覆盖规则按构造满足）。
3. `status = checks.every(c => c.status === 'passed') ? 'passed' : 'failed'`。
4. 载荷：`{ version: 1, verificationId: DevFrameVerificationId(randomUUID()), binding, snapshotId: binding.snapshotId, status, requiredChecks: { config, digest }, checks }` —— `snapshotId` 单源自 binding（schema 交叉校验 :443-445 按构造满足）。
5. `journal.append(session, 'devframe/verification', payload)` —— decode（含 digest 自洽 + 覆盖规则）→ append → flush；`DevFramePersistenceError` 传播并闩锁该 Session。
6. 返回 `event.data`。

**`recordReview` 流程**：
1. 载荷：`{ version: 1, reviewId: DevFrameReviewId(randomUUID()), binding, snapshotId: binding.snapshotId, reviewerSessionId, policyVersion, decision, findings }`。
2. `journal.append(session, 'devframe/review', payload)` —— decode（`pass` 不得保留 blocking findings :504-507）→ `gate.requireReviewer(reviewerSessionId)`（未授权/未绑定 → `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED`，事件不入日志，不闩锁）→ append → flush。
3. 返回 `event.data`。

**导入面（Worker 逐字采用，子路径全为先例）**：
- `@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts`：`DevFrameSessionJournal`、type `DevFrameFlush`（:20）。
- `@deepseek-ai/dsh-experimental-devframe/src/events.ts`：`DevFrameReviewId`、`DevFrameVerificationId`（:47,56）；type `DevFrameCheckResult`、`DevFrameReviewEventData`、`DevFrameReviewFinding`、`DevFrameVerificationEventData`。
- `@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts`：type `DevFrameRequiredChecksConfig`、`RequiredChecksConfigStore`、`RequiredChecksDigest`。
- `@deepseek-ai/dsh-experimental-devframe/controller/goal-binding`：type `GoalResultBinding`。
- `./review-gate.ts`：`EvidenceReviewGate`、type `EvidenceReviewerDirectory`。
- `@deepseek-ai/dsh-session`：type `Session`、`SessionId`；`node:crypto` 的 `randomUUID`；`node:child_process` 的 `execFile` + `node:util` 的 `promisify`。

### 3.3 `src/index.ts` 增量导出

```ts
export { createSubprocessRequiredChecksExecution, subprocessRequiredChecksExecution } from './check-runner.ts'
export type { RequiredChecksExecution, SubprocessExecutionOptions } from './check-runner.ts'
export { AgentEvidenceJournal } from './journal.ts'
export type { AgentEvidenceJournalOptions, ReviewEvidenceRequest, VerificationEvidenceRequest } from './journal.ts'
```

每个导出带简洁 JSDoc（`verify-export-jsdoc`；函数型含 `@param`/`@returns`）。默认导出仍是 ledger，不动。

## 4. 测试矩阵（`tests/check-runner.spec.ts` 5 例 + `tests/journal.spec.ts` 12 例）

执行面（真实子进程，node `-e` 脚本）：
1. exit 0 → `passed`/`exitCode 0`，命令三元组逐字回显。
2. exit 3 → `failed`/`exitCode 3`。
3. `createSubprocessRequiredChecksExecution({ timeoutMs: 50 })` + 挂起脚本 → `timed_out`、无 `exitCode`。
4. 不存在可执行名 → `unknown`、无 `exitCode`。
5. 多条 config → 逐条对应、config 序、每条 `checkId/executable/arguments/cwd` 逐字回显（覆盖规则前提）。

生产者（注入 execution + 真实存储 harness `tests/helpers.ts`）：
6. 正向：注入 passed execution → 会话日志恰一 `devframe/verification`、返回数据=载荷、flush 回调被调、`decodeDevFramePayload` 往返等值。
7. **真实子进程端到端**：默认 execution + `MemoryRequiredChecksConfigStore`（save → recordVerification）→ 事件 `requiredChecks.digest ===` 登记 digest、coverage 校验过、事件可解码（诚实路径全链）。
8. **投影衔接**：对追加事件用 `devFrameProjectionDefinition.init(header, 0)` + 逐事件 `apply` 纯面折叠 → `state.verifications`/`state.reviews` 含记录且 `binding.goalId` 归属正确（hostcmd `latestAttributedVerification`/`latestReview` 读取面取到）；失败时回退断言 decode 边界并引用 devframe events.spec:483-495 锚。
9. digest 未登记（真实 Memory store）→ `RequiredChecksError`/`REQUIRED_CHECKS_CONFIG_NOT_FOUND` 传播、日志零事件。
10. store 抛 `REQUIRED_CHECKS_INVALID_CONFIG`（测试桩 store）→ 原样传播、零事件。
11. 失败检查 → 诚实 `failed` evidence 入账且可解码（记录事实，不判定）。
12. flush 拒绝 → `DevFramePersistenceError` 传播、journal 闩锁（后续 append 报 `blocked`）。
13. recordReview 正向（授权 reviewer）→ 恰一 `devframe/review`、gate 被询、返回数据。
14. recordReview 未授权/未绑定 Session → `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED`、零事件。
15. `pass` 决策带 blocking findings → schema 拒绝传播、零事件。
16. 两次 recordVerification 顺序追加、id 互异（journal 序列化语义在本包消费面的最小锚）。

覆盖设计：check-runner 四分支 + 回显 + 序全测；journal 的构造默认 execution 分支由用例 7 覆盖——对齐 per-file 100% 覆盖门（`thresholds.perFile`）。

## 5. 文档增量（双语同 commit）

- `README.md`/`README.zh.md`：Summary 增一句 journal producer；Use this package 增 producer 小节（构造 options + 两个 record 调用示例 + 错误传播说明）；Source map 表增 `src/check-runner.ts`、`src/journal.ts` 两行；Model Experience 更新为诚实表述——包仍不注册工具/提示节，不新增事件类型，但 producer 会向控制器 Session 日志追加 DevFrame 证据记录（宿主侧 durable 记录，从不进入模型请求，token 效应零）；Known Limitations 增两条：`outputRef` 有界日志捕获缺席、producer 记录证据而不判定完成（admission 归 devframe controller）。双语行对齐；如 `verify-translation-pairing` 报漂移，按其 `--write` 指令再生成 `README.i18n.yaml`。
- `package.json` description 与 `packages/experimental/README.md(.zh.md)` 组表行**不动**（描述仍真实；组表措辞同步随 toolface 波一并裁定，见 GAP 5）。

## 6. 精确文件清单（写入域，全在 Worker 树）

1. `packages/experimental/agent-evidence/src/check-runner.ts` — 新模块。
2. `packages/experimental/agent-evidence/src/journal.ts` — 新模块。
3. `packages/experimental/agent-evidence/src/index.ts` — 增 4 行导出。
4. `packages/experimental/agent-evidence/tests/check-runner.spec.ts` — 新测试。
5. `packages/experimental/agent-evidence/tests/journal.spec.ts` — 新测试。
6. `packages/experimental/agent-evidence/README.md` / `README.zh.md`（/ 必要时 `README.i18n.yaml` 再生成）。
7. `.agents/devframe/v14-evjournal/worker/design.md` — Worker 设计/收据文档。

禁区（零触碰）：`.agents/devframe/v14/next/**`、`snapshots/**`、`packages/test-support/session-snapshot/**`、`scripts/session-snapshot-corpus*`、`vendor/**`、`packages/experimental/command-goal-binding/**`、`packages/experimental/shadow-router/**`、`packages/experimental/project-memory/**`、`packages/experimental/devframe/**`、主树 `D:/dsh-devframe`（只读）、`.agents/notes/**`、`pnpm-lock.yaml`、历史 worktree `D:/dsh-devframe-p-*`。禁 push/PR/发布/删文件/禁创建任何 Agent/subagent/workflow/goal。

## 7. 门禁计划（真实退出码，未跑不得声称通过）

1. worktree `pnpm install` — exit 0。
2. 聚焦 vitest：`pnpm vitest run packages/experimental/agent-evidence` — 全绿（既有 4 spec + 新 2 spec）。
3. 删全部 `*.tsbuildinfo` → `pnpm run build` — exit 0。
4. `pnpm run gen-cordis-catalog` — 0 written（producer 非 Context merge、无新服务键；**若非 0：停手上报组长，不自行改 `scripts/`**）。
5. `git diff --check` — exit 0（提交时含 `--cached --check`）；每文件恰一尾随换行。
6. `pnpm run test:docs` — exit 0（15 门全绿）。
7. 提交 `--no-verify`（宿主无 bash，lefthook vendor manifest guard exit 127 环境事实），message 登记 skip + 替代验证收据（staged `--cached --check` exit 0、尾随换行核对、触及域零 vendor/禁区路径）；禁 push/PR/发布/删除。

## 8. GAP/未尽

1. **组合接线缺席（有意）**：shipped profile/toolface 挂载（谁构造 `AgentEvidenceJournal` 并接 `ctx.sessions.flush` + live 角色权威）归 S4 toolface 切片（s4-toolface-plan §6）；本波交付生产源本体，与 `startBinding`（composition 的测试可见车道）同层的"宿主面生产代码"。
2. **台账不镜像 journal 证据**：ledger 三表保持纯溯源；journal 证据与台账回执是两条正交记录轨（AT105 矩既有裁定），是否需要在 producer 内双写归后续裁定。
3. **`outputRef` 有界日志捕获缺席**：退出码是本波裁决信号；stdout/stderr 有界捕获与 artifact 落盘归后续切片（s4-toolface-plan §4.3"有界日志引用"的完整形态）。
4. **超时为参考实现固定默认（600s）**：部署可变超时随 toolface Config 面裁定（本波 `timeoutMs` 构造参数已留注入缝）。
5. **包描述/组表措辞**：producer 并入描述的措辞随 toolface 波一并裁定。
6. **Agent Note**：仓库规则要求非平凡变更同 PR 附 Agent Note；Worker 写入域不含 `.agents/notes/**`——正式 Note 归属主树合流波。
