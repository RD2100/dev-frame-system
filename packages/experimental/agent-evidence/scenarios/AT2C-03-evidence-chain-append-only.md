---
description: "AT2C-03 recorded-session 场景草案：证据链 append-only——goal binding（DevFrame 元组）→ submission → verification 三段回执逐字回读，非零 exit code 原样入账，畸形 receipt 逐探针 fail loud 且零落盘。"
kind: "acceptance-scenario-draft"
---

# AT2C-03 场景草案：三段证据链 append-only

包已在 main（agent-evidence 合并提交 `c8992f8154`；本分支基点 `4bc507e332` 验证），场景对其当前契约。

映射：[at2c-runner-checklist](../../../../.agents/devframe/accept/at2c-runner-checklist.md) `AT2C-03`；P22 验收矩阵 `AT1-03`/`AT1-04` 的 P05 责任面（证据链）的模型可见半边（[pluginized-round-registry.md](../../../../.agents/devframe/pluginized-round-registry.md) 6b 节；[testAndAcceptance.md](../../../../docs/testAndAcceptance.md#part-1-acceptance)）。

## 覆盖契约要点

- 三段链各返回 frozen receipt：`recordTaskGoalBinding`（DevFrame goal-result binding 元组：`controllerSessionId`/`goalId`/`goalRevision`/`workspaceId`/`acceptanceHash`/`sourceFingerprint`）→ `recordSubmission`（`commit`/`changedPaths`/`inputDigest`）→ `recordVerification`（`command`/`exitCode`/`artifactPaths`）。
- `receiptId`（randomUUID）与 `recordedAt` 由 ledger/schema 打点，调用方不提供。
- 只记 provenance 不判验收：非零 exit code 原样入账，结果与落盘均无验收字段。
- schema 在持久边界校验并施 brand：畸形 receipt fail loud `AGENT_EVIDENCE_INVALID_RECEIPT`（`receipt failed its schema validation`）且零落盘；`commit` 是 40/64 位小写 hex，路径列表逐项非空 trim，`command` 必须 trim。
- append-only：同 task 重录（新 `goalRevision`、重提交、复检）加行，不改不删。

## 前提（宿主集成）

- 组合挂载 storage 栈 + `@deepseek-ai/dsh-experimental-agent-evidence`（hard-inject `storageDomain`）。
- 模型可见桥由组合挂载波提供（工具桥，落地名草案：`evidence_ledger`），暴露三个 recording 调用，结果携带返回 receipt 或 `AgentEvidenceError` 稳定码文本；桥形态未定前本条记 `blocked`，不降级为包内单测。
- 合成身份种子：controller-1 / worker-1 / t-1 / goal-1；`acceptanceHash`、`sourceFingerprint`、`commit` 均为合成 fixture 值。

## 计划录制布局

`snapshots/session/agent-evidence-chain-append-only/`：`snapshot.yml`（`profile: headless`、`recording: authored`、header pin 同 `text-turn`）；`session.jsonl` 单会话桥探针序列；`workspace.expected/` 固定 `agent_evidence` 域三表（`bindings`/`submissions`/`verifications`）终态行数与字段面（`receiptId`/`recordedAt` 掩码见开放问题）。

## 剧本（replay 步骤）

1. `recordTaskGoalBinding({ taskId: 't-1', controllerSessionId: 'controller-1', goalId: 'goal-1', goalRevision: 3, workspaceId: 'ws-default', acceptanceHash: 'acceptance:sha256:abc…', sourceFingerprint: 'source:sha256:def…' })` → receipt：`receiptId` 存在、`recordedAt` 打点，其余字段逐字回读。
2. `recordSubmission({ taskId: 't-1', submittedBy: 'worker-1', commit: <64-hex>, changedPaths: ['packages/a/src/x.ts'], inputDigest: <同 fingerprint> })` → receipt 逐字回读。
3. `recordVerification({ taskId: 't-1', command: 'pnpm exec vitest run packages/a', exitCode: 0, artifactPaths: ['artifacts/vitest.xml'] })` → snapshot 逐字回读。
4. 失败验证原样入账：`recordVerification({ taskId: 't-1', command: 'pnpm run lint', exitCode: 1, artifactPaths: [] })` → snapshot `exitCode: 1`，先前 snapshot 不被改写。
5. 畸形探针（各自 fail loud、零落盘）：空 `taskId` → `AGENT_EVIDENCE_INVALID_RECEIPT`；大写 hex `commit` → 同码；`changedPaths` 含未 trim 项（`" x.ts"`）→ 同码；`command` 未 trim → 同码。
6. append-only 观察点：同 t-1 重录 binding（`goalRevision: 4`）→ `bindings` 表 2 行、两个 receipt 并存；查询面归 AT2C-04，此处只看落盘行数。

## 可观察通过标准

- 三类 receipt 各字段逐字回读；`receiptId`/`recordedAt` 由 ledger 打点而非调用方（调用方多传也被 schema 面拒绝或覆盖，以首录定案）。
- 非零 exit code 是 recorded fact：桥结果与落盘均为 1，无成功化改写、无验收字段。
- 每个畸形探针零落盘：三表行数不变。

## 环境与安全

合成 taskId/goalId/sessionId；commit 与 digest 为合成 hex fixture；临时 JSON storage 用后清理。

## 开放问题

- 桥落地形态与 receipt 暴露字段面由组合挂载波定；JSONL envelope 以首录回填。
- `workspace.expected` 对 `receiptId`（UUID）/`recordedAt` 的掩码方式由 snapshots 属主定。
- `AGENT_EVIDENCE_PERSISTENCE` 写路径失败需 fault 注入点，归包测试，不挤进首录。
