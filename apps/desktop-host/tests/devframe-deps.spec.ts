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
import { composeEntries, loadOverlayPatches } from '@deepseek-ai/dsh-app-boot'
import type { AgentHierarchyConfig } from '@deepseek-ai/dsh-experimental-agent-hierarchy'

const MANIFEST = resolve(import.meta.dirname, '../package.json')

interface Manifest {
  readonly dependencies?: Record<string, string>
  readonly devDependencies?: Record<string, string>
}

const REQUIRED = [
  '@deepseek-ai/dsh-experimental-project-contracts',
  '@deepseek-ai/dsh-experimental-shadow-bridge',
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
  it('leaves the Shadow designation to the deployment', () => {
    const profile = loadOverlayPatches('dsh desktop', resolve(import.meta.dirname, '../../../packages/experimental/devframe-profile/cordis.patch.yml'))
    const overlay = loadOverlayPatches('dsh desktop', resolve(import.meta.dirname, '../config/desktop.cordis.patch.yml'))
    const shadow = composeEntries([profile, overlay]).find(row => row.id === 'shadow-router')
    expect(shadow?.config ?? {}).toEqual({})
  })

  it('extends the profile hierarchy policy only with its mounted project-controller tools', () => {
    const profile = loadOverlayPatches('dsh desktop', resolve(import.meta.dirname, '../../../packages/experimental/devframe-profile/cordis.patch.yml'))
    const overlay = loadOverlayPatches('dsh desktop', resolve(import.meta.dirname, '../config/desktop.cordis.patch.yml'))
    const base = composeEntries([profile]).find(row => row.id === 'agent-hierarchy')!.config as AgentHierarchyConfig
    const desktop = composeEntries([profile, overlay]).find(row => row.id === 'agent-hierarchy')!.config as AgentHierarchyConfig
    const projectTools = ['project_commit', 'project_deliver', 'project_evidence', 'project_integrate', 'project_review', 'project_task']
    for (const role of ['controller', 'lead'] as const) {
      expect(desktop.roleToolPolicies[role].inheritedTools).toEqual([
        ...base.roleToolPolicies[role].inheritedTools,
        ...projectTools,
      ])
    }
    expect(desktop.roleToolPolicies.worker.inheritedTools).toEqual([])
    expect(desktop.leadPluginScopes).toEqual({})
  })

  it('declares every §C row', () => {
    const deps = { ...read().dependencies, ...read().devDependencies }
    for (const name of REQUIRED) expect(deps[name], name).toBe('workspace:^')
  })

  it('does not redeclare self-contained libs or the profile bundle', () => {
    const deps = { ...read().dependencies, ...read().devDependencies }
    for (const name of FORBIDDEN) expect(deps[name], name).toBeUndefined()
  })

  it('lists worktree-registry exactly once (no duplicate loader entry)', () => {
    const deps = { ...read().dependencies, ...read().devDependencies }
    expect(Object.keys(deps).filter(name => name === '@deepseek-ai/dsh-worktree-registry')).toHaveLength(1)
  })

  it('mounts the production project-controller faces without inventing a project root or commit scope', () => {
    const overlay = resolve(import.meta.dirname, '../config/desktop.cordis.patch.yml')
    const rows = composeEntries([loadOverlayPatches('dsh desktop', overlay)])
    const ids = rows.flatMap(row => typeof row.id === 'string' ? [row.id] : [])
    expect(new Set(ids).size).toBe(ids.length)
    const byId = new Map(rows.flatMap(row => typeof row.id === 'string' ? [[row.id, row] as const] : []))
    expect([...byId.keys()]).toEqual(expect.arrayContaining([
      'agent-evidence',
      'project-controller',
      'project-controller-consumer',
      'project-controller-task-consumer',
      'project-controller-delivery-consumer',
    ]))
    expect(byId.get('project-controller')).toMatchObject({
      name: '@deepseek-ai/dsh-experimental-project-controller',
      config: { maxActiveTasks: 2, requestBudget: 64 },
    })
    expect(byId.get('project-controller-consumer')).toMatchObject({
      name: '@deepseek-ai/dsh-experimental-project-controller/consumer',
      config: {
        gitExecutable: 'git',
        gitTimeoutMs: 60000,
        gitMaxOutputBytes: 10485760,
      },
    })
    expect(byId.get('project-controller-delivery-consumer')).toMatchObject({
      name: '@deepseek-ai/dsh-experimental-project-controller/delivery-consumer',
      config: {
        repairLimit: 3,
        requiredChecksByTask: {},
        commitPathsByTask: {},
        checkTimeoutMs: 600000,
        checkMaxOutputBytes: 1048576,
      },
    })
    for (const id of ['project-controller', 'project-controller-consumer', 'project-controller-task-consumer', 'project-controller-delivery-consumer']) {
      const config = byId.get(id)?.config as Record<string, unknown> | undefined
      if (config !== undefined) {
        expect(config).not.toHaveProperty('workspaceRoot')
        expect(config).not.toHaveProperty('authorizedRoots')
        expect(config).not.toHaveProperty('defaultCommitPaths')
      }
    }
  })
})
