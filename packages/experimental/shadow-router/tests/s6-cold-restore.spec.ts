/**
 * S6 row-level cold recovery: two real project bindings traverse the real
 * provisioning state machine through real storage, then restore row-for-row
 * — and their received deliveries survive — after the context is disposed
 * and a fresh harness boots over the same storage root.
 * @module tests/s6-cold-restore
 */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import { harness } from './helpers.ts'
import type { ProjectOpenResult, ShadowBindingRecord } from '../src/index.ts'

describe('shadow-router S6 binding row-level cold recovery', () => {
  it('S6: provisioned bindings and received deliveries restore row-for-row after a cold restart on the same root', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-s6-cold-'))

    // Phase 1: provision two real projects so the binding rows traverse the
    // real state machine (reserving → provisioning → ready) through real
    // storage, then authorize each open run and deliver one message. The
    // recorded values are what the restart must reproduce.
    const phase1 = await (async () => {
      const h1 = await harness(root, { authorizedRoots: [root] })
      try {
        const dirA = await h1.makeProjectDir('s6-project-a')
        const dirB = await h1.makeProjectDir('s6-project-b')
        const openA = await h1.router.openProject(h1.shadow, { path: dirA, requestId: 's6-cold-open-a' })
        const openB = await h1.router.openProject(h1.shadow, { path: dirB, requestId: 's6-cold-open-b' })
        expect(openA.state).toBe('ready')
        expect(openB.state).toBe('ready')
        expect(openA.workspaceId).not.toBe(openB.workspaceId)
        expect(openA.controllerSessionId).not.toBe(openB.controllerSessionId)
        expect(h1.router.findBinding(openA.workspaceId)!.profileKey).toBe('devframe')
        expect(h1.router.findBinding(openB.workspaceId)!.profileKey).toBe('devframe')

        await h1.router.setActiveGoal(openA.workspaceId, 's6-goal-a', 's6-hash-a')
        await h1.router.setActiveGoal(openB.workspaceId, 's6-goal-b', 's6-hash-b')
        const sendA = await h1.router.sendToProject(h1.shadow, {
          workspaceId: openA.workspaceId,
          bindingRevision: h1.router.findBinding(openA.workspaceId)!.bindingRevision,
          goalId: 's6-goal-a',
          acceptanceHash: 's6-hash-a',
          requestId: 's6-cold-send-a',
          mode: 'work',
          text: 'S6 cold-restart delivery for project A',
        })
        const sendB = await h1.router.sendToProject(h1.shadow, {
          workspaceId: openB.workspaceId,
          bindingRevision: h1.router.findBinding(openB.workspaceId)!.bindingRevision,
          goalId: 's6-goal-b',
          acceptanceHash: 's6-hash-b',
          requestId: 's6-cold-send-b',
          mode: 'work',
          text: 'S6 cold-restart delivery for project B',
        })
        expect(sendA.status).toBe('received')
        expect(sendB.status).toBe('received')
        const preDeliveriesA = h1.router.listDeliveries(openA.workspaceId)
        const preDeliveriesB = h1.router.listDeliveries(openB.workspaceId)
        expect(preDeliveriesA.map(record => record.state)).toEqual(['received'])
        expect(preDeliveriesB.map(record => record.state)).toEqual(['received'])
        // Record the final pre-restart rows (after the goal bumped the
        // revisions) field by field.
        const beforeA = h1.router.findBinding(openA.workspaceId)!
        const beforeB = h1.router.findBinding(openB.workspaceId)!
        expect(beforeA.state).toBe('ready')
        expect(beforeB.state).toBe('ready')
        return {
          openA,
          openB,
          beforeA,
          beforeB,
          deliveryIds: { a: sendA.messageId, b: sendB.messageId },
          receivedAt: { a: preDeliveriesA[0]!.receivedAt!, b: preDeliveriesB[0]!.receivedAt! },
        }
      } finally {
        // Cold restart: dispose the context but keep the root on disk. The
        // JSON backend refuses a second live handle, so this settles first.
        await h1.close()
      }
    })()
    const { openA, openB, beforeA, beforeB } = phase1

    // Phase 2: a fresh harness boots over the same root.
    const h2 = await harness(root, { authorizedRoots: [root] })
    try {
      // Row-level re-assertion for EACH workspace, field by field.
      const afterA = h2.router.findBinding(beforeA.workspaceId)
      const afterB = h2.router.findBinding(beforeB.workspaceId)
      expect(afterA).toBeDefined()
      expect(afterB).toBeDefined()
      for (const [before, after] of [[beforeA, afterA!], [beforeB, afterB!]] as const) {
        expect(after.state, 'state').toBe('ready')
        expect(after.bindingRevision, 'bindingRevision').toBe(before.bindingRevision)
        expect(after.canonicalPath, 'canonicalPath').toBe(before.canonicalPath)
        expect(after.controllerSessionId, 'controllerSessionId').toBe(before.controllerSessionId)
        expect(after.profileKey, 'profileKey').toBe(before.profileKey)
        // The rest of the row round-trips too: no field was rewritten, so the
        // restored row is the same durable row, not a re-created one.
        expect(after).toEqual(before)
      }
      // The returned open receipts still describe the same restored rows.
      expect(afterA!.canonicalPath).toBe(openA.canonicalPath)
      expect(afterA!.controllerSessionId).toBe(openA.controllerSessionId)
      expect(afterB!.canonicalPath).toBe(openB.canonicalPath)
      expect(afterB!.controllerSessionId).toBe(openB.controllerSessionId)

      // Sessions are process-local: the reserved controller ids are absent
      // right after the restart, and an explicit host creation on the SAME id
      // brings each controller session back with its canonical cwd.
      expect(h2.ctx.sessions.get(beforeA.controllerSessionId)).toBeUndefined()
      expect(h2.ctx.sessions.get(beforeB.controllerSessionId)).toBeUndefined()
      h2.ctx.sessions.create(SessionId(beforeA.controllerSessionId), { meta: { cwd: beforeA.canonicalPath } })
      h2.ctx.sessions.create(SessionId(beforeB.controllerSessionId), { meta: { cwd: beforeB.canonicalPath } })
      expect(h2.ctx.sessions.get(beforeA.controllerSessionId)?.header.cwd).toBe(beforeA.canonicalPath)
      expect(h2.ctx.sessions.get(beforeB.controllerSessionId)?.header.cwd).toBe(beforeB.canonicalPath)

      // The deliveries table round-trips: the persisted received state is a
      // durable fact distinct from completed, and it survives the restart.
      const restoredA = h2.router.listDeliveries(beforeA.workspaceId)
      const restoredB = h2.router.listDeliveries(beforeB.workspaceId)
      expect(restoredA.map(record => record.messageId)).toEqual([phase1.deliveryIds.a])
      expect(restoredB.map(record => record.messageId)).toEqual([phase1.deliveryIds.b])
      expect(restoredA[0]!.state).toBe('received')
      expect(restoredB[0]!.state).toBe('received')
      expect(restoredA[0]!.receivedAt).toBe(phase1.receivedAt.a)
      expect(restoredB[0]!.receivedAt).toBe(phase1.receivedAt.b)
    } finally {
      await h2.dispose()
    }
  })
})
