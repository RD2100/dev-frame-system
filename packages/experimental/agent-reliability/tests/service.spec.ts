/** Behavior tests for the agent reliability service. */

import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentReliability, { AgentReliabilityError } from '../src/index.ts'
import type { StopProjectOptions } from '../src/index.ts'

const IDENTITY = { controllerSessionId: 'session-ctrl' as const, goalId: 'goal-1' as const }

/** One booted context with the reliability service mounted. */
async function reliabilityHarness(): Promise<{ ctx: Context; service: AgentReliability; dispose: () => Promise<void> }> {
  const ctx = new Context()
  await ctx.plugin(AgentReliability)
  return { ctx, service: ctx.agentReliability, dispose: () => ctx.fiber.dispose() }
}

describe('admission cutoff', () => {
  it('starts closed and rejects every pre-step until admission opens', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      expect(service.admissionState).toBe('closed')
      expect(() => service.assertAdmitted(IDENTITY)).toThrow(AgentReliabilityError)
    } finally {
      await dispose()
    }
  })

  it('admits exactly the opened identity and rejects mismatched work bindings', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      service.openAdmission(IDENTITY)
      expect(service.admissionState).toBe('open')
      expect(() => service.assertAdmitted(IDENTITY)).not.toThrow()
      expect(() => service.assertAdmitted({ controllerSessionId: 'session-ctrl' as const, goalId: 'goal-2' as const }))
        .toThrowError(/does not match the admitted identity/)
      expect(() => service.assertAdmitted({ controllerSessionId: 'session-other' as const, goalId: 'goal-1' as const }))
        .toThrowError(/does not match the admitted identity/)
    } finally {
      await dispose()
    }
  })

  it('replaces the admitted identity on reopen and closes fail-loud', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      service.openAdmission(IDENTITY)
      const next = { controllerSessionId: 'session-ctrl' as const, goalId: 'goal-2' as const }
      service.openAdmission(next)
      expect(() => service.assertAdmitted(next)).not.toThrow()
      expect(() => service.assertAdmitted(IDENTITY)).toThrow(AgentReliabilityError)
      service.closeAdmission()
      expect(() => service.assertAdmitted(next)).toThrowError(/admission is closed/)
    } finally {
      await dispose()
    }
  })
})

describe('uncertain-call reconciliation', () => {
  it('settles confirmed effects from the probe alone and never retries', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      let retries = 0
      const outcome = await service.reconcileUncertainCall<string>({
        operation: 'create-worktree',
        probe: async () => ({ status: 'confirmed' }),
        retry: async () => { retries += 1; return 'retried' },
      })
      expect(outcome).toEqual({ status: 'settled', via: 'probe' })
      expect(retries).toBe(0)
    } finally {
      await dispose()
    }
  })

  it('retries at most once and only after the probe proved the effect absent', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      let probes = 0
      let retries = 0
      const outcome = await service.reconcileUncertainCall<string>({
        operation: 'create-worktree',
        probe: async () => { probes += 1; return { status: 'absent' } },
        retry: async () => { retries += 1; return 'created' },
      })
      expect(outcome).toEqual({ status: 'settled', via: 'retry', result: 'created' })
      expect(probes).toBe(1)
      expect(retries).toBe(1)
    } finally {
      await dispose()
    }
  })

  it('reports absent without a retry and unresolved without ever resending', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      const absent = await service.reconcileUncertainCall({
        operation: 'delete-worktree',
        probe: async () => ({ status: 'absent' }),
      })
      expect(absent).toEqual({ status: 'absent' })

      let retries = 0
      const unresolved = await service.reconcileUncertainCall({
        operation: 'create-worktree',
        probe: async () => ({ status: 'still_uncertain' }),
        retry: async () => { retries += 1; return 'retried' },
      })
      expect(unresolved).toEqual({ status: 'unresolved' })
      expect(retries).toBe(0)
    } finally {
      await dispose()
    }
  })
})

describe('flush barrier', () => {
  it('keeps admission untouched on a flushed log', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      service.openAdmission(IDENTITY)
      const result = await service.flushBarrier(async () => undefined)
      expect(result.flushed).toBe(true)
      expect(result.admissionClosed).toBe(false)
      expect(result.writerRetained).toBe(false)
      expect(service.admissionState).toBe('open')
    } finally {
      await dispose()
    }
  })

  it('closes admission and retains the writer when the flush fails', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      service.openAdmission(IDENTITY)
      const boom = new Error('session log refused the write')
      const result = await service.flushBarrier(async () => { throw boom })
      expect(result.flushed).toBe(false)
      expect(result.admissionClosed).toBe(true)
      expect(result.writerRetained).toBe(true)
      expect(result.failure).toBe(boom)
      // The cutoff wiring holds after a failed flush: no further dispatch passes.
      expect(() => service.assertAdmitted(IDENTITY)).toThrowError(/admission is closed/)
    } finally {
      await dispose()
    }
  })
})

describe('process-tree stop productization', () => {
  it('delegates the DevFrame stop contract: admission first, quiescence before release', async () => {
    const { service, dispose } = await reliabilityHarness()
    try {
      const order: string[] = []
      const options: StopProjectOptions = {
        agents: [],
        registry: { get: () => { throw new Error('unused without agents') } },
        goals: { disarm: () => undefined, pause: () => undefined },
        jobs: { list: () => [], kill: () => undefined, wait: async () => { throw new Error('unused') } },
        processes: () => [],
        graceMs: 1000,
        closeAdmission: () => { order.push('closeAdmission') },
        record: (observation) => { order.push(`record:${observation.status}`) },
        flush: async () => { order.push('flush') },
        releaseWriter: () => { order.push('releaseWriter') },
      }
      const result = await service.stopProject(options)
      expect(result.status).toBe('stopped')
      expect(result.remaining).toHaveLength(0)
      expect(order).toEqual(['closeAdmission', 'record:stop_requested', 'record:quiescence_confirmed', 'flush', 'releaseWriter'])
    } finally {
      await dispose()
    }
  })
})
