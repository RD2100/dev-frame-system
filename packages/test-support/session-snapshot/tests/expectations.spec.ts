import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  childExpectationFileName,
  childSessionFixtureFileName,
  declaredExpectationVariantFiles,
  expectationFileName,
  platformExpectationVariant,
  resolveChildExpectationPath,
  resolveChildSessionFixturePath,
  resolveExpectationPath,
  resolveSessionFixturePath,
  resolveWorkspaceExpectedDir,
  sessionFixtureFileName,
  workspaceExpectedDirName,
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
const CHILD_VARIANT_OWNER = parseSnapshotManifest([
  'version: 1',
  'profile: headless',
  'childSessionVariants:',
  '  win32: [1, 2]',
  '',
].join('\n'))
const CHILD_SIDECAR_VARIANT_OWNER = parseSnapshotManifest([
  'version: 1',
  'profile: headless',
  'header:',
  '  class: default',
  '  childToolSchemas: [1]',
  'childExpectations:',
  '  variants:',
  '    win32: [tool-schemas]',
  '',
].join('\n'))
const WORKSPACE_VARIANT_OWNER = parseSnapshotManifest([
  'version: 1',
  'profile: headless',
  'workspace:',
  '  final: true',
  'workspaceVariants:',
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

  it('names the session fixture target without requiring the file to exist', () => {
    expect(sessionFixtureFileName(PLAIN_PIN, 'win32')).toBe('session.jsonl')
    expect(sessionFixtureFileName(SESSION_VARIANT_OWNER, 'win32')).toBe('session.win32.jsonl')
    expect(sessionFixtureFileName(SESSION_VARIANT_OWNER, 'linux')).toBe('session.jsonl')
  })

  it('fails loud when a declared session fixture variant file is missing', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), 'base\n')
    expect(() => resolveSessionFixturePath({ dir: root, manifest: SESSION_VARIANT_OWNER, platform: 'win32' }))
      .toThrow(`session-snapshot: ${root}: declared platform session fixture variant file is missing: session.win32.jsonl`)
  })

  it('consumes a declared child session variant on its host platform', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), 'parent\n')
    await writeFile(join(root, 'session.1.jsonl'), 'child 1 base\n')
    await writeFile(join(root, 'session.1.win32.jsonl'), 'child 1 win32\n')
    expect(resolveChildSessionFixturePath({ dir: root, manifest: CHILD_VARIANT_OWNER, index: 1, platform: 'win32' }))
      .toBe(join(root, 'session.1.win32.jsonl'))
  })

  it('falls back to the base child fixture for undeclared indexes and platforms', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), 'parent\n')
    await writeFile(join(root, 'session.1.jsonl'), 'child 1 base\n')
    await writeFile(join(root, 'session.2.jsonl'), 'child 2 base\n')
    // Undeclared child index on the declaring platform.
    expect(resolveChildSessionFixturePath({ dir: root, manifest: CHILD_VARIANT_OWNER, index: 3, platform: 'win32' }))
      .toBe(join(root, 'session.3.jsonl'))
    // POSIX hosts keep the base child fixtures even where win32 variants are declared.
    expect(resolveChildSessionFixturePath({ dir: root, manifest: CHILD_VARIANT_OWNER, index: 1, platform: 'linux' }))
      .toBe(join(root, 'session.1.jsonl'))
    // No declaration at all keeps the base name on every platform.
    expect(resolveChildSessionFixturePath({ dir: root, manifest: PLAIN_PIN, index: 1, platform: process.platform }))
      .toBe(join(root, 'session.1.jsonl'))
  })

  it('fails loud when a declared child session variant file is missing', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'session.jsonl'), 'parent\n')
    await writeFile(join(root, 'session.1.jsonl'), 'child 1 base\n')
    expect(() => resolveChildSessionFixturePath({ dir: root, manifest: CHILD_VARIANT_OWNER, index: 2, platform: 'win32' }))
      .toThrow(`session-snapshot: ${root}: declared platform child session fixture variant file is missing: session.2.win32.jsonl`)
  })

  it('names child session fixture write targets without requiring the files to exist', () => {
    expect(childSessionFixtureFileName(CHILD_VARIANT_OWNER, 1, 'win32')).toBe('session.1.win32.jsonl')
    expect(childSessionFixtureFileName(CHILD_VARIANT_OWNER, 3, 'win32')).toBe('session.3.jsonl')
    expect(childSessionFixtureFileName(CHILD_VARIANT_OWNER, 1, 'linux')).toBe('session.1.jsonl')
    expect(childSessionFixtureFileName(PLAIN_PIN, 1, process.platform)).toBe('session.1.jsonl')
  })

  it('names base and child-indexed expected files with the variant vocabulary', () => {
    expect(childExpectationFileName('tool-schemas', 1)).toBe('tool-schemas.1.expected.json')
    expect(childExpectationFileName('system-prompt', 2)).toBe('system-prompt.2.expected.md')
    expect(childExpectationFileName('tool-schemas', 1, 'win32')).toBe('tool-schemas.1.win32.expected.json')
  })

  it('resolves a declared child sidecar variant on its host platform and the base otherwise', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'tool-schemas.1.expected.json'), 'base\n')
    await writeFile(join(root, 'tool-schemas.1.win32.expected.json'), 'win32\n')
    expect(resolveChildExpectationPath({ dir: root, kind: 'tool-schemas', index: 1, manifest: CHILD_SIDECAR_VARIANT_OWNER, platform: 'win32' }))
      .toBe(join(root, 'tool-schemas.1.win32.expected.json'))
    expect(resolveChildExpectationPath({ dir: root, kind: 'tool-schemas', index: 1, manifest: CHILD_SIDECAR_VARIANT_OWNER, platform: 'linux' }))
      .toBe(join(root, 'tool-schemas.1.expected.json'))
  })

  it('fails loud when a declared child sidecar variant file is missing', async () => {
    const root = await scenarioDir()
    await writeFile(join(root, 'tool-schemas.1.expected.json'), 'base\n')
    expect(() => resolveChildExpectationPath({ dir: root, kind: 'tool-schemas', index: 1, manifest: CHILD_SIDECAR_VARIANT_OWNER, platform: 'win32' }))
      .toThrow(`session-snapshot: ${root}: declared platform child expectation variant file is missing: tool-schemas.1.win32.expected.json`)
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

  it('names the workspace expectation directory without requiring it to exist', () => {
    expect(workspaceExpectedDirName(WORKSPACE_VARIANT_OWNER, 'win32')).toBe('workspace.win32.expected')
    expect(workspaceExpectedDirName(WORKSPACE_VARIANT_OWNER, 'linux')).toBe('workspace.expected')
    expect(workspaceExpectedDirName(PLAIN_PIN, process.platform)).toBe('workspace.expected')
  })

  it('resolves a declared workspace variant directory on its host platform', async () => {
    const root = await scenarioDir()
    await mkdir(join(root, 'workspace.expected'))
    await mkdir(join(root, 'workspace.win32.expected'))
    expect(resolveWorkspaceExpectedDir({ dir: root, manifest: WORKSPACE_VARIANT_OWNER, platform: 'win32' }))
      .toBe(join(root, 'workspace.win32.expected'))
  })

  it('resolves the base workspace expectation directory for undeclared platforms', async () => {
    const root = await scenarioDir()
    await mkdir(join(root, 'workspace.expected'))
    await mkdir(join(root, 'workspace.win32.expected'))
    expect(resolveWorkspaceExpectedDir({ dir: root, manifest: WORKSPACE_VARIANT_OWNER, platform: 'linux' }))
      .toBe(join(root, 'workspace.expected'))
    expect(resolveWorkspaceExpectedDir({ dir: root, manifest: PLAIN_PIN, platform: process.platform }))
      .toBe(join(root, 'workspace.expected'))
  })

  it('fails loud when a declared workspace variant directory is missing', async () => {
    const root = await scenarioDir()
    await mkdir(join(root, 'workspace.expected'))
    expect(() => resolveWorkspaceExpectedDir({ dir: root, manifest: WORKSPACE_VARIANT_OWNER, platform: 'win32' }))
      .toThrow(`session-snapshot: ${root}: declared platform workspace expectation directory is missing: workspace.win32.expected`)
  })

  it('lists declared variant files for inventory guards', () => {
    expect(declaredExpectationVariantFiles(VARIANT_PIN)).toEqual([
      'system-prompt.posix.expected.md',
      'tool-schemas.win32.expected.json',
      'ui.win32.expected.md',
    ])
    expect(declaredExpectationVariantFiles(PLAIN_PIN)).toEqual([])
    expect(declaredExpectationVariantFiles(SESSION_VARIANT_OWNER)).toEqual(['session.win32.jsonl'])
    expect(declaredExpectationVariantFiles(CHILD_VARIANT_OWNER)).toEqual([
      'session.1.win32.jsonl',
      'session.2.win32.jsonl',
    ])
  })
})
