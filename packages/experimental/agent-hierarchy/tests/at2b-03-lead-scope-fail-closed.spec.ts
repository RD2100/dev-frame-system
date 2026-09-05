/**
 * AT2B-03 lead 插件范围 fail-closed — anchored from
 * `scenarios/AT2B-03-lead-scope-fail-closed.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：未列名 lead、缺 pluginId 绑定、越集 scope 三条 fail-closed 拒绝
 * 路径各有独立探针且文本逐字；lead deny face 吞掉 Team 工具（reviewer 语义
 * 并入）且与 scope 无关；一次已批 scope 委派为正对照；拒绝先于工具体。
 *
 * @module tests/at2b-03-lead-scope-fail-closed
 */

import { expect, describe, it } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { baseConfig, bindAgent, createAgent, executeProbe, harness, type Harness } from './helpers.ts'
import type { AgentHierarchyConfigInput } from '../src/index.ts'

/**
 * The draft's scope roster: lead-2 listed but out of set, lead-4 deliberately
 * unlisted; lead-1 is the approved positive control.
 */
function scopeConfig(): AgentHierarchyConfigInput {
  return {
    ...baseConfig(),
    leadPluginScopes: {
      'lead-1': ['plugin-a'],
      'lead-2': ['plugin-c'],
    },
  }
}

/** Bind the four draft leads on one harness. */
async function bindLeads(h: Harness): Promise<Record<'lead1' | 'lead2' | 'lead3' | 'lead4', Agent>> {
  const lead1 = await createAgent(h.ctx, 'lead-1')
  await bindAgent(h.ctx, lead1, 'lead', 'plugin-a')
  const lead2 = await createAgent(h.ctx, 'lead-2')
  await bindAgent(h.ctx, lead2, 'lead', 'plugin-b')
  const lead3 = await createAgent(h.ctx, 'lead-3')
  await bindAgent(h.ctx, lead3, 'lead')
  const lead4 = await createAgent(h.ctx, 'lead-4')
  await bindAgent(h.ctx, lead4, 'lead', 'plugin-b')
  return { lead1, lead2, lead3, lead4 }
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

describe('AT2B-03 lead scope fail closed', () => {
  it('lets a lead with an approved scope delegate (positive control)', async () => {
    const h = await harness({ config: scopeConfig() })
    try {
      const { lead1 } = await bindLeads(h)
      await expectAllowed(h, lead1, 'fork')
      await expectAllowed(h, lead1, 'subagent')
    } finally {
      await h.dispose()
    }
  })

  it('denies the Team spawn face to a lead regardless of scope', async () => {
    const h = await harness({ config: scopeConfig() })
    try {
      const { lead1 } = await bindLeads(h)
      await expectExactDenial(h, lead1, 'spawn_teammate', 'agent-hierarchy: role "lead" cannot execute "spawn_teammate"')
      await expectExactDenial(h, lead1, 'team_task_create', 'agent-hierarchy: role "lead" cannot execute "team_task_create"')
    } finally {
      await h.dispose()
    }
  })

  it('refuses a listed lead whose bound scope is outside the approved set', async () => {
    const h = await harness({ config: scopeConfig() })
    try {
      const { lead2 } = await bindLeads(h)
      await expectExactDenial(
        h, lead2, 'subagent',
        'agent-hierarchy: plugin scope "plugin-b" is not in the approved set of lead "lead-2"',
      )
    } finally {
      await h.dispose()
    }
  })

  it('refuses a lead without a plugin scope binding', async () => {
    const h = await harness({ config: scopeConfig() })
    try {
      const { lead3 } = await bindLeads(h)
      await expectExactDenial(
        h, lead3, 'subagent',
        'agent-hierarchy: lead "lead-3" has no plugin scope binding and cannot delegate',
      )
    } finally {
      await h.dispose()
    }
  })

  it('refuses an unlisted lead with the same out-of-set text (approved set empty)', async () => {
    const h = await harness({ config: scopeConfig() })
    try {
      const { lead4 } = await bindLeads(h)
      await expectExactDenial(
        h, lead4, 'subagent',
        'agent-hierarchy: plugin scope "plugin-b" is not in the approved set of lead "lead-4"',
      )
    } finally {
      await h.dispose()
    }
  })
})
