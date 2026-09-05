/**
 * AT2C-01 精确 cwd 绑定创建 — anchored from
 * `scenarios/AT2C-01-exact-cwd-bound-creation.md` (recorded-session 场景草案,
 * 组合挂载波未启动; 本文件把草案断言面落为包内 vitest 测试).
 *
 * 断言面：createBoundSession 一次调用写齐 header（逐字 cwd、parent、深度
 * 派生/显式）与 binding record；前置校验先于 sessions.create——未知 role、
 * 空 cwd、未知 parent、显式深度无父、非绝对 cwd 各有探针；拒绝路径零
 * record；成功调用与落盘行一一对应。
 *
 * @module tests/at2c-01-exact-cwd-bound-creation
 */

import { expect, describe, it } from 'vitest'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { harness, type Harness } from './helpers.ts'
import type { AgentBindingRecord } from '@deepseek-ai/dsh-experimental-project-contracts'

const CWD = (h: Harness) => join(h.root, `ws-${Math.random().toString(36).slice(2, 8)}`)

/** Assert one creation fails loud with the exact code and reason, before any record exists. */
async function expectCreationRejected(
  creation: Promise<unknown>,
  code: string,
  message: string,
): Promise<void> {
  await expect(creation).rejects.toMatchObject({ code, message })
}

describe('AT2C-01 exact cwd bound creation', () => {
  it('writes the verbatim cwd, lineage, and depth derivation in one call', async () => {
    const h = await harness()
    try {
      const parent = h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })

      // Top-level creation: no lineage, no depth, exact cwd.
      const topCwd = CWD(h)
      const top = await h.ctx.agentBindings.createBoundSession({ cwd: topCwd, role: 'controller' })
      expect(top.session.header.cwd).toBe(topCwd)
      expect(top.session.header.parentSession).toBeUndefined()
      expect(top.session.header.delegationDepth).toBeUndefined()
      expect(top.record.role).toBe('controller')
      expect(top.record.parentSessionId).toBeUndefined()

      // Delegated creation: derived depth is parent depth + 1.
      const leadCwd = CWD(h)
      const lead = await h.ctx.agentBindings.createBoundSession({
        cwd: leadCwd,
        role: 'lead',
        parentSessionId: parent.id,
        pluginId: PluginId('plugin-a'),
        taskId: TaskId('t-1'),
      })
      expect(lead.session.header.cwd).toBe(leadCwd)
      expect(lead.session.header.parentSession).toBe(parent.id)
      expect(lead.session.header.delegationDepth).toBe(1)
      expect(lead.record.parentSessionId).toBe(parent.id)
      expect(lead.record.pluginId).toBe('plugin-a')
      expect(lead.record.taskId).toBe('t-1')

      // Explicit depth overrides the derivation (parent depth + 1 would be 2).
      const workerCwd = CWD(h)
      const worker = await h.ctx.agentBindings.createBoundSession({
        cwd: workerCwd,
        role: 'worker',
        parentSessionId: lead.session.id,
        delegationDepth: 1,
      })
      expect(worker.session.header.cwd).toBe(workerCwd)
      expect(worker.session.header.delegationDepth).toBe(1)
    } finally {
      await h.dispose()
    }
  })

  it('rejects every malformed creation before the session store is consulted', async () => {
    const h = await harness()
    try {
      h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })
      await expectCreationRejected(
        h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'gatekeeper' as never }),
        'SESSION_IDENTITY_INVALID_REQUEST',
        '"gatekeeper" is not a hierarchy role',
      )
      await expectCreationRejected(
        h.ctx.agentBindings.createBoundSession({ cwd: '', role: 'controller' }),
        'SESSION_IDENTITY_INVALID_REQUEST',
        'cwd must be a non-empty absolute path',
      )
      await expectCreationRejected(
        h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'lead', parentSessionId: SessionId('session-404') }),
        'SESSION_IDENTITY_PARENT_UNKNOWN',
        'parent session "session-404" does not exist in the session store',
      )
      await expectCreationRejected(
        h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'worker', delegationDepth: 1 }),
        'SESSION_IDENTITY_INVALID_REQUEST',
        'delegationDepth requires a parentSessionId',
      )
      await expectCreationRejected(
        h.ctx.agentBindings.createBoundSession({ cwd: 'relative/path', role: 'lead' }),
        'SESSION_IDENTITY_INVALID_REQUEST',
        'the session store rejected the creation metadata (an existing id or a non-absolute cwd is the usual cause)',
      )
      expect(h.ctx.agentBindings.list()).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('persists exactly one binding row per successful creation', async () => {
    const h = await harness()
    try {
      const created: AgentBindingRecord[] = []
      created.push((await h.ctx.agentBindings.createBoundSession({ cwd: CWD(h), role: 'controller' })).record)
      const parent = h.ctx.sessions.create(undefined, { meta: { cwd: CWD(h) } })
      created.push((await h.ctx.agentBindings.createBoundSession({
        cwd: CWD(h), role: 'lead', parentSessionId: parent.id, pluginId: PluginId('plugin-a'),
      })).record)
      created.push((await h.ctx.agentBindings.createBoundSession({
        cwd: CWD(h), role: 'worker', parentSessionId: parent.id,
      })).record)

      const rows = h.ctx.agentBindings.list()
      expect(rows).toHaveLength(3)
      for (const record of created) {
        expect(record.agentId).toBe(record.sessionId)
        expect(h.ctx.agentBindings.find(record.agentId)).toEqual(record)
      }
      expect(rows).toEqual(created)
    } finally {
      await h.dispose()
    }
  })
})
