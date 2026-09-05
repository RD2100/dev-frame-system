/** AT2-02: the whitelist rejection face — forbidden callers, tools, and inputs fail before target mutation. */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { dispatch, failureCode, failureText, harness } from './helpers.ts'

describe('shadow-router whitelist', () => {
  it('AT2-02: rejects worker calls, forbidden host tools, forged targets, unauthorized workspaces, and stale revisions before mutation', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-02-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('project-a')

      // A worker session is never the Shadow: the service rejects before any
      // mutation, and no binding or workspace row appears.
      await expect(h.router.openProject(h.worker, { path: dir, requestId: 'at2-02-worker-open' }))
        .rejects.toMatchObject({ code: 'SHADOW_CALLER_FORBIDDEN' })
      expect(h.router.listBindings()).toEqual([])
      const dispatched = await dispatch(h.ctx, h.worker, 'project_status', {})
      expect(dispatched.isError).toBe(true)
      // The four tools are installed only in the Shadow scope, so a worker
      // cannot even resolve the name — let alone reach the service guard.
      expect(failureText(dispatched)).toContain('unknown tool "project_status"')

      // The Shadow model face is exactly the four project tools: host shell and
      // raw-session tool names are not reachable from the Shadow scope.
      for (const forbidden of ['bash', 'read', 'write', 'spawn_agent']) {
        const probe = await dispatch(h.ctx, h.shadow, forbidden, {})
        expect(probe.isError, forbidden).toBe(true)
      }
      const allowed = await dispatch(h.ctx, h.shadow, 'project_status', {})
      expect(allowed.isError).toBe(false)

      // The caller cannot choose a target session: the schema rejects the
      // forged field before the service runs, so nothing is mutated.
      const open = await h.router.openProject(h.shadow, { path: dir, requestId: 'at2-02-open' })
      await h.router.setActiveGoal(open.workspaceId, 'goal-1', 'hash-run-1')
      const forged = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: open.workspaceId,
        binding_revision: h.router.findBinding(open.workspaceId)!.bindingRevision,
        goal_id: 'goal-1',
        acceptance_hash: 'hash-run-1',
        request_id: 'at2-02-forged',
        mode: 'work',
        text: 'sent with a forged target session id session-forged-xyz',
        target_session_id: 'session-forged-xyz',
      })
      expect(forged.isError).toBe(true)
      expect(h.router.listDeliveries(open.workspaceId)).toEqual([])

      // An unauthorized (unbound) workspace fails before any delivery exists,
      // and the rejection carries no project content.
      const secret = 'secret project content that must not leak'
      const unknownWorkspace = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: 'ws-not-open',
        binding_revision: 1,
        goal_id: 'goal-1',
        acceptance_hash: 'hash-run-1',
        request_id: 'at2-02-unknown-ws',
        mode: 'work',
        text: secret,
      })
      expect(unknownWorkspace.isError).toBe(true)
      expect(failureCode(unknownWorkspace)).toBe('SHADOW_WORKSPACE_UNKNOWN')
      expect(failureText(unknownWorkspace)).not.toContain(secret)

      // An obsolete binding revision is rejected before target mutation.
      // setActiveGoal bumped the revision, so revision 1 is stale here.
      const stale = await dispatch(h.ctx, h.shadow, 'project_send', {
        workspace_id: open.workspaceId,
        binding_revision: 1,
        goal_id: 'goal-1',
        acceptance_hash: 'hash-run-1',
        request_id: 'at2-02-stale-revision',
        mode: 'work',
        text: secret,
      })
      expect(stale.isError).toBe(true)
      expect(failureCode(stale)).toBe('SHADOW_STALE_REVISION')
      expect(failureText(stale)).not.toContain(secret)
      expect(h.router.listDeliveries(open.workspaceId)).toEqual([])
    } finally {
      await h.dispose()
    }
  })
})
