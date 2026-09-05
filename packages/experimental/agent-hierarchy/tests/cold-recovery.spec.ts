import { rm } from 'node:fs/promises'
import { describe, expect, it, vi } from 'vitest'
import { SessionId } from '@deepseek-ai/dsh-session'
import { baseConfig, bindAgent, createAgent, executeProbe, harness, mountHierarchy } from './helpers.ts'

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
})
