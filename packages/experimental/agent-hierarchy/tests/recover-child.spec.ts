/** Explicit reserved-identity recovery distinguishes absent logs from failed reads. */
import { join } from 'node:path'
import { expect, it, vi } from 'vitest'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { BoundWorktree } from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId } from '@deepseek-ai/dsh-session'
import { SessionPersistenceNotFoundError } from '@deepseek-ai/dsh-session-persistence'
import { harness } from './helpers.ts'

it('recovers the same reservation after an absent-log result and serializes duplicate recovery', async () => {
  const h = await harness()
  try {
    const parent = (await h.ctx.agents.create({ sessionId: SessionId('recovery-parent'), meta: { cwd: h.root } })).agent
    await h.ctx.agentBindings.bind({ agentId: parent.id, role: 'controller' })
    const childId = SessionId('recovery-child')
    const request = {
      cwd: join(h.root, 'child'), role: 'lead' as const, taskId: TaskId('task'), pluginId: PluginId('plugin-a'),
      worktree: { worktreeId: 'recovery-tree' as BoundWorktree['worktreeId'], worktreePath: join(h.root, 'child') },
    }
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, request, {
      sessionId: childId, setup: () => ({ commit() { throw new Error('veto') } }),
    })).rejects.toThrow('veto')
    const before = h.ctx.agentBindings.find(childId)
    const resume = vi.spyOn(h.ctx.agents, 'resume').mockRejectedValue(new SessionPersistenceNotFoundError(childId))
    try {
      const [first, second] = await Promise.all([
        h.ctx.agentHierarchy.recoverChildAgent(parent, request, { sessionId: childId }),
        h.ctx.agentHierarchy.recoverChildAgent(parent, request, { sessionId: childId }),
      ])
      expect(first.agent).toBe(second.agent)
      expect(first.agent.id).toBe(childId)
      expect(first.record).toEqual(before)
      expect(h.ctx.agentBindings.list()).toHaveLength(2)
      expect(resume).toHaveBeenCalledTimes(1)
    } finally { resume.mockRestore() }
  } finally { await h.dispose() }
})

it('keeps corruption and other missing identities from recreating a reserved child', async () => {
  const h = await harness()
  try {
    const parent = (await h.ctx.agents.create({ sessionId: SessionId('failure-parent'), meta: { cwd: h.root } })).agent
    await h.ctx.agentBindings.bind({ agentId: parent.id, role: 'controller' })
    const childId = SessionId('failure-child')
    const request = {
      cwd: join(h.root, 'child'), role: 'lead' as const, taskId: TaskId('task'), pluginId: PluginId('plugin-a'),
      worktree: { worktreeId: 'failure-tree' as BoundWorktree['worktreeId'], worktreePath: join(h.root, 'child') },
    }
    await expect(h.ctx.agentHierarchy.recoverChildAgent(parent, request, { sessionId: childId }))
      .rejects.toThrow('existing child reservation')
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, request, {
      sessionId: childId, setup: () => ({ commit() { throw new Error('veto') } }),
    })).rejects.toThrow('veto')
    const resume = vi.spyOn(h.ctx.agents, 'resume')
    try {
      for (const error of [new Error('corrupt log'), new DOMException('cancelled', 'AbortError'), new SessionPersistenceNotFoundError(SessionId('different'))]) {
        resume.mockRejectedValueOnce(error)
        await expect(h.ctx.agentHierarchy.recoverChildAgent(parent, request, { sessionId: childId })).rejects.toBe(error)
        expect(h.ctx.agents.get(childId)).toBeUndefined()
        expect(h.ctx.sessions.get(childId)).toBeUndefined()
      }
      await expect(h.ctx.agentHierarchy.recoverChildAgent(parent, { ...request, pluginId: PluginId('other') }, { sessionId: childId }))
        .rejects.toThrow('different child binding')
    } finally { resume.mockRestore() }
  } finally { await h.dispose() }
})

it('does not recreate when resumed host setup throws a missing-session error', async () => {
  const h = await harness()
  try {
    const parent = (await h.ctx.agents.create({ sessionId: SessionId('setup-parent'), meta: { cwd: h.root } })).agent
    await h.ctx.agentBindings.bind({ agentId: parent.id, role: 'controller' })
    const childId = SessionId('setup-child')
    const request = {
      cwd: join(h.root, 'child'), role: 'lead' as const, taskId: TaskId('task'), pluginId: PluginId('plugin-a'),
      worktree: { worktreeId: 'setup-tree' as BoundWorktree['worktreeId'], worktreePath: join(h.root, 'child') },
    }
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, request, {
      sessionId: childId, setup: () => ({ commit() { throw new Error('veto') } }),
    })).rejects.toThrow('veto')
    const create = vi.spyOn(h.ctx.agents, 'create')
    const resume = vi.spyOn(h.ctx.agents, 'resume').mockImplementation(options => h.ctx.agents.create({
      sessionId: options.resumeSessionId,
      meta: { cwd: request.cwd, parentSession: parent.id, delegationDepth: 1 },
      ...(options.setup === undefined ? {} : { setup: options.setup }),
    }))
    try {
      const error = new SessionPersistenceNotFoundError(childId)
      await expect(h.ctx.agentHierarchy.recoverChildAgent(parent, request, {
        sessionId: childId, setup() { throw error },
      })).rejects.toBe(error)
      expect(create).toHaveBeenCalledTimes(1)
      expect(h.ctx.agents.get(childId)).toBeUndefined()
      expect(h.ctx.agentBindings.list()).toHaveLength(2)
    } finally {
      resume.mockRestore()
      create.mockRestore()
    }
  } finally { await h.dispose() }
})
