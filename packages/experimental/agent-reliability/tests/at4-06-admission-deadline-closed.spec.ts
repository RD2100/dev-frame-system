/**
 * AT4-06 短截止过期→闭准入 — 收口 AT4-06 的截止关闭准入缝（p/at406 波；
 * 『截止已后在途任务的有界取消』半边仍 GAP、语义待总控裁定，本文件不
 * 覆盖在途任务取消）。
 *
 * 断言面：openAdmission 可附 epoch 截止（AdmissionCutoff），截止时刻（含）
 * 起 assertAdmitted 以 AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED 文本逐字
 * 拒绝；非有限截止在 open 处以 AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID
 * 文本逐字 fail-loud 且不触碰当前代际；检查顺序 closed → deadline →
 * identity（截止已过是对窗口的陈述，非对身份的陈述）；存储态与前置步骤
 * 强制执行分离——admissionState 联合不变，admissionCutoff 只报告存储时刻，
 * 截止由前置步骤（唯一派发闸门）执行；与 reconciler 重试（截止先于 retry
 * 的工作）及 flush barrier（失败关闭准入后 ADMISSION_CLOSED 仍优先于截止）
 * 的组合；恢复唯显式重开（新代际）。
 *
 * 时间用 vi.useFakeTimers + vi.setSystemTime 确定性控制墙钟（前置步骤经
 * Date.now 读钟）。无截止准入不受钟针推进影响的既有语义同测（回归守卫）。
 *
 * @module tests/at4-06-admission-deadline-closed
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import AgentReliability, { AgentReliabilityError } from '../src/index.ts'

/** The draft's synthetic identities; identity-2 swaps the goal half. */
const IDENTITY1 = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-1') }
const IDENTITY2 = { controllerSessionId: ControllerSessionId('controller-1'), goalId: GoalId('goal-2') }

const ADMISSION_CLOSED = { code: 'AGENT_RELIABILITY_ADMISSION_CLOSED', message: 'admission is closed' }
const IDENTITY_MISMATCH = {
  code: 'AGENT_RELIABILITY_IDENTITY_MISMATCH',
  message: 'work binding does not match the admitted identity; dispatch rejected',
}
const DEADLINE_CLOSED = {
  code: 'AGENT_RELIABILITY_ADMISSION_DEADLINE_CLOSED',
  message: 'admission deadline has passed; dispatch rejected',
}
const DEADLINE_INVALID = {
  code: 'AGENT_RELIABILITY_ADMISSION_DEADLINE_INVALID',
  message: 'admission deadline must be a finite epoch millisecond instant',
}

/** The deterministic wall-clock base every test rewinds to. */
const BASE = 1_700_000_000_000

/** Assert the guarded sync call throws exactly the given stable code and message. */
function expectAssertRejected(assert: () => void, failure: { code: string; message: string }): void {
  try {
    assert()
    expect.unreachable('the guarded call must reject')
  } catch (error: unknown) {
    expect(error).toMatchObject(failure)
  }
}

describe('AT4-06 admission deadline closed', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(BASE)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('admits before the cutoff and rejects from the deadline instant onward', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      const deadline = BASE + 1000
      service.openAdmission(IDENTITY1, { deadline })

      vi.setSystemTime(deadline - 1)
      expect(() =>{  service.assertAdmitted(IDENTITY1) }).not.toThrow()

      // The deadline instant itself is inclusive: already rejected.
      vi.setSystemTime(deadline)
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, DEADLINE_CLOSED)

      vi.setSystemTime(deadline + 5)
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, DEADLINE_CLOSED)

      // A generation whose deadline is already past opens fine ...
      service.openAdmission(IDENTITY2, { deadline: BASE - 1000 })
      expect(service.admissionState).toBe('open')
      // ... and its first pre-step call rejects DEADLINE_CLOSED.
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY2) }, DEADLINE_CLOSED)
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('keeps the three rejections distinguishable across the deadline', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      const deadline = BASE + 1000

      // closed stays its own code before anything is opened.
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, ADMISSION_CLOSED)

      service.openAdmission(IDENTITY1, { deadline })
      vi.setSystemTime(deadline - 1)
      // Before the deadline the wrong identity is the visible failure ...
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY2) }, IDENTITY_MISMATCH)

      vi.setSystemTime(deadline)
      // ... after it even that wrong identity reports the dead window:
      // the deadline check precedes the identity check.
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY2) }, DEADLINE_CLOSED)
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, DEADLINE_CLOSED)
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('fails loud on a non-finite cutoff and leaves the current generation untouched', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY1)

      expectAssertRejected(() =>{  service.openAdmission(IDENTITY2, { deadline: Number.NaN }) }, DEADLINE_INVALID)
      expectAssertRejected(() =>{  service.openAdmission(IDENTITY2, { deadline: Number.POSITIVE_INFINITY }) }, DEADLINE_INVALID)

      // Validation precedes mutation: the current generation survives both
      // rejected opens unchanged.
      expect(() =>{  service.assertAdmitted(IDENTITY1) }).not.toThrow()
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY2) }, IDENTITY_MISMATCH)
      expect(service.admissionState).toBe('open')
      expect(service.admissionCutoff).toBeUndefined()
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('pins stored state against pre-step enforcement', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      const deadline = BASE + 1000
      service.openAdmission(IDENTITY1, { deadline })

      vi.setSystemTime(deadline)
      // Stored state keeps reporting the open generation and its cutoff ...
      expect(service.admissionState).toBe('open')
      expect(service.admissionCutoff).toBe(deadline)
      // ... while the pre-step enforces the dead window.
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, DEADLINE_CLOSED)

      service.closeAdmission()
      expect(service.admissionState).toBe('closed')
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, ADMISSION_CLOSED)
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('recovers only through an explicit reopen with a fresh generation', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY1, { deadline: BASE + 1000 })
      vi.setSystemTime(BASE + 1000)
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, DEADLINE_CLOSED)

      // The reopen is a fresh generation: new identity, new cutoff.
      service.openAdmission(IDENTITY2, { deadline: Date.now() + 1000 })
      expect(() =>{  service.assertAdmitted(IDENTITY2) }).not.toThrow()
      expect(service.admissionCutoff).toBe(BASE + 2000)
      // The old identity is now a plain mismatch of the new generation.
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, IDENTITY_MISMATCH)
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('leaves no-cutoff admission unchanged', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY1)
      expect(service.admissionCutoff).toBeUndefined()

      // Arbitrary clock advances never close an unbounded generation.
      vi.setSystemTime(BASE + 3_600_000)
      expect(() =>{  service.assertAdmitted(IDENTITY1) }).not.toThrow()
      vi.setSystemTime(BASE + 86_400_000)
      expect(() =>{  service.assertAdmitted(IDENTITY1) }).not.toThrow()
      expect(service.admissionCutoff).toBeUndefined()
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('routes reconciliation retries through the cutoff', async () => {
    const ctxA = new Context()
    const ctxB = new Context()
    try {
      await ctxA.plugin(AgentReliability)
      await ctxB.plugin(AgentReliability)
      const serviceA = ctxA.agentReliability
      const serviceB = ctxB.agentReliability

      // (1) Before the deadline: the probe proves absence, then the retry
      // runs the pre-step and produces the effect exactly once.
      serviceA.openAdmission(IDENTITY1, { deadline: BASE + 1000 })
      const runsA = { count: 0 }
      const settled = await serviceA.reconcileUncertainCall({
        operation: 'create-worktree',
        probe: async () => ({ status: 'absent' }),
        retry: async () => {
          serviceA.assertAdmitted(IDENTITY1)
          runsA.count += 1
          return 'created'
        },
      })
      expect(settled).toEqual({ status: 'settled', via: 'retry', result: 'created' })
      expect(runsA.count).toBe(1)

      // (2) After the deadline: the seam cuts the retry before any work starts.
      serviceB.openAdmission(IDENTITY1, { deadline: BASE + 1000 })
      vi.setSystemTime(BASE + 1000)
      const runsB = { count: 0 }
      const rejected = serviceB.reconcileUncertainCall({
        operation: 'create-worktree',
        probe: async () => ({ status: 'absent' }),
        retry: async () => {
          serviceB.assertAdmitted(IDENTITY1)
          runsB.count += 1
          return 'created'
        },
      })
      await expect(rejected).rejects.toBeInstanceOf(AgentReliabilityError)
      await expect(rejected).rejects.toMatchObject(DEADLINE_CLOSED)
      expect(runsB.count).toBe(0)
    } finally {
      await ctxA.fiber.dispose()
      await ctxB.fiber.dispose()
    }
  })

  it('keeps ADMISSION_CLOSED precedence over the deadline after a failed flush', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability
      service.openAdmission(IDENTITY1, { deadline: BASE + 1000 })

      const fixtureFailure = new Error('the session log refused the write')
      const result = await service.flushBarrier(async () => {
        throw fixtureFailure
      })
      expect(result.flushed).toBe(false)
      expect(result.admissionClosed).toBe(true)
      expect(result.writerRetained).toBe(true)
      expect(result.failure).toBe(fixtureFailure)

      vi.setSystemTime(BASE + 1000)
      // A manually closed window reports closed, not the dead deadline.
      expect(service.admissionState).toBe('closed')
      expectAssertRejected(() =>{  service.assertAdmitted(IDENTITY1) }, ADMISSION_CLOSED)
    } finally {
      await ctx.fiber.dispose()
    }
  })
})
