/**
 * AT2B-02 深度预算 2 双保险 — anchored from
 * `scenarios/AT2B-02-depth-budget-double-guard.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：本包 pre-execute 守卫是 SubagentDepthError 之外的独立第二半——
 * depth-2 会话（绑 lead）再委派被深度文本拒绝；深度检查先于 lead scope、
 * 后于 deny face；预算只拦委派面，不拦受控面之外的工具。
 *
 * @module tests/at2b-02-depth-budget-double-guard
 */

import { expect, describe, it } from 'vitest'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET } from '../src/policy.ts'
import { baseConfig, bindAgent, createAgent, executeProbe, harness, type Harness } from './helpers.ts'

/** The exact depth denial for a depth-2 session delegating (child would be depth 3). */
const DEPTH_TEXT = `agent-hierarchy: delegating from depth 2 would create a child at depth 3 beyond the absolute budget ${AGENT_HIERARCHY_DELEGATION_DEPTH_BUDGET}`

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

describe('AT2B-02 depth budget double guard', () => {
  it('lets the in-budget generations delegate: depth-0 controller and depth-1 lead', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-1': ['plugin-a'] } } })
    try {
      const controller = await createAgent(h.ctx, 'controller-1')
      await bindAgent(h.ctx, controller, 'controller')
      await expectAllowed(h, controller, 'subagent')
      const lead = await createAgent(h.ctx, 'lead-1', 1)
      await bindAgent(h.ctx, lead, 'lead', 'plugin-a')
      await expectAllowed(h, lead, 'subagent')
    } finally {
      await h.dispose()
    }
  })

  it('refuses a depth-2 session bound as lead from delegating, before any tool body runs', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-deep': ['plugin-a'] } } })
    try {
      const deepLead = await createAgent(h.ctx, 'lead-deep', 2)
      await bindAgent(h.ctx, deepLead, 'lead', 'plugin-a')
      await expectExactDenial(h, deepLead, 'subagent', DEPTH_TEXT)
      await expectExactDenial(h, deepLead, 'fork', DEPTH_TEXT)
    } finally {
      await h.dispose()
    }
  })

  it('only bars delegation at the budget: a depth-2 session still runs non-delegation tools', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-deep': ['plugin-a'] } } })
    try {
      const deepLead = await createAgent(h.ctx, 'lead-deep', 2)
      await bindAgent(h.ctx, deepLead, 'lead', 'plugin-a')
      await expectAllowed(h, deepLead, 'project_read')
    } finally {
      await h.dispose()
    }
  })

  it('orders the checks deny face → depth → lead scope', async () => {
    const h = await harness({ config: { ...baseConfig(), leadPluginScopes: { 'lead-deep': ['plugin-a'] } } })
    try {
      // Deny face precedes depth: a depth-2 worker reads the role text, not the depth text.
      const deepWorker = await createAgent(h.ctx, 'worker-deep', 2)
      await bindAgent(h.ctx, deepWorker, 'worker')
      await expectExactDenial(h, deepWorker, 'subagent', 'agent-hierarchy: role "worker" cannot execute "subagent"')
      // Depth precedes scope: an out-of-set depth-2 lead reads the depth text.
      const deepOutOfSet = await createAgent(h.ctx, 'lead-out', 2)
      await bindAgent(h.ctx, deepOutOfSet, 'lead', 'plugin-z')
      await expectExactDenial(h, deepOutOfSet, 'subagent', DEPTH_TEXT)
    } finally {
      await h.dispose()
    }
  })
})
