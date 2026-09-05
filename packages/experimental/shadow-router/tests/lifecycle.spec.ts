/** AT2-01: full open → send → status → stop lifecycle across two independent projects. */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { harness } from './helpers.ts'

describe('shadow-router lifecycle', () => {
  it('AT2-01: opens two independent controller roots, routes work to each, and stops one without touching the other', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-01-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dirA = await h.makeProjectDir('project-a')
      const dirB = await h.makeProjectDir('project-b')

      const openA = await h.router.openProject(h.shadow, { path: dirA, requestId: 'at2-01-open-a' })
      const openB = await h.router.openProject(h.shadow, { path: dirB, requestId: 'at2-01-open-b' })
      // Two independent roots: distinct workspaces and controller sessions.
      expect(openA.state).toBe('ready')
      expect(openB.state).toBe('ready')
      expect(openA.workspaceId).not.toBe(openB.workspaceId)
      expect(openA.controllerSessionId).not.toBe(openB.controllerSessionId)
      // Each controller root is a top-level native session with the exact cwd,
      // never a child of the Shadow session, and no Team is nested.
      const sessionA = h.ctx.sessions.get(openA.controllerSessionId)
      const sessionB = h.ctx.sessions.get(openB.controllerSessionId)
      expect(sessionA?.header.cwd).toBe(openA.canonicalPath)
      expect(sessionB?.header.cwd).toBe(openB.canonicalPath)
      expect(sessionA?.header.parentSession).toBeUndefined()
      expect(sessionB?.header.parentSession).toBeUndefined()
      expect(h.ctx.get('agentTeams')).toBeUndefined()
      // Controller role persisted through the session-identity registry.
      expect(h.ctx.agentBindings.find(openA.controllerSessionId)?.role).toBe('controller')
      expect(h.ctx.agentBindings.find(openB.controllerSessionId)?.role).toBe('controller')

      // The host authorizes each project's open run; deliveries follow it.
      await h.router.setActiveGoal(openA.workspaceId, 'goal-a-1', 'hash-a-1')
      await h.router.setActiveGoal(openB.workspaceId, 'goal-b-1', 'hash-b-1')
      const revisionA = h.router.findBinding(openA.workspaceId)!.bindingRevision
      const revisionB = h.router.findBinding(openB.workspaceId)!.bindingRevision
      const sendA = await h.router.sendToProject(h.shadow, {
        workspaceId: openA.workspaceId,
        bindingRevision: revisionA,
        goalId: 'goal-a-1',
        acceptanceHash: 'hash-a-1',
        requestId: 'at2-01-send-a',
        mode: 'work',
        text: 'work for project A only',
      })
      const sendB = await h.router.sendToProject(h.shadow, {
        workspaceId: openB.workspaceId,
        bindingRevision: revisionB,
        goalId: 'goal-b-1',
        acceptanceHash: 'hash-b-1',
        requestId: 'at2-01-send-b',
        mode: 'work',
        text: 'work for project B only',
      })
      expect(sendA.status).toBe('received')
      expect(sendB.status).toBe('received')
      // Outputs stay in the intended project: each workspace sees exactly its own delivery.
      const deliveriesA = h.router.listDeliveries(openA.workspaceId)
      const deliveriesB = h.router.listDeliveries(openB.workspaceId)
      expect(deliveriesA.map(record => record.messageId)).toEqual([sendA.messageId])
      expect(deliveriesB.map(record => record.messageId)).toEqual([sendB.messageId])
      expect(deliveriesA[0]!.text).toBe('work for project A only')
      expect(deliveriesB[0]!.text).toBe('work for project B only')

      // Status reports both projects with their durable delivery states.
      const status = await h.router.projectStatus(h.shadow, {})
      expect(status.projects.map(project => project.state).sort()).toEqual(['ready', 'ready'])
      const statusA = status.projects.find(project => project.workspaceId === openA.workspaceId)!
      expect(statusA.deliveries.map(delivery => delivery.state)).toEqual(['received'])

      // Stopping A is isolated: B keeps its queue, controller, and receiving.
      const stopA = await h.router.stopProject(h.shadow, {
        workspaceId: openA.workspaceId,
        expectedRevision: h.router.findBinding(openA.workspaceId)!.bindingRevision,
        requestId: 'at2-01-stop-a',
      })
      expect(stopA.status).toBe('stopping')
      await h.router.confirmProjectStopped(openA.workspaceId)
      expect(h.router.findBinding(openA.workspaceId)?.state).toBe('stopped')
      expect(h.router.findBinding(openB.workspaceId)?.state).toBe('ready')
      expect(h.ctx.sessions.get(openB.controllerSessionId)).toBeDefined()
      const sendB2 = await h.router.sendToProject(h.shadow, {
        workspaceId: openB.workspaceId,
        bindingRevision: h.router.findBinding(openB.workspaceId)!.bindingRevision,
        goalId: 'goal-b-1',
        acceptanceHash: 'hash-b-1',
        requestId: 'at2-01-send-b-2',
        mode: 'note',
        text: 'B keeps receiving after A stopped',
      })
      expect(sendB2.status).toBe('received')
    } finally {
      await h.dispose()
    }
  })
})
