import { describe, expect, it } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { PluginId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { AgentHandle } from '@deepseek-ai/dsh-agent'
import { baseConfig, bindAgent, createAgent, createAgentHandle, executeProbe, harness, type Harness } from './helpers.ts'
import type { AgentHierarchyConfigInput } from '../src/index.ts'

/** Bound roster returned by {@link rosterHarness}. */
interface Roster {
  readonly h: Harness
  readonly controller: Agent
  readonly lead: Agent
  readonly worker: Agent
}

/** Partial top-level config overrides merged over {@link baseConfig}; full input stays required at the service boundary. */
type HarnessConfigOverrides = Partial<AgentHierarchyConfigInput>

/** Boot one harness with lead-1 approved for plugin-a and the full three-role roster bound. */
async function rosterHarness(config: HarnessConfigOverrides = {}): Promise<Roster> {
  const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] }, ...config } })
  const controller = await createAgent(h.ctx, 'controller-1')
  await bindAgent(h.ctx, controller, 'controller')
  const lead = await createAgent(h.ctx, 'lead-1')
  await bindAgent(h.ctx, lead, 'lead', 'plugin-a')
  const worker = await createAgent(h.ctx, 'worker-1')
  await bindAgent(h.ctx, worker, 'worker')
  return { h, controller, lead, worker }
}

/** Assert one probe is denied before any tool body runs, with the expected reason fragment. */
async function expectDenied(h: Harness, agent: Agent, name: string, fragment: string): Promise<void> {
  const result = await executeProbe(h.ctx, agent, name)
  expect(result.isError).toBe(true)
  expect(result.error?.message).toContain(fragment)
  expect(h.calls.get(name) ?? 0).toBe(0)
}

/** Assert one probe runs its body exactly once more. */
async function expectAllowed(h: Harness, agent: Agent, name: string): Promise<void> {
  const before = h.calls.get(name) ?? 0
  const result = await executeProbe(h.ctx, agent, name)
  expect(result.isError, `${name} denied: ${result.error?.message ?? '(no error)'}`).toBe(false)
  expect(h.calls.get(name)).toBe(before + 1)
}

describe('agent-hierarchy guard (real dispatcher)', () => {
  it('lets the controller execute every probe', async () => {
    const { h, controller } = await rosterHarness()
    try {
      for (const name of ['subagent', 'fork', 'spawn_teammate', 'team_task_create', 'project_read', 'send_message', 'admin_panel']) {
        await expectAllowed(h, controller, name)
      }
      expect(h.ctx.agentHierarchy.roleOf(controller)).toBe('controller')
    } finally {
      await h.dispose()
    }
  })

  it('denies every agent-creating probe to the worker before execution', async () => {
    const { h, worker } = await rosterHarness()
    try {
      for (const name of ['subagent', 'fork', 'spawn_teammate', 'team_task_create']) {
        await expectDenied(h, worker, name, 'role "worker" cannot execute')
      }
      await expectAllowed(h, worker, 'project_read')
      await expectAllowed(h, worker, 'send_message')
    } finally {
      await h.dispose()
    }
  })

  it('denies the Team spawn face to the lead but allows delegation inside the approved scope', async () => {
    const { h, lead } = await rosterHarness()
    try {
      for (const name of ['spawn_teammate', 'team_task_create']) {
        await expectDenied(h, lead, name, 'role "lead" cannot execute')
      }
      await expectAllowed(h, lead, 'subagent')
      await expectAllowed(h, lead, 'fork')
    } finally {
      await h.dispose()
    }
  })

  it('rejects a lead delegating outside its approved plugin scopes, including an unlisted lead', async () => {
    const { h, lead } = await rosterHarness({ leadPluginScopes: { 'lead-1': ['plugin-b'] } })
    try {
      await expectDenied(h, lead, 'subagent', 'plugin scope "plugin-a" is not in the approved set of lead "lead-1"')
    } finally {
      await h.dispose()
    }
    const unlisted = await harness({ config: { ...baseConfig() } })
    try {
      const strayLead = await createAgent(unlisted.ctx, 'lead-9')
      await bindAgent(unlisted.ctx, strayLead, 'lead', 'plugin-a')
      await expectDenied(unlisted, strayLead, 'subagent', 'is not in the approved set')
    } finally {
      await unlisted.dispose()
    }
  })

  it('rejects a lead with no plugin scope binding from delegating', async () => {
    const { h } = await rosterHarness()
    try {
      const scopelessLead = await createAgent(h.ctx, 'lead-2')
      await bindAgent(h.ctx, scopelessLead, 'lead')
      await expectDenied(h, scopelessLead, 'subagent', 'has no plugin scope binding')
    } finally {
      await h.dispose()
    }
  })

  it('enforces the absolute depth budget as the second, independent refusal path', async () => {
    const { h } = await rosterHarness()
    try {
      // A depth-2 session bound as lead: the role face alone would allow
      // delegation, so only the depth half can refuse child depth 3.
      const deepLead = await createAgent(h.ctx, 'lead-deep', 2)
      await bindAgent(h.ctx, deepLead, 'lead', 'plugin-a')
      await expectDenied(h, deepLead, 'subagent', 'beyond the absolute budget 2')
      const deepController = await createAgent(h.ctx, 'controller-deep', 2)
      await bindAgent(h.ctx, deepController, 'controller')
      await expectDenied(h, deepController, 'subagent', 'beyond the absolute budget 2')
    } finally {
      await h.dispose()
    }
  })

  it('fails closed on controlled tools for a session without a role binding', async () => {
    const { h } = await rosterHarness()
    try {
      const stray = await createAgent(h.ctx, 'stray-1')
      await expectDenied(h, stray, 'subagent', 'no role binding')
      await expectDenied(h, stray, 'team_task_create', 'missing role')
      // Non-controlled tools stay open: the creation seam is this package's boundary.
      await expectAllowed(h, stray, 'project_read')
    } finally {
      await h.dispose()
    }
  })

  it('denies a stale agent identity before consulting its record', async () => {
    const { h } = await rosterHarness()
    try {
      const doomedHandle: AgentHandle = await createAgentHandle(h.ctx, 'doomed-1')
      const doomed = doomedHandle.agent
      await bindAgent(h.ctx, doomed, 'worker')
      await doomedHandle.dispose()
      const result = await executeProbe(h.ctx, doomed, 'subagent')
      expect(result.isError).toBe(true)
      expect(result.error?.message).toContain('stale Agent identity')
    } finally {
      await h.dispose()
    }
  })

  it('applies the inherited allow face lazily and processes disposal', async () => {
    const { h, worker, workerHandle } = await rosterHarnessWithHandles()
    try {
      // Drive the guard once with an allowed probe: resolving the role
      // installs the allow face synchronously via onRoleResolved.
      await expectAllowed(h, worker, 'project_read')
      // Now admin_panel is restricted away for the worker: unknown-tool denial.
      const hidden = await executeProbe(h.ctx, worker, 'admin_panel')
      expect(hidden.isError, `admin_panel allowed: ${JSON.stringify(hidden)}`).toBe(true)
      expect(h.calls.get('admin_panel') ?? 0).toBe(0)
      // Disposal releases the restriction without disturbing the context.
      await workerHandle.dispose()
      const dead = await executeProbe(h.ctx, worker, 'project_read')
      expect(dead.isError).toBe(true)
      expect(dead.error?.message).toContain('stale Agent identity')
    } finally {
      await h.dispose()
    }
  })

  it('exposes roleOf and the programmatic creation evaluator on the service', async () => {
    const { h, controller, lead, worker } = await rosterHarness()
    try {
      expect(h.ctx.agentHierarchy.roleOf(controller)).toBe('controller')
      expect(h.ctx.agentHierarchy.roleOf(lead)).toBe('lead')
      expect(h.ctx.agentHierarchy.roleOf(worker)).toBe('worker')
      const controllerRecord = h.ctx.agentBindings.find(controller.id)!
      const leadRecord = h.ctx.agentBindings.find(lead.id)!
      const workerRecord = h.ctx.agentBindings.find(worker.id)!
      for (const requestedRole of ['controller', 'worker'] as const) {
        expect(h.ctx.agentHierarchy.evaluateCreation(controllerRecord, {
          parentSessionId: controller.id, requestedRole,
        })).toMatchObject({ allowed: false, reason: expect.stringContaining('may only create leads') })
      }
      expect(h.ctx.agentHierarchy.evaluateCreation(controllerRecord, {
        parentSessionId: controller.id, requestedRole: 'lead',
      })).toMatchObject({ allowed: true })
      expect(h.ctx.agentHierarchy.evaluateCreation(leadRecord, {
        parentSessionId: lead.id, requestedRole: 'worker', pluginScope: PluginId('plugin-a'),
      })).toMatchObject({ allowed: true })
      expect(h.ctx.agentHierarchy.evaluateCreation(leadRecord, {
        parentSessionId: lead.id, requestedRole: 'worker', pluginScope: PluginId('plugin-z'),
      })).toMatchObject({ allowed: false, reason: expect.stringContaining('not in the approved set') })
      expect(h.ctx.agentHierarchy.evaluateCreation(leadRecord, {
        parentSessionId: lead.id, requestedRole: 'lead', pluginScope: PluginId('plugin-a'),
      })).toMatchObject({ allowed: false, reason: expect.stringContaining('may only create workers') })
      expect(h.ctx.agentHierarchy.evaluateCreation(leadRecord, {
        parentSessionId: lead.id, requestedRole: 'worker',
      })).toMatchObject({ allowed: false, reason: expect.stringContaining('carries no pluginScope') })
      expect(h.ctx.agentHierarchy.evaluateCreation(workerRecord, {
        parentSessionId: worker.id, requestedRole: 'worker',
      })).toMatchObject({ allowed: false, reason: expect.stringContaining('cannot create agents') })
    } finally {
      await h.dispose()
    }
  })

  it('fails loud at load on invalid configuration', async () => {
    const padded = baseConfig()
    await expect(harness({ config: {
      ...padded,
      roleToolPolicies: {
        ...padded.roleToolPolicies,
        worker: { inheritedTools: [' padded '] },
      },
    } })).rejects.toMatchObject({ code: 'HIERARCHY_INVALID_CONFIG' })
    await expect(harness({ config: {
      ...padded,
      delegationToolNames: ['subagent'],
      teamToolNames: ['subagent'],
    } })).rejects.toMatchObject({ code: 'HIERARCHY_INVALID_CONFIG' })
  })
})

/** Roster variant that also returns the worker's owning handle for disposal assertions. */
async function rosterHarnessWithHandles(): Promise<{ h: Harness; worker: Agent; workerHandle: AgentHandle }> {
  const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] } } })
  const controller = await createAgent(h.ctx, 'controller-1')
  await bindAgent(h.ctx, controller, 'controller')
  const workerHandle = await createAgentHandle(h.ctx, 'worker-1')
  await bindAgent(h.ctx, workerHandle.agent, 'worker')
  return { h, worker: workerHandle.agent, workerHandle }
}
