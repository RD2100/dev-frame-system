/**
 * The host write bridges: openProjectForHost, sendToProjectForHost, and
 * releaseProjectForHost run the same gated flows as the model-facing tools,
 * riding the designated Shadow's authority — never bypassing validation.
 */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { harness } from './helpers.ts'

describe('shadow-router host write bridges', () => {
  it('opens a project through the designated Shadow without a caller argument', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-open-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const dir = await h.makeProjectDir('host-open-project')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'host-open-1' })
      expect(opened.state).toBe('ready')
      expect(opened.bindingRevision).toBe(1)
      // A human-initiated open is the authorization action: the bridge records
      // the authorized open run, which bumps the binding past the receipt.
      expect(h.router.findBinding(opened.workspaceId)).toMatchObject({
        activeGoalId: 'host-run-1',
        activeAcceptanceHash: 'open-run-1',
        bindingRevision: 2,
      })
      expect(h.router.readStatus().bindings).toEqual([{
        workspaceId: opened.workspaceId,
        canonicalPath: opened.canonicalPath,
        bindingRevision: 2,
        state: 'ready',
      }])
      // The controller session the open provisions really exists.
      expect(h.ctx.sessions.get(opened.controllerSessionId)).toBeDefined()
    } finally {
      await h.dispose()
    }
  })

  it('refuses the open bridge when the composition declares no Shadow session', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-nodecl-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('undeclined')
      await expect(h.router.openProjectForHost({ path: dir, requestId: 'host-open-2' }))
        .rejects.toThrow('declares no Shadow session')
    } finally {
      await h.dispose()
    }
  })

  it('refuses the open bridge while the designated session is not live', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-cold-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-never-created' })
    try {
      const dir = await h.makeProjectDir('cold')
      await expect(h.router.openProjectForHost({ path: dir, requestId: 'host-open-3' }))
        .rejects.toThrow('is not live')
    } finally {
      await h.dispose()
    }
  })

  it('delivers a work message through the existing delivery channel with the binding run it supplies', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-send-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const dir = await h.makeProjectDir('host-send-project')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'host-send-open' })
      await h.router.setActiveGoal(opened.workspaceId, 'goal-host-1', 'hash-host-1')

      const sent = await h.router.sendToProjectForHost({
        workspaceId: opened.workspaceId, text: 'host-driven work', requestId: 'host-send-1',
      })
      expect(sent.status).toBe('received')
      const delivery = h.router.listDeliveries(opened.workspaceId).at(-1)
      expect(delivery).toMatchObject({
        mode: 'work',
        text: 'host-driven work',
        goalId: 'goal-host-1',
        state: 'received',
      })
    } finally {
      await h.dispose()
    }
  })

  it('refuses a send against a workspace that records no authorized open run', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-sendnoauth-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const dir = await h.makeProjectDir('host-send-noauth')
      // The model-facing tool path records no run — only a host-plane open does.
      const opened = await h.router.openProject(h.shadow, { path: dir, requestId: 'host-send-open-2' })
      await expect(h.router.sendToProjectForHost({
        workspaceId: opened.workspaceId, text: 'no run yet', requestId: 'host-send-2',
      })).rejects.toThrow('records no authorized open run')
    } finally {
      await h.dispose()
    }
  })

  it('releases a project: stop plus quiescence confirmation in one step', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-release-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const dir = await h.makeProjectDir('host-release-project')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'host-release-open' })

      const released = await h.router.releaseProjectForHost({
        workspaceId: opened.workspaceId, requestId: 'host-release-1',
      })
      expect(released.status).toBe('stopped')
      const row = h.router.readStatus().bindings[0]
      expect(row).toMatchObject({ workspaceId: opened.workspaceId, state: 'stopped' })
      // The open's recorded run took the binding to revision 2; the stop adds one.
      expect(row?.bindingRevision).toBe(3)
    } finally {
      await h.dispose()
    }
  })

  it('refuses a release for a workspace without a binding', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-relunk-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      await expect(h.router.releaseProjectForHost({
        workspaceId: 'ws-never-opened', requestId: 'host-release-2',
      })).rejects.toThrow('no controller binding exists')
    } finally {
      await h.dispose()
    }
  })

  it('delivers after a host open with no manual authorization step', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-openauth-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const dir = await h.makeProjectDir('host-open-send')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'host-openauth-open' })
      expect(opened.state).toBe('ready')
      const sent = await h.router.sendToProjectForHost({
        workspaceId: opened.workspaceId, text: 'first work after open', requestId: 'host-openauth-send',
      })
      expect(sent).toMatchObject({ status: 'received' })
      expect(h.router.listDeliveries(opened.workspaceId).at(-1)).toMatchObject({
        goalId: 'host-run-1',
        acceptanceHash: 'open-run-1',
        state: 'received',
      })
    } finally {
      await h.dispose()
    }
  })

  it('keeps repeated and replayed host opens idempotent over the recorded run', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-host-repeat-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      const dir = await h.makeProjectDir('host-repeat-project')
      const first = await h.router.openProjectForHost({ path: dir, requestId: 'host-repeat-1' })
      const again = await h.router.openProjectForHost({ path: dir, requestId: 'host-repeat-2' })
      const replay = await h.router.openProjectForHost({ path: dir, requestId: 'host-repeat-1' })
      expect(replay).toEqual(first)
      // Only the first open establishes the run: later opens and replays keep
      // the recorded run and its revision instead of re-minting one.
      expect(h.router.findBinding(first.workspaceId)).toMatchObject({
        activeGoalId: 'host-run-1',
        activeAcceptanceHash: 'open-run-1',
        bindingRevision: 2,
      })
      expect(again.bindingRevision).toBe(2)
      expect(h.router.listDeliveries(first.workspaceId)).toHaveLength(0)
    } finally {
      await h.dispose()
    }
  })
})
