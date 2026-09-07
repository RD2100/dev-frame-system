/** AT2-06: retries, conflicts, size/queue limits, and old-Goal ownership. */

import { describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, realpath } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import { HARNESS_BACKENDS, harness, seedHarness, seedWorkspaceFact } from './helpers.ts'
import type { ShadowDeliveryRecord } from '../src/index.ts'

describe('shadow-router delivery limits and ownership', () => {
  it('AT2-06: identical retries deduplicate, different payloads conflict, and oversized text rejects', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-06a-'))
    const h = await harness(root, { authorizedRoots: [root], maxMessageChars: 64 })
    try {
      const dir = await h.makeProjectDir('project-a')
      const open = await h.router.openProject(h.shadow, { path: dir, requestId: 'at2-06-open' })
      await h.router.setActiveGoal(open.workspaceId, 'goal-1', 'hash-run-1')
      const revision = h.router.findBinding(open.workspaceId)!.bindingRevision
      const sendArgs = {
        workspaceId: open.workspaceId,
        bindingRevision: revision,
        goalId: 'goal-1',
        acceptanceHash: 'hash-run-1',
        requestId: 'at2-06-send-1',
        mode: 'work' as const,
        text: 'identical text for a stable retry',
      }
      const first = await h.router.sendToProject(h.shadow, sendArgs)
      const retry = await h.router.sendToProject(h.shadow, sendArgs)
      expect(retry.messageId).toBe(first.messageId)
      expect(h.router.listDeliveries(open.workspaceId)).toHaveLength(1)

      await expect(h.router.sendToProject(h.shadow, { ...sendArgs, text: 'a different payload with the same request id' }))
        .rejects.toMatchObject({ code: 'SHADOW_REQUEST_CONFLICT' })
      expect(h.router.listDeliveries(open.workspaceId)).toHaveLength(1)

      await expect(h.router.sendToProject(h.shadow, {
        ...sendArgs, requestId: 'at2-06-send-oversize', text: 'x'.repeat(65),
      })).rejects.toMatchObject({ code: 'SHADOW_MESSAGE_TOO_LARGE' })
      expect(h.router.listDeliveries(open.workspaceId)).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-06 [%s]: the pending queue limit rejects new input before acceptance', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-06b-'))
    const dir = join(root, 'project-a')
    await mkdir(dir)
    const canonical = await realpath(dir)
    // Crash residue: a ready binding plus two queued intents that already
    // occupy the bounded queue.
    const seed = await seedHarness(root, { backend })
    try {
      const now = new Date().toISOString()
      await seedWorkspaceFact(seed.workspaceDomain, 'ws-limit-1', canonical)
      await seed.domain.table('bindings').put(WorkspaceId('ws-limit-1'), {
        workspaceId: WorkspaceId('ws-limit-1'),
        canonicalPath: canonical,
        controllerSessionId: SessionId('session-ctrl-l1'),
        profileKey: 'devframe',
        bindingRevision: 2,
        requestId: 'seed-open-1',
        state: 'ready',
        activeGoalId: 'goal-1',
        activeAcceptanceHash: AcceptanceHash('hash-run-1'),
        createdAt: now,
        updatedAt: now,
      })
      for (const index of [1, 2]) {
        const delivery: ShadowDeliveryRecord = {
          messageId: ShadowMessageId(`msg-seed-q-${index}`),
          requestId: ShadowRequestId(`seed-q-${index}`),
          sourceSessionId: SessionId('session-shadow'),
          workspaceId: WorkspaceId('ws-limit-1'),
          bindingRevision: 2,
          goalId: 'goal-1',
          acceptanceHash: AcceptanceHash('hash-run-1'),
          mode: 'work',
          text: `queued residue ${index}`,
          state: 'queued',
          createdAt: now,
          updatedAt: now,
        }
        await seed.domain.table('deliveries').put(delivery.messageId, delivery)
      }
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root], maxPendingDeliveries: 2 }, { backend })
    try {
      h.ctx.sessions.create(SessionId('session-ctrl-l1'), { meta: { cwd: canonical } })
      expect(h.router.listDeliveries(WorkspaceId('ws-limit-1'))).toHaveLength(2)
      // A fresh send would be a THIRD pending input: rejected before acceptance.
      await expect(h.router.sendToProject(h.shadow, {
        workspaceId: 'ws-limit-1',
        bindingRevision: 2,
        goalId: 'goal-1',
        acceptanceHash: 'hash-run-1',
        requestId: 'at2-06b-send-3',
        mode: 'work',
        text: 'rejected while the queue is full',
      })).rejects.toMatchObject({ code: 'SHADOW_QUEUE_FULL' })
      expect(h.router.listDeliveries(WorkspaceId('ws-limit-1'))).toHaveLength(2)
    } finally {
      await h.dispose()
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-06 [%s]: a previous Goal message never reaches the new Goal and its retry limits do not reset', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-06c-'))
    const h1 = await harness(root, { authorizedRoots: [root] }, { backend })
    // Generation 1 runs the goal switch to its visible rejection surface.
    const gen1 = await (async () => {
      try {
        const dir = await h1.makeProjectDir('project-a')
        const open = await h1.router.openProject(h1.shadow, { path: dir, requestId: 'at2-06c-open' })
        await h1.router.setActiveGoal(open.workspaceId, 'goal-1', 'hash-run-1')
        const revisionGoal1 = h1.router.findBinding(open.workspaceId)!.bindingRevision
        const first = await h1.router.sendToProject(h1.shadow, {
          workspaceId: open.workspaceId,
          bindingRevision: revisionGoal1,
          goalId: 'goal-1',
          acceptanceHash: 'hash-run-1',
          requestId: 'at2-06c-send-goal-1',
          mode: 'work',
          text: 'work bound to goal 1',
        })
        expect(first.status).toBe('received')

        // The controller starts another Goal; the association version moves on.
        await h1.router.setActiveGoal(open.workspaceId, 'goal-2', 'hash-run-2')
        const revisionGoal2 = h1.router.findBinding(open.workspaceId)!.bindingRevision
        expect(revisionGoal2).toBeGreaterThan(revisionGoal1)

        // The old revision is stale outright...
        await expect(h1.router.sendToProject(h1.shadow, {
          workspaceId: open.workspaceId,
          bindingRevision: revisionGoal1,
          goalId: 'goal-1',
          acceptanceHash: 'hash-run-1',
          requestId: 'at2-06c-stale-revision',
          mode: 'work',
          text: 'old revision',
        })).rejects.toMatchObject({ code: 'SHADOW_STALE_REVISION' })

        // ...and the current revision with the previous Goal's association is
        // never accepted as input to the new Goal — repeatedly, without reset.
        for (let attempt = 0; attempt < 3; attempt++) {
          await expect(h1.router.sendToProject(h1.shadow, {
            workspaceId: open.workspaceId,
            bindingRevision: revisionGoal2,
            goalId: 'goal-1',
            acceptanceHash: 'hash-run-1',
            requestId: `at2-06c-old-goal-${attempt}`,
            mode: 'work',
            text: 'old goal association',
          })).rejects.toMatchObject({ code: 'SHADOW_GOAL_STALE' })
        }
        const deliveries = h1.router.listDeliveries(open.workspaceId)
        expect(deliveries).toHaveLength(1)
        expect(deliveries[0]!.goalId).toBe('goal-1')
        return { workspaceId: open.workspaceId, revisionGoal1 }
      } finally {
        // Cold restart: the context stops, the root stays on disk for the
        // residue seed and the recovery reopen — both write and restore the
        // root while no router process holds it (each medium is single-writer).
        await h1.close()
      }
    })()

    // Crash residue after the switch: one queued intent still bound to the
    // old Goal's association, persisted through the real domain.
    const seed = await seedHarness(root, { backend })
    try {
      const now = new Date().toISOString()
      const delivery: ShadowDeliveryRecord = {
        messageId: ShadowMessageId('msg-old-goal-queued'),
        requestId: ShadowRequestId('old-goal-queued'),
        sourceSessionId: SessionId('session-shadow'),
        workspaceId: WorkspaceId(gen1.workspaceId),
        bindingRevision: gen1.revisionGoal1,
        goalId: 'goal-1',
        acceptanceHash: AcceptanceHash('hash-run-1'),
        mode: 'work',
        text: 'queued before the Goal switch',
        state: 'queued',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('deliveries').put(delivery.messageId, delivery)
    } finally {
      await seed.dispose()
    }

    // Reopen the real storage: the stale-Goal residue converges to
    // cancelled, never to the controller's current Goal.
    const h2 = await harness(root, { authorizedRoots: [root] }, { backend })
    try {
      const recovered = await h2.router.recoverDeliveries(WorkspaceId(gen1.workspaceId))
      expect(recovered.map(record => record.state)).toEqual(['cancelled'])
      expect(recovered[0]!.cancelReason).toBe('goal-no-longer-authorized')
    } finally {
      await h2.dispose()
    }
  })
})
