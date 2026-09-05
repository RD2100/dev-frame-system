/**
 * AT2C-02 冷恢复重装 — anchored from
 * `scenarios/AT2C-02-cold-restore-rebind.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试, 两段 harness
 * 共享同一 storage root, dispose({ keepRoot: true }) 后重开).
 *
 * 断言面：新进程 Service.init 一次性从 bindings 表重建查询索引、find/
 * byRole/list 免会话重放作答、记录逐字恢复且 createdAt 保持首写值；重启后
 * rebind 三分——同内容幂等、不同内容 ALREADY_BOUND、未知 agent
 * AGENT_UNKNOWN。
 *
 * 与草案的已记差异：草案假定 run B 的 session store 也冷恢复出 run A 的
 * 会话；实现里 `SessionStore` 是纯内存服务（不持久、不恢复），故 run B
 * 先以相同 id 重建 live 会话再执行 rebind 探针。
 *
 * @module tests/at2c-02-cold-restore-rebind
 */

import { expect, describe, it } from 'vitest'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness, type Harness } from './helpers.ts'

const CWD = (h: Harness) => join(h.root, `ws-${Math.random().toString(36).slice(2, 8)}`)

describe('AT2C-02 cold restore rebind', () => {
  it('answers queries from the restored index and splits rebind into idempotent, conflict, and unknown', async () => {
    // Run A: the seeding segment.
    const h1 = await harness()
    const controller = await h1.ctx.agentBindings.createBoundSession({ cwd: CWD(h1), role: 'controller' })
    const lead = await h1.ctx.agentBindings.createBoundSession({
      cwd: CWD(h1), role: 'lead', parentSessionId: controller.record.agentId, pluginId: PluginId('plugin-a'),
    })
    const worker = await h1.ctx.agentBindings.createBoundSession({
      cwd: CWD(h1), role: 'worker', parentSessionId: lead.record.agentId, taskId: TaskId('t-1'),
    })
    expect(h1.ctx.agentBindings.list().map(record => record.role)).toEqual(['controller', 'lead', 'worker'])
    const root = h1.root
    await h1.dispose({ keepRoot: true })

    // Run B: a fresh process over the same storage root; no session replay.
    const h2 = await harness(root)
    try {
      // Every restored record returns verbatim, with its first-write createdAt.
      expect(h2.ctx.agentBindings.list()).toEqual([controller.record, lead.record, worker.record])
      expect(h2.ctx.agentBindings.byRole('lead')).toEqual([lead.record])
      expect(h2.ctx.agentBindings.byRole('worker')).toEqual([worker.record])
      expect(h2.ctx.agentBindings.byRole('controller')).toEqual([controller.record])
      expect(h2.ctx.agentBindings.find(lead.record.agentId)).toEqual(lead.record)
      expect(h2.ctx.agentBindings.find(SessionId('session-404'))).toBeUndefined()

      // Idempotent rebind: same content returns the existing record untouched.
      // The session store is in-memory, so run B recreates the live session
      // under the recorded id before binding (see the file-header note).
      const liveLead = h2.ctx.sessions.create(SessionId(lead.record.agentId), { meta: { cwd: CWD(h2) } })
      const rebound = await h2.ctx.agentBindings.bind({
        agentId: liveLead.id,
        role: 'lead',
        parentSessionId: lead.record.parentSessionId,
        pluginId: lead.record.pluginId,
        taskId: lead.record.taskId,
      })
      expect(rebound).toEqual(lead.record)
      expect(h2.ctx.agentBindings.list()).toHaveLength(3)

      // Conflicting rebind: different content fails loud, zero rewrite.
      await expect(h2.ctx.agentBindings.bind({
        agentId: liveLead.id, role: 'worker', taskId: lead.record.taskId,
      })).rejects.toMatchObject({
        code: 'SESSION_IDENTITY_ALREADY_BOUND',
        message: `agent "${lead.record.agentId}" is already bound with different content`,
      })
      expect(h2.ctx.agentBindings.list()).toHaveLength(3)
      expect(h2.ctx.agentBindings.find(lead.record.agentId)).toEqual(lead.record)

      // Unknown agent: the session store has no such live agent.
      await expect(h2.ctx.agentBindings.bind({ agentId: SessionId('session-404'), role: 'worker' }))
        .rejects.toMatchObject({
          code: 'SESSION_IDENTITY_AGENT_UNKNOWN',
          message: 'agent "session-404" does not exist in the session store',
        })
      expect(h2.ctx.agentBindings.list()).toHaveLength(3)
    } finally {
      await h2.dispose()
    }
  })
})
