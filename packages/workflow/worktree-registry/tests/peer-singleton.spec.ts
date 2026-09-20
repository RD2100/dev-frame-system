/**
 * R1: worktree-registry must not nest a second copy of the host singletons.
 * dsh-brand and schemastery move out of dependencies and into peerDependencies;
 * zod stays a self-contained runtime dependency.
 * @module tests/worktree-registry-peer-singleton
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const MANIFEST = resolve(import.meta.dirname, '../package.json')

interface Manifest {
  readonly dependencies?: Record<string, string>
  readonly peerDependencies?: Record<string, string>
}

function read(): Manifest {
  return JSON.parse(readFileSync(MANIFEST, 'utf8')) as Manifest
}

describe('worktree-registry singleton disambiguation', () => {
  it('keeps framework singletons out of dependencies', () => {
    const manifest = read()
    expect(manifest.dependencies?.['@deepseek-ai/dsh-brand']).toBeUndefined()
    expect(manifest.dependencies?.['@deepseek-ai/schemastery']).toBeUndefined()
    // zod remains self-contained.
    expect(manifest.dependencies?.zod).toBeDefined()
  })

  it('offers the moved singletons as peers', () => {
    const manifest = read()
    expect(manifest.peerDependencies?.['@deepseek-ai/dsh-brand']).toBe('workspace:^')
    expect(manifest.peerDependencies?.['@deepseek-ai/schemastery']).toBe('workspace:^')
  })
})
