/** Child creation persists role and lineage before Agent publication. */
import { join } from 'node:path'
import { expect, it } from 'vitest'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { BoundWorktree } from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId } from '@deepseek-ai/dsh-session'
import { baseConfig, harness } from './helpers.ts'

it('binds factory-owned sessions before publication without taking their lifecycle ownership', async () => {
  const h = await harness()
  try {
    const id = SessionId('factory-bound-lead')
    let observedRole: string | undefined
    h.ctx.on('agent/created', ({ agent }) => {
      if (agent.id === id) observedRole = h.ctx.agentBindings.find(id)?.role
    })
    const handle = await h.ctx.agents.create({
      sessionId: id,
      meta: { cwd: h.root },
      async setup(childCtx) {
        const child = childCtx.agent!
        expect(h.ctx.sessions.get(id)).toBeUndefined()
        expect(h.ctx.agents.get(id)).toBeUndefined()
        await h.ctx.agentBindings.bindPreparedSession(child.session, { role: 'lead' })
        expect(h.ctx.sessions.get(id)).toBeUndefined()
      },
    })
    expect(observedRole).toBe('lead')
    expect(h.ctx.agents.get(id)).toBe(handle.agent)
    expect(h.ctx.sessions.get(id)).toBe(handle.agent.session)
    await expect(h.ctx.agentBindings.bindPreparedSession(handle.agent.session, { role: 'lead' }))
      .rejects.toThrow('unpublished Session')
  } finally {
    await h.dispose()
  }
})

it('retains the reserved binding when later factory setup fails without publishing a live child', async () => {
  const h = await harness()
  try {
    const id = SessionId('failed-factory-child')
    await expect(h.ctx.agents.create({
      sessionId: id,
      async setup(childCtx) {
        await h.ctx.agentBindings.bindPreparedSession(childCtx.agent!.session, { role: 'lead' })
        throw new Error('composition failed')
      },
    })).rejects.toThrow()
    expect(h.ctx.sessions.get(id)).toBeUndefined()
    expect(h.ctx.agents.get(id)).toBeUndefined()
    expect(h.ctx.agentBindings.find(id)?.role).toBe('lead')
  } finally {
    await h.dispose()
  }
})

it('publishes an approved lead with its binding and rejects a controller creating a worker', async () => {
  const h = await harness()
  try {
    const parent = (await h.ctx.agents.create({
      sessionId: SessionId('preparation-controller'), meta: { cwd: join(h.root, 'controller') },
    })).agent
    await h.ctx.agentBindings.bind({ agentId: parent.id, role: 'controller' })
    // The creation consumer owns registration; this fixture supplies its observed row.
    const worktree: BoundWorktree = {
      worktreeId: 'registered-lead-tree' as BoundWorktree['worktreeId'],
      worktreePath: join(h.root, 'lead'),
    }
    const request = {
      cwd: worktree.worktreePath, role: 'lead' as const, worktree,
      taskId: TaskId('plugin-task'), pluginId: PluginId('plugin-a'),
    }
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, { ...request, role: 'worker' }))
      .rejects.toThrow('may only create leads')
    expect(h.ctx.agentBindings.list()).toHaveLength(1)
    const [child, duplicate] = await Promise.all([
      h.ctx.agentHierarchy.createChildAgent(parent, request),
      h.ctx.agentHierarchy.createChildAgent(parent, request),
    ])
    expect(duplicate.agent.id).toBe(child.agent.id)
    expect(h.ctx.agentBindings.list()).toHaveLength(2)
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, request, { sessionId: SessionId('different-child') }))
      .rejects.toThrow('task already has a different child binding')
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, { ...request, taskId: TaskId('other-task') }))
      .rejects.toThrow('worktree already belongs')
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, { ...request, pluginId: PluginId('plugin-b') }))
      .rejects.toThrow('task already has a different child binding')
    expect(child.record).toMatchObject({
      parentSessionId: parent.id, role: 'lead', worktreeId: worktree.worktreeId,
      worktreePath: request.cwd, taskId: request.taskId,
    })
    expect(child.agent.session.header).toMatchObject({ cwd: request.cwd, parentSession: parent.id, delegationDepth: 1 })
    expect(h.ctx.agents.get(child.agent.id)).toBe(child.agent)
  } finally {
    await h.dispose()
  }
})

it('creates exactly three hierarchy levels and rejects cross-plugin or worker delegation', async () => {
  const leadId = SessionId('three-level-lead')
  const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { [leadId]: ['plugin-a'] } } })
  try {
    const root = (await h.ctx.agents.create({ sessionId: SessionId('three-level-root'), meta: { cwd: h.root } })).agent
    await h.ctx.agentBindings.bind({ agentId: root.id, role: 'controller' })
    const request = (name: string, role: 'lead' | 'worker') => ({
      cwd: join(h.root, name), role, taskId: TaskId(name), pluginId: PluginId('plugin-a'),
      worktree: { worktreeId: name as BoundWorktree['worktreeId'], worktreePath: join(h.root, name) },
    })
    const lead = await h.ctx.agentHierarchy.createChildAgent(root, request('lead', 'lead'), { sessionId: leadId })
    await expect(h.ctx.agentHierarchy.createChildAgent(lead.agent, {
      ...request('wrong-plugin', 'worker'), pluginId: PluginId('plugin-b'),
    })).rejects.toThrow()
    const worker = await h.ctx.agentHierarchy.createChildAgent(lead.agent, request('worker', 'worker'))
    expect(worker.agent.session.header).toMatchObject({ parentSession: lead.agent.id, delegationDepth: 2 })
    expect(h.ctx.agentHierarchy.roleOf(worker.agent)).toBe('worker')
    await expect(h.ctx.agentHierarchy.createChildAgent(worker.agent, request('fourth', 'worker'))).rejects.toThrow()
    expect(h.ctx.agentBindings.list()).toHaveLength(3)
  } finally {
    await h.dispose()
  }
})

it('rejects missing ownership and a mismatched worktree directory before persisting a child', async () => {
  const h = await harness()
  try {
    const parent = (await h.ctx.agents.create({ sessionId: SessionId('ownership-controller') })).agent
    await h.ctx.agentBindings.bind({ agentId: parent.id, role: 'controller' })
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, { cwd: h.root, role: 'lead' }))
      .rejects.toThrow('requires a task and registered worktree')
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, {
      cwd: h.root, role: 'lead', taskId: TaskId('task'),
      worktree: { worktreeId: 'fixture-tree' as BoundWorktree['worktreeId'], worktreePath: join(h.root, 'other') },
    })).rejects.toThrow('cwd must match')
    expect(h.ctx.agentBindings.list()).toHaveLength(1)
  } finally {
    await h.dispose()
  }
})

it('reserves the child after publication is vetoed and rejects a replacement retry', async () => {
  const h = await harness()
  try {
    const parent = (await h.ctx.agents.create({ sessionId: SessionId('veto-controller'), meta: { cwd: h.root } })).agent
    await h.ctx.agentBindings.bind({ agentId: parent.id, role: 'controller' })
    const request = {
      cwd: join(h.root, 'reserved'), role: 'lead' as const, taskId: TaskId('reserved-task'),
      worktree: { worktreeId: 'reserved-tree' as BoundWorktree['worktreeId'], worktreePath: join(h.root, 'reserved') },
    }
    const childId = SessionId('veto-child')
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, request, {
      sessionId: childId,
      setup: () => ({ commit() { throw new Error('publication veto') } }),
    })).rejects.toThrow()
    expect(h.ctx.agentBindings.find(childId)?.taskId).toBe(request.taskId)
    expect(h.ctx.agents.get(childId)).toBeUndefined()
    expect(h.ctx.sessions.get(childId)).toBeUndefined()
    await expect(h.ctx.agentHierarchy.createChildAgent(parent, request)).rejects.toThrow('requires session recovery')
    expect(h.ctx.agentBindings.list()).toHaveLength(2)
  } finally {
    await h.dispose()
  }
})
