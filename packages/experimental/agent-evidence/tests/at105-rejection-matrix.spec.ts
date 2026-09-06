/**
 * AT1-05 证据拒绝矩阵 + AT1-06 证据引用解析 — 收口自
 * `.agents/devframe/p22/anchor-matrix.md` AT1-05/AT1-06 行（P05 接线波后：六个
 * 拒绝变体中四个已有具名用例——伪造成功、失败/跳过检查、错审查者、错快照；
 * "削弱必需检查"已由 P05 接线波收口为 durable schema 级拒绝（见逐变体对照，
 * 本文件 verificationPayload 已携带自声明覆盖面）；"审查后改未跟踪文件"的重算
 * 实现面已落盘（fprecompute 波 verifySourceFingerprint + P05 接线波完成
 * admission 合取），本文件仍未落具名用例，见其行）与 `docs/testAndAcceptance.md`
 * Part 1 两行断言面。诚实映射：只落有真实实现锚点的用例，其余登记 GAP/语义
 * 差异，不虚构拒绝路径。
 *
 * 逐变体对照（变体 → 实现面结论 → 落点）：
 *
 * | 变体 | 实现面结论 | 落点 / GAP 登记 |
 * | 伪造成功 | 拒绝路径存在于 devframe durable 事件边界：verification 载荷的
 *   passed 聚合与逐 check 结果不一致即拒绝（events.ts verificationEventSchema
 *   superRefine）；台账层为语义差异——受信溯源、入账不判验收（README 已知
 *   限制，at2c-03 相邻锚定） | 本文件 "rejects a fabricated success" |
 * | 失败/跳过检查 | 实现路径存在：skipped 是 check status 一等值；failed/
 *   skipped check 可作为 failed evidence 诚实入账，但永不能支撑 passed 声明
 *   | 本文件 "records failed and skipped checks ..." |
 * | 错审查者 | 已落盘（P05 src 波，设计见 .agents/devframe/p22/p05harden-design.md）：
 *   devframe journal 写入缝构造器强制 DevFrameReviewGate，devframe/review 在
 *   schema 解码后按 reviewerSessionId 交叉授权；evidence 侧 EvidenceReviewGate
 *   （SessionId 键角色目录）抛稳定码 AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED；
 *   投影重放层对 durable role-policy assignments 二次校验。读取面=DevFrame 角色
 *   词表（hierarchy/session-identity 的 AgentRole=controller|lead|worker 无
 *   reviewer，不可授权） | 本文件 "rejects a review submitted by a Session
 *   without the reviewer role"；残余：生产组合接线归 P23/S4 工具面 |
 * | 错快照 | 已落盘（P05 src 波）：GoalBinding/GoalResultBinding/StartGoalRequest
 *   同录 required snapshotId（request→make→record 全链，品牌工厂+非空校验）；
 *   resolveResultBinding 全元组断言含 snapshotId（不一致 → GOAL_BINDING_
 *   IDENTITY_MISMATCH，既有族扩展、只多拒）；durable schema 交叉校验 + 投影重放
 *   双层 fail-closed | 本文件 "rejects a result bound to a different source
 *   snapshot"（snapshotId 探针已入）；bindingsByGoal 双键过滤已由 at2c-04 锚定 |
 * | 审查后改未跟踪文件 | 实现面已落盘（本文件仍无具名用例）：指纹重算引擎
 *   verifySourceFingerprint（fprecompute 波）+ 完成 admission
 *   evaluateCompletionAdmission 指纹先行合取（P05 接线波）；指纹覆盖 tracked
 *   (index) 态，untracked 为已裁定边界 | 实现登记：devframe
 *   source-fingerprint.ts + controller/goal-binding.ts；本文件无用例 |
 * | 削弱必需检查 | 已收口（P05 接线波，设计见
 *   .agents/devframe/p22/required-checks-design.md GAP 节）：durable schema 级
 *   ——verification 载荷自声明 requiredChecks 覆盖面（approved config + canonical
 *   digest），verificationEventSchema 校验 digest 自洽且每条声明 check 被逐字
 *   执行（同 checkId + 精确命令），缺项/换命令的削弱载荷解码即拒；比对面
 *   evaluateRequiredChecks verdict 独立双层拒绝；完成 admission
 *   evaluateCompletionAdmission 按 指纹→检查→审查 序消费 stored config
 *   （digest → config 经 RequiredChecksConfigStore 登记） | schema 级落点：
 *   devframe events.ts verificationEventSchema（本文件 verificationPayload 已
 *   携带声明）；比对面：devframe required-checks.ts；admission：devframe
 *   controller/goal-binding.ts |
 * | AT1-06 重复完成请求无害 | 语义差异：project-controller complete 二次 =
 *   PROJECT_CONTROLLER_ILLEGAL_TRANSITION、integrate 二次 = MARKER_INVALID
 *   （拒绝而非无害）；dsh-goal complete 二次 = GOAL_STALE_REVISION /
 *   GOAL_INVALID_TRANSITION（恰好完成一次、状态不损坏）；append-only 无害语
 *   义仅存在于 dsh-goal recordReceipt（同 revision 重复 receipt 合法且不改
 *   revision）。本包依赖面不可驱动（需 dsh-agent / SessionProjectionRegistry
 *   ） | 语义差异登记，不落用例 |
 * | AT1-06 证据引用可解析 | 实现路径存在（跨服务组合）：devframe 绑定身份 →
 *   agent-evidence bindingsByGoal → byTask 轨迹 → devframe
 *   resolveResultBinding；"无独立验收数据库"由台账设计声明落实（receipt 无
 *   验收字段，at2c-03 已锚） | 本文件 "resolves evidence references ..." |
 *
 * 纪律：真实存储 harness（tests/helpers.ts）、品牌工厂、稳定错误码逐字断
 * 言、合成 id；跨包导入走已声明子路径（controller/goal-binding、shared 与
 * ./src/* 通配）。
 *
 * @module tests/at105-rejection-matrix
 */

import { describe, expect, it } from 'vitest'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { Session, SessionId } from '@deepseek-ai/dsh-session'
import { TaskId as EvidenceTaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { AcceptanceHash, SourceFingerprint, WorkspaceId } from '@deepseek-ai/dsh-experimental-devframe/shared'
import { decodeDevFramePayload, DevFrameReviewId, DevFrameSnapshotId, DevFrameVerificationId } from '@deepseek-ai/dsh-experimental-devframe/src/events.ts'
import { requiredChecksDigest } from '@deepseek-ai/dsh-experimental-devframe/src/required-checks.ts'
import { DevFrameSessionJournal } from '@deepseek-ai/dsh-experimental-devframe/src/session-journal.ts'
import {
  ControllerSessionId,
  GoalBindingController,
  MemoryGoalBindingStore,
  TaskId as StartTaskId,
  createHumanAuthorization,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type {
  GoalBinding,
  GoalResultBinding,
  NativeGoalPort,
  NativeGoalState,
} from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import { EvidenceReviewGate } from '../src/review-gate.ts'
import type { EvidenceReviewerDirectory } from '../src/review-gate.ts'
import { harness } from './helpers.ts'

const WORKSPACE = WorkspaceId('ws-at105')
const CONTROLLER = ControllerSessionId('controller-at105')
const TASK_RAW = 'task-at105'
const ACCEPTANCE = AcceptanceHash('acceptance-at105')
const SOURCE = SourceFingerprint('source-at105')

/** The complete work tuple every devframe verification/review payload carries. */
const RESULT_BINDING: GoalResultBinding = {
  controllerSessionId: SessionId('controller-at105'),
  goalId: GoalId('goal-at105'),
  goalRevision: 2,
  taskIds: [StartTaskId(TASK_RAW)],
  acceptanceHash: ACCEPTANCE,
  workspaceId: WORKSPACE,
  sourceFingerprint: SOURCE,
  snapshotId: DevFrameSnapshotId('snapshot-at105'),
}

/** One configured-check result with a realistic host-captured shape. */
function checkResult(status: 'passed' | 'failed' | 'skipped', id: string) {
  return {
    checkId: id,
    executable: 'pnpm',
    arguments: ['exec', 'vitest', 'run', 'packages/a'],
    cwd: 'C:/ws-at105',
    status,
    ...(status === 'passed' ? { exitCode: 0 } : status === 'failed' ? { exitCode: 1 } : {}),
    durationMs: 12,
  }
}

/** One devframe verification payload over the shared work tuple. */
function verificationPayload(status: 'passed' | 'failed', checks: readonly ReturnType<typeof checkResult>[]) {
  // The payload self-declares the approved checklist it covers (P05 接线波
  // schema 覆盖规则): the declared config is derived from the recorded checks
  // so the honest cases decode and the aggregate-status rejections below keep
  // testing their own rule.
  const declaredConfig = {
    version: 1 as const,
    checks: checks.map(check => ({
      checkId: check.checkId,
      executable: check.executable,
      arguments: [...check.arguments],
      cwd: check.cwd,
    })),
  }
  return {
    version: 1,
    verificationId: DevFrameVerificationId('verification-at105'),
    binding: RESULT_BINDING,
    snapshotId: DevFrameSnapshotId('snapshot-at105'),
    status,
    requiredChecks: { config: declaredConfig, digest: requiredChecksDigest(declaredConfig) },
    checks: [...checks],
  }
}

/** A minimal in-memory native Goal port: create arms, resume advances the revision. */
function fakeGoalPort(): NativeGoalPort & { current: NativeGoalState | undefined } {
  const port: NativeGoalPort & { current: NativeGoalState | undefined } = {
    current: undefined,
    create(_request) {
      port.current = { id: GoalId('goal-at105-1'), revision: 1, phase: 'active' }
      return port.current
    },
    disarm() {
      return port.current
    },
    get() {
      return port.current
    },
    resume(ref) {
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('resume target mismatch')
      }
      port.current = { ...port.current, revision: port.current.revision + 1 }
      return port.current
    },
    complete(ref) {
      if (port.current === undefined || port.current.id !== ref.id) {
        throw new Error('complete target mismatch')
      }
      port.current = { ...port.current, revision: port.current.revision + 1, phase: 'complete' }
      return port.current
    },
  }
  return port
}

/** The start request every controller case runs. */
function startRequest() {
  return {
    objective: 'implement the at105 fixture',
    taskIds: [StartTaskId(TASK_RAW)],
    acceptanceHash: ACCEPTANCE,
    sourceFingerprint: SOURCE,
    snapshotId: DevFrameSnapshotId('snapshot-at105'),
    budget: { maxAttempts: 3 },
    authorization: createHumanAuthorization('confirm-at105'),
  }
}

/** Build the GoalResultBinding reference for one produced binding. */
function resultReference(binding: GoalBinding): GoalResultBinding {
  return {
    controllerSessionId: binding.controllerSessionId,
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    taskIds: binding.taskIds,
    acceptanceHash: binding.acceptanceHash,
    workspaceId: binding.workspaceId,
    sourceFingerprint: binding.sourceFingerprint,
    snapshotId: binding.snapshotId,
  }
}

/** Boot one controller over a fresh in-memory store. */
function controller(): GoalBindingController {
  return new GoalBindingController({
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    goals: fakeGoalPort(),
    store: new MemoryGoalBindingStore(),
  })
}

describe('AT1-05 evidence rejection matrix', () => {
  it('rejects a fabricated success: a passed aggregate over a failed or skipped check', () => {
    // The durable event boundary rejects the success claim the recorded
    // checks contradict; nothing is stored.
    expect(() => decodeDevFramePayload('devframe/verification', verificationPayload('passed', [
      checkResult('failed', 'check-a'),
    ]))).toThrow(/DevFrame devframe\/verification payload is invalid/)
    expect(() => decodeDevFramePayload('devframe/verification', verificationPayload('passed', [
      checkResult('skipped', 'check-b'),
    ]))).toThrow(/DevFrame devframe\/verification payload is invalid/)
  })

  it('records failed and skipped checks as honest failed evidence; a passed claim over them stays rejected', () => {
    const checks = [checkResult('failed', 'check-a'), checkResult('skipped', 'check-b')]

    // Honest evidence: failed/skipped checks are real recorded facts under a
    // failed aggregate; the ledger layer keeps them as provenance too.
    const decoded = decodeDevFramePayload('devframe/verification', verificationPayload('failed', checks))
    expect(decoded.status).toBe('failed')
    expect(decoded.checks.map(check => check.status)).toEqual(['failed', 'skipped'])

    // The same checks can never ride a passed claim.
    expect(() => decodeDevFramePayload('devframe/verification', verificationPayload('passed', checks)))
      .toThrow(/DevFrame devframe\/verification payload is invalid/)
  })

  it('rejects a result bound to a different source snapshot with GOAL_BINDING_IDENTITY_MISMATCH', async () => {
    const h = await harness()
    try {
      const owner = controller()
      const started = await owner.start(startRequest())

      // The exact tuple resolves; a foreign snapshot fingerprint, revision, or
      // snapshot identity cannot.
      expect(owner.resolveResultBinding(resultReference(started))).toEqual(started)
      expect(() => owner.resolveResultBinding({
        ...resultReference(started),
        sourceFingerprint: SourceFingerprint('source-OTHER'),
      })).toThrow(expect.objectContaining({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' }))
      expect(() => owner.resolveResultBinding({
        ...resultReference(started),
        goalRevision: started.goalRevision + 1,
      })).toThrow(expect.objectContaining({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' }))
      expect(() => owner.resolveResultBinding({
        ...resultReference(started),
        snapshotId: DevFrameSnapshotId('snapshot-OTHER'),
      })).toThrow(expect.objectContaining({ code: 'GOAL_BINDING_IDENTITY_MISMATCH' }))

      // The rejection happens before any evidence is recorded.
      expect(h.ctx.agentEvidence.byTask(EvidenceTaskId(TASK_RAW)).bindings).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('rejects a review submitted by a Session without the reviewer role with AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED', async () => {
    const reviewer = SessionId('reviewer-at105')
    const directory: EvidenceReviewerDirectory = {
      roleOf: sessionId => sessionId === reviewer ? 'reviewer' : 'worker',
    }
    const current = Session.create(SessionId('controller-at105-review'), undefined, {
      version: 0,
      id: SessionId('controller-at105-review'),
      createdAt: 0,
      isSeeded: false,
    })
    const journal = new DevFrameSessionJournal(async () => true, new EvidenceReviewGate(directory))
    const reviewPayload = {
      version: 1 as const,
      reviewId: DevFrameReviewId('review-at105'),
      binding: RESULT_BINDING,
      snapshotId: DevFrameSnapshotId('snapshot-at105'),
      reviewerSessionId: SessionId('worker-at105'),
      policyVersion: 'policy-at105',
      decision: 'pass' as const,
      findings: [],
    }

    // A worker cannot submit a review: the gate rejects with the stable code
    // before the event reaches the Session log.
    await expect(journal.append(current, 'devframe/review', reviewPayload))
      .rejects.toMatchObject({ name: 'AgentEvidenceError', code: 'AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED' })

    // An unbound Session identity is rejected the same way.
    await expect(journal.append(current, 'devframe/review', {
      ...reviewPayload,
      reviewerSessionId: SessionId('session-404'),
    })).rejects.toMatchObject({ code: 'AGENT_EVIDENCE_REVIEWER_UNAUTHORIZED' })

    expect(current.snapshotEvents().some(event => event.type === 'devframe/review')).toBe(false)
  })

  it('records a review submitted by the authorized reviewer Session through the same gate', async () => {
    const reviewer = SessionId('reviewer-at105')
    const directory: EvidenceReviewerDirectory = {
      roleOf: sessionId => sessionId === reviewer ? 'reviewer' : 'worker',
    }
    const current = Session.create(SessionId('controller-at105-review'), undefined, {
      version: 0,
      id: SessionId('controller-at105-review'),
      createdAt: 0,
      isSeeded: false,
    })
    const journal = new DevFrameSessionJournal(async () => true, new EvidenceReviewGate(directory))

    const event = await journal.append(current, 'devframe/review', {
      version: 1,
      reviewId: DevFrameReviewId('review-at105'),
      binding: RESULT_BINDING,
      snapshotId: DevFrameSnapshotId('snapshot-at105'),
      reviewerSessionId: reviewer,
      policyVersion: 'policy-at105',
      decision: 'pass',
      findings: [],
    })

    expect(event.data.reviewerSessionId).toBe(reviewer)
    expect(current.snapshotEvents().filter(logged => logged.type === 'devframe/review')).toHaveLength(1)
  })
})

describe('AT1-06 evidence resolution', () => {
  it('resolves evidence references through the Goal binding identity across bindingsByGoal and byTask', async () => {
    const h = await harness()
    try {
      const owner = controller()
      const binding = await owner.start(startRequest())

      // Record the evidence under the exact binding identity the controller produced.
      const taskId = EvidenceTaskId(TASK_RAW)
      const receipt = await h.ctx.agentEvidence.recordTaskGoalBinding({
        taskId,
        controllerSessionId: binding.controllerSessionId,
        goalId: binding.goalId,
        goalRevision: binding.goalRevision,
        workspaceId: binding.workspaceId,
        acceptanceHash: binding.acceptanceHash,
        sourceFingerprint: binding.sourceFingerprint,
      })
      await h.ctx.agentEvidence.recordSubmission({
        taskId,
        submittedBy: SessionId('worker-at105'),
        commit: 'a'.repeat(64),
        changedPaths: ['packages/a/src/fixture.ts'],
        inputDigest: binding.sourceFingerprint,
      })
      await h.ctx.agentEvidence.recordVerification({
        taskId,
        command: 'pnpm exec vitest run packages/a',
        exitCode: 0,
        artifactPaths: [],
      })

      // The Goal identity resolves the binding receipt field-for-field.
      const byGoal = h.ctx.agentEvidence.bindingsByGoal(binding.controllerSessionId, binding.goalId)
      expect(byGoal).toHaveLength(1)
      expect(byGoal[0]?.receiptId).toBe(receipt.receiptId)
      expect(byGoal[0]?.goalRevision).toBe(binding.goalRevision)
      expect(byGoal[0]?.acceptanceHash).toBe(binding.acceptanceHash)
      expect(byGoal[0]?.sourceFingerprint).toBe(binding.sourceFingerprint)
      expect(byGoal[0]?.workspaceId).toBe(binding.workspaceId)
      expect(String(byGoal[0]?.taskId)).toBe(TASK_RAW)

      // The task identity resolves the full three-trail evidence record.
      const trail = h.ctx.agentEvidence.byTask(taskId)
      expect(trail.bindings).toEqual([receipt])
      expect(trail.submissions).toHaveLength(1)
      expect(trail.verifications).toHaveLength(1)

      // The same identity tuple resolves the devframe binding for late results.
      expect(owner.resolveResultBinding(resultReference(binding))).toEqual(binding)
    } finally {
      await h.dispose()
    }
  })
})
