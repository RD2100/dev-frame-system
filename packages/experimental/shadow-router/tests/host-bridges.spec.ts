/**
 * The host write bridges: openProjectForHost, sendToProjectForHost, and
 * releaseProjectForHost run the same gated flows as the model-facing tools,
 * riding the designated Shadow's authority — never bypassing validation.
 */

import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { SessionId } from '@deepseek-ai/dsh-session'
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

/**
 * The host-side provisioner: a cold restore brings every ready controller
 * session live so the bridge's forwarding gate can resolve it. Resume goes
 * through `prepare`, while a fresh in-process open creates the live agent in
 * its factory setup. These specs run the real agent loop; a resumed controller emits
 * `agent/created` exactly once per live incarnation.
 */
describe('shadow-router host-side controller provisioner', () => {
  const withDefaultModel = { provide: (ctx: Context) => ctx.provide(
    'agentDefaultModel',
    { currentSelection: () => ({ provider: 'mock', model: 'mock' }) } as never,
  ) }

  it('resumes every ready controller on the boot sweep after a cold restore', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-provisioner-'))
    let h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' }, withDefaultModel)
    try {
      const dir = await h.makeProjectDir('provisioned-project')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'provision-1' })
      expect(opened.state).toBe('ready')
      // First process: the host factory creates the controller agent before
      // the open returns, so the fresh binding is immediately live.
      expect(h.ctx.agents.get(opened.controllerSessionId)).toBeDefined()
    } finally {
      await h.close()
    }
    // Second process over the same root: the boot sweep resumes the restored
    // ready binding's controller from the durable log.
    h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' }, withDefaultModel)
    try {
      const row = h.router.readStatus().bindings[0]
      expect(row?.state).toBe('ready')
      const binding = h.router.findBinding(row!.workspaceId)
      await vi.waitFor(() => {
        expect(h.ctx.agents.get(binding!.controllerSessionId)).toBeDefined()
      })
    } finally {
      await h.dispose()
    }
  })

  it('leaves an already-live controller untouched on a host open after restore', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-provisioner-repeat-'))
    let h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' }, withDefaultModel)
    let controllerSessionId: SessionId
    let dir: string
    try {
      dir = await h.makeProjectDir('repeat-project')
      const first = await h.router.openProjectForHost({ path: dir, requestId: 'provision-repeat-1' })
      controllerSessionId = first.controllerSessionId
    } finally {
      await h.close()
    }
    h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' }, withDefaultModel)
    try {
      const controller = h.ctx.agents.get(controllerSessionId)
      expect(controller).toBeDefined()
      let created = 0
      const off = h.ctx.on('agent/created', () => { created += 1 })
      try {
        // Replay and a fresh open both land on the same live incarnation; the
        // sweep already resumed it, so neither open re-resumes.
        await h.router.openProjectForHost({ path: dir, requestId: 'provision-repeat-1' })
        await h.router.openProjectForHost({ path: dir, requestId: 'provision-repeat-2' })
        expect(created).toBe(0)
        expect(h.ctx.agents.get(controllerSessionId)).toBe(controller)
      } finally {
        off()
      }
    } finally {
      await h.dispose()
    }
  })

  it('binds a fresh controller to a registered linked worktree before ready', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-provisioner-worktree-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' }, {
      provide: withDefaultModel.provide,
      worktreeRegistry: true,
    })
    try {
      const dir = await h.makeGitProjectDir('linked-project')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'provision-worktree-1' })
      const controller = h.ctx.agents.get(opened.controllerSessionId)
      const binding = h.ctx.agentBindings.find(opened.controllerSessionId)
      const rows = h.ctx.worktreeRegistry.list(opened.workspaceId)
      expect(controller).toBeDefined()
      expect(rows).toHaveLength(1)
      expect(binding).toMatchObject({
        role: 'controller',
        worktreeId: rows[0]?.id,
        worktreePath: rows[0]?.path,
        branch: rows[0]?.branch,
      })
      expect(rows[0]?.lockedBy).toBe(opened.controllerSessionId)
      expect(controller?.session.header.cwd).toBe(rows[0]?.path)
    } finally {
      await h.dispose()
    }
  })

  it('keeps the open usable when the composition declares no default model', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-provisioner-nomodel-'))
    const h = await harness(root, { authorizedRoots: [root], shadowSessionId: 'session-shadow' })
    try {
      // No agentDefaultModel provided: the provisioner logs loud and skips; the
      // open itself and the recorded run still land, and the delivery channel
      // stays usable for a later provisioner.
      const dir = await h.makeProjectDir('nomodel-project')
      const opened = await h.router.openProjectForHost({ path: dir, requestId: 'provision-nomodel-1' })
      expect(opened.state).toBe('ready')
      expect(h.ctx.agents.get(opened.controllerSessionId)).toBeUndefined()
      const sent = await h.router.sendToProjectForHost({
        workspaceId: opened.workspaceId, text: 'work while offline', requestId: 'provision-nomodel-send',
      })
      expect(sent.status).toBe('received')
    } finally {
      await h.dispose()
    }
  })
})
