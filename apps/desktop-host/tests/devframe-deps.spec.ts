/**
 * P5: the desktop host must pull in the whole DevFrame closure as npm
 * dependencies so Electron Builder flattens them into the asar. It lists the
 * 19 explicit rows from the detailed design §C, and must NOT redeclare the
 * self-contained third-party libs (pnpm resolves those from the experimental
 * packages) or the profile bundle (loaded through cordis.patch.yml).
 * @module tests/desktop-host-devframe-deps
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const MANIFEST = resolve(import.meta.dirname, '../package.json')

interface Manifest {
  readonly dependencies?: Record<string, string>
}

const REQUIRED = [
  '@deepseek-ai/dsh-experimental-project-contracts',
  '@deepseek-ai/dsh-experimental-session-identity',
  '@deepseek-ai/dsh-experimental-devframe',
  '@deepseek-ai/dsh-experimental-agent-evidence',
  '@deepseek-ai/dsh-experimental-agent-hierarchy',
  '@deepseek-ai/dsh-experimental-project-controller',
  '@deepseek-ai/dsh-experimental-shadow-routing',
  '@deepseek-ai/dsh-experimental-shadow-router',
  '@deepseek-ai/dsh-experimental-shadow-controller',
  '@deepseek-ai/dsh-experimental-agent-dispatch',
  '@deepseek-ai/dsh-experimental-command-goal-binding',
  '@deepseek-ai/dsh-experimental-expert-team',
  '@deepseek-ai/dsh-experimental-project-memory',
  '@deepseek-ai/dsh-experimental-client-ui-expert-team',
  '@deepseek-ai/dsh-experimental-client-ui-project-memory',
  '@deepseek-ai/dsh-experimental-expert-pack-dev',
  '@deepseek-ai/dsh-experimental-expert-pack-paper',
  '@deepseek-ai/dsh-worktree-registry',
  '@deepseek-ai/cordis-plugin-logger-console',
] as const

const FORBIDDEN = [
  'zod',
  'ajv',
  'js-yaml',
  'react',
  '@deepseek-ai/dsh-experimental-devframe-profile',
] as const

function read(): Manifest {
  return JSON.parse(readFileSync(MANIFEST, 'utf8')) as Manifest
}

describe('desktop-host DevFrame dependency closure', () => {
  it('declares every §C row', () => {
    const deps = read().dependencies ?? {}
    for (const name of REQUIRED) expect(deps[name], name).toBe('workspace:^')
  })

  it('does not redeclare self-contained libs or the profile bundle', () => {
    const deps = read().dependencies ?? {}
    for (const name of FORBIDDEN) expect(deps[name], name).toBeUndefined()
  })

  it('lists worktree-registry exactly once (no duplicate loader entry)', () => {
    const deps = read().dependencies ?? {}
    expect(Object.keys(deps).filter(name => name === '@deepseek-ai/dsh-worktree-registry')).toHaveLength(1)
  })
})
