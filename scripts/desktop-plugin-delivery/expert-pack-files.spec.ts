/**
 * P0: the expert-team data packs must carry their loose data files into the
 * tarball. The runtime loads experts/ skills/ team.yml/ schemas/ from the
 * installed package, so a `files` field that only listed lib/ would publish a
 * broken pack. The paper pack must additionally exclude its draft
 * `team.m2-draft.yml`.
 * @module tests/desktop-plugin-delivery-expert-pack-files
 */

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = resolve(import.meta.dirname, '../../')

interface Manifest {
  readonly files?: readonly string[]
}

function files(dir: string): readonly string[] {
  const manifest = JSON.parse(readFileSync(join(ROOT, dir, 'package.json'), 'utf8')) as Manifest
  return manifest.files ?? []
}

interface PackedEntry {
  readonly path: string
}

/**
 * Run `npm pack --dry-run --json` in a pack directory and return the
 * tarball-relative paths npm actually includes. This is the real packing
 * result (the interaction of `files`, `.npmignore` and `.gitignore`), not
 * the declared glob list. `--dry-run` writes nothing to disk.
 */
function packedPaths(dir: string): string[] {
  const raw = execFileSync('npm', ['pack', '--dry-run', '--json'], {
    cwd: join(ROOT, dir),
    encoding: 'utf8',
    shell: true,
    timeout: 60_000,
  })
  const parsed = JSON.parse(raw) as readonly { readonly files?: readonly PackedEntry[] }[]
  return (parsed[0]?.files ?? []).map(entry => entry.path)
}

describe('expert-pack data files are declared for packing', () => {
  it('expert-pack-dev declares experts/ skills/ team.yml/ schemas/', () => {
    const list = files('packages/experimental/expert-pack-dev')
    expect(list).toContain('experts/**')
    expect(list).toContain('skills/**')
    expect(list).toContain('team.yml')
    expect(list).toContain('schemas/**')
    expect(list).toContain('lib/**/*.js')
  })

  it('expert-pack-paper declares the data dirs and excludes the draft team file', () => {
    const list = files('packages/experimental/expert-pack-paper')
    expect(list).toContain('experts/**')
    expect(list).toContain('skills/**')
    expect(list).toContain('team.yml')
    expect(list).toContain('schemas/**')
    // team.m2-draft.yml must never be reached by a glob; team.yml is exact.
    expect(list.some(entry => entry.includes('m2-draft'))).toBe(false)
    expect(list).not.toContain('team*.yml')
  })

  it('expert-pack-dev actually tarballs experts/ skills/ team.yml/ schemas/ lib/', () => {
    const paths = packedPaths('packages/experimental/expert-pack-dev')
    expect(paths).toContain('experts/engineer.md')
    expect(paths).toContain('team.yml')
    expect(paths.some(path => path.startsWith('skills/'))).toBe(true)
    expect(paths.some(path => path.startsWith('schemas/'))).toBe(true)
    expect(paths.some(path => path.startsWith('lib/') && path.endsWith('.js'))).toBe(true)
  })

  it('ships a non-empty experts/engineer.md (guards against a silently empty expert file)', () => {
    const body = readFileSync(join(ROOT, 'packages/experimental/expert-pack-dev/experts/engineer.md'), 'utf8')
    expect(body.length).toBeGreaterThan(0)
    expect(body).toContain('id: engineer')
  })

  it('expert-pack-paper tarball excludes team.m2-draft.yml but keeps team.yml', () => {
    const paths = packedPaths('packages/experimental/expert-pack-paper')
    expect(paths).toContain('team.yml')
    expect(paths).not.toContain('team.m2-draft.yml')
    expect(paths.some(path => path.includes('m2-draft'))).toBe(false)
  })
})
