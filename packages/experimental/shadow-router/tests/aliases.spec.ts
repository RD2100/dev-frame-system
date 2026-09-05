/** AT2-04: alias resolution consistency and physical-overlap rejection. */

import { describe, expect, it } from 'vitest'
import { mkdtemp, rm, stat, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { harness } from './helpers.ts'

const isWindows = process.platform === 'win32'

describe('shadow-router aliases and overlap', () => {
  it.skipIf(!isWindows)('AT2-04: case-alias spellings resolve to one workspace on Windows', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-04a-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const dir = await h.makeProjectDir('CaseProject')
      const alias = join(root, 'cASEpROJECT')
      const opened = await h.router.openProject(h.shadow, { path: dir, requestId: 'at2-04-open-canonical' })
      const viaAlias = await h.router.openProject(h.shadow, { path: alias, requestId: 'at2-04-open-alias' })
      expect(viaAlias.workspaceId).toBe(opened.workspaceId)
      expect(viaAlias.controllerSessionId).toBe(opened.controllerSessionId)
      expect(viaAlias.canonicalPath).toBe(opened.canonicalPath)
      expect(h.router.listBindings()).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it.skipIf(!isWindows)('AT2-04: a junction alias resolves to the target workspace on Windows', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-04b-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const target = await h.makeProjectDir('junction-target')
      const link = join(root, 'junction-link')
      await symlink(target, link, 'junction')
      const viaTarget = await h.router.openProject(h.shadow, { path: target, requestId: 'at2-04-open-target' })
      const viaLink = await h.router.openProject(h.shadow, { path: link, requestId: 'at2-04-open-link' })
      expect(viaLink.workspaceId).toBe(viaTarget.workspaceId)
      expect(viaLink.canonicalPath).toBe(viaTarget.canonicalPath)
      expect(h.router.listBindings()).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it.skipIf(isWindows)('AT2-04: a symlink alias resolves to the target workspace on POSIX', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-04b-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const target = await h.makeProjectDir('link-target')
      const link = join(root, 'link-name')
      await symlink(target, link)
      const viaTarget = await h.router.openProject(h.shadow, { path: target, requestId: 'at2-04-open-target' })
      const viaLink = await h.router.openProject(h.shadow, { path: link, requestId: 'at2-04-open-link' })
      expect(viaLink.workspaceId).toBe(viaTarget.workspaceId)
      expect(h.router.listBindings()).toHaveLength(1)
    } finally {
      await h.dispose()
    }
  })

  it('AT2-04: physically overlapping roots are rejected in both directions, without segment-prefix false positives', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-04c-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const parent = await h.makeProjectDir('outer')
      const child = await h.makeProjectDir(join('outer', 'inner'))
      await h.router.openProject(h.shadow, { path: parent, requestId: 'at2-04-open-parent' })
      // Opening the nested root while the parent project is open is rejected.
      await expect(h.router.openProject(h.shadow, { path: child, requestId: 'at2-04-open-child' }))
        .rejects.toMatchObject({ code: 'SHADOW_ROOTS_OVERLAP' })
      expect(h.router.listBindings()).toHaveLength(1)

      // The other direction: child first, parent second.
      const h2root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-04d-'))
      try {
        const h2 = await harness(h2root, { authorizedRoots: [h2root] })
        try {
          const parent2 = await h2.makeProjectDir('outer')
          const child2 = await h2.makeProjectDir(join('outer', 'inner'))
          await h2.router.openProject(h2.shadow, { path: child2, requestId: 'at2-04-open-child-first' })
          await expect(h2.router.openProject(h2.shadow, { path: parent2, requestId: 'at2-04-open-parent-second' }))
            .rejects.toMatchObject({ code: 'SHADOW_ROOTS_OVERLAP' })
        } finally {
          await h2.dispose()
        }
      } finally {
        await rm(h2root, { recursive: true, force: true })
      }

      // Sibling roots that merely share a string prefix are distinct projects.
      const seg = await h.makeProjectDir('seg')
      const segment = await h.makeProjectDir('segment')
      const segOpen = await h.router.openProject(h.shadow, { path: seg, requestId: 'at2-04-open-seg' })
      const segmentOpen = await h.router.openProject(h.shadow, { path: segment, requestId: 'at2-04-open-segment' })
      expect(segOpen.workspaceId).not.toBe(segmentOpen.workspaceId)
      expect(h.router.listBindings()).toHaveLength(3)
    } finally {
      await h.dispose()
    }
  })

  it('AT2-04: a missing root is rejected without creating anything', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-at2-04e-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      const missing = join(root, 'does-not-exist')
      await expect(h.router.openProject(h.shadow, { path: missing, requestId: 'at2-04-open-missing' }))
        .rejects.toMatchObject({ code: 'SHADOW_ROOT_MISSING' })
      // The rejected open never created the directory or a binding row.
      expect(h.router.listBindings()).toHaveLength(0)
      await expect(stat(missing)).rejects.toMatchObject({ code: 'ENOENT' })
    } finally {
      await h.dispose()
    }
  })
})
