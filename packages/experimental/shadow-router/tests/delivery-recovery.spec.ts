/** AT2-05: interrupted deliveries converge on one accepted input after reopening the real storage. */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import { harness, seedHarness, seedWorkspaceFact } from './helpers.ts'
import type { ShadowBindingRecord, ShadowDeliveryRecord } from '../src/index.ts'

interface ScenarioSeed {
  readonly workspaceId: string
  readonly canonicalPath: string
  readonly controllerSessionId: string
  readonly goalId: string
  readonly acceptanceHash: string
}

/** Seed one ready binding (authorized goal) through the real domain. */
async function seedReadyBinding(seed: Awaited<ReturnType<typeof seedHarness>>, scenario: ScenarioSeed): Promise<void> {
  const now = new Date().toISOString()
  await seedWorkspaceFact(seed.workspaceDomain, scenario.workspaceId, scenario.canonicalPath)
  const binding: ShadowBindingRecord = {
    workspaceId: WorkspaceId(scenario.workspaceId),
    canonicalPath: scenario.canonicalPath,
    controllerSessionId: SessionId(scenario.controllerSessionId),
    profileKey: 'devframe',
    bindingRevision: 1,
    requestId: 'seed-open-1',
    state: 'ready',
    activeGoalId: scenario.goalId,
    activeAcceptanceHash: AcceptanceHash(scenario.acceptanceHash),
    createdAt: now,
    updatedAt: now,
  }
  await seed.domain.table('bindings').put(binding.workspaceId, binding)
}

/** Seed one crash-residue delivery row through the real domain. */
async function seedDelivery(seed: Awaited<ReturnType<typeof seedHarness>>, scenario: ScenarioSeed, overrides: Omit<Partial<ShadowDeliveryRecord>, 'messageId' | 'requestId'> & { readonly messageId: string; readonly requestId: string; readonly state: ShadowDeliveryRecord['state'] }): Promise<void> {
  const now = new Date().toISOString()
  const { messageId, requestId, ...rest } = overrides
  const delivery: ShadowDeliveryRecord = {
    messageId: ShadowMessageId(messageId),
    requestId: ShadowRequestId(requestId),
    sourceSessionId: SessionId('session-shadow'),
    workspaceId: WorkspaceId(scenario.workspaceId),
    bindingRevision: 1,
    goalId: scenario.goalId,
    acceptanceHash: AcceptanceHash(scenario.acceptanceHash),
    mode: 'work',
    text: 'seeded delivery text',
    createdAt: now,
    updatedAt: now,
    ...rest,
  }
  await seed.domain.table('deliveries').put(delivery.messageId, delivery)
}

describe('shadow-router delivery recovery', () => {
  it('AT2-05: an intent persisted before target acceptance converges to one received input on retry and on recovery', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-05a-'))
    const scenario: ScenarioSeed = {
      workspaceId: 'ws-recovery-1',
      canonicalPath: join(root, 'project-a'),
      controllerSessionId: 'session-ctrl-r1',
      goalId: 'goal-r1',
      acceptanceHash: 'hash-run-r1',
    }
    const seed = await seedHarness(root)
    try {
      await seedReadyBinding(seed, scenario)
      await seedDelivery(seed, scenario, { messageId: 'msg-seed-q-1', requestId: 'seed-q-1', state: 'queued' })
      await seedDelivery(seed, scenario, { messageId: 'msg-seed-q-2', requestId: 'seed-q-2', state: 'queued' })
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] })
    try {
      h.ctx.sessions.create(SessionId('session-ctrl-r1'), { meta: { cwd: scenario.canonicalPath } })
      // Retry the first interrupted delivery with the same stable request id.
      const receipt = await h.router.sendToProject(h.shadow, {
        workspaceId: scenario.workspaceId,
        bindingRevision: 1,
        goalId: scenario.goalId,
        acceptanceHash: scenario.acceptanceHash,
        requestId: 'seed-q-1',
        mode: 'work',
        text: 'seeded delivery text',
      })
      expect(receipt.messageId).toBe('msg-seed-q-1')
      expect(receipt.status).toBe('received')
      // Recover the second through the host recovery seam.
      const recovered = await h.router.recoverDeliveries(WorkspaceId(scenario.workspaceId))
      expect(recovered.map(record => record.messageId)).toEqual(['msg-seed-q-2'])
      expect(recovered[0]!.state).toBe('received')
      // One accepted input per message id — no duplicate rows, and the
      // controller session the reservations converge on is the same one.
      const deliveries = h.router.listDeliveries(WorkspaceId(scenario.workspaceId))
      expect(deliveries).toHaveLength(2)
      expect(deliveries.every(record => record.state === 'received')).toBe(true)
      expect(h.ctx.sessions.get(SessionId('session-ctrl-r1'))?.header.cwd).toBe(scenario.canonicalPath)
    } finally {
      await h.dispose()
    }
  })

  it('AT2-05: an accepted delivery whose sender receipt was lost is returned without rewriting the acceptance', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-05b-'))
    const scenario: ScenarioSeed = {
      workspaceId: 'ws-recovery-2',
      canonicalPath: join(root, 'project-a'),
      controllerSessionId: 'session-ctrl-r2',
      goalId: 'goal-r2',
      acceptanceHash: 'hash-run-r2',
    }
    const acceptedAt = '2026-09-05T10:00:00.000Z'
    const seed = await seedHarness(root)
    try {
      await seedReadyBinding(seed, scenario)
      await seedDelivery(seed, scenario, {
        messageId: 'msg-seed-r-1',
        requestId: 'seed-r-1',
        state: 'received',
        receivedAt: acceptedAt,
      })
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] })
    try {
      h.ctx.sessions.create(SessionId('session-ctrl-r2'), { meta: { cwd: scenario.canonicalPath } })
      const receipt = await h.router.sendToProject(h.shadow, {
        workspaceId: scenario.workspaceId,
        bindingRevision: 1,
        goalId: scenario.goalId,
        acceptanceHash: scenario.acceptanceHash,
        requestId: 'seed-r-1',
        mode: 'work',
        text: 'seeded delivery text',
      })
      expect(receipt.status).toBe('received')
      const deliveries = h.router.listDeliveries(WorkspaceId(scenario.workspaceId))
      expect(deliveries).toHaveLength(1)
      expect(deliveries[0]!.state).toBe('received')
      expect(deliveries[0]!.receivedAt).toBe(acceptedAt)
    } finally {
      await h.dispose()
    }
  })

  it('AT2-05: a delivery interrupted before its intent was persisted is a fresh accepted delivery', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-05c-'))
    const scenario: ScenarioSeed = {
      workspaceId: 'ws-recovery-3',
      canonicalPath: join(root, 'project-a'),
      controllerSessionId: 'session-ctrl-r3',
      goalId: 'goal-r3',
      acceptanceHash: 'hash-run-r3',
    }
    const seed = await seedHarness(root)
    try {
      await seedReadyBinding(seed, scenario)
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] })
    try {
      h.ctx.sessions.create(SessionId('session-ctrl-r3'), { meta: { cwd: scenario.canonicalPath } })
      const receipt = await h.router.sendToProject(h.shadow, {
        workspaceId: scenario.workspaceId,
        bindingRevision: 1,
        goalId: scenario.goalId,
        acceptanceHash: scenario.acceptanceHash,
        requestId: 'fresh-send-1',
        mode: 'work',
        text: 'fresh text after a lost race',
      })
      expect(receipt.status).toBe('received')
      expect(h.router.listDeliveries(WorkspaceId(scenario.workspaceId))).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })
})
