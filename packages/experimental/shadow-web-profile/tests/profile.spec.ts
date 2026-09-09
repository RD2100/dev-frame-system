/** The experimental Web bundle must carry one parseable Shadow entry layer. */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import * as yaml from 'js-yaml'
import { entryListSchema } from '@deepseek-ai/cordis-plugin-include'

describe('Shadow Web profile bundle', () => {
  it('declares a private parseable layer containing the Shadow entry', () => {
    const root = fileURLToPath(new URL('..', import.meta.url))
    const manifest = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')) as {
      private?: boolean
      publishConfig?: unknown
      dependencies?: Record<string, string>
      dsh?: { bundle?: { patch?: string } }
    }
    expect(manifest.private).toBe(true)
    expect(manifest.publishConfig).toBeUndefined()
    expect(manifest.dsh?.bundle?.patch).toBe('./cordis.patch.yml')
    expect(manifest.dependencies).toEqual({
      '@deepseek-ai/dsh-experimental-client-ui-shadow-entry': 'workspace:^',
    })

    const parsed = yaml.load(
      readFileSync(resolve(root, manifest.dsh!.bundle!.patch!), 'utf8'),
      { schema: entryListSchema },
    ) as { insert?: { id?: string; name?: string }[] }[]
    expect(parsed.flatMap(patch => patch.insert ?? [])).toEqual([
      { id: 'ui-shadow-entry', name: '@deepseek-ai/dsh-experimental-client-ui-shadow-entry' },
    ])
  })
})
