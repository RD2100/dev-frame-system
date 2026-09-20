/**
 * Static invariants for the 20 DevFrame self-contained publish objects.
 * These are the package.json half of the detailed-design preflight
 * (docs/working/detailed-design-self-contained-distribution.md §A/§B): every
 * object is publishable (not private, versioned, engines/repository/public
 * access) and never nests a framework singleton in its own dependencies.
 * @module tests/desktop-plugin-delivery-devframe-preflight
 */

import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = resolve(import.meta.dirname, '../../')

interface Manifest {
  readonly private?: boolean
  readonly version?: string
  readonly engines?: Record<string, string>
  readonly publishConfig?: { readonly access?: string }
  readonly repository?: unknown
  readonly dependencies?: Record<string, string>
}

interface Spec {
  readonly dir: string
  readonly version: string
}

const PACKAGES: readonly Spec[] = [
  { dir: 'packages/experimental/project-contracts', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/session-identity', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/devframe', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/agent-evidence', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/agent-hierarchy', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/project-controller', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/shadow-routing', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/shadow-router', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/shadow-controller', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/agent-dispatch', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/command-goal-binding', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/expert-team', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/project-memory', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/client-ui-expert-team', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/client-ui-project-memory', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/expert-pack-dev', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/expert-pack-paper', version: '0.1.6-alpha.1' },
  { dir: 'packages/experimental/devframe-profile', version: '0.1.6-alpha.1' },
  { dir: 'packages/workflow/worktree-registry', version: '0.1.6-alpha.1' },
  { dir: 'vendor/logger-console', version: '1.0.2' },
]

const FORBIDDEN_DEPS = [
  '@deepseek-ai/cordis',
  '@deepseek-ai/schemastery',
  '@deepseek-ai/dsh-brand',
  '@deepseek-ai/cosmokit',
] as const

function read(spec: Spec): Manifest {
  return JSON.parse(readFileSync(join(ROOT, spec.dir, 'package.json'), 'utf8')) as Manifest
}

describe('DevFrame self-contained publish objects', () => {
  for (const spec of PACKAGES) {
    it(`${spec.dir} is publishable and singleton-free in dependencies`, () => {
      const manifest = read(spec)
      expect(manifest.private, `${spec.dir} must not be private`).not.toBe(true)
      expect(manifest.version).toBe(spec.version)
      expect(manifest.engines?.node, `${spec.dir} engines`).toMatch(/22\.19/)
      expect(manifest.publishConfig?.access, `${spec.dir} publish access`).toBe('public')
      expect(manifest.repository, `${spec.dir} repository`).toBeDefined()
      for (const forbidden of FORBIDDEN_DEPS) {
        expect(manifest.dependencies?.[forbidden], `${spec.dir} must not bundle ${forbidden}`).toBeUndefined()
      }
    })
  }
})
