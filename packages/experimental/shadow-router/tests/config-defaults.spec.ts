/**
 * The config defaults the router serves when a composition configures none.
 * The R2 real-machine verification surfaced the shipped default pointing at a
 * preset that does not exist, so the default is pinned by behavior here.
 */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { harness } from './helpers.ts'

describe('shadow-router config defaults', () => {
  it('pins provisioned controllers to the standard preset when no controllerProfile is configured', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-default-profile-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('default-profile-project')
      const opened = await h.router.openProject(h.shadow, { path: dir, requestId: 'default-profile-open' })
      expect(opened.state).toBe('ready')
      expect(h.router.findBinding(opened.workspaceId)).toMatchObject({ profileKey: 'standard' })
      expect(h.ctx.sessions.get(opened.controllerSessionId)?.header.agentPreset).toBe('standard')
    } finally {
      await h.dispose()
    }
  })

  it('accepts an absolute designatedCwd and surfaces it in readStatus', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designated-cwd-'))
    const h = await harness(root, {
      authorizedRoots: [root],
      shadowSessionId: 'session-shadow',
      designatedCwd: '/projects/shadow',
    })
    try {
      expect(h.router.readStatus().designatedCwd).toBe('/projects/shadow')
    } finally {
      await h.dispose()
    }
  })

  it('rejects a relative or blank designatedCwd at load', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designated-cwd-bad-'))
    await expect(harness(root, {
      authorizedRoots: [root],
      shadowSessionId: 'session-shadow',
      designatedCwd: 'relative/path',
    })).rejects.toThrow('designatedCwd must be a non-empty absolute path')
    await expect(harness(root, {
      authorizedRoots: [root],
      shadowSessionId: 'session-shadow',
      designatedCwd: '   ',
    })).rejects.toThrow('designatedCwd must be a non-empty absolute path')
  })

  it('folds a reported designation issue into readStatus and clears it on repair', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-design-issue-'))
    const h = await harness(root, {
      authorizedRoots: [root],
      shadowSessionId: 'session-shadow',
      designatedCwd: '/projects/shadow',
    })
    try {
      const service = h.router as unknown as {
        reportDesignIssue(issue: 'designated-session-missing-cwd'): void
        clearDesignIssue(): void
      }
      expect(h.router.readStatus().designIssue).toBeUndefined()
      service.reportDesignIssue('designated-session-missing-cwd')
      expect(h.router.readStatus().designIssue).toBe('designated-session-missing-cwd')
      service.clearDesignIssue()
      expect(h.router.readStatus().designIssue).toBeUndefined()
    } finally {
      await h.dispose()
    }
  })
})
