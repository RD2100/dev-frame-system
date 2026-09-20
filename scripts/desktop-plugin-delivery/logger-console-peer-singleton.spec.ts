/**
 * R1: the vendored console logger must not nest a second host singleton.
 * cosmokit and schemastery move out of dependencies and into peerDependencies;
 * supports-color stays a self-contained terminal-color runtime dependency.
 * Lives under scripts/ because vendor/ is outside the vitest include globs.
 * @module tests/desktop-plugin-delivery-logger-console-peer-singleton
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const MANIFEST = resolve(import.meta.dirname, '../../vendor/logger-console/package.json')

interface Manifest {
  readonly version?: string
  readonly dependencies?: Record<string, string>
  readonly peerDependencies?: Record<string, string>
}

function read(): Manifest {
  return JSON.parse(readFileSync(MANIFEST, 'utf8')) as Manifest
}

describe('logger-console singleton disambiguation', () => {
  it('keeps framework singletons out of dependencies', () => {
    const manifest = read()
    expect(manifest.dependencies?.['@deepseek-ai/cosmokit']).toBeUndefined()
    expect(manifest.dependencies?.['@deepseek-ai/schemastery']).toBeUndefined()
    // supports-color is a terminal-color runtime tool, not a framework singleton.
    expect(manifest.dependencies?.['supports-color']).toBeDefined()
  })

  it('offers the moved singletons as peers and keeps its own version line', () => {
    const manifest = read()
    expect(manifest.peerDependencies?.['@deepseek-ai/cosmokit']).toBe('workspace:^')
    expect(manifest.peerDependencies?.['@deepseek-ai/schemastery']).toBe('workspace:^')
    expect(manifest.version).toBe('1.0.2')
  })
})
