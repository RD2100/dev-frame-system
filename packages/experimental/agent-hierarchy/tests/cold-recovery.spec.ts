import { rm } from 'node:fs/promises'
import { describe, expect, it, vi } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { baseConfig, bindAgent, createAgent, createAgentHandle, executeProbe, harness, mountHierarchy } from './helpers.ts'

/** Worker delegation denial, verbatim from src/guard.ts. */
const WORKER_SUBAGENT_DENY = 'agent-hierarchy: role "worker" cannot execute "subagent"'

describe('agent-hierarchy cold recovery', () => {
  it('rebuilds roles and reinstalls guards for still-active sessions after restart', async () => {
    const first = await harness({ mountHierarchy: false })
    try {
      const lead = await createAgent(first.ctx, 'lead-1')
      await bindAgent(first.ctx, lead, 'lead', 'plugin-a')
      const worker = await createAgent(first.ctx, 'worker-1')
      await bindAgent(first.ctx, worker, 'worker')
      const dormantLead = await createAgent(first.ctx, 'lead-2')
      await bindAgent(first.ctx, dormantLead, 'lead', 'plugin-b')
    } finally {
      await first.dispose({ keepRoot: true })
    }

    // Second boot over the same root: bindings restore, then the init pass
    // reinstalls the allow face for the agents that are live again.
    const second = await harness({ root: first.root, mountHierarchy: false })
    try {
      expect(second.ctx.agentBindings.list()).toHaveLength(3)
      expect(second.ctx.agentBindings.byRole('lead')).toHaveLength(2)
      expect(second.ctx.agentBindings.find(SessionId('lead-2'))).toBeDefined()
      await createAgent(second.ctx, 'lead-1')
      await createAgent(second.ctx, 'worker-1')
      await mountHierarchy(second.ctx, { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] } })

      // The worker's allow face was installed by the init pass, so the
      // out-of-face probe is invisible on the VERY first execution.
      const worker = second.ctx.agents.get(SessionId('worker-1'))!
      const hidden = await executeProbe(second.ctx, worker, 'admin_panel')
      expect(hidden.isError).toBe(true)
      expect(second.calls.get('admin_panel') ?? 0).toBe(0)
      const spawn = await executeProbe(second.ctx, worker, 'subagent')
      expect(spawn.isError).toBe(true)

      const lead = second.ctx.agents.get(SessionId('lead-1'))!
      const delegated = await executeProbe(second.ctx, lead, 'subagent')
      expect(delegated.isError).toBe(false)
      expect(second.calls.get('subagent')).toBe(1)
    } finally {
      await second.dispose({ keepRoot: true })
    }

    // Third boot: the hierarchy service mounts BEFORE the agents exist, so
    // the `agent/created` listener is the reinstall path. Creation resolves
    // before the announcement dispatches, so the reinstall races the first
    // probe; wait for the enforcement to appear instead of assuming timing.
    const third = await harness({ root: first.root, mountHierarchy: true })
    try {
      await createAgent(third.ctx, 'worker-1')
      const worker = third.ctx.agents.get(SessionId('worker-1'))!
      await vi.waitFor(async () => {
        const hidden = await executeProbe(third.ctx, worker, 'admin_panel')
        expect(hidden.isError).toBe(true)
      }, { timeout: 5_000 })
      expect(third.calls.get('admin_panel') ?? 0).toBe(0)
    } finally {
      await third.dispose()
    }
    await rm(first.root, { recursive: true, force: true })
  })

  it('denies a never-bound session after restart with the exact missing-role text and keeps non-controlled tools open', async () => {
    const first = await harness({ mountHierarchy: false })
    try {
      const worker = await createAgent(first.ctx, 'worker-1')
      await bindAgent(first.ctx, worker, 'worker')
    } finally {
      await first.dispose({ keepRoot: true })
    }

    // Second boot over the same root with the hierarchy mounted at boot: the
    // init pass reinstalls the restored worker and must leave a never-bound
    // session fail-closed on the controlled face.
    const second = await harness({ root: first.root, mountHierarchy: true })
    try {
      expect(second.ctx.agentBindings.list()).toHaveLength(1)
      const stray = await createAgent(second.ctx, 'stray-1')
      const denied = await executeProbe(second.ctx, stray, 'subagent')
      expect(denied.isError, `subagent allowed: ${denied.error?.message ?? '(no error)'}`).toBe(true)
      expect(denied.error?.message).toBe('agent-hierarchy: session "stray-1" has no role binding and cannot execute controlled tool "subagent" (missing role)')
      expect(second.calls.get('subagent') ?? 0).toBe(0)
      // Non-controlled tools stay open for the same session across restart.
      const allowed = await executeProbe(second.ctx, stray, 'project_read')
      expect(allowed.isError, `project_read denied: ${allowed.error?.message ?? '(no error)'}`).toBe(false)
      expect(second.calls.get('project_read')).toBe(1)
      expect(second.ctx.agentBindings.list()).toHaveLength(1)
    } finally {
      await second.dispose()
    }
    await rm(first.root, { recursive: true, force: true })
  })

  it('leaves no stale guard across restart: a disposed bound session keeps its binding and a same-id successor works per role', async () => {
    const first = await harness()
    try {
      const workerHandle = await createAgentHandle(first.ctx, 'worker-1')
      await bindAgent(first.ctx, workerHandle.agent, 'worker')
      const live = await executeProbe(first.ctx, workerHandle.agent, 'subagent')
      expect(live.isError, `subagent allowed: ${live.error?.message ?? '(no error)'}`).toBe(true)
      expect(live.error?.message).toBe(WORKER_SUBAGENT_DENY)
      await workerHandle.dispose()
      // Disposal releases the installed restriction but keeps the durable binding.
      expect(first.ctx.agentBindings.list()).toHaveLength(1)
    } finally {
      await first.dispose({ keepRoot: true })
    }

    // Second boot over the same root: the restored binding outlived the
    // disposal, so a same-id successor gets the full role face — the allow
    // face reinstall, the untouched deny face, and no stale or doubled guard.
    const second = await harness({ root: first.root, mountHierarchy: true })
    try {
      expect(second.ctx.agentBindings.list()).toHaveLength(1)
      const successor = await createAgent(second.ctx, 'worker-1')
      await bindAgent(second.ctx, successor, 'worker')
      expect(second.ctx.agentBindings.list()).toHaveLength(1)
      expect(second.ctx.agentHierarchy.roleOf(successor)).toBe('worker')
      // Drive one guard resolution first: the allow face installs lazily via
      // onRoleResolved, so the out-of-face probe is only meaningful after an
      // allowed execution has run.
      const allowed = await executeProbe(second.ctx, successor, 'project_read')
      expect(allowed.isError, `project_read denied: ${allowed.error?.message ?? '(no error)'}`).toBe(false)
      expect(second.calls.get('project_read')).toBe(1)
      const hidden = await executeProbe(second.ctx, successor, 'admin_panel')
      expect(hidden.isError).toBe(true)
      expect(second.calls.get('admin_panel') ?? 0).toBe(0)
      const denied = await executeProbe(second.ctx, successor, 'subagent')
      expect(denied.isError, `subagent allowed: ${denied.error?.message ?? '(no error)'}`).toBe(true)
      expect(denied.error?.message).toBe(WORKER_SUBAGENT_DENY)
      expect(second.calls.get('subagent') ?? 0).toBe(0)
    } finally {
      await second.dispose()
    }
    await rm(first.root, { recursive: true, force: true })
  })
})
