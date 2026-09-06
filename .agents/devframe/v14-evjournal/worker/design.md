---
description: V1.4 evjournal Worker 实现记录（v14-evjournal w1）：agent-evidence 诚实生产者的逐文件落点、与组长设计的一致性声明、门禁收据与偏差/GAP 登记。
---

# V1.4 devframe 证据 journal 生产者 — Worker 实现记录（w1）

- Worker 工作树：`D:/dsh-devframe-v14-evjournal-w1`，分支 `codex/v14-evjournal-w1`，基点 `c71438cdbe955091a57602b556b0be95a1be6401`（开工自查：HEAD 等于基点、`git status --porcelain` 为空）。
- 权威设计：`.agents/devframe/v14-evjournal/lead/design.md`；第 3 节 API 逐字采用，第 4 节矩阵逐例落地，未重新设计。

## 1. 树内锚点复核结论（开工时逐条 file:line 复核，全部一致）

- `devframe/src/session-journal.ts:66-166` `DevFrameSessionJournal`：decode :106 → review 门交叉授权 :107-111 → append :115 → flush 闩锁 :116-134；`isBlocked` :163-165。
- `agent-evidence/src/review-gate.ts:42-66` `EvidenceReviewGate`：:8-10 明文结构满足 `DevFrameReviewGate` 缝；:59-66 稳定码 `AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED`。
- `devframe/src/events.ts:442-481` `verificationEventSchema` superRefine（snapshotId 交叉 :443-445、聚合一致性 :446-452、digest 自洽 :463-469、逐字执行覆盖 :470-480）；:253-276 事件词表合并；:504-507 `pass` 不得保留 blocking findings。
- `devframe/src/required-checks.ts:43-56` `RequiredCheckCommand`；:335-340 `sameRequiredCheckCommand`；:163-223 store 缝与 `MemoryRequiredChecksConfigStore`。
- src 层深导入先例：`command-goal-binding/src/composition.ts:27-30`。
- 投影纯面：`devframe/src/projection.ts:512-521`（`init`/`apply`）；`applyVerification` :422-428 与 `applyReview` :431-448 的接受条件要求先有 role-policy 与 goal-binding 事件——用例 8 据此带宿主上下文事件折叠（见 §2.5）。

## 2. 逐文件落点

1. **`src/check-runner.ts`（新）**：`RequiredChecksExecution`、`SubprocessExecutionOptions`（`timeoutMs` 默认 600_000）、`createSubprocessRequiredChecksExecution`、`subprocessRequiredChecksExecution` 默认实例。`promisify(execFile)` 顺序执行 `config.checks`（结果序=配置序，按构造）；状态映射：resolve → `passed`+`exitCode 0`；reject 上 `killed === true` → `timed_out` 无 exitCode，数值 `code` → `failed`+`exitCode` 如实，其余（ENOENT 等字符串 code / signal 死亡）→ `unknown` 无 exitCode；`durationMs` = `Math.max(0, Date.now() 差)`；每条结果 `checkId/executable/arguments/cwd` 逐字回显自 config；不重试、不修补。stdio ignore 为设计裁定（注释随码）。
2. **`src/journal.ts`（新）**：`AgentEvidenceJournal` 构造即接线 `new DevFrameSessionJournal(options.flush, new EvidenceReviewGate(options.reviewerDirectory))`（评审门为必填构造项，无绕过路径）；`execution` 缺省 `subprocessRequiredChecksExecution`。`recordVerification`：`store.load(digest)`（`RequiredChecksError` 原样传播、零事件）→ `execution(config)` → 聚合 status（全 passed ? passed : failed）→ 载荷（version:1、`DevFrameVerificationId(randomUUID())`、binding、`snapshotId: binding.snapshotId`、requiredChecks `{config,digest}`、checks）→ `journal.append(session,'devframe/verification',payload)` → 返回 `event.data`。`recordReview`：载荷（`DevFrameReviewId(randomUUID())`、reviewerSessionId、policyVersion、decision、findings）→ `journal.append(session,'devframe/review',payload)`（门在 decode 后 append 前交叉授权；`AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED` 不入日志不闩锁）→ 返回 `event.data`。请求类型字段与 JSDoc 按设计 3.2（设计未注字段补齐 devframe events.ts 同词汇文档）。
3. **`src/index.ts`**：+4 行导出（设计 3.3 精确清单，插在 review-gate 导出与默认导出之间）；默认导出 ledger 不动。导出 JSDoc 落在两新模块的声明处——`verify-export-jsdoc` 规定 re-export 的文档留在声明契约（scripts/verify-export-jsdoc.ts 头注）。
4. **`tests/check-runner.spec.ts`（新，恰 5 例）**：① exit 0 → passed/exitCode 0 + 三元组逐字回显；② exit 3 → failed/exitCode 3（走 `subprocessRequiredChecksExecution` 默认实例）；③ `timeoutMs: 50` + 挂起脚本 → `timed_out`、`Object.hasOwn(…,'exitCode')` false；④ 不存在可执行名 → `unknown`、无 exitCode；⑤ 三条 config → config 序对应 + 逐条逐字回显。
5. **`tests/journal.spec.ts`（新，恰 12 例）**：设计矩阵 6-16 逐例，其中矩阵 14（"未授权/未绑定"）拆为非 reviewer 角色（controller 角色）与未绑定身份两例，共 12。用例 7 默认 execution 真实子进程端到端 + `MemoryRequiredChecksConfigStore` save→recordVerification（digest 等值、coverage 校验经 decode、事件可解码）。用例 8 用 `devFrameProjectionDefinition.init(header, SessionLogOffset(0))` + 逐事件 `apply` 纯面折叠：`state.verifications`/`state.reviews` 含记录且 `binding.goalId` 归属正确、`failure` 为 null——**主路径通过，未启用回退分支**；宿主上下文事件（role-policy + goal-binding）由测试直接 append，因 `assertResultBinding`/`applyReview` 要求其存在（这是宿主职责的忠实模拟，非设计偏离）。正向用例附台账正交断言（`ctx.agentEvidence.byTask(...).bindings` 为空，对应 GAP 2 的双轨语义）。
6. **`README.md` / `README.zh.md`**：Summary 增一句；Use this package 增 producer 小节（构造 options + 两个 record 调用示例 + 错误传播说明）；Source map 表增 `src/check-runner.ts`、`src/journal.ts` 两行；Model Experience 诚实更新（包仍零工具/零提示节/零新事件类型；producer 向控制器 Session 日志追加既有 DevFrame 词汇的证据记录——宿主侧 durable 记录，从不进入模型请求）；Known Limitations 增两条（无有界输出捕获/outputRef；producer 记录证据不判定完成）。双语行对齐；代码块双语逐字一致（配对门 verbatim 规则，见 §4 复盘）。
7. **`README.i18n.yaml`**：按其头注指令以 `verify-translation-pairing --write` 再生成（共两次，见 §4）。
8. **`.agents/devframe/v14-evjournal/worker/design.md`**：本文档。

## 3. 与设计的一致性声明

- API 面、导入子路径、执行语义、事件类型、错误传播（零新错误码族）与设计第 3 节一致；测试矩阵与设计第 4 节逐例对应；文档增量与设计第 5 节对应；写入域与设计第 6 节穷举一致（`git status` 全程仅 8 个写入域文件）；`pnpm-lock.yaml`、devframe 包、command-goal-binding/shadow-router/project-memory、vendor、scripts、禁区路径零 diff。
- **偏差 1（类型面，非语义）**：`check-runner.ts` 增 `import type { ExecFileOptions } from 'node:child_process'` 并对 options 字面量 `as ExecFileOptions`——`@types/node@22` 的 `ExecFileOptions` 未声明 `stdio`（运行时 Node 接受），设计要求的 `stdio: ['ignore','ignore','ignore']` 须以此通过类型检查；运行时行为与设计逐字一致。
- **偏差 2（导入面裁剪，非语义）**：`journal.ts` 不导入 `DevFrameRequiredChecksConfig`——`noUnusedLocals` 拒绝未用导入，该类型由 `check-runner.ts` 使用；设计 3.2 的导入面由两模块联合满足。
- 其余无偏差。

## 4. 门禁收据（真实退出码；第 2、3、6 项在修正后重跑）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `pnpm install --frozen-lockfile` | exit 0 |
| 2 | `pnpm vitest run packages/experimental/agent-evidence` | exit 0；Test Files 6 passed (6)，Tests 34 passed (34)（既有 17 + 新 17） |
| 3 | `Get-ChildItem -Recurse -Filter *.tsbuildinfo \| Remove-Item -Force` → `pnpm run build` | exit 0 |
| 4 | `pnpm run gen-cordis-catalog` | exit 0；`115 artifact(s) computed, 0 written`（**非 0 即停**条款未触发） |
| 5 | `git diff --check` | exit 0；8 个触及文件字节级核对均恰一尾随换行（末字节 0x0A、倒数第二字节非 0x0A） |
| 6 | `pnpm run test:docs` | exit 0；`15 passed, 0 failed, 0 skipped`（含 translation pairing：`1172 pair(s) checked … all consistent`） |
| 7 | `git add <写入域>` → `git diff --cached --check` → `git commit --no-verify` | 见提交信息登记 |

- 附加自检：`pnpm vitest run packages/experimental/agent-evidence --coverage --coverage.include='packages/experimental/agent-evidence/src/**'`——`check-runner.ts` 与 `journal.ts` 无 uncovered locations（per-file 100% 对齐）；报告仅列既有 `ids.ts`/`ledger.ts` 缺口（基点既有状态；本波测试只增不减覆盖，全量覆盖归 CI 车道）。
- 复盘：首次 `test:docs` 的 translation pairing 门失败——配对门对 fenced code block 逐字比较（scripts/translation-pairing.ts:311,427），zh 代码块内注释为中文与 en 分叉；按 devframe README 对的既有惯例（代码块英文注释、双语逐字一致）修正 zh 代码块后 `--write` 复录并全绿。

## 5. GAP / 未尽

- 无新增 GAP；设计第 8 节 1-6 原样继承：组合接线缺席（S4 toolface）、台账不镜像 journal 证据、`outputRef` 有界日志捕获缺席、超时固定默认 600s（`timeoutMs` 已留注入缝）、包描述/组表措辞随 toolface 波裁定、Agent Note 归属主树合流波（Worker 写入域不含 `.agents/notes/**`）。
- 环境事实：宿主无 bash；pre-commit（lefthook）以 `--no-verify` 跳过（vendor manifest guard exit 127 环境事实），替代验证收据已写入提交信息正文。
