/**
 * AT2B-01 worker 全拒面 — anchored from
 * `scenarios/AT2B-01-worker-creation-denial.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：worker deny face = delegation seam + Team spawn/task-control +
 * 宿主声明 otherCreationToolNames；`send_message`/`project_read` 刻意放行；
 * 拒绝是 pre-execute 错误结果、工具体永不执行；继承 allow face 独立收缩
 * worker 可见工具列表。
 *
 * @module tests/at2b-01-worker-creation-denial
 */

import { expect, describe, it } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import { baseConfig, bindAgent, createAgent, executeProbe, harness, PROBE_TOOLS, type Harness } from './helpers.ts'
import type { AgentHierarchyConfigInput } from '../src/index.ts'

/** Team face members beyond the helpers' probe list, plus the host-declared creation surface. */
const EXTRA_TOOLS = ['team_task_update', 'followup_task', 'interrupt_agent', 'sdk_bridge_create'] as const

/** Every deny-face probe the draft names, in replay order. */
const DENY_PROBES = [
  'subagent', 'fork', 'spawn_teammate', 'team_task_create', 'team_task_update', 'followup_task', 'interrupt_agent', 'sdk_bridge_create',
] as const

/** Variant A (guard face): every controlled tool stays visible and callable to the worker. */
function guardFaceConfig(): AgentHierarchyConfigInput {
  const all = [...PROBE_TOOLS, ...EXTRA_TOOLS]
  return {
    roleToolPolicies: {
      controller: { inheritedTools: all },
      lead: { inheritedTools: all },
      worker: { inheritedTools: all },
    },
    otherCreationToolNames: ['sdk_bridge_create'],
  }
}

/** Variant B (allow face): README default worker surface plus the host-declared creation name. */
function allowFaceConfig(): AgentHierarchyConfigInput {
  return { ...baseConfig(), otherCreationToolNames: ['sdk_bridge_create'] }
}

/** Register the creation-face probe tools the shared harness does not know. */
function registerExtraTools(h: Harness): void {
  for (const name of EXTRA_TOOLS) {
    h.ctx.tools.register(defineContentToolFixture({
      name,
      description: `at2b-01 probe ${name}`,
      parameters: {},
      async execute() {
        h.calls.set(name, (h.calls.get(name) ?? 0) + 1)
        return []
      },
    }))
  }
}

/** Assert one probe is denied before any tool body runs, with the exact guard reason. */
async function expectExactDenial(h: Harness, agent: Agent, name: string, message: string): Promise<void> {
  const result = await executeProbe(h.ctx, agent, name)
  expect(result.isError).toBe(true)
  expect(result.error?.message).toBe(message)
  expect(h.calls.get(name) ?? 0).toBe(0)
}

/** Assert one probe runs its body exactly once more and reports no error. */
async function expectAllowed(h: Harness, agent: Agent, name: string): Promise<void> {
  const before = h.calls.get(name) ?? 0
  const result = await executeProbe(h.ctx, agent, name)
  expect(result.isError, `${name} denied: ${result.error?.message ?? '(no error)'}`).toBe(false)
  expect(h.calls.get(name)).toBe(before + 1)
}

describe('AT2B-01 worker creation denial', () => {
  it('denies every creation-face probe to the guard-face worker before execution', async () => {
    const h = await harness({ config: guardFaceConfig() })
    try {
      registerExtraTools(h)
      const worker = await createAgent(h.ctx, 'worker-1')
      await bindAgent(h.ctx, worker, 'worker')
      for (const name of DENY_PROBES) {
        await expectExactDenial(h, worker, name, `agent-hierarchy: role "worker" cannot execute "${name}"`)
      }
    } finally {
      await h.dispose()
    }
  })

  it('keeps the reporting channel open: send_message and project_read execute for the worker', async () => {
    const h = await harness({ config: guardFaceConfig() })
    try {
      registerExtraTools(h)
      const worker = await createAgent(h.ctx, 'worker-1')
      await bindAgent(h.ctx, worker, 'worker')
      await expectAllowed(h, worker, 'send_message')
      await expectAllowed(h, worker, 'project_read')
    } finally {
      await h.dispose()
    }
  })

  it('fails closed on a controlled tool for an unbound session and keeps non-controlled tools open', async () => {
    const h = await harness({ config: guardFaceConfig() })
    try {
      registerExtraTools(h)
      const stray = await createAgent(h.ctx, 'stray-1')
      await expectExactDenial(
        h, stray, 'subagent',
        `agent-hierarchy: session "${stray.id}" has no role binding and cannot execute controlled tool "subagent" (missing role)`,
      )
      await expectAllowed(h, stray, 'project_read')
    } finally {
      await h.dispose()
    }
  })

  it('shrinks the worker allow face and keeps the guard denial independent of it', async () => {
    const h = await harness({ config: allowFaceConfig() })
    try {
      registerExtraTools(h)
      const worker = await createAgent(h.ctx, 'worker-1')
      await bindAgent(h.ctx, worker, 'worker')
      // Resolving the role on the first guarded execution installs the allow face.
      await expectAllowed(h, worker, 'project_read')
      const visible = h.ctx.tools.schemas(worker).map(schema => schema.name)
      expect(visible).toContain('project_read')
      expect(visible).toContain('send_message')
      for (const name of DENY_PROBES) {
        expect(visible, `${name} must vanish from the worker prompt`).not.toContain(name)
      }
      // The guard face still denies a directly issued controlled call.
      await expectExactDenial(h, worker, 'spawn_teammate', 'agent-hierarchy: role "worker" cannot execute "spawn_teammate"')
    } finally {
      await h.dispose()
    }
  })
})
