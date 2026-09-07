/**
 * AT3-08 lead assignment landing: the `agent/created` publication fact whose
 * durable binding names a controller-parented lead lands one new role-policy
 * snapshot on the controller Session log — read from the existing
 * `ctx.agentBindings` authority, idempotent on re-publication, skipped for
 * facts outside the controller-to-lead scope, and fail-loud when the
 * controller dispatches before its policy landed. Cold restore re-derives
 * every landed assignment.
 * @module tests/lead-role-landing
 */

import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import SessionStore, { Session, SessionId, SessionLogOffset } from '@deepseek-ai/dsh-session'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import type { AgentBindingRecord, AgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentBindingRegistry } from '@deepseek-ai/dsh-experimental-session-identity/src/registry.ts'
import { foldDevFrameState, devFrameProjectionDefinition } from '../src/projection.ts'
import { leadRoleLanding } from '../src/index.ts'
import type { DevFrameRolePolicyEventData } from '../src/events.ts'
import { WorkspaceId } from '../src/shared/types.ts'

const CONTROLLER = SessionId('session-controller')
const WORKSPACE = WorkspaceId('workspace-landing')

const CONTEXTS: Context[] = []
const ROOTS: string[] = []

afterEach(async () => {
  for (const ctx of CONTEXTS.splice(0).reverse()) await ctx.fiber.dispose()
  while (ROOTS.length > 0) {
    const root = ROOTS.pop()
    if (root !== undefined) await rm(root, { recursive: true, force: true })
  }
})

function binding(
  agentId: string,
  role: AgentRole,
  overrides: Partial<AgentBindingRecord> = {},
): AgentBindingRecord {
  return {
    agentId: SessionId(agentId),
    sessionId: SessionId(agentId),
    role,
    createdAt: '2026-01-01T00:00:00.000Z',
    ...overrides,
  }
}

/** The binding authority double: the records the landing reads facts from. */
function stubBindings(records: readonly AgentBindingRecord[]): AgentBindingRegistry {
  return {
    find: (agentId: SessionId) => records.find(record => String(record.agentId) === String(agentId)),
    byRole: (role: AgentRole) => records.filter(record => record.role === role),
    list: () => [...records],
  } as unknown as AgentBindingRegistry
}

function rolePolicy(): DevFrameRolePolicyEventData {
  const emptyPolicy = { inheritedTools: [] as string[], denyScopedTools: [] as string[] }
  return {
    version: 1,
    workspaceId: WORKSPACE,
    controllerSessionId: CONTROLLER,
    policyVersion: 'policy-workspace-landing-v1',
    config: {
      controller: { ...emptyPolicy },
      worker: { ...emptyPolicy },
      reviewer: { ...emptyPolicy },
    },
    assignments: [{ role: 'controller', sessionId: CONTROLLER }],
  }
}

async function boot(records: readonly AgentBindingRecord[]): Promise<{ ctx: Context; controller: Session }> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-lead-landing-'))
  ROOTS.push(root)
  const ctx = new Context()
  CONTEXTS.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(JsonlSessionPersistence, { root, compression: 'none' })
  await ctx.plugin(SessionProjectionRegistry)
  ctx.sessionProjections.register(devFrameProjectionDefinition)
  await ctx.plugin((inner: Context) => { inner.provide('agentBindings', stubBindings(records)) })
  await ctx.plugin(leadRoleLanding)
  const controller = ctx.sessions.create(CONTROLLER, { meta: { createdAt: 0 } })
  controller.append('devframe/role-policy', rolePolicy())
  return { ctx, controller }
}

function rolePolicyEvents(session: Session) {
  return session.snapshotEvents().filter((event): event is SessionEvent<'devframe/role-policy'> => event.type === 'devframe/role-policy')
}

describe('AT3-08 lead assignment landing', () => {
  it('lands one advanced snapshot when the controller dispatches a lead', async () => {
    const { ctx, controller } = await boot([
      binding('agent-lead-1', 'lead', { parentSessionId: CONTROLLER }),
    ])
    const state = ctx.sessionProjections.stateOf(controller, 'devframe')!
    expect(state.rolePolicy?.assignments.map(assignment => assignment.role)).toEqual(['controller'])

    const outcome = await ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-1'))
    expect(outcome).toBe('landed')

    const events = rolePolicyEvents(controller)
    expect(events).toHaveLength(2)
    const landed = events[1]!.data
    expect(landed.policyVersion).toBe('policy-workspace-landing-v2')
    expect(landed.assignments.map(assignment => assignment.role)).toEqual(['controller', 'lead'])
    expect(String(landed.assignments[1]!.sessionId)).toBe('agent-lead-1')
    const folded = ctx.sessionProjections.stateOf(controller, 'devframe')!
    expect(folded.failure).toBeNull()
    expect(folded.rolePolicy?.assignments).toHaveLength(2)
    expect(ctx.devframeLeadRoleLanding.failureOf(CONTROLLER)).toBeUndefined()
  })

  it('re-derives a landed assignment on cold restore', async () => {
    const { ctx, controller } = await boot([
      binding('agent-lead-1', 'lead', { parentSessionId: CONTROLLER }),
    ])
    await ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-1'))

    const restored = Session.fromRestore(
      controller.id,
      structuredClone(controller.snapshotEvents()),
      controller.header,
      SessionLogOffset(0),
    )
    const cold = foldDevFrameState(restored.snapshotEvents(), restored.header)
    expect(cold.failure).toBeNull()
    expect(cold.rolePolicy?.assignments.some(assignment =>
      assignment.role === 'lead' && String(assignment.sessionId) === 'agent-lead-1')).toBe(true)
  })

  it('stays idempotent when a lead re-publishes and advances per new lead', async () => {
    const { ctx, controller } = await boot([
      binding('agent-lead-1', 'lead', { parentSessionId: CONTROLLER }),
      binding('agent-lead-2', 'lead', { parentSessionId: CONTROLLER }),
    ])
    await ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-1'))
    expect(await ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-1'))).toBe('assigned')
    expect(await ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-2'))).toBe('landed')

    const events = rolePolicyEvents(controller)
    expect(events).toHaveLength(3)
    expect(events[2]!.data.policyVersion).toBe('policy-workspace-landing-v3')
    expect(events[2]!.data.assignments.map(assignment => assignment.role)).toEqual(['controller', 'lead', 'lead'])
  })

  it('skips a lead whose parent is not this project controller without touching the log', async () => {
    const other = SessionId('session-other-root')
    const { ctx, controller } = await boot([
      binding('agent-lead-x', 'lead', { parentSessionId: other }),
    ])
    const outcome = await ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-x'))
    expect(outcome).toBe('skipped')
    expect(rolePolicyEvents(controller)).toHaveLength(1)
  })

  it('fails loud when a controller dispatches before its role policy landed', async () => {
    const ctx = new Context()
    CONTEXTS.push(ctx)
    await ctx.plugin(SessionStore)
    await ctx.plugin(SessionProjectionRegistry)
    ctx.sessionProjections.register(devFrameProjectionDefinition)
    ctx.provide('agentBindings', stubBindings([
      binding('agent-lead-early', 'lead', { parentSessionId: CONTROLLER }),
    ]))
    await ctx.plugin(leadRoleLanding)
    const controller = ctx.sessions.create(CONTROLLER, { meta: { createdAt: 0 } })

    await expect(ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-early')))
      .rejects.toThrow(/before its role policy landed/)
    expect(ctx.devframeLeadRoleLanding.failureOf(CONTROLLER)).toBeInstanceOf(Error)
    expect(rolePolicyEvents(controller)).toHaveLength(0)
  })

  it('lands through the agent/created listener and ignores worker publications', async () => {
    const { ctx, controller } = await boot([
      binding('agent-lead-live', 'lead', { parentSessionId: CONTROLLER }),
      binding('agent-worker-1', 'worker', { parentSessionId: SessionId('agent-lead-live') }),
    ])
    ctx.emit('agent/created', { agent: { id: SessionId('agent-lead-live') } as Agent })
    await new Promise(resolve => setImmediate(resolve))
    expect(rolePolicyEvents(controller)).toHaveLength(2)

    ctx.emit('agent/created', { agent: { id: SessionId('agent-worker-1') } as Agent })
    await new Promise(resolve => setImmediate(resolve))
    expect(rolePolicyEvents(controller)).toHaveLength(2)
  })

  it('refuses to invent a policy version when the recorded scheme has no trailing number', async () => {
    const { ctx, controller } = await boot([
      binding('agent-lead-9', 'lead', { parentSessionId: CONTROLLER }),
    ])
    controller.append('devframe/role-policy', {
      ...rolePolicy(),
      policyVersion: 'release-candidate',
    })
    await expect(ctx.devframeLeadRoleLanding.land(SessionId('agent-lead-9')))
      .rejects.toThrow(/no trailing number/)
    expect(ctx.devframeLeadRoleLanding.failureOf(CONTROLLER)).toBeInstanceOf(Error)
  })
})
