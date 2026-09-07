/**
 * AT4-01 排队工作重启 — pre-step 注入两分支旅程（纯测试组装切片）。
 *
 * 草案 = anchor-matrix AT4-01 行："排队工作重启：pre-step 拒绝两分支、
 * 显式 resume、身份与限额保持"。缺口（at3-at4-recon.md:32，
 * b5-uncovered-refresh.md §b-3）："排队 controller/child 工作跨进程重启 +
 * 步前/步后两分支 pre-step 拒绝 + 显式 resume 同一 Goal"单一旅程未组装。
 *
 * 本文件按派单口径落两个用例：
 * (a) pre-step 中断（任务前置阶段失败/中止路径）：重启后 admission 进程
 *     局部、初值 closed（src/service.ts:25-26），排队工作的 dispatch
 *     pre-step（assertAdmitted）fail-closed 拒绝——被中断任务不自动续跑、
 *     不自动重放；
 * (b) pre-step 重试路径：恢复唯显式重开（at2c-05:104-106 判据）——
 *     openAdmission 同一 identity 元组后同一 pre-step 放行；换代恰好只认
 *     该身份，换 goal/换 session 一半失配即 IDENTITY_MISMATCH（身份保持）。
 *
 * harness 复用（src/ 零改动）：boot 与断言形状逐字复用本包既有锚——
 * service.spec/at2c-05 的 Context+AgentReliability harness 与
 * expectAssertRejected 逐字 code+message 断言；跨重启 = at4-02 旅程的
 * 进程内模型（宿主死亡 = 丢弃结果并 dispose 第一 Context，重开 = 新
 * Context 重挂服务）。
 *
 * 范围如实登记：真实跨进程重启 + ctx.agents.resume 冷加载（S5 双进程骨架）
 * 归 B1 链 S8-S10 站；组合级显式 resume + 身份/预算保持已由 AT1-09 旅程
 * 证明（start-resume-composition.spec.ts:366,632）。步后分支（已执行保持
 * ambiguous、不作未开始重放）由既有 service.spec:96 与 at4-02:236 锚定，
 * 本切片不重复。零模型调用。
 *
 * @module tests/at4-01-pre-step-injection-journey
 */

import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import AgentReliability from '../src/index.ts'

/** The queued work's binding identity; the swapped variants change one half each. */
const IDENTITY = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-1') }
const GOAL_SWAPPED = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-2') }
const SESSION_SWAPPED = { controllerSessionId: ControllerSessionId('controller-2'), goalId: GoalId('goal-1') }

const ADMISSION_CLOSED = { code: 'AGENT_RELIABILITY_ADMISSION_CLOSED', message: 'admission is closed' }
const IDENTITY_MISMATCH = {
  code: 'AGENT_RELIABILITY_IDENTITY_MISMATCH',
  message: 'work binding does not match the admitted identity; dispatch rejected',
}

/** Assert the sync pre-step throws exactly the given stable code and message. */
function expectAssertRejected(assert: () => void, failure: { code: string; message: string }): void {
  try {
    assert()
    expect.unreachable('the dispatch pre-step must reject')
  } catch (error: unknown) {
    expect(error).toMatchObject(failure)
  }
}

/** One booted context with the reliability service mounted. */
async function bootReliability(): Promise<{ service: AgentReliability; dispose: () => Promise<void> }> {
  const ctx = new Context()
  await ctx.plugin(AgentReliability)
  return { service: ctx.agentReliability, dispose: () => ctx.fiber.dispose() }
}

describe('AT4-01 queued-work pre-step injection journey', () => {
  it('interrupts the queued work at the pre-step gate after a restart and never auto-resumes', async () => {
    // Boot 1: the queued work is admitted and its pre-step passes.
    const first = await bootReliability()
    try {
      first.service.openAdmission(IDENTITY)
      expect(() => first.service.assertAdmitted(IDENTITY)).not.toThrow()
    } finally {
      // The interruption: the host dies with the first context (in-process
      // model, at4-02 journey precedent).
      await first.dispose()
    }

    // Boot 2: admission is process-local, so the restart starts closed.
    const reopened = await bootReliability()
    try {
      expect(reopened.service.admissionState).toBe('closed')
      // The interrupted task's pre-stage rejects fail-closed: no auto-resume,
      // no replay of the queued work.
      expectAssertRejected(() => reopened.service.assertAdmitted(IDENTITY), ADMISSION_CLOSED)
      // The cutoff holds for the whole queue, not one identity.
      expectAssertRejected(() => reopened.service.assertAdmitted(GOAL_SWAPPED), ADMISSION_CLOSED)
    } finally {
      await reopened.dispose()
    }
  })

  it('retries the queued work only through the explicit resume of the same goal identity', async () => {
    const first = await bootReliability()
    try {
      first.service.openAdmission(IDENTITY)
    } finally {
      await first.dispose()
    }

    const reopened = await bootReliability()
    try {
      // Without the explicit resume there is no retry path.
      expectAssertRejected(() => reopened.service.assertAdmitted(IDENTITY), ADMISSION_CLOSED)

      // The host's explicit resume reopens admission for the SAME identity.
      reopened.service.openAdmission(IDENTITY)
      expect(reopened.service.admissionState).toBe('open')
      // The queued work's pre-step passes again: the not-started step is resumable.
      expect(() => reopened.service.assertAdmitted(IDENTITY)).not.toThrow()

      // The resumed generation admits exactly that identity: each swapped half
      // is its own rejection with the stable mismatch code (identity preservation).
      expectAssertRejected(() => reopened.service.assertAdmitted(GOAL_SWAPPED), IDENTITY_MISMATCH)
      expectAssertRejected(() => reopened.service.assertAdmitted(SESSION_SWAPPED), IDENTITY_MISMATCH)
    } finally {
      await reopened.dispose()
    }
  })
})
