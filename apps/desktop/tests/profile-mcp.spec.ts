/** MCP resource ownership in the shipped Desktop composition. */

/* oxlint-disable typescript/no-unsafe-argument -- Vitest runs this composition test outside the Desktop source tsconfig. */
/* oxlint-disable typescript/no-unsafe-assignment -- The app-boot package has no test-project declaration graph. */
/* oxlint-disable typescript/no-unsafe-call -- The package import is exercised by the runtime composition test. */
/* oxlint-disable typescript/no-unsafe-member-access -- The package import is exercised by the runtime composition test. */
/* oxlint-disable typescript/no-unsafe-return -- The package import is exercised by the runtime composition test. */

import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'
import { composeEntries, loadOverlayPatches, loadProfileDirectory } from '@deepseek-ai/dsh-app-boot'
import { createPluginProfile } from '../src/project-manager.ts'

it('retains one shared resource consumer after the Desktop host overlay', () => {
  const home = mkdtempSync(join(tmpdir(), 'dsh-desktop-profile-mcp-'))
  try {
    const profileDir = join(home, 'profiles', 'desktop')
    createPluginProfile(profileDir)
    const installAnchor = fileURLToPath(new URL('../../cli/package.json', import.meta.url))
    const profile = loadProfileDirectory('dsh desktop', profileDir, installAnchor)
    const overlay = fileURLToPath(new URL('../../desktop-host/config/desktop.cordis.patch.yml', import.meta.url))
    const warnings: string[] = []
    const rows = composeEntries([
      ...profile.layers.map(layer => layer.patches),
      profile.patches,
      loadOverlayPatches('dsh desktop', overlay),
    ], message => warnings.push(message))

    expect(rows.filter(row => row.name === '@deepseek-ai/dsh-mcp-resources')).toEqual([])
    expect(rows.filter(row => row.name === '@deepseek-ai/dsh-mcp-client')).toEqual([])
    const webserver = rows.find(row => row.id === 'webserver')
    expect(webserver).toMatchObject({ id: 'webserver', name: '@deepseek-ai/dsh-host-webserver' })
    expect(webserver?.disabled).toBeUndefined()
    expect(warnings).toEqual([])
  } finally {
    rmSync(home, { recursive: true, force: true })
  }
})
