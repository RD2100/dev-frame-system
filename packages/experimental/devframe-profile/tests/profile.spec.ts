/** The experimental bundle must carry one parseable, explicit DevFrame layer. */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import * as yaml from 'js-yaml'
import { entryListSchema } from '@deepseek-ai/cordis-plugin-include'

describe('DevFrame profile bundle', () => {
  it('declares a private parseable layer mounting the seven DevFrame rows', () => {
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
    expect(manifest.dependencies).toMatchObject({
      '@deepseek-ai/dsh-experimental-agent-dispatch': 'workspace:^',
      '@deepseek-ai/dsh-experimental-agent-hierarchy': 'workspace:^',
      '@deepseek-ai/dsh-experimental-command-goal-binding': 'workspace:^',
      '@deepseek-ai/dsh-experimental-project-memory': 'workspace:^',
      '@deepseek-ai/dsh-experimental-session-identity': 'workspace:^',
      '@deepseek-ai/dsh-experimental-shadow-controller': 'workspace:^',
      '@deepseek-ai/dsh-experimental-shadow-router': 'workspace:^',
    })

    const parsed = yaml.load(
      readFileSync(resolve(root, manifest.dsh!.bundle!.patch!), 'utf8'),
      { schema: entryListSchema },
    )
    expect(Array.isArray(parsed)).toBe(true)
    const patches = parsed as { insert?: { id?: string; name?: string }[] }[]
    const inserted = patches.flatMap(patch => patch.insert ?? [])
    expect(inserted.map(row => row.id)).toEqual([
      'session-identity',
      'shadow-router',
      'shadow-controller',
      'project-memory',
      'command-goal-binding',
      'agent-hierarchy',
      'agent-dispatch',
    ])
    expect(inserted.find(row => row.id === 'shadow-controller')?.name).toBe('@deepseek-ai/dsh-experimental-shadow-controller')
    expect(inserted.find(row => row.id === 'project-memory')?.name).toBe('@deepseek-ai/dsh-experimental-project-memory')
    expect(inserted.find(row => row.id === 'agent-dispatch')?.name).toBe('@deepseek-ai/dsh-experimental-agent-dispatch')
  })
})
