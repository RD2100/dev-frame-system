import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'
import { GoalId } from '@deepseek-ai/dsh-goal'
import { ControllerSessionId } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import AgentReliability, { type StopProjectOptions } from '../src/index.ts'

const identity = { controllerSessionId: ControllerSessionId('deadline-owner'), goalId: GoalId('deadline-goal') }

afterEach(() => { vi.useRealTimers() })

async function fixture() {
  const ctx = new Context()
  await ctx.plugin(AgentReliability)
  const release = vi.fn()
  const fence = vi.fn()
  const options: StopProjectOptions = {
    agents: [], registry: { get: () => undefined },
    goals: { disarm: () => undefined, pause: vi.fn() },
    jobs: { list: () => [], kill: vi.fn(), wait: vi.fn() },
    processes: () => [], graceMs: 1000,
    closeAdmission: fence, record: vi.fn(), flush: async () => {}, releaseWriter: release,
  }
  return { ctx, service: ctx.agentReliability, options, release, fence }
}

describe('admission deadline stop lifecycle', () => {
  it.each(['cancel', 'identity'] as const)('retains ownership when %s cannot be confirmed', async (failure) => {
    vi.useFakeTimers()
    const { ctx, service, options, release } = await fixture()
    const agent = {
      id: SessionId('deadline-worker'),
      cancel: () => { throw new Error('cancel failed') },
      whenIdle: async () => {},
    } as unknown as Agent
    const stop = { ...options, agents: [agent], registry: { get: () => failure === 'identity' ? undefined : agent } }
    try {
      service.openAdmission(identity, { deadline: Date.now(), stop })
      await vi.advanceTimersByTimeAsync(1)
      const result = await service.deadlineStopResult
      expect(result?.status).toBe('needs_attention')
      expect(result?.remaining.some(issue => issue.reason === (failure === 'identity' ? 'identity_unknown' : 'operation_failed'))).toBe(true)
      expect(release).not.toHaveBeenCalled()
      expect(service.admissionState).toBe('closed')
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('does not clamp a distant deadline into an immediate stop', async () => {
    vi.useFakeTimers()
    const { ctx, service, options, fence } = await fixture()
    try {
      service.openAdmission(identity, { deadline: Date.now() + 2_147_483_647 + 100, stop: options })
      await vi.advanceTimersByTimeAsync(2_147_483_647)
      expect(fence).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(100)
      expect(await service.deadlineStopResult).toEqual({ status: 'stopped', remaining: [] })
      expect(fence).toHaveBeenCalledOnce()
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('rejects invalid stop grace before replacing the admitted generation', async () => {
    vi.useFakeTimers()
    const { ctx, service, options, fence } = await fixture()
    try {
      const at = Date.now() + 100
      service.openAdmission(identity, { deadline: at, stop: options })
      expect(() => { service.openAdmission(identity, { deadline: at + 500, stop: { ...options, graceMs: 0 } }) }).toThrow('stop graceMs')
      expect(service.admissionCutoff).toBe(at)
      await vi.advanceTimersByTimeAsync(100)
      await service.deadlineStopResult
      expect(fence).toHaveBeenCalledOnce()
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('closes service admission before the host fence and releases only after flush', async () => {
    vi.useFakeTimers()
    const { ctx, service, options, release } = await fixture()
    const flush = Promise.withResolvers<undefined>()
    const stop = { ...options, closeAdmission: () => { expect(service.admissionState).toBe('closed') }, flush: () => flush.promise }
    try {
      service.openAdmission(identity, { deadline: Date.now() + 100, stop })
      await vi.advanceTimersByTimeAsync(100)
      expect(service.admissionState).toBe('closed')
      expect(release).not.toHaveBeenCalled()
      expect(() => { service.openAdmission(identity) }).toThrow('stop is still running')
      flush.resolve(undefined)
      expect(await service.deadlineStopResult).toEqual({ status: 'stopped', remaining: [] })
      expect(release).toHaveBeenCalledOnce()
      service.openAdmission(identity)
      expect(service.deadlineStopResult).toBeUndefined()
    } finally {
      flush.resolve(undefined)
      await ctx.fiber.dispose()
    }
  })

  it.each(['reopen', 'close', 'dispose'] as const)('disarms a queued old deadline on %s', async (action) => {
    vi.useFakeTimers()
    const { ctx, service, options, fence } = await fixture()
    try {
      service.openAdmission(identity, { deadline: Date.now() + 100, stop: options })
      if (action === 'reopen') service.openAdmission({ ...identity, goalId: GoalId('new-goal') })
      else if (action === 'close') service.closeAdmission()
      else await ctx.fiber.dispose()
      await vi.advanceTimersByTimeAsync(1000)
      expect(fence).not.toHaveBeenCalled()
      expect(vi.getTimerCount()).toBe(0)
      expect(service.admissionState).toBe(action === 'reopen' ? 'open' : 'closed')
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('retains the writer when the stop protocol reports a failed flush', async () => {
    vi.useFakeTimers()
    const { ctx, service, options, release } = await fixture()
    const stop = { ...options, flush: async () => { throw new Error('private flush failure') } }
    try {
      service.openAdmission(identity, { deadline: Date.now(), stop })
      await vi.advanceTimersByTimeAsync(1)
      const result = await service.deadlineStopResult
      expect(result?.status).toBe('needs_attention')
      expect(result?.remaining).toContainEqual({ resource: 'session:flush', reason: 'operation_failed' })
      expect(JSON.stringify(result)).not.toContain('private flush failure')
      expect(release).not.toHaveBeenCalled()
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('waits for an already-triggered stop when its service is disposed', async () => {
    vi.useFakeTimers()
    const { ctx, service, options } = await fixture()
    const flush = Promise.withResolvers<undefined>()
    const stop = { ...options, flush: () => flush.promise }
    try {
      service.openAdmission(identity, { deadline: Date.now(), stop })
      await vi.advanceTimersByTimeAsync(1)
      let disposed = false
      const disposal = ctx.fiber.dispose().then(() => { disposed = true })
      await Promise.resolve()
      expect(disposed).toBe(false)
      flush.resolve(undefined)
      await disposal
      expect(disposed).toBe(true)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      flush.resolve(undefined)
      await ctx.fiber.dispose()
    }
  })
})
