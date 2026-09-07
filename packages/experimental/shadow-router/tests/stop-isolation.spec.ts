/** AT2-07: stopping one project twice is safe and isolated from the others. */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import { HARNESS_BACKENDS, harness, seedHarness } from './helpers.ts'
import type { ShadowDeliveryRecord } from '../src/index.ts'

describe('shadow-router stop isolation', () => {
  it.each(HARNESS_BACKENDS)('AT2-07 [%s]: project A stops idempotently after draining while B continues unaffected', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-07-'))
    const h1 = await harness(root, { authorizedRoots: [root] }, { backend })
    const dirA = await h1.makeProjectDir('project-a')
    const dirB = await h1.makeProjectDir('project-b')
    const openA = await h1.router.openProject(h1.shadow, { path: dirA, requestId: 'at2-07-open-a' })
    const openB = await h1.router.openProject(h1.shadow, { path: dirB, requestId: 'at2-07-open-b' })
    await h1.router.setActiveGoal(openA.workspaceId, 'goal-a', 'hash-run-a')
    await h1.router.setActiveGoal(openB.workspaceId, 'goal-b', 'hash-run-b')
    const revisionA = h1.router.findBinding(openA.workspaceId)!.bindingRevision
    const revisionB = h1.router.findBinding(openB.workspaceId)!.bindingRevision
    const sendA = await h1.router.sendToProject(h1.shadow, {
      workspaceId: openA.workspaceId, bindingRevision: revisionA,
      goalId: 'goal-a', acceptanceHash: 'hash-run-a',
      requestId: 'at2-07-send-a', mode: 'work', text: 'real owned work in A',
    })
    const sendB = await h1.router.sendToProject(h1.shadow, {
      workspaceId: openB.workspaceId, bindingRevision: revisionB,
      goalId: 'goal-b', acceptanceHash: 'hash-run-b',
      requestId: 'at2-07-send-b', mode: 'work', text: 'real owned work in B',
    })
    expect(sendA.status).toBe('received')
    expect(sendB.status).toBe('received')
    // Cold restart: the context stops, the root stays on disk for the seed and h2.
    await h1.close()

    // Crash residue: one queued note in A that stop must drain visibly.
    const seed = await seedHarness(root, { backend })
    try {
      const now = new Date().toISOString()
      const queued: ShadowDeliveryRecord = {
        messageId: ShadowMessageId('msg-at2-07-queued'),
        requestId: ShadowRequestId('at2-07-queued'),
        sourceSessionId: SessionId('session-shadow'),
        workspaceId: WorkspaceId(openA.workspaceId),
        bindingRevision: revisionA,
        goalId: 'goal-a',
        acceptanceHash: AcceptanceHash('hash-run-a'),
        mode: 'note',
        text: 'queued note in A',
        state: 'queued',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('deliveries').put(queued.messageId, queued)
    } finally {
      await seed.dispose()
    }

    const h2 = await harness(root, { authorizedRoots: [root] }, { backend })
    try {
      expect(h2.router.listDeliveries(openA.workspaceId)).toHaveLength(2)

      // First stop: the owned queue drains into visible cancellations, the
      // accepted delivery stays received, and the binding parks in stopping.
      const stopA = await h2.router.stopProject(h2.shadow, {
        workspaceId: openA.workspaceId,
        expectedRevision: revisionA,
        requestId: 'at2-07-stop-a-1',
      })
      expect(stopA.status).toBe('stopping')
      expect(stopA.cancelledDeliveries).toBe(1)
      expect(stopA.bindingRevision).toBe(revisionA + 1)
      const afterStop = h2.router.listDeliveries(openA.workspaceId)
      expect(afterStop.find(delivery => delivery.messageId === sendA.messageId)?.state).toBe('received')
      expect(afterStop.find(delivery => delivery.messageId === 'msg-at2-07-queued')?.state).toBe('cancelled')

      await h2.router.confirmProjectStopped(openA.workspaceId)
      expect(h2.router.findBinding(openA.workspaceId)?.state).toBe('stopped')

      // Second stop with the SAME request id replays the same receipt...
      const stopReplay = await h2.router.stopProject(h2.shadow, {
        workspaceId: openA.workspaceId,
        expectedRevision: revisionA,
        requestId: 'at2-07-stop-a-1',
      })
      expect(stopReplay).toEqual(stopA)
      // ...and a fresh request id against the stopped project is a no-op.
      const stopAgain = await h2.router.stopProject(h2.shadow, {
        workspaceId: openA.workspaceId,
        expectedRevision: stopA.bindingRevision,
        requestId: 'at2-07-stop-a-2',
      })
      expect(stopAgain.status).toBe('stopped')
      expect(stopAgain.bindingRevision).toBe(stopA.bindingRevision)

      // B is untouched: binding ready, controller live, queue intact, and it
      // still receives new input at its current revision.
      expect(h2.router.findBinding(openB.workspaceId)?.state).toBe('ready')
      h2.ctx.sessions.create(openB.controllerSessionId, { meta: { cwd: openB.canonicalPath } })
      expect(h2.router.listDeliveries(openB.workspaceId).map(delivery => delivery.messageId)).toEqual([sendB.messageId])
      const sendB2 = await h2.router.sendToProject(h2.shadow, {
        workspaceId: openB.workspaceId,
        bindingRevision: revisionB,
        goalId: 'goal-b',
        acceptanceHash: 'hash-run-b',
        requestId: 'at2-07-send-b-2',
        mode: 'note',
        text: 'B keeps receiving',
      })
      expect(sendB2.status).toBe('received')

      // A closed receiver rejects sends instead of accepting silently.
      await expect(h2.router.sendToProject(h2.shadow, {
        workspaceId: openA.workspaceId,
        bindingRevision: stopA.bindingRevision,
        goalId: 'goal-a',
        acceptanceHash: 'hash-run-a',
        requestId: 'at2-07-send-a-after-stop',
        mode: 'work',
        text: 'must not land',
      })).rejects.toMatchObject({ code: 'SHADOW_RECEIVER_CLOSED' })
    } finally {
      await h2.dispose()
    }
  })
})
