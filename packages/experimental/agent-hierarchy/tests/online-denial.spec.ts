import { readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PluginId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { SessionId } from '@deepseek-ai/dsh-session'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import {
  baseConfig, bindAgent, createAgent, createAgentHandle, executeProbe, executeProbeWithoutAgent,
  harness, mountHierarchy, PROBE_TOOLS,
  type Harness, type ToolResultLike,
} from './helpers.ts'
import type { AgentHierarchyConfigInput } from '../src/index.ts'

/**
 * Online denial probes on the real dispatcher (`ctx.tools.execute`) over the
 * real Service path: every denial below asserts the current `src/guard.ts`
 * text character-for-character, that the probe tool body never ran, and that
 * the durable binding registry is untouched by the refusal.
 */

/** Worker role-face denials, verbatim from src/guard.ts. */
const WORKER_DENY_FACE = {
  subagent: 'agent-hierarchy: role "worker" cannot execute "subagent"',
  fork: 'agent-hierarchy: role "worker" cannot execute "fork"',
  spawn_teammate: 'agent-hierarchy: role "worker" cannot execute "spawn_teammate"',
  team_task_create: 'agent-hierarchy: role "worker" cannot execute "team_task_create"',
  team_task_update: 'agent-hierarchy: role "worker" cannot execute "team_task_update"',
} as const

/** Lead Team-face denials, verbatim from src/guard.ts. */
const LEAD_TEAM_FACE = {
  spawn_teammate: 'agent-hierarchy: role "lead" cannot execute "spawn_teammate"',
  team_task_update: 'agent-hierarchy: role "lead" cannot execute "team_task_update"',
} as const

/** Missing-role denials for the unbound session "stray-1", verbatim from src/guard.ts. */
const MISSING_ROLE_STRAY = {
  subagent: 'agent-hierarchy: session "stray-1" has no role binding and cannot execute controlled tool "subagent" (missing role)',
  team_task_update: 'agent-hierarchy: session "stray-1" has no role binding and cannot execute controlled tool "team_task_update" (missing role)',
} as const

/** Assert one probe is denied before any tool body runs, with the exact current guard text and no side effects. */
async function expectExactDenial(
  h: Harness,
  probe: () => Promise<ToolResultLike>,
  name: string,
  expected: string,
): Promise<void> {
  const bindingsBefore = JSON.stringify(h.ctx.agentBindings.list())
  const result = await probe()
  expect(result.isError, `${name} allowed: ${result.error?.message ?? '(no error)'}`).toBe(true)
  expect(result.error?.message).toBe(expected)
  expect(h.calls.get(name) ?? 0).toBe(0)
  expect(JSON.stringify(h.ctx.agentBindings.list()), `${name} denial mutated the binding registry`).toBe(bindingsBefore)
}

/** Assert one probe runs its body exactly once more. */
async function expectExactAllow(h: Harness, probe: () => Promise<ToolResultLike>, name: string): Promise<void> {
  const before = h.calls.get(name) ?? 0
  const result = await probe()
  expect(result.isError, `${name} denied: ${result.error?.message ?? '(no error)'}`).toBe(false)
  expect(h.calls.get(name)).toBe(before + 1)
}

describe('agent-hierarchy online denial probes (real dispatcher)', () => {
  it('denies an unbound session fail-closed on the controlled probes with the exact missing-role text', async () => {
    const h = await harness()
    try {
      const stray = await createAgent(h.ctx, 'stray-1')
      await expectExactDenial(h, () => executeProbe(h.ctx, stray, 'subagent'), 'subagent', MISSING_ROLE_STRAY.subagent)
      await expectExactDenial(h, () => executeProbe(h.ctx, stray, 'team_task_update'), 'team_task_update', MISSING_ROLE_STRAY.team_task_update)
      // Non-controlled tools stay open for the same session: the creation seam is this package's boundary.
      await expectExactAllow(h, () => executeProbe(h.ctx, stray, 'project_read'), 'project_read')
      expect(h.ctx.agentBindings.find(stray.id)).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })

  it('denies every creation and Team probe to the worker with the exact role-face text and keeps the reporting routes open', async () => {
    const h = await harness()
    try {
      const worker = await createAgent(h.ctx, 'worker-1')
      await bindAgent(h.ctx, worker, 'worker')
      for (const [name, expected] of Object.entries(WORKER_DENY_FACE)) {
        await expectExactDenial(h, () => executeProbe(h.ctx, worker, name), name, expected)
      }
      await expectExactAllow(h, () => executeProbe(h.ctx, worker, 'project_read'), 'project_read')
      await expectExactAllow(h, () => executeProbe(h.ctx, worker, 'send_message'), 'send_message')
    } finally {
      await h.dispose()
    }
  })

  it('denies the Team face to the lead with the exact role-face text and lets the controller execute every probe', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] } } })
    try {
      const lead = await createAgent(h.ctx, 'lead-1')
      await bindAgent(h.ctx, lead, 'lead', 'plugin-a')
      for (const [name, expected] of Object.entries(LEAD_TEAM_FACE)) {
        await expectExactDenial(h, () => executeProbe(h.ctx, lead, name), name, expected)
      }
      const controller = await createAgent(h.ctx, 'controller-1')
      await bindAgent(h.ctx, controller, 'controller')
      for (const name of PROBE_TOOLS) {
        await expectExactAllow(h, () => executeProbe(h.ctx, controller, name), name)
      }
    } finally {
      await h.dispose()
    }
  })

  it('denies a stale disposed identity with the exact unknown-identity text', async () => {
    const h = await harness()
    try {
      const workerHandle = await createAgentHandle(h.ctx, 'worker-1')
      await bindAgent(h.ctx, workerHandle.agent, 'worker')
      await workerHandle.dispose()
      await expectExactDenial(
        h,
        () => executeProbe(h.ctx, workerHandle.agent, 'team_task_update'),
        'team_task_update',
        'agent-hierarchy: stale Agent identity "worker-1" cannot execute "team_task_update"',
      )
    } finally {
      await h.dispose()
    }
  })

  it('denies an agent-less execution with the exact no-agent text', async () => {
    const h = await harness()
    try {
      const controller = await createAgent(h.ctx, 'controller-1')
      await bindAgent(h.ctx, controller, 'controller')
      await expectExactDenial(
        h,
        () => executeProbeWithoutAgent(h.ctx, 'subagent'),
        'subagent',
        'agent-hierarchy: tool "subagent" requires an exact live Agent',
      )
    } finally {
      await h.dispose()
    }
  })

  it('rejects delegation at the absolute depth budget with the exact numeric text', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] } } })
    try {
      // A depth-2 session bound as lead: the role face alone would allow
      // delegation, so only the depth half can refuse child depth 3.
      const deepLead = await createAgent(h.ctx, 'lead-1', 2)
      await bindAgent(h.ctx, deepLead, 'lead', 'plugin-a')
      await expectExactDenial(
        h,
        () => executeProbe(h.ctx, deepLead, 'fork'),
        'fork',
        'agent-hierarchy: delegating from depth 2 would create a child at depth 3 beyond the absolute budget 2',
      )
    } finally {
      await h.dispose()
    }
  })

  it('rejects a lead whose plugin scope is not in the approved set with the exact text, including an unlisted lead', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-b'] } } })
    try {
      const lead = await createAgent(h.ctx, 'lead-1')
      await bindAgent(h.ctx, lead, 'lead', 'plugin-a')
      await expectExactDenial(
        h,
        () => executeProbe(h.ctx, lead, 'subagent'),
        'subagent',
        'agent-hierarchy: plugin scope "plugin-a" is not in the approved set of lead "lead-1"',
      )
    } finally {
      await h.dispose()
    }
    const unlisted = await harness()
    try {
      const strayLead = await createAgent(unlisted.ctx, 'lead-9')
      await bindAgent(unlisted.ctx, strayLead, 'lead', 'plugin-a')
      await expectExactDenial(
        unlisted,
        () => executeProbe(unlisted.ctx, strayLead, 'subagent'),
        'subagent',
        'agent-hierarchy: plugin scope "plugin-a" is not in the approved set of lead "lead-9"',
      )
    } finally {
      await unlisted.dispose()
    }
  })

  it('rejects a lead with no plugin scope binding with the exact text and allows delegation inside the approved scope', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] } } })
    try {
      const scopelessLead = await createAgent(h.ctx, 'lead-2')
      await bindAgent(h.ctx, scopelessLead, 'lead')
      await expectExactDenial(
        h,
        () => executeProbe(h.ctx, scopelessLead, 'subagent'),
        'subagent',
        'agent-hierarchy: lead "lead-2" has no plugin scope binding and cannot delegate',
      )
      const lead = await createAgent(h.ctx, 'lead-1')
      await bindAgent(h.ctx, lead, 'lead', 'plugin-a')
      await expectExactAllow(h, () => executeProbe(h.ctx, lead, 'subagent'), 'subagent')
    } finally {
      await h.dispose()
    }
  })

  it('denies the host-declared creation face to the worker and allows the controller', async () => {
    const all = [...PROBE_TOOLS]
    const config: AgentHierarchyConfigInput = {
      ...baseConfig(),
      otherCreationToolNames: ['sdk_bridge_spawn'],
      roleToolPolicies: {
        controller: { inheritedTools: [...all, 'sdk_bridge_spawn'] },
        lead: { inheritedTools: all },
        worker: { inheritedTools: ['project_read', 'send_message'] },
      },
    }
    const h = await harness({ config })
    try {
      // Registered before any agent exists so the installed allow faces can
      // admit the declared name; the harness body counter does not track it.
      let sdkBridgeCalls = 0
      h.ctx.tools.register(defineContentToolFixture({
        name: 'sdk_bridge_spawn',
        description: 'agent-hierarchy probe sdk_bridge_spawn (host-declared creation face)',
        parameters: {},
        async execute() {
          sdkBridgeCalls += 1
          return []
        },
      }))
      const controller = await createAgent(h.ctx, 'controller-1')
      await bindAgent(h.ctx, controller, 'controller')
      const worker = await createAgent(h.ctx, 'worker-1')
      await bindAgent(h.ctx, worker, 'worker')
      await expectExactDenial(
        h,
        () => executeProbe(h.ctx, worker, 'sdk_bridge_spawn'),
        'sdk_bridge_spawn',
        'agent-hierarchy: role "worker" cannot execute "sdk_bridge_spawn"',
      )
      expect(sdkBridgeCalls).toBe(0)
      const allowed = await executeProbe(h.ctx, controller, 'sdk_bridge_spawn')
      expect(allowed.isError, `controller denied: ${allowed.error?.message ?? '(no error)'}`).toBe(false)
      expect(sdkBridgeCalls).toBe(1)
    } finally {
      await h.dispose()
    }
  })

  it('denies a controlled tool to a role-less session after restart with the exact missing-role text', async () => {
    const first = await harness()
    try {
      await createAgent(first.ctx, 'stray-1')
    } finally {
      await first.dispose({ keepRoot: true })
    }
    const second = await harness({ root: first.root, mountHierarchy: false })
    try {
      await createAgent(second.ctx, 'stray-1')
      await mountHierarchy(second.ctx)
      const stray = second.ctx.agents.get(SessionId('stray-1'))!
      await expectExactDenial(
        second,
        () => executeProbe(second.ctx, stray, 'team_task_update'),
        'team_task_update',
        'agent-hierarchy: session "stray-1" has no role binding and cannot execute controlled tool "team_task_update" (missing role)',
      )
    } finally {
      await second.dispose()
    }
  })

  it('fails loud at the durable boundary when a restored binding carries a retired role', async () => {
    const first = await harness()
    try {
      const worker = await createAgent(first.ctx, 'worker-1')
      await bindAgent(first.ctx, worker, 'worker')
    } finally {
      await first.dispose({ keepRoot: true })
    }
    // Every path below removes the kept root itself (a failed boot removes it
    // in the harness), so the rewritten temp tree cannot leak on any failure.
    try {
      await runRetiredRoleRestart(first.root)
    } finally {
      await rm(first.root, { recursive: true, force: true })
    }
  })

  it('leaves no stale guard after disposal: the old reference is denied and a same-id successor gets its full face', async () => {
    const h = await harness()
    try {
      const controllerHandle = await createAgentHandle(h.ctx, 'controller-1')
      await bindAgent(h.ctx, controllerHandle.agent, 'controller')
      const worker = await createAgent(h.ctx, 'worker-1')
      await bindAgent(h.ctx, worker, 'worker')
      expect(h.ctx.agentBindings.list()).toHaveLength(2)
      await controllerHandle.dispose()
      await expectExactDenial(
        h,
        () => executeProbe(h.ctx, controllerHandle.agent, 'subagent'),
        'subagent',
        'agent-hierarchy: stale Agent identity "controller-1" cannot execute "subagent"',
      )
      // Disposal keeps the durable binding; the successor rebinds idempotently.
      expect(h.ctx.agentBindings.list()).toHaveLength(2)
      const successor = await createAgent(h.ctx, 'controller-1')
      await bindAgent(h.ctx, successor, 'controller')
      expect(h.ctx.agentHierarchy.roleOf(successor)).toBe('controller')
      await expectExactAllow(h, () => executeProbe(h.ctx, successor, 'admin_panel'), 'admin_panel')
      await expectExactAllow(h, () => executeProbe(h.ctx, successor, 'subagent'), 'subagent')
      // The guard still enforces the untouched worker normally — no loosened
      // or doubled enforcement after the disposal/recreation churn.
      await expectExactDenial(h, () => executeProbe(h.ctx, worker, 'team_task_update'), 'team_task_update', WORKER_DENY_FACE.team_task_update)
      expect(h.ctx.agentBindings.list()).toHaveLength(2)
    } finally {
      await h.dispose()
    }
  })

  it('mirrors the guard face on the programmatic creation evaluator with real binding records', async () => {
    const unlisted = await harness()
    try {
      const strayLead = await createAgent(unlisted.ctx, 'lead-9')
      await bindAgent(unlisted.ctx, strayLead, 'lead', 'plugin-a')
      const leadRecord = unlisted.ctx.agentBindings.find(strayLead.id)!
      expect(unlisted.ctx.agentHierarchy.evaluateCreation(leadRecord, {
        parentSessionId: strayLead.id,
        requestedRole: 'worker',
        pluginScope: PluginId('plugin-a'),
      })).toEqual({
        allowed: false,
        reason: 'agent-hierarchy: plugin scope "plugin-a" is not in the approved set of lead "lead-9"',
      })
    } finally {
      await unlisted.dispose()
    }
    const h = await harness()
    try {
      const controller = await createAgent(h.ctx, 'controller-1')
      await bindAgent(h.ctx, controller, 'controller')
      const controllerRecord = h.ctx.agentBindings.find(controller.id)!
      expect(h.ctx.agentHierarchy.evaluateCreation(controllerRecord, {
        parentSessionId: controller.id,
        requestedRole: 'lead',
      })).toEqual({ allowed: true })
    } finally {
      await h.dispose()
    }
  })
})

/** Rewrite and restart body of the retired-role durable-boundary case. */
async function runRetiredRoleRestart(root: string): Promise<void> {
  // The `session_identity` domain is a single-layout unit: one document at
  // `<root>/session_identity.json`. Rewrite only the role field of the
  // worker's durable record to the retired role, leaving every other field
  // and record untouched.
  const unitPath = join(root, 'session_identity.json')
  const stored = JSON.parse(await readFile(unitPath, 'utf8')) as {
    unit: { name: string; version: number }
    tables: { bindings: Record<string, { role: string }> }
  }
  const record = stored.tables.bindings['worker-1']
  expect(record?.role).toBe('worker')
  record!.role = 'reviewer'
  await writeFile(unitPath, `${JSON.stringify(stored, null, 2)}\n`, 'utf8')
  // Restart: the durable boundary rejects the retired role fail-loud while
  // the binding registry restores, before the hierarchy service ever mounts
  // (registered as a gap in the evidence doc: the service-init
  // HIERARCHY_ROLE_UNKNOWN pass is a defense-in-depth layer behind it).
  const attempt = await harness({ root }).then(
    (booted: Harness) => ({ booted }) as const,
    (error: unknown) => ({ error }) as const,
  )
  if ('booted' in attempt) await attempt.booted.dispose()
  if (!('error' in attempt)) throw new Error('the second boot must fail loud against a retired-role record')
  const failure = attempt.error as {
    name?: string
    code?: string
    message?: string
    detail?: { table?: string; key?: string }
  }
  expect(failure.name).toBe('DomainError')
  expect(failure.code).toBe('invalid-record')
  expect(failure.message).toBe("domain 'session_identity': stored record 'worker-1' in table 'bindings' does not match its schema")
  expect(failure.detail).toEqual({ table: 'bindings', key: 'worker-1' })
}
