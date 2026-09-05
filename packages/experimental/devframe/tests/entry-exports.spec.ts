import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { KNOWN_SESSION_EVENT_TYPES } from '@deepseek-ai/dsh-session'
import * as devframe from '../src/index.ts'
import * as controller from '../src/controller/goal-binding.ts'
import * as hierarchy from '../src/hierarchy/index.ts'
import * as permissions from '../src/permissions/index.ts'
import * as reliability from '../src/reliability/index.ts'
import * as shared from '../src/shared/index.ts'

interface PackageManifest {
  readonly exports: Record<string, { readonly types: string; readonly default: string } | string>
  readonly files: readonly string[]
}

const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')) as PackageManifest

describe('DevFrame public entry points', () => {
  it('resolves every runtime subpath from the package root and manifest', () => {
    expect(devframe.GoalBindingController).toBe(controller.GoalBindingController)
    expect(devframe.devframeSpawnOverrides).toBe(hierarchy.devframeSpawnOverrides)
    expect(devframe.RolePolicy).toBe(permissions.RolePolicy)
    expect(devframe.stopProject).toBe(reliability.stopProject)
    expect(devframe.WorkspaceId).toBe(shared.WorkspaceId)
    expect(typeof controller.GoalBindingController).toBe('function')
    expect(typeof permissions.installRolePolicy).toBe('function')
    expect(typeof reliability.stopProject).toBe('function')
    expect(typeof shared.WorkspaceId).toBe('function')

    expect(manifest.exports['./controller']).toEqual({
      types: './lib/types/controller/goal-binding.d.ts',
      default: './lib/types/controller/goal-binding.js',
    })
    expect(manifest.exports['./permissions']).toEqual({
      types: './lib/types/permissions/index.d.ts',
      default: './lib/types/permissions/index.js',
    })
    expect(manifest.exports['./hierarchy']).toEqual({
      types: './lib/types/hierarchy/index.d.ts',
      default: './lib/types/hierarchy/index.js',
    })
    expect(manifest.exports['./reliability']).toEqual({
      types: './lib/types/reliability/index.d.ts',
      default: './lib/types/reliability/index.js',
    })
    expect(manifest.exports['./shared']).toEqual({
      types: './lib/types/shared/index.d.ts',
      default: './lib/types/shared/index.js',
    })
    expect(manifest.files).toEqual([
      'lib/index.js',
      'lib/types/**/*.js',
      'lib/types/**/*.d.ts',
    ])
    expect(KNOWN_SESSION_EVENT_TYPES.has('devframe/role-policy')).toBe(true)
  })
})
