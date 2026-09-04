import { mkdtempSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { composeEntries, loadProfile, PROFILE_TEMPLATES } from '../src/index.ts'

const tmp = (): string => mkdtempSync(join(tmpdir(), 'dsh-devframe-profile-'))
const installAnchor = fileURLToPath(new URL('../../../../apps/cli/package.json', import.meta.url))
const devframePatch = fileURLToPath(new URL('../../../bundle/devframe/cordis.patch.yml', import.meta.url))

describe('devframe profile', () => {
  it('preserves existing templates and composes all official DevFrame layers', () => {
    expect(PROFILE_TEMPLATES.web).toEqual(['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'])
    expect(PROFILE_TEMPLATES.headless).toEqual(['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'])

    const home = tmp()
    const profile = loadProfile('t', 'devframe', installAnchor, home, { userLayer: false })
    expect(profile.layers.map(layer => layer.packageName)).toEqual(PROFILE_TEMPLATES.devframe)
    expect(realpathSync(profile.layers[2]!.patchPath)).toBe(realpathSync(devframePatch))

    const entries = composeEntries(profile.layers.map(layer => layer.patches))
    expect(entries.filter(entry => entry.id === 'devframe-control-session')).toEqual([{
      id: 'devframe-control-session',
      name: '@deepseek-ai/dsh-devframe-control-session',
    }])
    expect(entries.filter(entry => entry.id === 'client-ui-devframe-control-session')).toEqual([{
      id: 'client-ui-devframe-control-session',
      name: '@deepseek-ai/dsh-client-ui-devframe-control-session',
    }])
    expect(entries.filter(entry => entry.id === 'devframe-task-startup')).toEqual([{
      id: 'devframe-task-startup',
      name: '@deepseek-ai/dsh-devframe/task-startup',
    }])
    expect(entries.filter(entry => entry.id === 'devframe-task-runner')).toEqual([{
      id: 'devframe-task-runner',
      name: '@deepseek-ai/dsh-devframe/task-runner',
      config: { request: { __jsExpr: "ctx.get('devframeTaskStartup')" } },
    }])
    expect(entries.filter(entry => entry.id === 'credentials')).toEqual([{
      id: 'credentials',
      name: '@deepseek-ai/dsh-credentials-local',
      config: { allowManagedOverride: true },
    }])
  })
})
