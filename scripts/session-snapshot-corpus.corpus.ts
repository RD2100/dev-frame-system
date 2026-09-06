/** Repository-wide ownership and storage invariants for the recorded-session corpus. */

import { existsSync } from 'node:fs'
import { lstat, readFile, readdir, realpath } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { expect, it } from 'vitest'
import * as yaml from 'js-yaml'
import { evaluate } from '@deepseek-ai/cordis-plugin-loader'
import { entryListSchema } from '@deepseek-ai/cordis-plugin-include'
import {
  captureExpectedWorkspaceSnapshot,
  childExpectationFileName,
  declaredExpectationVariantFiles,
  EMPTY_WORKSPACE_MARKER,
  parseSnapshotManifest,
  redactSessionSnapshotIds,
  resolveWorkspaceExpectedDir,
  scrubSystemPrompts,
  scrubToolSchemas,
  sessionFixtureNames,
  type SnapshotExpectationPlatform,
  type SnapshotManifest,
} from '@deepseek-ai/dsh-session-snapshot'

const repoRoot = resolve(import.meta.dirname, '..')
const corpusRoot = join(repoRoot, 'snapshots')
const profiles = ['acp', 'sdk', 'session', 'web'] as const
const snapshotAdapters = [
  'apps/web/tests/message-feedback-protocol.snapshot.ts',
  'apps/web/tests/minimal-preset.snapshot.ts',
  'snapshots/acp/acp.snapshot.ts',
  'snapshots/sdk/sdk.snapshot.ts',
  'snapshots/session/headless.snapshot.ts',
] as const

interface Scenario {
  readonly key: string
  readonly profile: string
  readonly name: string
  readonly dir: string
  readonly manifest: SnapshotManifest & {
    composition: string
    recording: 'live' | 'authored'
    header: NonNullable<SnapshotManifest['header']>
  }
}

async function scenarios(): Promise<Scenario[]> {
  const result: Scenario[] = []
  for (const profile of profiles) {
    const root = join(corpusRoot, profile)
    for (const entry of await readdir(root, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      const dir = join(root, entry.name)
      const path = join(dir, 'snapshot.yml')
      expect(existsSync(path), `${profile}/${entry.name}/snapshot.yml`).toBe(true)
      const manifest = parseSnapshotManifest(await readFile(path, 'utf8'), path)
      expect(manifest.scenario, `${profile}/${entry.name}: scenario`).toBe(entry.name)
      expect(manifest.profile, `${profile}/${entry.name}: profile`).toBe(profile === 'session' ? 'headless' : profile)
      expect(manifest.composition, `${profile}/${entry.name}: composition`).toBeTypeOf('string')
      expect(manifest.recording, `${profile}/${entry.name}: recording`).toMatch(/^(live|authored)$/)
      expect(manifest.header, `${profile}/${entry.name}: header`).toBeDefined()
      result.push({
        key: `${profile}/${entry.name}`,
        profile,
        name: entry.name,
        dir,
        manifest: {
          ...manifest,
          composition: manifest.composition as string,
          recording: manifest.recording as 'live' | 'authored',
          header: manifest.header as NonNullable<SnapshotManifest['header']>,
        },
      })
    }
  }
  return result
}

function referencedScenario(owner: Scenario, source: string): string {
  return source.includes('/') ? source : `${owner.profile}/${source}`
}

async function snapshotNamedTests(): Promise<string[]> {
  const files: string[] = []
  const visit = async (directory: string, relativeDir: string): Promise<void> => {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (['dist', 'lib', 'node_modules'].includes(entry.name)) continue
        await visit(join(directory, entry.name), join(relativeDir, entry.name))
      } else if (entry.isFile() && /\.snapshot\.tsx?$/u.test(entry.name)) {
        files.push(join(relativeDir, entry.name).split(/[/\\]/u).join('/'))
      }
    }
  }
  for (const root of ['apps', 'native', 'packages', 'python', 'scripts', 'snapshots', 'website']) {
    await visit(join(repoRoot, root), root)
  }
  return files.sort()
}

it('reserves the snapshot test suffix for recorded-session adapters', async () => {
  expect(await snapshotNamedTests()).toEqual([...snapshotAdapters])
})

it('keeps every recorded session owned, pinned, redacted, and header-scrubbed', async () => {
  const all = await scenarios()
  const byKey = new Map(all.map(scenario => [scenario.key, scenario]))
  const pinByClass = new Map<string, Scenario>()

  for (const scenario of all) {
    if (scenario.manifest.header.pin !== true) continue
    const key = `${scenario.manifest.composition}/${scenario.manifest.header.class}`
    expect(pinByClass.has(key), `${key}: duplicate header pin`).toBe(false)
    pinByClass.set(key, scenario)
  }

  for (const scenario of all) {
    const { manifest, dir, key } = scenario
    const classKey = `${manifest.composition}/${manifest.header.class}`
    expect(pinByClass.has(classKey), `${key}: missing composition/header pin ${classKey}`).toBe(true)

    const localSession = join(dir, 'session.jsonl')
    if (manifest.session === undefined) {
      expect(existsSync(localSession), `${key}: owner session.jsonl`).toBe(true)
    } else {
      expect(existsSync(localSession), `${key}: borrower must not own session.jsonl`).toBe(false)
      const target = resolve(dir, manifest.session.source)
      expect(existsSync(target), `${key}: session source`).toBe(true)
      const targetDir = await realpath(dirname(target))
      const sourceKey = relative(corpusRoot, targetDir).split(/[/\\]/).join('/')
      expect(byKey.has(sourceKey), `${key}: session source must name a corpus owner`).toBe(true)
      expect(byKey.get(sourceKey)?.manifest.session, `${key}: session source cannot chain through a borrower`).toBeUndefined()
    }

    expect(existsSync(join(dir, 'replay.override.json')), `${key}: replay override presence`)
      .toBe(manifest.replay?.override === true)
    expect(existsSync(join(dir, 'workspace.expected')), `${key}: final workspace presence`)
      .toBe(manifest.workspace?.final === true)
    if (manifest.workspace?.final === true) {
      // The host platform's comparison target is the resolved expectation
      // directory (a declared variant replaces the base on its platform); the
      // resolver fails loud on a declared-but-missing variant directory.
      const expectedRoot = resolveWorkspaceExpectedDir({ dir, manifest, platform: process.platform })
      const expectedWorkspace = await captureExpectedWorkspaceSnapshot(expectedRoot)
      expect(existsSync(join(expectedRoot, EMPTY_WORKSPACE_MARKER)), `${key}: empty workspace marker`)
        .toBe(expectedWorkspace.length === 0)
    }
    expect(existsSync(join(dir, 'input.json')), `${key}: executable input metadata is ACP-only`)
      .toBe(scenario.profile === 'acp')
    if (scenario.profile !== 'acp') {
      expect(existsSync(join(dir, 'stdout.expected.jsonl')), `${key}: ACP transcript outside ACP`).toBe(false)
    }

    if (manifest.header.pin === true) {
      const promptSource = byKey.get(referencedScenario(scenario, manifest.header.systemPromptSource ?? scenario.name))
      const schemaSource = byKey.get(referencedScenario(scenario, manifest.header.toolSchemasSource ?? scenario.name))
      expect(promptSource, `${key}: system-prompt source`).toBeDefined()
      expect(schemaSource, `${key}: tool-schema source`).toBeDefined()
      expect(existsSync(join((promptSource as Scenario).dir, 'system-prompt.expected.md')), `${key}: system-prompt sidecar`).toBe(true)
      expect(existsSync(join((schemaSource as Scenario).dir, 'tool-schemas.expected.json')), `${key}: tool-schema sidecar`).toBe(true)
      for (const [field, source] of [
        ['system-prompt.expected.md', promptSource],
        ['tool-schemas.expected.json', schemaSource],
      ] as const) {
        const local = join(dir, field)
        if (!existsSync(local) || !(await lstat(local)).isSymbolicLink()) continue
        expect(await realpath(local), `${key}: ${field} symlink follows its manifest source`)
          .toBe(await realpath(join((source as Scenario).dir, field)))
      }
    }

    if (manifest.session !== undefined) continue
    // Declared platform-variant files are manifest-owned inventory: the
    // session-fixture namer sees only base and child fixtures, while every
    // declared variant JSONL satisfies the same redaction and scrub invariants
    // as the base recording.
    const variantFiles = declaredExpectationVariantFiles(manifest)
    const names = sessionFixtureNames((await readdir(dir)).filter(name => !variantFiles.includes(name)))
    const fixtures = await Promise.all(names.map(name => readFile(join(dir, name), 'utf8')))
    expect(redactSessionSnapshotIds(fixtures), `${key}: typed identity fixed point`).toEqual(fixtures)
    for (const [index, fixture] of fixtures.entries()) {
      expect(scrubSystemPrompts(fixture), `${key}/${names[index]}: system prompt must be a sidecar`).toBe(fixture)
      expect(scrubToolSchemas(fixture), `${key}/${names[index]}: tool schemas must be a sidecar`).toBe(fixture)
    }
    for (const file of variantFiles.filter(name => name.endsWith('.jsonl'))) {
      const fixture = await readFile(join(dir, file), 'utf8')
      expect(redactSessionSnapshotIds([fixture]), `${key}/${file}: typed identity fixed point`).toEqual([fixture])
      expect(scrubSystemPrompts(fixture), `${key}/${file}: system prompt must be a sidecar`).toBe(fixture)
      expect(scrubToolSchemas(fixture), `${key}/${file}: tool schemas must be a sidecar`).toBe(fixture)
    }
    // Declared child session variants must name committed variant files whose
    // indexes exist in the base child inventory.
    for (const [variant, indexes] of Object.entries(manifest.childSessionVariants ?? {})) {
      for (const index of indexes) {
        expect(names[index], `${key}: child variant ${variant} index ${index}`).toBeDefined()
      }
    }
    // Every declared child sidecar variant must be committed beside the base
    // sidecars it replaces on its platform.
    for (const [variant, kinds] of Object.entries(manifest.childExpectations?.variants ?? {})) {
      for (const kind of kinds) {
        for (const index of (kind === 'system-prompt' ? manifest.header.childSystemPrompts : manifest.header.childToolSchemas) ?? []) {
          expect(existsSync(join(dir, childExpectationFileName(kind, index, variant as SnapshotExpectationPlatform))),
            `${key}: child ${kind} sidecar variant ${index}/${variant}`).toBe(true)
        }
      }
    }
    // Declared SDK wire-golden variants must be committed as a complete pair.
    for (const variant of Object.keys(manifest.wireVariants ?? {})) {
      expect(existsSync(join(dir, `notifications.${variant}.expected.jsonl`)), `${key}: notifications.${variant} golden`).toBe(true)
      expect(existsSync(join(dir, `result.${variant}.expected.json`)), `${key}: result.${variant} golden`).toBe(true)
    }
    // Declared workspace expectation variants must be committed beside the base
    // workspace expectation they replace on their platform.
    for (const variant of Object.keys(manifest.workspaceVariants ?? {})) {
      expect(existsSync(join(dir, `workspace.${variant}.expected`)), `${key}: workspace.${variant} expectation directory`).toBe(true)
    }
    for (const index of manifest.header.childSystemPrompts ?? []) {
      expect(names[index], `${key}: child prompt index ${index}`).toBeDefined()
      expect(existsSync(join(dir, `system-prompt.${index}.expected.md`)), `${key}: child prompt sidecar ${index}`).toBe(true)
    }
    for (const index of manifest.header.childToolSchemas ?? []) {
      expect(names[index], `${key}: child schema index ${index}`).toBeDefined()
      expect(existsSync(join(dir, `tool-schemas.${index}.expected.json`)), `${key}: child schema sidecar ${index}`).toBe(true)
    }
  }
})

/** Shell tool families: every row in a family registers the same tool name, so two active rows cannot both mount. */
const SHELL_FAMILIES = [
  { tool: 'bash', names: ['@deepseek-ai/dsh-tool-bash', '@deepseek-ai/dsh-tool-bash-persistent'] },
  { tool: 'pwsh', names: ['@deepseek-ai/dsh-tool-pwsh', '@deepseek-ai/dsh-tool-pwsh-persistent'] },
] as const
/** The persistent twins whose insert into a composition obliges the family to keep exactly one active row per host. */
const SHELL_TWINS = new Set<string>(SHELL_FAMILIES.flatMap(family => family.names.filter(name => name.endsWith('-persistent'))))
const SHELL_PLATFORMS = ['win32', 'linux'] as const

interface ShellRow {
  readonly id: string | undefined
  readonly name: string
  readonly disabled: unknown
}

function isShellRow(record: Record<string, unknown>): boolean {
  return typeof record.name === 'string' && SHELL_FAMILIES.some(family => (family.names as readonly string[]).includes(record.name as string))
}

function toShellRow(record: Record<string, unknown>): ShellRow {
  return {
    id: typeof record.id === 'string' ? record.id : undefined,
    name: record.name as string,
    disabled: record.disabled,
  }
}

/** Collect every shell row anywhere in a parsed patch document, regardless of nesting. */
function deepShellRows(value: unknown, into: ShellRow[] = []): ShellRow[] {
  if (Array.isArray(value)) {
    for (const item of value) deepShellRows(item, into)
  } else if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (isShellRow(record)) into.push(toShellRow(record))
    for (const child of Object.values(record)) deepShellRows(child, into)
  }
  return into
}

/** Parse a composition or patch document with the product's entry schema (the only one that carries `!!js`). */
async function loadComposition(path: string): Promise<unknown> {
  return yaml.load(await readFile(path, 'utf8'), { schema: entryListSchema })
}

/**
 * Split a composition document's shell rows by position: top-level rows overlay
 * the base bundle by id (their `disabled` replaces the base row's), while rows
 * under `insert` (at any depth) are additional registrations in their own right.
 */
function compositionShellRows(entries: unknown[]): { overlays: ShellRow[]; additions: ShellRow[] } {
  const overlays: ShellRow[] = []
  const additions: ShellRow[] = []
  const walkInserts = (value: unknown): void => {
    if (Array.isArray(value)) {
      for (const item of value) walkInserts(item)
    } else if (value !== null && typeof value === 'object') {
      const record = value as Record<string, unknown>
      if (isShellRow(record)) additions.push(toShellRow(record))
      if (record.insert !== undefined) walkInserts(record.insert)
    }
  }
  for (const entry of entries) {
    if (entry === null || typeof entry !== 'object') continue
    const record = entry as Record<string, unknown>
    if (isShellRow(record)) overlays.push(toShellRow(record))
    if (record.insert !== undefined) walkInserts(record.insert)
  }
  return { overlays, additions }
}

/** Resolve one row's activity for a platform: literal flags stay literal, `!!js` expressions evaluate under the injected process. */
function shellRowActive(row: { readonly disabled: unknown }, platform: string): boolean {
  if (row.disabled === true) return false
  const expression = (row.disabled as { __jsExpr?: string } | undefined)?.__jsExpr
  return expression === undefined ? true : !evaluate({ process: { platform } }, expression)
}

it('keeps exactly one active shell tool per family in every headless composition that mounts a persistent twin', async () => {
  const baseRoot = join(repoRoot, 'packages', 'bundle', 'base')
  const baseManifest = JSON.parse(await readFile(join(baseRoot, 'package.json'), 'utf8')) as {
    dsh?: { bundle?: { patch?: string } }
  }
  const basePatchPath = join(baseRoot, baseManifest.dsh?.bundle?.patch as string)
  const baseRows = deepShellRows(await loadComposition(basePatchPath))
  expect(baseRows.length, 'base bundle must mount the shell tool rows').toBeGreaterThan(0)

  for (const owner of (await scenarios()).filter(scenario => scenario.profile === 'session')) {
    const livePath = join(owner.dir, 'cordis.yml')
    const replayPath = join(owner.dir, 'cordis.snapshot.yml')
    const liveDoc = existsSync(livePath) ? await loadComposition(livePath) : undefined
    const replayDoc = existsSync(replayPath) ? await loadComposition(replayPath) : undefined
    const parts = [liveDoc, replayDoc].filter((doc): doc is unknown[] => Array.isArray(doc))
    if (!parts.some((doc) => {
      const rows = compositionShellRows(doc)
      return rows.overlays.length + rows.additions.length > 0
    })) continue

    // A composition that claims a shell family must keep both patches in the
    // owner directory in sync, or record and replay load different tool sets.
    expect(liveDoc !== undefined && replayDoc !== undefined,
      `${owner.key}: shell composition must keep cordis.yml and cordis.snapshot.yml paired`).toBe(true)

    for (const [path, doc] of [[livePath, liveDoc], [replayPath, replayDoc]] as const) {
      const label = `${owner.key}/${path === livePath ? 'cordis.yml' : 'cordis.snapshot.yml'}`
      const { overlays, additions } = compositionShellRows(doc as unknown[])
      for (const family of SHELL_FAMILIES) {
        const familyNames = family.names as readonly string[]
        const rows = [...overlays, ...additions]
        if (!rows.some(row => familyNames.includes(row.name) && SHELL_TWINS.has(row.name))) continue
        const baseIds = new Set(baseRows.map(row => row.id))
        const effective = [
          ...baseRows
            .filter(row => familyNames.includes(row.name))
            .map((row) => {
              const overlay = overlays.find(candidate => candidate.id !== undefined && candidate.id === row.id)
              return { name: row.name, disabled: overlay?.disabled ?? row.disabled }
            }),
          ...additions,
          ...overlays.filter(row => row.id === undefined || !baseIds.has(row.id)),
        ].filter(row => familyNames.includes(row.name))
        for (const platform of SHELL_PLATFORMS) {
          const active = effective.filter(row => shellRowActive(row, platform))
          expect(active, `${label}: ${family.tool} family must keep exactly one active row on ${platform}`).toHaveLength(1)
        }
      }
    }
  }
})
