import { describe, expect, it, vi } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { SubagentRun } from '../src/types.ts'
import { OwnedRuns } from '../src/owned-runs.ts'
import { SubagentStartupCleanupError } from '../src/error.ts'

const owner = (): Agent => ({ id: SessionId('owner') }) as Agent
const run = (dispose = vi.fn(async () => {})): SubagentRun => ({
  id: SessionId('child'), localAgent: undefined,
  result: Promise.resolve({ output: [], stopReason: 'completed' }), dispose,
})

describe('one-shot resource ownership', () => {
  it('retains failed unpublished cleanup until its real provider retry succeeds', async () => {
    const owned = new OwnedRuns()
    const parent = owner()
    const retry = vi.fn().mockRejectedValueOnce(new Error('still alive')).mockResolvedValue(undefined)
    const failure = new SubagentStartupCleanupError([new Error('rollback failed')], 'startup cleanup failed', retry)
    await expect(owned.start(parent, new AbortController().signal, async () => { throw failure })).rejects.toBe(failure)
    expect(owned.has(parent)).toBe(true)
    await expect(owned.drain(parent)).rejects.toThrow('owned subagent disposal failed')
    expect(() =>{  owned.reopen(parent) }).toThrow('retained resources')
    await owned.drain(parent)
    expect(retry).toHaveBeenCalledTimes(2)
    expect(owned.has(parent)).toBe(false)
  })

  it('does not interpret an unreconciled provider rollback failure as quiescence', async () => {
    const owned = new OwnedRuns()
    const parent = owner()
    const failure = new AggregateError([new Error('unknown cleanup')])
    await expect(owned.start(parent, new AbortController().signal, async () => { throw failure })).rejects.toBe(failure)
    await expect(owned.drain(parent)).rejects.toThrow('owned subagent disposal failed')
    expect(owned.has(parent)).toBe(true)
    await expect(owned.dispose()).rejects.toThrow('subagent service disposal failed')
  })

  it('retains completed results until disposal and leaves another exact owner admitted', async () => {
    const owned = new OwnedRuns()
    const parent = owner()
    const foreign = owner()
    const childDispose = vi.fn(async () => {})
    const child = run(childDispose)
    const published = await owned.start(parent, new AbortController().signal, async () => child)
    await published.result
    expect(owned.has(parent)).toBe(true)
    expect(() =>{  owned.reopen(parent) }).toThrow('retained resources')
    await owned.drain(parent)
    expect(childDispose).toHaveBeenCalledTimes(1)
    expect(owned.has(parent)).toBe(false)
    await expect(owned.start(parent, new AbortController().signal, async () => run())).rejects.toMatchObject({ code: 'OWNER_DRAINING' })
    owned.reopen(parent)
    const resumed = await owned.start(parent, new AbortController().signal, async () => run())
    await resumed.dispose()
    await owned.start(foreign, new AbortController().signal, async () => run())
    expect(owned.has(foreign)).toBe(true)
    await owned.dispose()
    expect(() =>{  owned.reopen(parent) }).toThrow('retained resources')
  })

  it('waits for pending startup rollback and prevents late publication', async () => {
    const owned = new OwnedRuns()
    const parent = owner()
    const setup = Promise.withResolvers<SubagentRun>()
    const closed = Promise.withResolvers<undefined>()
    const closing = Promise.withResolvers<undefined>()
    let providerSignal: AbortSignal | undefined
    const started = owned.start(parent, new AbortController().signal, (signal) => {
      providerSignal = signal
      return setup.promise
    })
    const rejected = expect(started).rejects.toMatchObject({ code: 'OWNER_DRAINING' })
    let drained = false
    const drain = owned.drain(parent).then(() => { drained = true })
    expect(providerSignal?.aborted).toBe(true)
    expect(owned.has(parent)).toBe(true)
    setup.resolve(run(vi.fn(async () => { closing.resolve(undefined); await closed.promise })))
    await closing.promise
    expect(drained).toBe(false)
    closed.resolve(undefined)
    await Promise.all([drain, rejected])
    expect(owned.has(parent)).toBe(false)
  })

  it('retains failed disposal for retry and shares concurrent disposal', async () => {
    const owned = new OwnedRuns()
    const parent = owner()
    const failure = new Error('still alive')
    const dispose = vi.fn().mockRejectedValueOnce(failure).mockResolvedValue(undefined)
    const published = await owned.start(parent, new AbortController().signal, async () => run(dispose))
    const first = published.dispose()
    expect(published.dispose()).toBe(first)
    await expect(first).rejects.toBe(failure)
    expect(owned.has(parent)).toBe(true)
    await owned.drain(parent)
    expect(dispose).toHaveBeenCalledTimes(2)
    expect(owned.has(parent)).toBe(false)
  })

  it('clears rejected unpublished setup and fences service teardown', async () => {
    const owned = new OwnedRuns()
    const parent = owner()
    await expect(owned.start(parent, new AbortController().signal, async () => { throw new Error('setup failed') })).rejects.toThrow('setup failed')
    expect(owned.has(parent)).toBe(false)
    await owned.dispose()
    await expect(owned.start(owner(), new AbortController().signal, async () => run())).rejects.toMatchObject({ code: 'OWNER_DRAINING' })
  })
})
