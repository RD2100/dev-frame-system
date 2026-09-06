/**
 * Real-git fixture suite for the source fingerprint engine. Every case runs
 * the engine against a genuine repository in a unique `mkdtemp` root; the
 * engine's git face is the production one (no mocks), with the unavailable-git
 * case asserted through the engine's `gitCommand` injection seam instead of
 * PATH mutation.
 * @module dsh-experimental-devframe/tests/source-fingerprint
 */

import { execFile } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { promisify } from 'node:util'
import { afterEach, describe, expect, it } from 'vitest'
import { computeSourceFingerprint, SourceFingerprintError, verifySourceFingerprint } from '../src/source-fingerprint.ts'
import type { SourceFingerprintErrorCode, VerifyVerdict } from '../src/source-fingerprint.ts'
import { SourceFingerprint as makeSourceFingerprint } from '../src/shared/types.ts'

const execFileAsync = promisify(execFile)

/** Temp roots acquired by this file, drained to quiescence by afterEach. */
const tempRoots: string[] = []

interface GitFixture {
  readonly root: string
  readonly git: (args: readonly string[]) => Promise<string>
  readonly write: (relPath: string, content: string) => Promise<void>
}

afterEach(async () => {
  const roots = [...tempRoots]
  tempRoots.length = 0
  // Windows releases child/file handles asynchronously: fs.rm's bounded
  // linear backoff (20 × 25 ms ≈ 5.25 s worst case) is sized to the observed
  // EPERM/EBUSY contention, and its resolution is the completion signal —
  // no sleeps.
  await Promise.all(roots.map(root => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })))
})

/** Acquire and register one unique temporary root before any other work. */
async function createTempRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-sfp-'))
  tempRoots.push(root)
  return root
}

/**
 * Create a real repository with local commit identity and a fully isolated
 * git config: global/system config are redirected to an empty file in the
 * temp root via per-invocation env, so developer-machine config (autocrlf,
 * hooks, default branch) cannot leak in and `process.env` is never mutated.
 * The repository lives in a `repo/` subdirectory of the registered root so
 * the isolated config file itself is outside the repository and can never be
 * staged by `add -A`.
 */
async function createRepository(): Promise<GitFixture> {
  const tempRoot = await createTempRoot()
  const root = join(tempRoot, 'repo')
  const isolatedConfig = join(tempRoot, 'isolated-git.config')
  await writeFile(isolatedConfig, '', 'utf8')
  const gitEnv = {
    ...process.env,
    GIT_CONFIG_GLOBAL: isolatedConfig,
    GIT_CONFIG_SYSTEM: isolatedConfig,
    LC_ALL: 'C',
  }
  const git = async (args: readonly string[]): Promise<string> => {
    const { stdout } = await execFileAsync('git', ['-C', root, ...args], {
      encoding: 'utf8',
      windowsHide: true,
      env: gitEnv,
    })
    return stdout
  }
  const write = async (relPath: string, content: string): Promise<void> => {
    const target = join(root, relPath)
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, content, 'utf8')
  }
  await mkdir(root, { recursive: true })
  await git(['init', '--quiet', '--initial-branch=main'])
  await git(['config', 'user.name', 'DevFrame Fingerprint Test'])
  await git(['config', 'user.email', 'devframe-fingerprint@example.test'])
  return { root, git, write }
}

/** Stage everything and commit, returning the fresh commit id. */
async function commitAll(fixture: GitFixture, message: string): Promise<string> {
  await fixture.git(['add', '-A'])
  await fixture.git(['commit', '--quiet', '--allow-empty', '-m', message])
  return (await fixture.git(['rev-parse', 'HEAD'])).trim()
}

/** Assert the computation fails with the expected code and return the error. */
async function expectErrorCode(
  computation: Promise<unknown>,
  code: SourceFingerprintErrorCode,
): Promise<SourceFingerprintError> {
  const caught = await computation.then(
    () => {
      throw new Error(`expected the computation to fail with ${code}`)
    },
    (caught: unknown) => caught,
  )
  expect(caught).toBeInstanceOf(SourceFingerprintError)
  const error = caught as SourceFingerprintError
  expect(error.code).toBe(code)
  return error
}

/** Assert the verification rejects the record and return the mismatch arm. */
async function expectMismatch(verification: Promise<VerifyVerdict>): Promise<Extract<VerifyVerdict, { kind: 'mismatch' }>> {
  const verdict = await verification
  expect(verdict.kind).toBe('mismatch')
  if (verdict.kind !== 'mismatch') throw new Error('expected a mismatch verdict')
  return verdict
}

describe('computeSourceFingerprint', { timeout: 30_000 }, () => {
  // Every case is backed by real git process creation; the per-test budget
  // stays above the runner default to absorb lane contention on that cost.

  it('returns a deterministic branded fingerprint for a committed repository', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')

    const first = await computeSourceFingerprint({ worktreePath: fixture.root })
    const second = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(second).toEqual(first)
    expect(first.algorithm).toBe('v1')
    expect(first.fingerprint).toBe(`dsh-source-fp-v1-${first.headCommit}-${first.trackedStateHash}`)
    expect(first.headCommit).toMatch(/^[0-9a-f]{40,64}$/)
    expect(first.trackedStateHash).toMatch(/^[0-9a-f]{64}$/)
    expect(first.trackedEntryCount).toBeGreaterThan(0)
  })

  it('changes when a tracked file is staged without committing, with HEAD unchanged', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    await fixture.write('src/extra.ts', 'export const extra = true\n')
    await fixture.git(['add', 'src/extra.ts'])
    const staged = await computeSourceFingerprint({ worktreePath: fixture.root })

    // Negative control for change detection: the HEAD commit is identical, so
    // an implementation hashing only the HEAD commit (no index state) would
    // return the baseline value here and fail the assertion below.
    expect(staged.headCommit).toBe(baseline.headCommit)
    expect(staged.fingerprint).not.toBe(baseline.fingerprint)
  })

  it('changes when a tracked edit is committed', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    await fixture.write('src/main.ts', 'export const changed = true\n')
    await commitAll(fixture, 'edit')
    const committed = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(committed.fingerprint).not.toBe(baseline.fingerprint)
    expect(committed.headCommit).not.toBe(baseline.headCommit)
    expect(committed.trackedStateHash).not.toBe(baseline.trackedStateHash)
  })

  it('ignores worktree mtime changes when the tracked content is identical', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    // Rewrite identical bytes for a fresh mtime; never restored (an mtime
    // write-back would assume an NTFS-tick-lossless round trip). The expected
    // value is the freshly computed baseline, and the fingerprint reads the
    // index, so the worktree stat change cannot reach it.
    await fixture.write('src/main.ts', 'export {}\n')
    const rewritten = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(rewritten.fingerprint).toBe(baseline.fingerprint)
  })

  it('ignores unstaged worktree line-ending rewrites', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    // CRLF rewrite stays unstaged: the index still holds the committed blob,
    // on every platform, so the worktree line-ending state is invisible.
    await writeFile(join(fixture.root, 'src', 'main.ts'), 'export {}\r\n', 'utf8')
    const rewritten = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(rewritten.fingerprint).toBe(baseline.fingerprint)
  })

  it('ignores untracked files (registered boundary)', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    // Registered boundary (fprecompute-design.md): a purely untracked file is
    // invisible to the HEAD+index fingerprint until it is staged or committed.
    await fixture.write('scratch/untracked.txt', 'unreviewed change\n')
    const withUntracked = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(withUntracked.fingerprint).toBe(baseline.fingerprint)
  })

  it('evaluates a nested directory as its containing worktree', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    const nested = await computeSourceFingerprint({ worktreePath: join(fixture.root, 'src') })

    expect(nested).toEqual(baseline)
  })

  it('rejects a directory outside any git worktree', async () => {
    const root = await createTempRoot()

    const error = await expectErrorCode(
      computeSourceFingerprint({ worktreePath: root }),
      'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    )

    expect(error.message).toContain('not inside a git worktree')
  })

  it('rejects a missing directory and a non-directory path', async () => {
    const root = await createTempRoot()
    const filePath = join(root, 'a-file.txt')
    await writeFile(filePath, 'x', 'utf8')

    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: join(root, 'missing-dir') }),
      'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    )
    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: filePath }),
      'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    )
  })

  it('rejects a bare repository', async () => {
    const root = await createTempRoot()
    const bare = join(root, 'bare.git')
    await execFileAsync('git', ['init', '--quiet', '--bare', '--initial-branch=main', bare], { windowsHide: true })

    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: bare }),
      'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    )
  })

  it('rejects a repository with no commits (unborn HEAD)', async () => {
    const fixture = await createRepository()

    const error = await expectErrorCode(
      computeSourceFingerprint({ worktreePath: fixture.root }),
      'SOURCE_FINGERPRINT_NO_COMMIT',
    )

    expect(error.message).toContain('unborn HEAD')
  })

  it('reports an unavailable git executable as a structured error', async () => {
    const root = await createTempRoot()

    const error = await expectErrorCode(
      computeSourceFingerprint({ worktreePath: root, gitCommand: 'dsh-sfp-no-such-git' }),
      'SOURCE_FINGERPRINT_GIT_UNAVAILABLE',
    )

    expect(error.message).toContain('dsh-sfp-no-such-git')
  })

  it('reports a git command that runs but is not git as a structured failure', async () => {
    const root = await createTempRoot()

    // process.execPath accepts the spawn but rejects the git argv, so the
    // engine must classify the generic failure instead of the discovery
    // message — the injection keeps process-global PATH state untouched.
    const error = await expectErrorCode(
      computeSourceFingerprint({ worktreePath: root, gitCommand: process.execPath }),
      'SOURCE_FINGERPRINT_GIT_FAILED',
    )

    expect(error.message).toContain('failed with code')
    expect(error.message).toContain('rev-parse')
  })

  it('reports a failing git command as a structured error', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')

    // Corrupting the index keeps repository discovery and HEAD resolution
    // working while `ls-files` fails, so the failure surfaces from the
    // state-collection call, not from repository classification.
    await writeFile(join(fixture.root, '.git', 'index'), 'dsh corrupt index probe\n', 'utf8')

    const error = await expectErrorCode(
      computeSourceFingerprint({ worktreePath: fixture.root }),
      'SOURCE_FINGERPRINT_GIT_FAILED',
    )

    expect(error.message).toContain('ls-files')
    expect(error.message).toContain('failed with code')
  })

  it('reports an exceeded output cap as a structured failure', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')

    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: fixture.root, maxOutputBytes: 1 }),
      'SOURCE_FINGERPRINT_GIT_FAILED',
    )
  })

  it('rejects invalid request input before touching git', async () => {
    const root = await createTempRoot()

    await expectErrorCode(computeSourceFingerprint({ worktreePath: '' }), 'SOURCE_FINGERPRINT_INVALID_REQUEST')
    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: 'relative/path' }),
      'SOURCE_FINGERPRINT_INVALID_REQUEST',
    )
    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: root, gitCommand: '' }),
      'SOURCE_FINGERPRINT_INVALID_REQUEST',
    )
    await expectErrorCode(
      computeSourceFingerprint({ worktreePath: root, maxOutputBytes: 0 }),
      'SOURCE_FINGERPRINT_INVALID_REQUEST',
    )
  })
})

describe('verifySourceFingerprint', { timeout: 30_000 }, () => {
  // Same real-git fixture discipline as the engine suite above. The verify
  // face has no gitCommand injection seam (it verifies the production face),
  // so its pass-through evidence is the codes reachable from real fixtures;
  // GIT_UNAVAILABLE/GIT_FAILED stay covered at the engine face.

  it('matches when the recorded fingerprint equals the fresh computation of the same tree', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const recorded = (await computeSourceFingerprint({ worktreePath: fixture.root })).fingerprint

    const verdict = await verifySourceFingerprint(fixture.root, recorded)

    expect(verdict).toEqual({ kind: 'match', fingerprint: recorded })
  })

  it('reports both sides when a tracked change is committed after the record', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    await fixture.write('src/added.ts', 'export const added = true\n')
    await commitAll(fixture, 'after record')
    const verdict = await expectMismatch(verifySourceFingerprint(fixture.root, baseline.fingerprint))

    // Dual-value presentation: the recorded side stays the stale claim, the
    // computed side carries the fresh full digest, and the two diverge.
    expect(verdict.recordedFingerprint).toBe(baseline.fingerprint)
    expect(verdict.computed.fingerprint).not.toBe(baseline.fingerprint)
    expect(verdict.computed.headCommit).not.toBe(baseline.headCommit)
  })

  it('reports a mismatch when a new file is staged without committing', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    await fixture.write('src/staged.ts', 'export const staged = true\n')
    await fixture.git(['add', 'src/staged.ts'])
    const verdict = await expectMismatch(verifySourceFingerprint(fixture.root, baseline.fingerprint))

    // Negative control: only the index moved (HEAD unchanged), so an
    // implementation ignoring index state would return a match here.
    expect(verdict.recordedFingerprint).toBe(baseline.fingerprint)
    expect(verdict.computed.headCommit).toBe(baseline.headCommit)
    expect(verdict.computed.fingerprint).not.toBe(baseline.fingerprint)
  })

  it('passes engine errors through with their original codes and shape', async () => {
    const root = await createTempRoot()
    const recorded = makeSourceFingerprint('dsh-source-fp-v1-verify-probe')

    // Non-repository directory: the engine's own classification, not a wrap.
    await expect(verifySourceFingerprint(root, recorded)).rejects.toThrow(SourceFingerprintError)
    await expect(verifySourceFingerprint(root, recorded)).rejects.toMatchObject({
      code: 'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    })

    // Repository with an unborn HEAD: NO_COMMIT bubbles unchanged.
    const unborn = await createRepository()
    await expect(verifySourceFingerprint(unborn.root, recorded)).rejects.toMatchObject({
      code: 'SOURCE_FINGERPRINT_NO_COMMIT',
    })

    // Pre-validation input shape: INVALID_REQUEST bubbles unchanged too.
    await expect(verifySourceFingerprint('relative/path', recorded)).rejects.toMatchObject({
      code: 'SOURCE_FINGERPRINT_INVALID_REQUEST',
    })
  })

  it('still matches when only untracked files appeared (untracked-invisible boundary)', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const recorded = (await computeSourceFingerprint({ worktreePath: fixture.root })).fingerprint

    // Registered boundary (fprecompute-design.md): a purely untracked file is
    // invisible to the HEAD+index fingerprint, so verify passes until the
    // change is staged or committed — the same edge the engine suite pins.
    await fixture.write('scratch/untracked.txt', 'unreviewed change\n')
    const verdict = await verifySourceFingerprint(fixture.root, recorded)

    expect(verdict).toEqual({ kind: 'match', fingerprint: recorded })
  })
})
