/** AT2-03: concurrent repeated opens, reservation-interrupt recovery, and provisioning rollback. */

import { describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, realpath, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { HARNESS_BACKENDS, harness, seedHarness, seedWorkspaceFact } from './helpers.ts'
import type { ShadowBindingRecord } from '../src/index.ts'

/** A schema-valid crash-residue binding row. */
function seedRow(overrides: Omit<Partial<ShadowBindingRecord>, 'workspaceId' | 'controllerSessionId'> & { readonly workspaceId: string; readonly controllerSessionId: string; readonly canonicalPath: string; readonly state: ShadowBindingRecord['state'] }): ShadowBindingRecord {
  const now = new Date().toISOString()
  const { workspaceId, controllerSessionId, ...rest } = overrides
  return {
    profileKey: 'devframe',
    bindingRevision: 1,
    requestId: 'seed-open-1',
    createdAt: now,
    updatedAt: now,
    ...rest,
    workspaceId: WorkspaceId(workspaceId),
    controllerSessionId: SessionId(controllerSessionId),
  }
}

describe('shadow-router provisioning', () => {
  it('AT2-03: concurrent repeated opens resolve to one controller and one binding', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-03a-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('project-a')
      const [first, replayed, secondRequest] = await Promise.all([
        h.router.openProject(h.shadow, { path: dir, requestId: 'at2-03-open-1' }),
        h.router.openProject(h.shadow, { path: dir, requestId: 'at2-03-open-1' }),
        h.router.openProject(h.shadow, { path: dir, requestId: 'at2-03-open-2' }),
      ])
      expect(first.state).toBe('ready')
      expect(replayed.workspaceId).toBe(first.workspaceId)
      expect(secondRequest.controllerSessionId).toBe(first.controllerSessionId)
      expect(h.router.listBindings()).toHaveLength(1)
      expect(h.router.listBindings()[0]!.controllerSessionId).toBe(first.controllerSessionId)
    } finally {
      await h.dispose()
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-03 [%s]: a reservation interrupted before readiness converges on the same reserved session id', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-03b-'))
    const dir = join(root, 'project-a')
    await mkdir(dir)
    const canonical = await realpath(dir)
    // Crash residue: the workspace fact and the in-creation association are
    // durable; the controller session is not.
    const seed = await seedHarness(root, { backend })
    try {
      await seedWorkspaceFact(seed.workspaceDomain, 'ws-seed-1', canonical)
      await seed.domain.table('bindings').put(WorkspaceId('ws-seed-1'), seedRow({
        workspaceId: 'ws-seed-1',
        canonicalPath: canonical,
        controllerSessionId: 'session-reserved-1',
        state: 'reserving',
      }))
    } finally {
      await seed.dispose()
    }

    const h = await harness(root, { authorizedRoots: [root] }, { backend })
    try {
      const reopened = await h.router.openProject(h.shadow, { path: dir, requestId: 'at2-03-open-recover' })
      // No duplicate writer: the SAME reserved id becomes the controller.
      expect(reopened.state).toBe('ready')
      expect(reopened.workspaceId).toBe('ws-seed-1')
      expect(reopened.controllerSessionId).toBe('session-reserved-1')
      const session = h.ctx.sessions.get(SessionId('session-reserved-1'))
      expect(session?.header.cwd).toBe(canonical)
      expect(h.ctx.agentBindings.find(SessionId('session-reserved-1'))?.role).toBe('controller')
      expect(h.router.listBindings()).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-03 [%s]: recovery completes a half-provisioned root whose session matches, and parks a cwd mismatch', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-03c-'))
    try {
      const project = join(root, 'project-a')
      await mkdir(project)
      const canonical = await realpath(project)
      const other = join(root, 'other-project')
      await mkdir(other)
      const canonicalOther = await realpath(other)
      // Row 1: the reserved session came to exist with the matching cwd — the
      // bind (role persistence) is what crashed; recovery completes it.
      // Row 2: a reserved session whose cwd stopped matching the row.
      const seed = await seedHarness(root, { backend })
      try {
        await seed.domain.table('bindings').put(WorkspaceId('ws-seed-2'), seedRow({
          workspaceId: 'ws-seed-2',
          canonicalPath: canonical,
          controllerSessionId: 'session-reserved-2',
          state: 'provisioning',
        }))
        await seed.domain.table('bindings').put(WorkspaceId('ws-seed-3'), seedRow({
          workspaceId: 'ws-seed-3',
          canonicalPath: canonicalOther,
          controllerSessionId: 'session-reserved-3',
          state: 'provisioning',
        }))
      } finally {
        await seed.dispose()
      }

      const h = await harness(root, { authorizedRoots: [root] }, { backend })
      try {
        // Row 2's reserved session exists but points somewhere else; the host
        // recovery converges both rows around their reserved ids.
        h.ctx.sessions.create(SessionId('session-reserved-3'), { meta: { cwd: canonical } })
        const mismatched = await h.router.reconcileProject(WorkspaceId('ws-seed-3'))
        expect(mismatched.state).toBe('needs_attention')
        expect(mismatched.failureReason).toContain('cwd does not match')

        const completed = await h.router.reconcileProject(WorkspaceId('ws-seed-2'))
        expect(completed.state).toBe('ready')
        expect(completed.controllerSessionId).toBe('session-reserved-2')
        expect(h.ctx.agentBindings.find(SessionId('session-reserved-2'))?.role).toBe('controller')
      } finally {
        await h.dispose()
      }
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-03 [%s]: a provisioning failure rolls back to a failed row, and the next open re-provisions with a new reservation', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-03d-'))
    try {
      const dir = join(root, 'project-a')
      await mkdir(dir)
      const canonical = await realpath(dir)
      // The session store rejects a non-absolute cwd, which deterministically
      // exercises the creation-failure rollback around the reserved id. A
      // second row holds a usable root and a failed state to retry.
      const seed = await seedHarness(root, { backend })
      try {
        await seedWorkspaceFact(seed.workspaceDomain, 'ws-seed-5', canonical)
        await seed.domain.table('bindings').put(WorkspaceId('ws-bad-path'), seedRow({
          workspaceId: 'ws-bad-path',
          canonicalPath: 'relative/not-absolute',
          controllerSessionId: 'session-reserved-4',
          state: 'reserving',
        }))
        await seed.domain.table('bindings').put(WorkspaceId('ws-seed-5'), seedRow({
          workspaceId: 'ws-seed-5',
          canonicalPath: canonical,
          controllerSessionId: 'session-reserved-5',
          state: 'failed',
          failureReason: 'the session store rejected the controller creation: existing id',
        }))
      } finally {
        await seed.dispose()
      }

      const h = await harness(root, { authorizedRoots: [root] }, { backend })
      try {
        await expect(h.router.reconcileProject(WorkspaceId('ws-bad-path')))
          .rejects.toMatchObject({ code: 'SHADOW_INVALID_REQUEST' })
        const failed = h.router.findBinding(WorkspaceId('ws-bad-path'))
        expect(failed?.state).toBe('failed')
        expect(failed?.failureReason).toContain('rejected the controller creation')
        expect(h.ctx.sessions.get(SessionId('session-reserved-4'))).toBeUndefined()

        // The failed row over a usable root re-provisions: new reservation,
        // same workspace, bumped revision, old reserved id left untouched.
        const reopened = await h.router.openProject(h.shadow, { path: dir, requestId: 'at2-03-open-retry' })
        expect(reopened.state).toBe('ready')
        expect(reopened.workspaceId).toBe('ws-seed-5')
        expect(reopened.controllerSessionId).not.toBe('session-reserved-5')
        expect(reopened.bindingRevision).toBe(2)
      } finally {
        await h.dispose()
      }
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })

  it.each(HARNESS_BACKENDS)('AT2-03 [%s]: request results replay across a cold restart and conflict on different input', async (backend) => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-03e-'))
    const h1 = await harness(root, { authorizedRoots: [root] }, { backend })
    const dirA = await h1.makeProjectDir('project-a')
    const dirB = await h1.makeProjectDir('project-b')
    const first = await h1.router.openProject(h1.shadow, { path: dirA, requestId: 'at2-03-replay' })
    // Cold restart: the context stops, the root stays on disk.
    await h1.close()

    const h2 = await harness(root, { authorizedRoots: [root] }, { backend })
    try {
      const replayed = await h2.router.openProject(h2.shadow, { path: dirA, requestId: 'at2-03-replay' })
      expect(replayed).toEqual(first)
      await expect(h2.router.openProject(h2.shadow, { path: dirB, requestId: 'at2-03-replay' }))
        .rejects.toMatchObject({ code: 'SHADOW_REQUEST_CONFLICT' })
    } finally {
      await h2.dispose()
    }
  })
})
