/** Behavior tests for the agent binding registry over the real storage composition. */

import { expect, describe, it } from 'vitest'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import { harness, type Harness } from './helpers.ts'
import { SessionIdentityError } from '../src/errors.ts'

const CWD = (h: Harness) => join(h.root, `ws-${Math.random().toString(36).slice(2, 8)}`)

describe('createBoundSession', () => {
  it('writes the exact header metadata and one durable record', async () => {
    const h = await harness()
    try {
      const parent = h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })
      const worktree = {
        worktreeId: WorktreeId('wt-1'),
        worktreePath: join(h.root, 'wt-1'),
        branch: 'p/task-7',
      }
      const { session, record } = await h.ctx.agentBindings.createBoundSession({
        cwd: CWD(h),
        role: 'lead',
        parentSessionId: parent.id,
        pluginId: PluginId('agent-reliability'),
        taskId: TaskId('task-7'),
        worktree,
      })
      expect(session.header.cwd).toBeTruthy()
      expect(session.header.parentSession).toBe(parent.id)
      expect(session.header.delegationDepth).toBe(1)
      expect(record.agentId).toBe(session.id)
      expect(record.sessionId).toBe(session.id)
      expect(record.parentSessionId).toBe(parent.id)
      expect(record.role).toBe('lead')
      expect(record.pluginId).toBe('agent-reliability')
      expect(record.taskId).toBe('task-7')
      expect(record.worktreeId).toBe('wt-1')
      expect(record.worktreePath).toBe(worktree.worktreePath)
      expect(record.branch).toBe('p/task-7')
      expect(h.ctx.agentBindings.find(session.id)).toEqual(record)
    } finally {
      await h.dispose()
    }
  })

  it('creates top-level sessions without lineage metadata', async () => {
    const h = await harness()
    try {
      const cwd = CWD(h)
      const { session, record } = await h.ctx.agentBindings.createBoundSession({ cwd, role: 'controller' })
      expect(session.header.cwd).toBe(cwd)
      expect(session.header.parentSession).toBeUndefined()
      expect(session.header.delegationDepth).toBeUndefined()
      expect(record.parentSessionId).toBeUndefined()
      expect(record.worktreeId).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })

  it('rejects an unknown role, an unknown parent, and a depth without a parent', async () => {
    const h = await harness()
    try {
      await expect(h.ctx.agentBindings.createBoundSession({
        cwd: CWD(h), role: 'reviewer' as never,
      })).rejects.toMatchObject({ code: 'SESSION_IDENTITY_INVALID_REQUEST' })
      await expect(h.ctx.agentBindings.createBoundSession({
        cwd: CWD(h), role: 'lead', parentSessionId: SessionId('session-missing'),
      })).rejects.toMatchObject({ code: 'SESSION_IDENTITY_PARENT_UNKNOWN' })
      await expect(h.ctx.agentBindings.createBoundSession({
        cwd: CWD(h), role: 'lead', delegationDepth: 3,
      })).rejects.toMatchObject({ code: 'SESSION_IDENTITY_INVALID_REQUEST' })
      await expect(h.ctx.agentBindings.createBoundSession({
        cwd: 'relative/path', role: 'lead',
      })).rejects.toMatchObject({ code: 'SESSION_IDENTITY_INVALID_REQUEST' })
      expect(h.ctx.agentBindings.list()).toEqual([])
    } finally {
      await h.dispose()
    }
  })
})

describe('bind', () => {
  it('binds a live session created by another entry point', async () => {
    const h = await harness()
    try {
      const session = h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })
      const record = await h.ctx.agentBindings.bind({
        agentId: session.id,
        role: 'worker',
        pluginId: PluginId('agent-evidence'),
        worktree: { worktreeId: WorktreeId('wt-2'), worktreePath: join(h.root, 'wt-2') },
      })
      expect(record.role).toBe('worker')
      expect(record.worktreeId).toBe('wt-2')
      expect(record.branch).toBeUndefined()
      expect(h.ctx.agentBindings.find(session.id)).toEqual(record)
    } finally {
      await h.dispose()
    }
  })

  it('accepts an identical rebind and rejects a conflicting one', async () => {
    const h = await harness()
    try {
      const session = h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })
      const request = { agentId: session.id, role: 'worker' as const, taskId: TaskId('task-1') }
      const first = await h.ctx.agentBindings.bind(request)
      const second = await h.ctx.agentBindings.bind(request)
      expect(second).toEqual(first)
      await expect(h.ctx.agentBindings.bind({ ...request, role: 'lead' }))
        .rejects.toMatchObject({ code: 'SESSION_IDENTITY_ALREADY_BOUND' })
      await expect(h.ctx.agentBindings.bind({ ...request, taskId: TaskId('task-2') }))
        .rejects.toMatchObject({ code: 'SESSION_IDENTITY_ALREADY_BOUND' })
    } finally {
      await h.dispose()
    }
  })

  it('requires the agent to exist and the role to be valid', async () => {
    const h = await harness()
    try {
      await expect(h.ctx.agentBindings.bind({ agentId: SessionId('session-x'), role: 'worker' }))
        .rejects.toMatchObject({ code: 'SESSION_IDENTITY_AGENT_UNKNOWN' })
      await expect(h.ctx.agentBindings.bind({ agentId: SessionId('session-x'), role: 'idle' as never }))
        .rejects.toMatchObject({ code: 'SESSION_IDENTITY_INVALID_REQUEST' })
      await expect(h.ctx.agentBindings.bind({
        agentId: SessionId('session-x'), role: 'worker',
        worktree: { worktreeId: WorktreeId('wt-3'), worktreePath: ' ' },
      })).rejects.toBeInstanceOf(SessionIdentityError)
    } finally {
      await h.dispose()
    }
  })
})

describe('queries', () => {
  it('filters by role and lists in stable order', async () => {
    const h = await harness()
    try {
      const controller = await h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'controller' })
      const lead = await h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'lead' })
      const worker = await h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'worker' })
      expect(h.ctx.agentBindings.byRole('controller').map(r => r.agentId)).toEqual([controller.record.agentId])
      expect(h.ctx.agentBindings.byRole('lead').map(r => r.agentId)).toEqual([lead.record.agentId])
      expect(h.ctx.agentBindings.byRole('worker').map(r => r.agentId)).toEqual([worker.record.agentId])
      expect(h.ctx.agentBindings.list().map(r => r.role)).toEqual(['controller', 'lead', 'worker'])
    } finally {
      await h.dispose()
    }
  })
})

describe('cold restore', () => {
  it('rebuilds every binding from the JSON store after a restart', async () => {
    const h1 = await harness()
    const controller = await h1.ctx.agentBindings.createBoundSession({ cwd: CWD(h1), role: 'controller' })
    const worker = await h1.ctx.agentBindings.bind({
      agentId: h1.ctx.sessions.create(undefined, { meta: { cwd: CWD(h1) } }).id,
      role: 'worker',
      taskId: TaskId('task-9'),
    })
    const root = h1.root
    await h1.dispose({ keepRoot: true })

    const h2 = await harness(root)
    try {
      expect(h2.ctx.sessions.get(controller.session.id)).toBeUndefined()
      expect(h2.ctx.agentBindings.list()).toEqual([controller.record, worker])
      expect(h2.ctx.agentBindings.byRole('worker')).toEqual([worker])
      expect(h2.ctx.agentBindings.find(worker.agentId)?.taskId).toBe('task-9')
      // The restored registry keeps accepting binds over new sessions.
      const next = await h2.ctx.agentBindings.createBoundSession({ cwd: CWD(h2), role: 'lead' })
      expect(h2.ctx.agentBindings.byRole('lead')).toEqual([next.record])
    } finally {
      await h2.dispose()
    }
  })
})
