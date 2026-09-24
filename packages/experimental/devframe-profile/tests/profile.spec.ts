/** The experimental bundle must carry one parseable, explicit DevFrame layer. */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import * as yaml from 'js-yaml'
import { entryListSchema } from '@deepseek-ai/cordis-plugin-include'

describe('DevFrame profile bundle', () => {
  it('declares a publishable parseable layer mounting the DevFrame and Agent Teams rows', () => {
    const root = fileURLToPath(new URL('..', import.meta.url))
    const manifest = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')) as {
      private?: boolean
      publishConfig?: { access?: string }
      dependencies?: Record<string, string>
      dsh?: { bundle?: { patch?: string } }
    }
    expect(manifest.private).toBeUndefined()
    expect(manifest.publishConfig?.access).toBe('public')
    expect(manifest.dsh?.bundle?.patch).toBe('./cordis.patch.yml')
    expect(manifest.dependencies).toMatchObject({
      '@deepseek-ai/cordis-plugin-logger-console': 'workspace:^',
      '@deepseek-ai/dsh-experimental-agent-team': 'workspace:^',
      '@deepseek-ai/dsh-experimental-agent-dispatch': 'workspace:^',
      '@deepseek-ai/dsh-experimental-agent-hierarchy': 'workspace:^',
      '@deepseek-ai/dsh-experimental-command-goal-binding': 'workspace:^',
      '@deepseek-ai/dsh-experimental-client-ui-agent-team': 'workspace:^',
      '@deepseek-ai/dsh-experimental-project-memory': 'workspace:^',
      '@deepseek-ai/dsh-experimental-session-identity': 'workspace:^',
      '@deepseek-ai/dsh-experimental-shadow-controller': 'workspace:^',
      '@deepseek-ai/dsh-experimental-shadow-router': 'workspace:^',
      '@deepseek-ai/dsh-experimental-tool-agent-team': 'workspace:^',
      '@deepseek-ai/dsh-experimental-client-ui-expert-team': 'workspace:^',
      '@deepseek-ai/dsh-experimental-expert-team': 'workspace:^',
      '@deepseek-ai/dsh-worktree-registry': 'workspace:^',
      '@deepseek-ai/dsh-client-ui-schedule': 'workspace:^',
      '@deepseek-ai/dsh-schedule': 'workspace:^',
      '@deepseek-ai/dsh-time-context': 'workspace:^',
    })

    const parsed = yaml.load(
      readFileSync(resolve(root, manifest.dsh!.bundle!.patch!), 'utf8'),
      { schema: entryListSchema },
    )
    expect(Array.isArray(parsed)).toBe(true)
    const patches = parsed as { insert?: { id?: string; name?: string }[] }[]
    const inserted = patches.flatMap(patch => patch.insert ?? [])
    expect(inserted.map(row => row.id)).toEqual([
      'logger-console',
      'session-identity',
      'shadow-router',
      'shadow-controller',
      'shadow-agent',
      'project-memory',
      'command-goal-binding',
      'agent-hierarchy',
      'agent-dispatch',
      'expert-team',
      'ui-expert-team',
      'ui-project-memory',
      'agent-team',
      'tool-agent-team',
      'ui-agent-team',
      'time-context',
      'schedule',
      'ui-schedule',
    ])
    expect(inserted.find(row => row.id === 'shadow-controller')?.name).toBe('@deepseek-ai/dsh-experimental-shadow-controller')
    expect(inserted.find(row => row.id === 'shadow-agent')?.name).toBe('@deepseek-ai/dsh-experimental-shadow-controller/shadow-agent')
    expect(inserted.find(row => row.id === 'project-memory')?.name).toBe('@deepseek-ai/dsh-experimental-project-memory')
    // worktree-registry is not patched here: the web-app bundle layer (which
    // precedes this layer in the profile composition) supplies the service.
    expect(inserted.find(row => row.id === 'worktree-registry')).toBeUndefined()
    expect(inserted.find(row => row.id === 'agent-dispatch')?.name).toBe('@deepseek-ai/dsh-experimental-agent-dispatch')
    expect(inserted.find(row => row.id === 'agent-team')?.name).toBe('@deepseek-ai/dsh-experimental-agent-team')
    expect(inserted.find(row => row.id === 'tool-agent-team')?.name).toBe('@deepseek-ai/dsh-experimental-tool-agent-team')
    expect(inserted.find(row => row.id === 'ui-agent-team')?.name).toBe('@deepseek-ai/dsh-experimental-client-ui-agent-team')
  })
})
