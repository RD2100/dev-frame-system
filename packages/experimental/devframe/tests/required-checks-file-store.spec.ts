/**
 * File-backed required-checks registration store: the JSON ledger's durable
 * boundary. Round-trip persistence across store instances, missing-ledger and
 * unregistered-digest rejections on the existing
 * `REQUIRED_CHECKS_CONFIG_NOT_FOUND` code, corrupt ledger documents on the new
 * `REQUIRED_CHECKS_STORE_CORRUPT` code, registered payload schema failures
 * still on the interface-mandated `REQUIRED_CHECKS_INVALID_CONFIG` code, and
 * the unchanged identity/comparison semantics flowing through a file-loaded
 * configuration.
 * @module dsh-experimental-devframe/tests/required-checks-file-store
 */

import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  acceptanceCheckComponent,
  evaluateRequiredChecks,
  type DevFrameRequiredCheck,
  type DevFrameRequiredChecksConfig,
  RequiredChecksError,
  requiredChecksDigest,
} from '../src/required-checks.ts'
import { FileRequiredChecksConfigStore } from '../src/required-checks-file-store.ts'
import type { DevFrameCheckResult } from '../src/events.ts'

const UNIT: DevFrameRequiredCheck = {
  checkId: 'unit-tests',
  executable: 'pnpm',
  arguments: ['exec', 'vitest', 'run', 'packages/a'],
  cwd: 'C:/ws-checksstore',
}
const LINT: DevFrameRequiredCheck = {
  checkId: 'lint',
  executable: 'pnpm',
  arguments: ['run', 'lint'],
  cwd: 'C:/ws-checksstore',
}
const CONFIG: DevFrameRequiredChecksConfig = { version: 1, checks: [UNIT, LINT] }
const CONFIG_JSON = JSON.stringify(CONFIG)

const NOT_FOUND = { name: 'RequiredChecksError', code: 'REQUIRED_CHECKS_CONFIG_NOT_FOUND' }
const CORRUPT = { name: 'RequiredChecksError', code: 'REQUIRED_CHECKS_STORE_CORRUPT' }

/** Temp roots acquired by this file, drained to quiescence by afterEach. */
const tempRoots: string[] = []

afterEach(async () => {
  const roots = [...tempRoots]
  tempRoots.length = 0
  await Promise.all(roots.map(root => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })))
})

/** Create one unique temp directory and a store whose ledger lives inside it. */
async function ledgerFixture(): Promise<{ path: string; store: FileRequiredChecksConfigStore }> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-checksstore-'))
  tempRoots.push(root)
  const path = join(root, 'required-checks-ledger.json')
  return { path, store: new FileRequiredChecksConfigStore({ path }) }
}

/** Write raw ledger bytes directly, bypassing the store, to pin the durable boundary. */
function writeLedger(path: string, content: string): Promise<void> {
  return writeFile(path, content, 'utf8')
}

/** One envelope-shaped registration entry JSON; `extra` injects schema-violating tail keys. */
function entryJson(digest: string, extra = ''): string {
  return `{"digest":"${digest}","config":${CONFIG_JSON}${extra}}`
}

/** Build one real executed check result matching (or deviating from) a required check. */
function executionFor(
  check: DevFrameRequiredCheck,
  status: DevFrameCheckResult['status'] = 'passed',
  command: Partial<Pick<DevFrameRequiredCheck, 'executable' | 'arguments' | 'cwd'>> = {},
): DevFrameCheckResult {
  return {
    checkId: check.checkId,
    executable: command.executable ?? check.executable,
    arguments: command.arguments ?? [...check.arguments],
    cwd: command.cwd ?? check.cwd,
    status,
    ...(status === 'passed' ? { exitCode: 0 } : status === 'failed' ? { exitCode: 1 } : {}),
    durationMs: 12,
  }
}

describe('file-backed registration round-trip and persistence', () => {
  it('registers a configuration under its canonical digest and decodes it back', async () => {
    const { store } = await ledgerFixture()
    const digest = await store.save(CONFIG)
    expect(digest).toBe(requiredChecksDigest(CONFIG))
    await expect(store.load(digest)).resolves.toEqual(CONFIG)
  })

  it('persists registrations across store instances', async () => {
    const { path, store } = await ledgerFixture()
    const digest = await store.save(CONFIG)
    const fresh = new FileRequiredChecksConfigStore({ path })
    await expect(fresh.load(digest)).resolves.toEqual(CONFIG)
  })

  it('treats a repeated registration of the same set as the same registration', async () => {
    const { path, store } = await ledgerFixture()
    const reordered: DevFrameRequiredChecksConfig = { version: 1, checks: [...CONFIG.checks].reverse() }
    const first = await store.save(CONFIG)
    const second = await store.save(reordered)
    expect(second).toBe(first)
    const document = JSON.parse(await readFile(path, 'utf8')) as { registrations: readonly unknown[] }
    expect(document.registrations).toHaveLength(1)
  })

  it('persists two distinct registrations and resolves both from a fresh instance', async () => {
    const { path, store } = await ledgerFixture()
    const other: DevFrameRequiredChecksConfig = { version: 1, checks: [LINT] }
    const first = await store.save(CONFIG)
    const second = await store.save(other)
    expect(second).not.toBe(first)
    const fresh = new FileRequiredChecksConfigStore({ path })
    await expect(fresh.load(first)).resolves.toEqual(CONFIG)
    await expect(fresh.load(second)).resolves.toEqual(other)
  })

  it('keeps the digest identity store-independent', async () => {
    const { store } = await ledgerFixture()
    const digest = await store.save(CONFIG)
    expect(digest).toBe(requiredChecksDigest(CONFIG))
    expect(digest).toBe(acceptanceCheckComponent(CONFIG))
  })

  it('feeds the loaded configuration through the unchanged comparison semantics', async () => {
    const { store } = await ledgerFixture()
    const digest = await store.save(CONFIG)
    const loaded = await store.load(digest)
    const executed = [executionFor(UNIT), executionFor(LINT)]
    expect(evaluateRequiredChecks(loaded, executed))
      .toEqual({ kind: 'satisfied', digest: requiredChecksDigest(CONFIG) })
    const weakened = [executionFor(UNIT, 'passed', { arguments: ['exec', 'vitest', 'run', '--silent'] })]
    const verdict = evaluateRequiredChecks(loaded, weakened)
    expect(verdict.kind).toBe('unsatisfied')
    if (verdict.kind !== 'unsatisfied') throw new Error('expected an unsatisfied verdict')
    expect(verdict.violations).toEqual([
      {
        reason: 'REQUIRED_CHECKS_COMMAND_MISMATCH',
        checkId: UNIT.checkId,
        configured: { executable: UNIT.executable, arguments: UNIT.arguments, cwd: UNIT.cwd },
        executed: [{ executable: UNIT.executable, arguments: ['exec', 'vitest', 'run', '--silent'], cwd: UNIT.cwd }],
      },
      { reason: 'REQUIRED_CHECKS_MISSING', checkId: LINT.checkId },
    ])
  })
})

describe('file-backed missing registrations', () => {
  it('fails loud with REQUIRED_CHECKS_CONFIG_NOT_FOUND when the ledger does not exist', async () => {
    const { path, store } = await ledgerFixture()
    const digest = requiredChecksDigest(CONFIG)
    const rejection = await store.load(digest).then(() => null, (error: unknown) => error)
    expect(rejection).toBeInstanceOf(RequiredChecksError)
    const error = rejection as RequiredChecksError
    expect(error.code).toBe('REQUIRED_CHECKS_CONFIG_NOT_FOUND')
    expect(error.message).toContain(path)
    expect(error.message).toContain(digest)
  })

  it('fails loud with REQUIRED_CHECKS_CONFIG_NOT_FOUND on an empty ledger', async () => {
    const { path, store } = await ledgerFixture()
    await writeLedger(path, '{"version":1,"registrations":[]}\n')
    await expect(store.load(requiredChecksDigest(CONFIG))).rejects.toMatchObject(NOT_FOUND)
  })

  it('fails loud with REQUIRED_CHECKS_CONFIG_NOT_FOUND for an unregistered digest', async () => {
    const { store } = await ledgerFixture()
    await store.save({ version: 1, checks: [LINT] })
    await expect(store.load(requiredChecksDigest(CONFIG))).rejects.toMatchObject(NOT_FOUND)
  })
})

describe('file-backed corrupt ledger boundary', () => {
  it('rejects unparseable ledger bytes with REQUIRED_CHECKS_STORE_CORRUPT', async () => {
    const { path, store } = await ledgerFixture()
    await writeLedger(path, '{not json')
    await expect(store.load(requiredChecksDigest(CONFIG))).rejects.toMatchObject(CORRUPT)
  })

  it.each([
    ['a missing registrations field', `{"version":1}`],
    ['a future ledger version', `{"version":2,"registrations":[]}`],
    ['an unknown top-level key', `{"version":1,"registrations":[],"extra":true}`],
    ['a non-array registrations value', `{"version":1,"registrations":"none"}`],
    ['a non-object root', '[]'],
    ['a string root', '"ledger"'],
    ['a registration missing its digest', `{"version":1,"registrations":[{"config":${CONFIG_JSON}}]}`],
    ['a malformed registration digest', `{"version":1,"registrations":[${entryJson('not-a-digest')}]}`],
    ['an unknown registration key', `{"version":1,"registrations":[${entryJson(requiredChecksDigest(CONFIG), ',"extra":true')}]}`],
  ])('rejects %s with REQUIRED_CHECKS_STORE_CORRUPT', async (_label, raw) => {
    const { path, store } = await ledgerFixture()
    await writeLedger(path, raw)
    await expect(store.load(requiredChecksDigest(CONFIG))).rejects.toMatchObject(CORRUPT)
  })

  it('rejects a registration whose digest disagrees with its configuration content', async () => {
    const { path, store } = await ledgerFixture()
    const digest = await store.save(CONFIG)
    const document = JSON.parse(await readFile(path, 'utf8')) as {
      registrations: Array<{ digest: string; config: unknown }>
    }
    const entry = document.registrations[0]
    if (entry === undefined) throw new Error('expected the saved registration entry')
    entry.config = { version: 1, checks: [UNIT] }
    await writeLedger(path, `${JSON.stringify(document, null, 2)}\n`)
    await expect(store.load(digest)).rejects.toMatchObject(CORRUPT)
  })

  it('refuses to save onto a corrupt ledger instead of repairing it', async () => {
    const { path, store } = await ledgerFixture()
    await writeLedger(path, '{not json')
    await expect(store.save(CONFIG)).rejects.toMatchObject(CORRUPT)
  })

  it('fails loud on corruption in an entry other than the requested one', async () => {
    const { path, store } = await ledgerFixture()
    const unitOnly: DevFrameRequiredChecksConfig = { version: 1, checks: [UNIT] }
    const lintOnly: DevFrameRequiredChecksConfig = { version: 1, checks: [LINT] }
    // Entry A is valid; entry B claims the lint-only digest but registers a
    // different configuration, so the whole ledger is corrupt.
    const registrations = [
      { digest: requiredChecksDigest(unitOnly), config: unitOnly },
      { digest: requiredChecksDigest(lintOnly), config: CONFIG },
    ]
    await writeLedger(path, `${JSON.stringify({ version: 1, registrations }, null, 2)}\n`)
    await expect(store.load(requiredChecksDigest(unitOnly))).rejects.toMatchObject(CORRUPT)
  })
})

describe('file-backed registered payload schema', () => {
  it('keeps registered payload schema failures on REQUIRED_CHECKS_INVALID_CONFIG', async () => {
    const { path, store } = await ledgerFixture()
    // The payload is decoded before the digest drift check, so the
    // interface-mandated code wins over ledger corruption here.
    const registrations = [{ digest: requiredChecksDigest(CONFIG), config: { version: 1, checks: [] } }]
    await writeLedger(path, `${JSON.stringify({ version: 1, registrations }, null, 2)}\n`)
    await expect(store.load(requiredChecksDigest(CONFIG))).rejects.toMatchObject({
      name: 'RequiredChecksError',
      code: 'REQUIRED_CHECKS_INVALID_CONFIG',
    })
  })
})

describe('file-backed ledger boundary details', () => {
  it('round-trips empty-string argv elements through the ledger', async () => {
    const { store } = await ledgerFixture()
    const config: DevFrameRequiredChecksConfig = {
      version: 1,
      checks: [{ checkId: 'ext', executable: 'tool', arguments: ['', '--flag'], cwd: 'C:/ws' }],
    }
    const digest = await store.save(config)
    await expect(store.load(digest)).resolves.toEqual(config)
  })

  it('writes a pretty JSON ledger with the pinned format and exactly one trailing newline', async () => {
    const { path, store } = await ledgerFixture()
    await store.save(CONFIG)
    const raw = await readFile(path, 'utf8')
    const document = JSON.parse(raw) as { version: number; registrations: readonly unknown[] }
    expect(document.version).toBe(1)
    expect(document.registrations).toHaveLength(1)
    expect(raw.endsWith('\n')).toBe(true)
    expect(raw.endsWith('\n\n')).toBe(false)
  })

  it('propagates the raw fs error when saving into a missing directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-checksstore-'))
    tempRoots.push(root)
    const store = new FileRequiredChecksConfigStore({ path: join(root, 'absent', 'ledger.json') })
    const rejection = await store.save(CONFIG).then(() => null, (error: unknown) => error)
    expect(rejection).toBeInstanceOf(Error)
    expect(rejection).not.toBeInstanceOf(RequiredChecksError)
  })

  it('propagates the raw fs error when the ledger path is a directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-checksstore-'))
    tempRoots.push(root)
    const store = new FileRequiredChecksConfigStore({ path: root })
    const rejection = await store.load(requiredChecksDigest(CONFIG)).then(() => null, (error: unknown) => error)
    expect(rejection).toBeInstanceOf(Error)
    expect(rejection).not.toBeInstanceOf(RequiredChecksError)
  })
})
