/**
 * Stop-writer exclusion over the real worktree agent locks: `stopProject`
 * hands a worktree's single-writer binding to the next session only after a
 * fully confirmed stop. While cancellation fails or an identity stays
 * unknown — or the release itself is refused — the real registry keeps the
 * binding with the original writer, and a second session's bind attempt meets
 * the real classified refusal instead of a silent takeover.
 * @module tests/reliability/stop-writer-exclusion
 */

import { rm } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorktreeLockError, WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { Worktree } from '@deepseek-ai/dsh-worktree-registry'
import { stopProject, type StopObservation, type StopProjectOptions } from '../../src/reliability/stop.ts'
import { harness, type Harness } from '../../../../workflow/worktree-registry/tests/helpers.ts'

const WRITER = WorktreeLockHolder('stop-owner-session')
const SECOND = WorktreeLockHolder('second-session')

const preparedHarnesses: Harness[] = []

afterEach(async () => {
  const prepared = preparedHarnesses.splice(0)
  await Promise.all(prepared.map(async (h) => {
    await h.ctx.fiber.dispose()
    await rm(h.root, { recursive: true, force: true })
  }))
})

/** An owner agent shaped like the shared stop fixture; the lock authority is always the real registry. */
function ownerAgent(cancel: () => void = () => {}): Agent {
  return {
    id: SessionId('stop-owner'),
    cancel,
    whenIdle: async () => {},
  } as unknown as Agent
}

/**
 * Boot the real registry composition, register one worktree bound to
 * {@link WRITER}, and build stop options whose writer release is the holder's
 * own real unbind.
 */
async function fixture(agent: Agent, overrides: Partial<StopProjectOptions> = {}) {
  const prepared = await harness()
  preparedHarnesses.push(prepared)
  const { workspaceId } = await prepared.createRepoWorkspace('repo')
  const tree = await prepared.ctx.worktreeRegistry.create({
    workspaceId,
    path: join(prepared.root, 'wt-stop'),
    branch: 'feature/stop',
  })
  await prepared.ctx.worktreeRegistry.bind(tree.id, WRITER)
  const records: StopObservation[] = []
  let releaseCalls = 0
  let release: Promise<Worktree> | undefined
  const options: StopProjectOptions = {
    agents: [agent],
    registry: { get: () => agent },
    goals: {
      disarm: () => undefined,
      pause: () => { throw new Error('no active goal survives disarm') },
    },
    jobs: {
      list: () => [],
      kill: () => 'requested',
      wait: async () => { throw new Error('no job is ever started here') },
    },
    processes: () => [],
    graceMs: 1000,
    closeAdmission: () => {},
    record: (observation) => { records.push(observation) },
    flush: async () => {},
    releaseWriter: () => {
      releaseCalls += 1
      release = prepared.ctx.worktreeRegistry.unbind(tree.id, WRITER)
    },
    ...overrides,
  }
  return {
    prepared,
    tree,
    row: () => prepared.ctx.worktreeRegistry.list(workspaceId).find(entry => entry.id === tree.id),
    records,
    options,
    releaseCalls: () => releaseCalls,
    release: () => release,
  }
}

/** Bind the same worktree as the second session and return the rejection, or the resolved row if the bind was not refused. */
async function secondSessionBind(prepared: Harness, tree: Worktree): Promise<unknown> {
  return await prepared.ctx.worktreeRegistry.bind(tree.id, SECOND).catch((error: unknown) => error)
}

describe('stop writer exclusion over real agent locks', () => {
  it('keeps the worktree bound to its writer when cancellation is refused, and refuses the second session on the real lock surface', async () => {
    const f = await fixture(ownerAgent(() => { throw new Error('cancel refused') }))
    const result = await stopProject(f.options)
    expect(result.status).toBe('needs_attention')
    expect(result.remaining).toEqual([{ resource: 'agent:stop-owner', reason: 'operation_failed' }])
    expect(f.records.map(record => record.status)).toEqual(['stop_requested', 'needs_attention'])
    expect(f.releaseCalls()).toBe(0)
    expect(f.row()?.lockedBy).toBe(WRITER)
    expect(f.row()?.lockedAt).toBeTypeOf('string')

    const seizure = await secondSessionBind(f.prepared, f.tree)
    expect(seizure).toBeInstanceOf(WorktreeLockError)
    expect((seizure as WorktreeLockError).kind).toBe('already-locked')
    expect((seizure as WorktreeLockError).message).toContain('already bound to writer')
    expect(f.row()?.lockedBy).toBe(WRITER)
  })

  it('keeps the worktree bound across an identity-unknown stop, and refuses the second session', async () => {
    const f = await fixture(ownerAgent(), { registry: { get: () => undefined } })
    const result = await stopProject(f.options)
    expect(result.status).toBe('needs_attention')
    expect(result.remaining).toEqual([{ resource: 'agent:stop-owner', reason: 'identity_unknown' }])
    expect(f.releaseCalls()).toBe(0)
    expect(f.row()?.lockedBy).toBe(WRITER)

    const seizure = await secondSessionBind(f.prepared, f.tree)
    expect(seizure).toBeInstanceOf(WorktreeLockError)
    expect((seizure as WorktreeLockError).kind).toBe('already-locked')
    expect((seizure as WorktreeLockError).message).toContain('already bound to writer')
    expect(f.row()?.lockedBy).toBe(WRITER)
  })

  it('releases the binding through the real registry on the stopped path, and hands the worktree to the second session', async () => {
    const f = await fixture(ownerAgent())
    const result = await stopProject(f.options)
    expect(result).toEqual({ status: 'stopped', remaining: [] })
    expect(f.records.map(record => record.status)).toEqual(['stop_requested', 'quiescence_confirmed'])
    expect(f.releaseCalls()).toBe(1)
    const release = f.release()
    expect(release).toBeInstanceOf(Promise)
    await release
    expect(f.row()?.lockedBy).toBeUndefined()
    expect(f.row()?.lockedAt).toBeUndefined()

    await f.prepared.ctx.worktreeRegistry.bind(f.tree.id, SECOND)
    expect(f.row()?.lockedBy).toBe(SECOND)
  })

  it('keeps the binding when the writer release itself is refused', async () => {
    const f = await fixture(ownerAgent(), {
      releaseWriter: () => { throw new Error('release refused by the owner check') },
    })
    const result = await stopProject(f.options)
    expect(result).toEqual({
      status: 'needs_attention',
      remaining: [{ resource: 'writer:release', reason: 'operation_failed' }],
    })
    expect(f.row()?.lockedBy).toBe(WRITER)
  })
})
