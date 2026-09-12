import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { describe, expect, it, vi } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'
import { JobId, type JobSnapshot } from '@deepseek-ai/dsh-jobs'
import type { SubprocessHandle } from '@deepseek-ai/dsh-subprocess'
import { spawnSubprocess } from '../../../../subprocess/subprocess-local/src/spawn.ts'
import { stopProject, type StopObservation, type StopProjectOptions } from '../../src/reliability/stop.ts'

function fixture() {
  const events: string[] = []
  const records: StopObservation[] = []
  const cancel = vi.fn(() => { events.push('cancel') })
  const whenIdle = vi.fn(async () => { events.push('idle') })
  const agent = {
    id: SessionId('stop-owner'),
    cancel,
    whenIdle,
  } as unknown as Agent
  const options: StopProjectOptions = {
    agents: [agent],
    registry: { get: () => agent },
    goals: { disarm: vi.fn(() => undefined), pause: vi.fn() },
    jobs: { list: () => [], kill: vi.fn(), wait: vi.fn() },
    processes: () => [],
    graceMs: 1000,
    closeAdmission: vi.fn(() => { events.push('closed') }),
    record: vi.fn((record: StopObservation) => { records.push(record); events.push(record.status) }),
    flush: vi.fn(async () => { events.push('flushed') }),
    releaseWriter: vi.fn(() => { events.push('released') }),
  }
  return { agent, cancel, whenIdle, options, events, records }
}

describe('project stop', () => {
  it('awaits owned lifecycle disposal before writer release', async () => {
    const f = fixture()
    const started = Promise.withResolvers<undefined>()
    const released = Promise.withResolvers<undefined>()
    const result = stopProject({
      ...f.options,
      processes: () => [{ ownerSession: f.agent.id, label: 'pty', operationId: 'pty:owner', drain: async () => {
        started.resolve(undefined)
        await released.promise
      } }],
    })
    await started.promise
    expect(f.options.releaseWriter).not.toHaveBeenCalled()
    released.resolve(undefined)
    expect(await result).toEqual({ status: 'stopped', remaining: [] })
  })

  it('retains the writer after failed owned lifecycle disposal and rejects foreign ownership', async () => {
    const f = fixture()
    const foreign = vi.fn(async () => {})
    const result = await stopProject({
      ...f.options,
      processes: () => [
        { ownerSession: f.agent.id, label: 'pty', drain: async () => { throw new Error('close failed') } },
        { ownerSession: SessionId('foreign'), label: 'foreign', drain: foreign },
      ],
    })
    expect(result).toEqual({ status: 'needs_attention', remaining: [
      { resource: 'process:foreign', reason: 'identity_unknown' },
      { resource: 'process:pty', reason: 'operation_failed' },
    ] })
    expect(foreign).not.toHaveBeenCalled()
    expect(f.options.releaseWriter).not.toHaveBeenCalled()
  })

  it('keeps pending inbox work and releases only after quiescence and flush', async () => {
    const f = fixture()
    expect(await stopProject(f.options)).toEqual({ status: 'stopped', remaining: [] })
    expect(f.cancel).toHaveBeenCalledWith({ kind: 'user' }, { keepInbox: true })
    expect(f.events).toEqual(['closed', 'stop_requested', 'cancel', 'idle', 'quiescence_confirmed', 'flushed', 'released'])
  })

  it('retains ownership for an agent that ignores cancellation', async () => {
    const f = fixture()
    vi.mocked(f.whenIdle).mockReturnValue(new Promise(() => {}))
    const result = await stopProject({ ...f.options, graceMs: 20 })
    expect(result.status).toBe('needs_attention')
    expect(result.remaining).toContainEqual({ resource: 'agent:stop-owner', reason: 'timeout' })
    expect(f.options.releaseWriter).not.toHaveBeenCalled()
  })

  it('retains ownership when a restored process has no verified handle', async () => {
    const f = fixture()
    const result = await stopProject({
      ...f.options, processes: () => [{ ownerSession: f.agent.id, label: 'old-operation', operationId: 'old-operation' }],
    })
    expect(result).toEqual({ status: 'needs_attention', remaining: [
      { resource: 'process:old-operation', reason: 'identity_unknown' },
    ] })
    expect(f.options.releaseWriter).not.toHaveBeenCalled()
  })

  it('terminates distinct same-label handles independently', async () => {
    const f = fixture()
    const first = {
      pid: 1,
      stdin: undefined,
      stdout: undefined,
      stderr: undefined,
      collected: {},
      terminate: vi.fn(),
      done: Promise.resolve({ exitCode: null, signal: 'SIGTERM' as const }),
      waitForExit: vi.fn(async () => true),
    } satisfies SubprocessHandle
    const second = {
      pid: 2,
      stdin: undefined,
      stdout: undefined,
      stderr: undefined,
      collected: {},
      terminate: vi.fn(),
      done: Promise.resolve({ exitCode: null, signal: 'SIGTERM' as const }),
      waitForExit: vi.fn(async () => true),
    } satisfies SubprocessHandle
    const result = await stopProject({
      ...f.options,
      processes: () => [
        { ownerSession: f.agent.id, label: 'same-label', handle: first },
        { ownerSession: f.agent.id, label: 'same-label', handle: second },
      ],
    })
    expect(result).toEqual({ status: 'stopped', remaining: [] })
    expect(first.terminate).toHaveBeenCalledOnce()
    expect(second.terminate).toHaveBeenCalledOnce()
    expect(first.waitForExit).toHaveBeenCalledOnce()
    expect(second.waitForExit).toHaveBeenCalledOnce()
  })

  it('retains ownership if final persistence fails', async () => {
    const f = fixture()
    const result = await stopProject({ ...f.options, flush: async () => { throw new Error('disk full') } })
    expect(result).toEqual({ status: 'needs_attention', remaining: [
      { resource: 'session:flush', reason: 'operation_failed' },
    ] })
    expect(f.options.releaseWriter).not.toHaveBeenCalled()
  })

  it('cancels only owner jobs, including a job registered by an already running tool', async () => {
    const f = fixture()
    const job = (id: string, ownerSession?: SessionId): JobSnapshot => ({
      id: JobId(id), kind: 'bash', label: id, status: 'running', startedAt: 0, reported: false,
      ...ownerSession === undefined ? {} : { ownerSession },
    })
    const own = job('bash-1', f.agent.id)
    const late = job('bash-2', f.agent.id)
    const unowned = job('bash-3')
    let drained = false
    vi.mocked(f.whenIdle).mockImplementation(async () => { drained = true })
    const kill = vi.fn<(id: ReturnType<typeof JobId>, agent: Agent, reason: string) => 'requested'>(() => 'requested')
    const result = await stopProject({ ...f.options, jobs: {
      list: () => drained ? [own, late, unowned] : [own, unowned],
      kill,
      wait: async id => ({ ...own, id, status: 'killed' }),
    } })
    expect(result.status).toBe('stopped')
    expect(kill.mock.calls.map(call => call[0])).toEqual([own.id, late.id])
  })

  it('stops a real owned descendant before its marker can continue changing', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'devframe-stop-'))
    const marker = join(directory, 'writes.txt')
    const leaf = `const fs=require('node:fs');setInterval(()=>fs.appendFileSync(${JSON.stringify(marker)},'x'),15)`
    const parent = `require('node:child_process').spawn(process.execPath,['-e',${JSON.stringify(leaf)}],{stdio:'inherit'});setInterval(()=>{},1000)`
    const handle = spawnSubprocess({
      argv: [process.execPath, '-e', parent], cwd: directory, graceMs: 50,
      stdio: { stdin: 'ignore', stdout: { maxBytes: 1000 }, stderr: { maxBytes: 1000 } },
    })
    const f = fixture()
    try {
      await vi.waitFor(async () => { expect((await readFile(marker, 'utf8')).length).toBeGreaterThan(0) }, { timeout: 5000 })
      const process = { ownerSession: f.agent.id, label: 'owned-tree', handle }
      const result = await stopProject({ ...f.options, graceMs: 5000, processes: () => [process] })
      expect(result).toEqual({ status: 'stopped', remaining: [] })
      expect(await handle.waitForExit()).toBe(true)
      const stoppedBytes = await readFile(marker, 'utf8')
      await delay(100)
      expect(await readFile(marker, 'utf8')).toBe(stoppedBytes)
      expect(f.options.releaseWriter).toHaveBeenCalledOnce()
    } finally {
      handle.terminate()
      await handle.done
      await handle.waitForExit()
      await rm(directory, { recursive: true, force: true })
    }
  }, 10000)
})
