/** AT2-08: status reads are bounded, honest about states, and side-effect free. */

import { describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, realpath } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { HARNESS_BACKENDS, harness, seedHarness } from './helpers.ts'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId } from '../src/index.ts'
import type { ShadowBindingRecord, ShadowDeliveryRecord } from '../src/index.ts'

describe('shadow-router status', () => {
  it('AT2-08: status pages projects, bounds deliveries, and never mutates state', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-08a-'))
    const h = await harness(root, { authorizedRoots: [root], statusPageSize: 2 })
    try {
      const [dirA, dirB, dirC] = await Promise.all([
        h.makeProjectDir('project-a'),
        h.makeProjectDir('project-b'),
        h.makeProjectDir('project-c'),
      ])
      const openA = await h.router.openProject(h.shadow, { path: dirA, requestId: 'at2-08-open-a' })
      const openB = await h.router.openProject(h.shadow, { path: dirB, requestId: 'at2-08-open-b' })
      await h.router.openProject(h.shadow, { path: dirC, requestId: 'at2-08-open-c' })

      // Three ready projects page two at a time with a stable cursor.
      const page1 = await h.router.projectStatus(h.shadow, {})
      expect(page1.projects).toHaveLength(2)
      expect(page1.nextCursor).toBe(2)
      const page2 = await h.router.projectStatus(h.shadow, {
        ...(page1.nextCursor === undefined ? {} : { cursor: page1.nextCursor }),
      })
      expect(page2.projects).toHaveLength(1)
      expect(page2.nextCursor).toBeUndefined()

      // Delivery states stay distinct: an acknowledged delivery is received
      // until the host completes it; a note never becomes completed. The
      // request ids fix the message-id order so the page contents are stable.
      await h.router.setActiveGoal(openA.workspaceId, 'goal-a', 'hash-run-a')
      const revision = h.router.findBinding(openA.workspaceId)!.bindingRevision
      const work = await h.router.sendToProject(h.shadow, {
        workspaceId: openA.workspaceId, bindingRevision: revision,
        goalId: 'goal-a', acceptanceHash: 'hash-run-a',
        requestId: 'at2-08-1-work', mode: 'work', text: 'owned work',
      })
      const note = await h.router.sendToProject(h.shadow, {
        workspaceId: openA.workspaceId, bindingRevision: revision,
        goalId: 'goal-a', acceptanceHash: 'hash-run-a',
        requestId: 'at2-08-2-note', mode: 'note', text: 'side note',
      })
      await h.router.completeDelivery(openA.workspaceId, work.messageId)
      await h.router.sendToProject(h.shadow, {
        workspaceId: openA.workspaceId, bindingRevision: revision,
        goalId: 'goal-a', acceptanceHash: 'hash-run-a',
        requestId: 'at2-08-3-note', mode: 'note', text: 'another side note',
      })

      const single = await h.router.projectStatus(h.shadow, { workspaceId: openA.workspaceId })
      expect(single.projects).toHaveLength(1)
      const entry = single.projects[0]!
      expect(entry.state).toBe('ready')
      // The bounded page shows the first two of three deliveries.
      expect(entry.deliveries.map(delivery => delivery.messageId)).toEqual([work.messageId, note.messageId])
      expect(entry.deliveriesTruncated).toBe(true)
      expect(entry.deliveries.find(delivery => delivery.messageId === work.messageId)?.state).toBe('completed')
      expect(entry.deliveries.find(delivery => delivery.messageId === work.messageId)?.completedAt).toBeDefined()
      expect(entry.deliveries.find(delivery => delivery.messageId === note.messageId)?.state).toBe('received')
      expect(entry.deliveries.find(delivery => delivery.messageId === note.messageId)?.completedAt).toBeUndefined()
      expect(entry.deliveries.every(delivery => delivery.receivedAt !== undefined)).toBe(true)

      // Reads are side-effect free: no new bindings, deliveries, controller
      // session events, and observedAt only moves forward.
      const before = JSON.stringify([
        h.router.listBindings(),
        h.router.listDeliveries(openA.workspaceId),
        h.router.listDeliveries(openB.workspaceId),
        h.ctx.sessions.get(openA.controllerSessionId)?.header.cwd,
      ])
      const first = await h.router.projectStatus(h.shadow, {})
      const second = await h.router.projectStatus(h.shadow, {})
      const third = await h.router.projectStatus(h.shadow, { workspaceId: openA.workspaceId })
      const after = JSON.stringify([
        h.router.listBindings(),
        h.router.listDeliveries(openA.workspaceId),
        h.router.listDeliveries(openB.workspaceId),
        h.ctx.sessions.get(openA.controllerSessionId)?.header.cwd,
      ])
      expect(after).toBe(before)
      expect(second.observedAt >= first.observedAt).toBe(true)
      expect(third.observedAt >= second.observedAt).toBe(true)
    } finally {
      await h.dispose()
    }
  })

  it('AT2-08: a queued delivery intent reads back as queued in the status readout', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-08c-'))
    const project = join(root, 'project-a')
    await mkdir(project)
    const canonical = await realpath(project)
    // Crash residue: a ready binding plus one queued intent that never got its
    // target-acceptance write, seeded through the real domain.
    const seed = await seedHarness(root)
    try {
      const now = new Date().toISOString()
      await seed.domain.table('bindings').put(WorkspaceId('ws-queued-1'), {
        workspaceId: WorkspaceId('ws-queued-1'),
        canonicalPath: canonical,
        controllerSessionId: SessionId('session-ctrl-q1'),
        profileKey: 'devframe',
        bindingRevision: 2,
        requestId: 'seed-open-1',
        state: 'ready',
        activeGoalId: 'goal-1',
        activeAcceptanceHash: AcceptanceHash('hash-run-1'),
        createdAt: now,
        updatedAt: now,
      })
      const residue: ShadowDeliveryRecord = {
        messageId: ShadowMessageId('msg-seed-queued-1'),
        requestId: ShadowRequestId('seed-queued-1'),
        sourceSessionId: SessionId('session-shadow'),
        workspaceId: WorkspaceId('ws-queued-1'),
        bindingRevision: 2,
        goalId: 'goal-1',
        acceptanceHash: AcceptanceHash('hash-run-1'),
        mode: 'work',
        text: 'queued residue',
        state: 'queued',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('deliveries').put(residue.messageId, residue)
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const status = await h.router.projectStatus(h.shadow, { workspaceId: 'ws-queued-1' })
      const entry = status.projects[0]!
      // The queued intent is visible with its own count, distinct from received
      // and completed: live sends converge to received, so only this durable
      // residue can prove the queued state reads back.
      expect(entry.deliveries.filter(delivery => delivery.state === 'queued')).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-08 [%s]: a parked provisioning mismatch surfaces as blocked with its failure reason', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-08b-'))
    const project = join(root, 'project-a')
    await mkdir(project)
    const canonical = await realpath(project)
    const other = join(root, 'other-project')
    await mkdir(other)
    const canonicalOther = await realpath(other)
    const seed = await seedHarness(root, { backend })
    try {
      const now = new Date().toISOString()
      const binding: ShadowBindingRecord = {
        workspaceId: WorkspaceId('ws-blocked-1'),
        canonicalPath: canonicalOther,
        controllerSessionId: SessionId('session-blocked-1'),
        profileKey: 'devframe',
        bindingRevision: 1,
        requestId: 'seed-open-1',
        state: 'provisioning',
        createdAt: now,
        updatedAt: now,
      }
      await seed.domain.table('bindings').put(binding.workspaceId, binding)
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] }, { backend })
    try {
      h.ctx.sessions.create(SessionId('session-blocked-1'), { meta: { cwd: canonical } })
      const parked = await h.router.reconcileProject(WorkspaceId('ws-blocked-1'))
      expect(parked.state).toBe('needs_attention')

      const status = await h.router.projectStatus(h.shadow, { workspaceId: 'ws-blocked-1' })
      expect(status.projects).toHaveLength(1)
      const entry = status.projects[0]!
      expect(entry.state).toBe('needs_attention')
      expect(entry.failureReason).toContain('cwd does not match')
      expect(entry.blockedReason).toContain('cwd does not match')
      expect(entry.deliveries).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('reads the host aggregate status: unconfigured reads disabled, designation and bindings read verbatim', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-status-aggregate-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      // Unconfigured deployment: honest empty designation, no live mark, the
      // canonicalized roots, and no binding rows yet.
      const before = h.router.readStatus()
      expect(before.shadowSessionId).toBeUndefined()
      expect(before.shadowLive).toBe(false)
      expect(before.authorizedRoots).toEqual([await realpath(root)])
      expect(before.bindings).toEqual([])

      const dir = await h.makeProjectDir('aggregate-project')
      const opened = await h.router.openProject(h.shadow, { path: dir, requestId: 'status-aggregate-open' })
      const after = h.router.readStatus()
      expect(after.bindings).toEqual([{
        workspaceId: opened.workspaceId,
        canonicalPath: opened.canonicalPath,
        bindingRevision: opened.bindingRevision,
        state: opened.state,
      }])
      // The read is a projection: the durable index is untouched by it.
      expect(after.bindings).not.toBe(h.router.listBindings())
    } finally {
      await h.dispose()
    }
  })

  it('reads the designated controller as live only while its host designation holds', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-status-live-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const status = h.router.readStatus()
      expect(status.shadowSessionId).toBe('session-shadow')
      expect(status.shadowLive).toBe(true)
    } finally {
      await h.dispose()
    }

    // An id that was never marked (and never becomes live) reads as not live.
    const coldRoot = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-status-cold-'))
    const cold = await harness(coldRoot, { authorizedRoots: [coldRoot], shadowSessionId: 'session-never-created' })
    try {
      expect(cold.router.readStatus()).toMatchObject({
        shadowSessionId: 'session-never-created',
        shadowLive: false,
        bindings: [],
      })
    } finally {
      await cold.dispose()
    }
  })
})
