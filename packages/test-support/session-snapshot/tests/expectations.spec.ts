import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  declaredExpectationVariantFiles,
  expectationFileName,
  platformExpectationVariant,
  resolveExpectationPath,
  resolveSessionFixturePath,
} from '../src/expectations.ts'
import { parseSnapshotManifest } from '../src/manifest.ts'

const PLAIN_PIN = parseSnapshotManifest('version: 1\nprofile: web\nheader:\n  class: base\n  pin: true\n')
const VARIANT_PIN = parseSnapshotManifest([
  'version: 1',
  'profile: web',
  'header:',
  '  class: web-minimal',
  '  pin: true',
  'expectations:',
  '  variants:',
  '    win32:',
  '      - tool-schemas',
  '      - ui',
  '    posix:',
  '      - system-prompt',
  '',
].join('\n'))
const SESSION_VARIANT_OWNER = parseSnapshotManifest([
  'version: 1',
  'profile: web',
  'sessionVariants:',
  '  win32: true',
  '',
].join('\n'))

describe('platform expectation variants', () => {
  let dir: string | undefined

  afterEach(async () => {
    if (dir !== undefined) await rm(dir, { recursive: true, force: true })
    dir = undefined
  })

  async function scenarioDir(): Promise<string> {
    dir = await mkdtemp(join(tmpdir(), 'dsh-expectations-'))
    return dir
  }

  it('maps host platforms onto the variant vocabulary', () => {
    expect(platformExpectationVariant('win32')).toBe('win32')
    expect(platformExpectationVariant('linux')).toBe('posix')
    expect(platformExpectationVariant('darwin')).toBe('posix')
  })

  it('names base and variant expected files', () => {
    expect(expectationFileName('system-prompt')).toBe('system-prompt.expected.md')
    expect(expectationFileName('tool-schemas')).toBe('tool-schemas.expected.json')
    expect(expectationFileName('ui')).toBe('ui.expected.md')
    expect(expectationFileName('tool-schemas', 'win32')).toBe('tool-schemas.win32.expected.json')
    expect(expectationFileName('ui', 'win32')).toBe('ui.win32.expected.md')
    expect(expectationFileName('system-prompt', 'posix')).toBe('system-prompt.posix.expected.md')
  })

  it('resolves a declared ui variant on its host platform', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'ui.expected.md'), 'base\n')
    await writeFile(join(root, 'ui.win32.expected.md'), 'win32\n')
    expect(resolveExpectationPath({ dir: root, kind: 'ui', manifest: VARIANT_PIN, platform: 'win32' }))
      .toBe(join(root, 'ui.win32.expected.md'))
  })

  it('resolves the base session fixture without a declaration on any host', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), '{}\n')
    expect(resolveSessionFixturePath({ dir: root, manifest: PLAIN_PIN, platform: 'win32' }))
      .toBe(join(root, 'session.jsonl'))
    expect(resolveSessionFixturePath({ dir: root, manifest: SESSION_VARIANT_OWNER, platform: 'linux' }))
      .toBe(join(root, 'session.jsonl'))
  })

  it('resolves a declared session fixture variant on its host platform', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), 'base\n')
    await writeFile(join(root, 'session.win32.jsonl'), 'win32\n')
    expect(resolveSessionFixturePath({ dir: root, manifest: SESSION_VARIANT_OWNER, platform: 'win32' }))
      .toBe(join(root, 'session.win32.jsonl'))
  })

  it('fails loud when a declared session fixture variant file is missing', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), 'base\n')
    expect(() => resolveSessionFixturePath({ dir: root, manifest: SESSION_VARIANT_OWNER, platform: 'win32' }))
      .toThrow(`session-snapshot: ${root}: declared platform session fixture variant file is missing: session.win32.jsonl`)
  })

  it('selects a declared variant file on its host platform', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'tool-schemas.expected.json'), '["bash"]\n')
    await writeFile(join(root, 'tool-schemas.win32.expected.json'), '["pwsh"]\n')
    expect(resolveExpectationPath({ dir: root, kind: 'tool-schemas', manifest: VARIANT_PIN, platform: 'win32' }))
      .toBe(join(root, 'tool-schemas.win32.expected.json'))
  })

  it('selects a declared posix variant on posix hosts', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'system-prompt.expected.md'), 'base\n')
    await writeFile(join(root, 'system-prompt.posix.expected.md'), 'posix\n')
    expect(resolveExpectationPath({ dir: root, kind: 'system-prompt', manifest: VARIANT_PIN, platform: 'darwin' }))
      .toBe(join(root, 'system-prompt.posix.expected.md'))
  })

  it('falls back to the base file when the kind is not declared for the host platform', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'tool-schemas.expected.json'), '["bash"]\n')
    expect(resolveExpectationPath({ dir: root, kind: 'tool-schemas', manifest: VARIANT_PIN, platform: 'linux' }))
      .toBe(join(root, 'tool-schemas.expected.json'))
  })

  it('uses the base file without any declaration', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'tool-schemas.expected.json'), '["bash"]\n')
    expect(resolveExpectationPath({ dir: root, kind: 'tool-schemas', manifest: PLAIN_PIN, platform: process.platform }))
      .toBe(join(root, 'tool-schemas.expected.json'))
  })

  it('fails loud when a declared win32 variant file is missing', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'tool-schemas.expected.json'), '["bash"]\n')
    expect(() => resolveExpectationPath({ dir: root, kind: 'tool-schemas', manifest: VARIANT_PIN, platform: 'win32' }))
      .toThrow(`session-snapshot: ${root}: declared platform expectation variant file is missing: tool-schemas.win32.expected.json`)
  })

  it('fails loud when a declared posix variant file is missing', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'system-prompt.expected.md'), 'base\n')
    expect(() => resolveExpectationPath({ dir: root, kind: 'system-prompt', manifest: VARIANT_PIN, platform: 'linux' }))
      .toThrow('system-prompt.posix.expected.md')
  })

  it('lists declared variant files for inventory guards', () => {
    expect(declaredExpectationVariantFiles(VARIANT_PIN)).toEqual([
      'system-prompt.posix.expected.md',
      'tool-schemas.win32.expected.json',
      'ui.win32.expected.md',
    ])
    expect(declaredExpectationVariantFiles(PLAIN_PIN)).toEqual([])
    expect(declaredExpectationVariantFiles(SESSION_VARIANT_OWNER)).toEqual(['session.win32.jsonl'])
  })
})
