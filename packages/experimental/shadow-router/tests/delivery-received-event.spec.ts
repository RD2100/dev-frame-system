/**
 * The `shadow/delivery-received` observe-only event: every real transition of
 * a queued delivery into `received` emits exactly once — on the send path and
 * on the recovery convergence — while replays, already-received rows, and
 * cancelled rows emit nothing.
 */

import { describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import { HARNESS_BACKENDS, harness, seedHarness, seedWorkspaceFact } from './helpers.ts'
import type { ShadowBindingRecord, ShadowDeliveryRecord } from '../src/index.ts'

/** One observed event: the workspace id plus the record snapshot as emitted. */
interface ObservedDelivery {
  readonly workspaceId: string
  readonly record: ShadowDeliveryRecord
}

/** Collect the delivery-received events one harness context emits. */
function observeEvents(ctx: Context): ObservedDelivery[] {
  const seen: ObservedDelivery[] = []
  ctx.on('shadow/delivery-received', (workspaceId, record) => {
    seen.push({ workspaceId, record })
  })
  return seen
}

describe('shadow-router shadow/delivery-received event', () => {
  it('emits once per accepted send with the frozen received snapshot, and not on replay', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-emit-send-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const projectDir = await h.makeProjectDir('emit-send')
      const opened = await h.router.openProject(h.shadow, { path: projectDir, requestId: 'emit-open-1' })
      await h.router.setActiveGoal(opened.workspaceId, 'goal-emit-1', 'hash-run-emit-1')
      // setActiveGoal bumps the association version; the send asserts the current one.
      const binding = h.router.findBinding(opened.workspaceId)
      if (binding === undefined) throw new Error('the opened project has no binding')
      const seen = observeEvents(h.ctx)
      const send = {
        workspaceId: opened.workspaceId,
        bindingRevision: binding.bindingRevision,
        goalId: 'goal-emit-1',
        acceptanceHash: 'hash-run-emit-1',
        requestId: 'emit-send-1',
        mode: 'work' as const,
        text: 'deliver once, emit once',
      }
      const receipt = await h.router.sendToProject(h.shadow, send)
      expect(receipt.status).toBe('received')
      // A replayed request returns the stored result without a second transition.
      await h.router.sendToProject(h.shadow, send)
      expect(seen).toHaveLength(1)
      expect(seen[0]!.workspaceId).toBe(opened.workspaceId)
      expect(seen[0]!.record.messageId).toBe(ShadowMessageId('msg-emit-send-1'))
      expect(seen[0]!.record.state).toBe('received')
      expect(seen[0]!.record.receivedAt).toBe(h.router.listDeliveries(opened.workspaceId)[0]!.receivedAt)
      expect(Object.isFrozen(seen[0]!.record)).toBe(true)
    } finally {
      await h.dispose()
    }
  })

  it.each(HARNESS_BACKENDS)('recovery convergence emits for rows landing received and not for cancelled rows [%s]', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-emit-recovery-'))
    const scenario = {
      workspaceId: 'ws-emit-recovery',
      canonicalPath: join(root, 'project-emit'),
      controllerSessionId: 'session-ctrl-emit',
      goalId: 'goal-emit-live',
      acceptanceHash: 'hash-run-emit-live',
    }
    const seed = await seedHarness(root, { backend })
    try {
      await seedWorkspaceFact(seed.workspaceDomain, scenario.workspaceId, scenario.canonicalPath)
      const now = new Date().toISOString()
      const binding: ShadowBindingRecord = {
        workspaceId: WorkspaceId(scenario.workspaceId),
        canonicalPath: scenario.canonicalPath,
        controllerSessionId: SessionId(scenario.controllerSessionId),
        profileKey: 'devframe',
        bindingRevision: 1,
        requestId: 'seed-emit-open-1',
        state: 'ready',
        activeGoalId: scenario.goalId,
        activeAcceptanceHash: AcceptanceHash(scenario.acceptanceHash),
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('bindings').put(binding.workspaceId, binding)
      const row = (messageId: string, requestId: string, goalId: string): ShadowDeliveryRecord => ({
        messageId: ShadowMessageId(messageId),
        requestId: ShadowRequestId(requestId),
        sourceSessionId: SessionId('session-shadow'),
        workspaceId: WorkspaceId(scenario.workspaceId),
        bindingRevision: 1,
        goalId,
        acceptanceHash: AcceptanceHash(scenario.acceptanceHash),
        mode: 'work',
        text: 'seeded recovery text',
        state: 'queued',
        createdAt: now,
        updatedAt: now,
      })
      // One row still authorized against the binding's open run, one stale.
      await seed.domain.table('deliveries').put(ShadowMessageId('msg-emit-live'), row('msg-emit-live', 'seed-emit-live', scenario.goalId))
      await seed.domain.table('deliveries').put(ShadowMessageId('msg-emit-stale'), row('msg-emit-stale', 'seed-emit-stale', 'goal-emit-stale'))
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] }, { backend })
    try {
      h.ctx.sessions.create(SessionId(scenario.controllerSessionId), { meta: { cwd: scenario.canonicalPath } })
      const seen = observeEvents(h.ctx)
      const recovered = await h.router.recoverDeliveries(WorkspaceId(scenario.workspaceId))
      expect(recovered.map(record => record.messageId)).toEqual(['msg-emit-live', 'msg-emit-stale'])
      expect(recovered.map(record => record.state)).toEqual(['received', 'cancelled'])
      // Only the real queued→received transition emitted; the cancellation did not.
      expect(seen.map(event => event.record.messageId)).toEqual([ShadowMessageId('msg-emit-live')])
      expect(seen[0]!.workspaceId).toBe(scenario.workspaceId)
      expect(seen[0]!.record.state).toBe('received')
    } finally {
      await h.dispose()
    }
  })
})
