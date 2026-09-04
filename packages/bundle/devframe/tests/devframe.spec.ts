import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadOverlayPatches } from '@deepseek-ai/dsh-app-boot'
import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('..', import.meta.url))

describe('dsh-devframe bundle', () => {
  it('declares one native insert layer through the standard profile parser', () => {
    const manifest = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')) as {
      dsh?: { bundle?: { patch?: string } }
    }
    expect(manifest.dsh?.bundle?.patch).toBe('./cordis.patch.yml')
    const patches = loadOverlayPatches('test', resolve(root, manifest.dsh!.bundle!.patch!))
    expect(patches).toHaveLength(1)
    expect(patches[0]).toEqual({
      insert: [
        {
          id: 'devframe-control-session',
          name: '@deepseek-ai/dsh-devframe-control-session',
        },
        {
          id: 'devframe-task-startup',
          name: '@deepseek-ai/dsh-devframe/task-startup',
        },
        {
          id: 'devframe-task-runner',
          name: '@deepseek-ai/dsh-devframe/task-runner',
          config: { request: { __jsExpr: "ctx.get('devframeTaskStartup')" } },
        },
        {
          id: 'client-ui-devframe-control-session',
          name: '@deepseek-ai/dsh-client-ui-devframe-control-session',
        },
      ],
    })
  })

  it('depends only on the plugin rows it contributes', async () => {
    const manifest = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>
    }
    expect(manifest.dependencies).toEqual({
      '@deepseek-ai/dsh-cmdline': 'workspace:^',
      '@deepseek-ai/dsh-client-ui-devframe-control-session': 'workspace:^',
      '@deepseek-ai/dsh-devframe-control-session': 'workspace:^',
      '@deepseek-ai/dsh-workspace': 'workspace:^',
      commander: '^15.0.0',
    })
    expect(Object.keys(await import('../src/index.ts'))).toEqual([])
  })
})
