/**
 * AT2C-05 准入切断 fail-closed — anchored from
 * `scenarios/AT2C-05-admission-cutoff-fail-closed.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：admission 进程局部、初值 closed（ADMISSION_CLOSED 文本逐字）；
 * openAdmission 恰为一个 work binding identity 开门，换代即旧身份失配
 * （IDENTITY_MISMATCH 文本逐字）；flushBarrier 成功/失败两形（失败关
 * admission、扣住 writer、failure 携带原因）；恢复唯显式重开。
 *
 * flush 注错按草案为合成 fixture（注定 reject 的 flush 函数），与既有
 * stop/flush 契约测试的 fail-loud 桩同一先例，不触真实 writer。
 *
 * @module tests/at2c-05-admission-cutoff-fail-closed
 */

import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import AgentReliability from '../src/index.ts'

/** The draft's synthetic identities; identity-2/3 swap one half each. */
const IDENTITY1 = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-1') }
const IDENTITY2 = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-2') }
const IDENTITY2B = { controllerSessionId: ControllerSessionId('controller-2'), goalId: GoalId('goal-1') }
const IDENTITY3 = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-3') }

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

describe('AT2C-05 admission cutoff fail closed', () => {
  it('starts closed, opens exactly one identity, and splits closed from mismatch', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability

      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, ADMISSION_CLOSED)

      service.openAdmission(IDENTITY1)
      expect(service.admissionState).toBe('open')
      expect(() =>{  service.assertAdmitted(IDENTITY1) }).not.toThrow()

      // Each mismatched half is its own probe, same stable code.
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY2) }, IDENTITY_MISMATCH)
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY2B) }, IDENTITY_MISMATCH)
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('invalidates the old identity on a new dispatch generation and reports a flushed barrier', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY1)

      service.openAdmission(IDENTITY3)
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, IDENTITY_MISMATCH)
      expect(() =>{  service.assertAdmitted(IDENTITY3) }).not.toThrow()

      const result = await service.flushBarrier(async () => undefined)
      expect(result).toEqual({ flushed: true, admissionClosed: false, writerRetained: false, failure: undefined })
      expect(service.admissionState).toBe('open')
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('closes admission and retains the writer on a failed flush; recovery is an explicit reopen', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY3)

      const fixtureFailure = new Error('the session log refused the write')
      const result = await service.flushBarrier(async () => {
        throw fixtureFailure
      })
      expect(result.flushed).toBe(false)
      expect(result.admissionClosed).toBe(true)
      expect(result.writerRetained).toBe(true)
      expect(result.failure).toBe(fixtureFailure)
      expect(service.admissionState).toBe('closed')

      // Fail-closed in fact, not just in report: dispatch is cut off...
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY3) }, ADMISSION_CLOSED)
      // ...and the only way back is the host's explicit reopen.
      service.openAdmission(IDENTITY3)
      expect(() =>{  service.assertAdmitted(IDENTITY3) }).not.toThrow()
    } finally {
      await ctx.fiber.dispose()
    }
  })
})
