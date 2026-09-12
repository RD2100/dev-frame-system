/**
 * AT2C-06 不确定调用 probe 结算不重发 — anchored from
 * `scenarios/AT2C-06-uncertain-call-probe-settlement.md` (recorded-session
 * 场景草案, 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：probe 先行；retry 至多一次且仅在 probe 返回 absent 之后；
 * confirmed 免重发；still_uncertain 即使提供 retry 也不重发、返回
 * unresolved；四种 outcome 全部是数据不是异常；reconciler 无跨调用状态。
 * probe/retry 为计数 fixture（零文件、零网络、零进程副作用）。
 *
 * @module tests/at2c-06-uncertain-call-probe-settlement
 */

import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentReliability from '../src/index.ts'
import type { ReconciliationProbe, ReconciledOutcome } from '../src/index.ts'

describe('AT2C-06 uncertain call probe settlement', () => {
  it('settles every plan without any blind resend across all four outcomes', async () => {
    const ctx = new Context()
    try {
      await ctx.plugin(AgentReliability)
      const service = ctx.agentReliability

      /** Call order within the plan under construction ('probe' before any 'retry'). */
      let order: string[] = []
      let retryCalls = 0
      /** Build a plan fixture: the probe answers `probeStatus`; the retry is a counting fixture. */
      const plan = (operation: string, probeStatus: ReconciliationProbe['status'], withRetry: boolean) => ({
        operation,
        probe: async (): Promise<ReconciliationProbe> => {
          order.push('probe')
          return { status: probeStatus }
        },
        ...withRetry ? {
          retry: async (): Promise<string> => {
            order.push('retry')
            retryCalls += 1
            return 'synthetic-retry-result'
          },
        } : {},
      })

      // plan-1: confirmed settles from the probe itself; the retry never runs.
      order = []
      const plan1 = await service.reconcileUncertainCall<string>(plan('create-worktree', 'confirmed', true))
      const settled1: ReconciledOutcome<string> = plan1
      expect(settled1.status).toBe('settled')
      expect(settled1).toEqual({ status: 'settled', via: 'probe' })
      expect('result' in settled1).toBe(false)
      expect(order).toEqual(['probe'])

      // plan-2: absent with a retry resends exactly once, after the probe.
      order = []
      const plan2 = await service.reconcileUncertainCall<string>(plan('delete-worktree', 'absent', true))
      expect(plan2).toEqual({ status: 'settled', via: 'retry', result: 'synthetic-retry-result' })
      expect(order).toEqual(['probe', 'retry'])
      expect(retryCalls).toBe(1)

      // plan-3: absent without a retry reports absence as data.
      const plan3 = await service.reconcileUncertainCall(plan('delete-worktree', 'absent', false))
      expect(plan3).toEqual({ status: 'absent' })

      // plan-4/5: still_uncertain never resends, with or without a retry.
      const plan4 = await service.reconcileUncertainCall<string>(plan('create-worktree', 'still_uncertain', true))
      expect(plan4).toEqual({ status: 'unresolved' })
      const plan5 = await service.reconcileUncertainCall(plan('delete-worktree', 'still_uncertain', false))
      expect(plan5).toEqual({ status: 'unresolved' })

      // plan-6: the same operation name settles independently — no cross-plan state.
      order = []
      const plan6 = await service.reconcileUncertainCall<string>(plan('create-worktree', 'confirmed', true))
      expect(plan6).toEqual({ status: 'settled', via: 'probe' })
      expect(order).toEqual(['probe'])

      // The whole sequence resends exactly once (plan-2).
      expect(retryCalls).toBe(1)
    } finally {
      await ctx.fiber.dispose()
    }
  })
})
