/**
 * Source fingerprints over real Git repositories in private temporary roots.
 * A Node executable fixture supplies hanging Git calls with socket readiness
 * to verify cancellation, deadlines, environment isolation, and child exit.
 * @module dsh-experimental-devframe/tests/source-fingerprint
 */

import { execFile } from 'node:child_process'
import { chmod, mkdir, mkdtemp, rm, symlink, unlink, utimes, writeFile } from 'node:fs/promises'
import * as filesystem from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { createServer, type Socket } from 'node:net'
import { pathToFileURL } from 'node:url'
import { dirname, join } from 'node:path'
import { promisify } from 'node:util'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { computeSourceFingerprint, SourceFingerprintError, verifySourceFingerprint } from '../src/source-fingerprint.ts'
import type { SourceFingerprintErrorCode, VerifyVerdict } from '../src/source-fingerprint.ts'
import { SourceFingerprint as makeSourceFingerprint } from '../src/shared/types.ts'

vi.mock('node:fs/promises', async importOriginal => ({
  ...await importOriginal<typeof import('node:fs/promises')>(),
}))

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
    expect(first.algorithm).toBe('v2')
    expect(first.fingerprint).toBe(`dsh-source-fp-v2-${first.headCommit}-${first.stateHash}`)
    expect(first.headCommit).toMatch(/^[0-9a-f]{40,64}$/)
    expect(first.stateHash).toMatch(/^[0-9a-f]{64}$/)
    expect(first.entryCount).toBeGreaterThan(0)
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
    expect(committed.stateHash).not.toBe(baseline.stateHash)
  })

  it('ignores worktree mtime changes when the tracked content is identical', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    // Rewrite identical bytes for a fresh mtime; never restored (an mtime
    // write-back would assume an NTFS-tick-lossless round trip). The expected
    // value is the freshly computed baseline; timestamps are not hash input.
    await fixture.write('src/main.ts', 'export {}\n')
    const rewritten = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(rewritten.fingerprint).toBe(baseline.fingerprint)
  })

  it('detects unstaged worktree line-ending rewrites', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    // The index stays unchanged; the bytes read by checks and review do not.
    await writeFile(join(fixture.root, 'src', 'main.ts'), 'export {}\r\n', 'utf8')
    const rewritten = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(rewritten.fingerprint).not.toBe(baseline.fingerprint)
  })

  it('includes nonignored untracked files', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })

    await fixture.write('scratch/untracked.txt', 'unreviewed change\n')
    const withUntracked = await computeSourceFingerprint({ worktreePath: fixture.root })

    expect(withUntracked.fingerprint).not.toBe(baseline.fingerprint)
  })

  it('detects same-size tracked edits and tracked deletions without changing HEAD or index', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export const value = 1\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })
    const index = await fixture.git(['ls-files', '-s'])
    await fixture.write('src/main.ts', 'export const value = 2\n')
    const edited = await computeSourceFingerprint({ worktreePath: fixture.root })
    expect(edited.headCommit).toBe(baseline.headCommit)
    expect(edited.fingerprint).not.toBe(baseline.fingerprint)
    await unlink(join(fixture.root, 'src/main.ts'))
    const deleted = await computeSourceFingerprint({ worktreePath: fixture.root })
    expect(deleted.fingerprint).not.toBe(edited.fingerprint)
    expect(deleted.fingerprint).not.toBe(baseline.fingerprint)
    expect(deleted.entryCount).toBe(1)
    expect(await fixture.git(['ls-files', '-s'])).toBe(index)
  })

  it('detects edits to existing untracked bytes even when size and mtime are restored', async () => {
    const fixture = await createRepository()
    await commitAll(fixture, 'initial')
    await fixture.write('source input 中文.txt', 'before\0bytes')
    const path = join(fixture.root, 'source input 中文.txt')
    const metadata = await filesystem.stat(path)
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })
    await fixture.write('source input 中文.txt', 'edited\0bytes')
    await utimes(path, metadata.atime, metadata.mtime)
    expect((await verifySourceFingerprint(fixture.root, baseline.fingerprint)).kind).toBe('mismatch')
    await unlink(path)
    expect((await verifySourceFingerprint(fixture.root, baseline.fingerprint)).kind).toBe('mismatch')
  })

  it('excludes ignored untracked inputs and empty directories', async () => {
    const fixture = await createRepository()
    await fixture.write('.gitignore', 'generated/\n')
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })
    await fixture.write('generated/cache.txt', 'not source')
    await mkdir(join(fixture.root, 'empty'))
    expect(await computeSourceFingerprint({ worktreePath: fixture.root })).toEqual(baseline)
  })

  it('hashes a symlink target without reading the external referent', async ({ skip }) => {
    const fixture = await createRepository()
    await commitAll(fixture, 'initial')
    const outside = join(await createTempRoot(), 'outside.txt')
    await writeFile(outside, 'outside one')
    const link = join(fixture.root, 'source-link')
    try { await symlink(outside, link, 'file') } catch (error) {
      if (process.platform === 'win32' && (error as NodeJS.ErrnoException).code === 'EPERM') {
        skip('Windows host does not grant symbolic-link creation')
        return
      }
      throw error
    }
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })
    await writeFile(outside, 'outside two')
    expect(await computeSourceFingerprint({ worktreePath: fixture.root })).toEqual(baseline)
    await unlink(link)
    await symlink(outside + '-missing', link, 'file')
    expect((await verifySourceFingerprint(fixture.root, baseline.fingerprint)).kind).toBe('mismatch')
  })

  it('refuses a tracked parent replaced with an external directory link', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'reviewed')
    await commitAll(fixture, 'initial')
    const outside = await createTempRoot()
    await writeFile(join(outside, 'main.ts'), 'external')
    await unlink(join(fixture.root, 'src/main.ts'))
    await filesystem.rmdir(join(fixture.root, 'src'))
    const link = join(fixture.root, 'src')
    await symlink(outside, link, process.platform === 'win32' ? 'junction' : 'dir')
    try {
      await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
    } finally { await unlink(link) }
  })

  it('refuses gitlink entries even when no submodule directory is checked out', async () => {
    const fixture = await createRepository()
    const head = await commitAll(fixture, 'initial')
    await fixture.git(['update-index', '--add', '--cacheinfo', '160000,' + head + ',module'])
    await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
  })

  it('refuses a tracked file replaced by an unsupported directory', async () => {
    const fixture = await createRepository()
    await fixture.write('source', 'reviewed')
    await commitAll(fixture, 'initial')
    await unlink(join(fixture.root, 'source'))
    await mkdir(join(fixture.root, 'source'))
    await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
  })

  it('bounds the aggregate contents of individually small files', async () => {
    const fixture = await createRepository()
    await commitAll(fixture, 'initial')
    await fixture.write('a', 'x'.repeat(3000))
    await fixture.write('b', 'y'.repeat(3000))
    await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root, maxSourceBytes: 4096 }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
    await expect(computeSourceFingerprint({ worktreePath: fixture.root, maxOutputBytes: 4096 })).resolves.toMatchObject({ entryCount: 2 })
  })

  it('closes an opened file when its request is cancelled before streaming', async () => {
    const fixture = await createRepository()
    await fixture.write('source', 'reviewed')
    await commitAll(fixture, 'initial')
    const abort = new AbortController()
    const original = filesystem.open
    let handle: Awaited<ReturnType<typeof filesystem.open>> | undefined
    const spy = vi.spyOn(filesystem, 'open').mockImplementation(async (...args) => {
      const opened = await original(...args)
      if (args[0] === join(fixture.root, 'source')) { handle = opened; abort.abort() }
      return opened
    })
    try {
      await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root, signal: abort.signal }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
      expect(handle?.fd).toBe(-1)
    } finally { spy.mockRestore() }
  })

  it('rejects cancellation during the final source observation', async () => {
    const fixture = await createRepository()
    await fixture.write('source', 'reviewed')
    await commitAll(fixture, 'initial')
    const abort = new AbortController()
    const original = filesystem.lstat
    let observations = 0
    const spy = vi.spyOn(filesystem, 'lstat').mockImplementation(async (...args) => {
      const result = await original(...args)
      if (args[0] === join(fixture.root, 'source') && ++observations === 3) abort.abort()
      return result
    })
    try {
      await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root, signal: abort.signal }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
      expect(observations).toBe(3)
    } finally { spy.mockRestore() }
  })

  it('cancels an active file stream and closes its descriptor', async () => {
    const fixture = await createRepository()
    await fixture.write('source', 'x'.repeat(256 * 1024))
    await commitAll(fixture, 'initial')
    const abort = new AbortController()
    const original = filesystem.open
    let handle: Awaited<ReturnType<typeof filesystem.open>> | undefined
    let streamed = false
    const spy = vi.spyOn(filesystem, 'open').mockImplementation(async (...args) => {
      const opened = await original(...args)
      if (args[0] === join(fixture.root, 'source')) {
        handle = opened
        const create = opened.createReadStream.bind(opened)
        vi.spyOn(opened, 'createReadStream').mockImplementation((options) => {
          const stream = create(options)
          stream.once('data', () => { streamed = true; abort.abort() })
          return stream
        })
      }
      return opened
    })
    try {
      await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root, signal: abort.signal }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
      expect(streamed).toBe(true)
      expect(handle?.fd).toBe(-1)
    } finally { spy.mockRestore() }
  })

  it('rejects a file changed between inventory observation and opening and closes its handle', async () => {
    const fixture = await createRepository()
    await fixture.write('source', 'reviewed')
    await commitAll(fixture, 'initial')
    const original = filesystem.open
    let handle: Awaited<ReturnType<typeof filesystem.open>> | undefined
    const spy = vi.spyOn(filesystem, 'open').mockImplementation(async (...args) => {
      const opened = await original(...args)
      if (args[0] === join(fixture.root, 'source')) { handle = opened; await fixture.write('source', 'changed while opening') }
      return opened
    })
    try {
      await expectErrorCode(computeSourceFingerprint({ worktreePath: fixture.root }), 'SOURCE_FINGERPRINT_SOURCE_FAILED')
      expect(handle?.fd).toBe(-1)
    } finally { spy.mockRestore() }
  })

  it.skipIf(process.platform === 'win32')('includes executable-bit changes on POSIX filesystems', async () => {
    const fixture = await createRepository()
    await fixture.write('source', 'reviewed')
    await chmod(join(fixture.root, 'source'), 0o644)
    await commitAll(fixture, 'initial')
    const baseline = await computeSourceFingerprint({ worktreePath: fixture.root })
    await chmod(join(fixture.root, 'source'), 0o755)
    expect((await verifySourceFingerprint(fixture.root, baseline.fingerprint)).kind).toBe('mismatch')
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
    for (const maxSourceBytes of [0, -1, 1.5, Number.POSITIVE_INFINITY]) {
      await expectErrorCode(computeSourceFingerprint({ worktreePath: root, maxSourceBytes }), 'SOURCE_FINGERPRINT_INVALID_REQUEST')
    }
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
    const recorded = makeSourceFingerprint('dsh-source-fp-v2-verify-probe')

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

  it('rejects when an untracked file appears after the recorded snapshot', async () => {
    const fixture = await createRepository()
    await fixture.write('src/main.ts', 'export {}\n')
    await commitAll(fixture, 'initial')
    const recorded = (await computeSourceFingerprint({ worktreePath: fixture.root })).fingerprint

    await fixture.write('scratch/untracked.txt', 'unreviewed change\n')
    const verdict = await verifySourceFingerprint(fixture.root, recorded)

    expect(verdict.kind).toBe('mismatch')
  })
})


describe('bounded fingerprint Git children', () => {
  it.each([0, -1, 1.5, Number.POSITIVE_INFINITY])('rejects invalid timeout %s before spawning', async (timeoutMs) => {
    await expect(computeSourceFingerprint({ worktreePath: await createTempRoot(), timeoutMs }))
      .rejects.toMatchObject({ code: 'SOURCE_FINGERPRINT_INVALID_REQUEST' })
  })

  // The timeout case includes native Node startup and an explicit socket handshake.
  it.each(['probe', 'head', 'listing', 'timeout'] as const)('settles a hung %s child only after exit', async (stage) => {
    const root = await createTempRoot()
    const script = join(root, 'git-fixture.mjs')
    const ready = Promise.withResolvers<number>()
    const sockets = new Set<Socket>()
    const server = createServer((socket) => {
      sockets.add(socket)
      // Killing the owned child resets its readiness socket on Windows.
      socket.on('error', (error: NodeJS.ErrnoException) => {
        if (error.code !== 'ECONNRESET') ready.reject(error)
      })
      socket.once('close', () => sockets.delete(socket))
      socket.once('data', (data) => {
        const value: unknown = JSON.parse(data.toString())
        if (typeof value !== 'object' || value === null || !('pid' in value) || typeof value.pid !== 'number'
          || !('clean' in value) || value.clean !== true) {
          ready.reject(new Error('Git child did not receive an isolated environment'))
        } else ready.resolve(value.pid)
      })
    })
    const abort = new AbortController()
    let pending: Promise<unknown> | undefined
    try {
      await new Promise<void>((resolve, reject) => {
        server.once('error', reject)
        server.listen(0, '127.0.0.1', () => { server.removeListener('error', reject); resolve() })
      })
      const address = server.address()
      if (address === null || typeof address === 'string') throw new Error('Missing fixture listener')
      await writeFile(script, [
        "import { connect } from 'node:net'",
        "import { writeSync } from 'node:fs'",
        "const stage = process.argv.includes('--is-inside-work-tree') ? 'probe' : process.argv[1]?.endsWith('ls-files') ? 'listing' : 'head'",
        'if (stage !== ' + JSON.stringify(stage === 'timeout' ? 'listing' : stage) + ') {',
        "  writeSync(1, stage === 'probe' ? 'true\\n' : 'a'.repeat(40) + '\\n'); process.exit(0)",
        '}',
        'const socket = connect(' + String(address.port) + ", '127.0.0.1', () => socket.write(JSON.stringify({ pid: process.pid, clean: process.env.DSH_FIXTURE_SECRET === undefined && process.env.GIT_INDEX_FILE === undefined })))",
        'await new Promise(() => {})',
      ].join('\n'))
      vi.stubEnv('NODE_OPTIONS', '--import=' + JSON.stringify(pathToFileURL(script).href))
      vi.stubEnv('DSH_FIXTURE_SECRET', 'fixture-only')
      vi.stubEnv('GIT_INDEX_FILE', join(root, 'must-not-be-used'))
      pending = computeSourceFingerprint({ worktreePath: root, gitCommand: process.execPath,
        signal: abort.signal, ...(stage === 'timeout' ? { timeoutMs: 8_000 } : {}) })
      const outcome = pending.then(value => ({ value }), (error: unknown) => ({ error }))
      const pid = await Promise.race([ready.promise, outcome.then((result) => { throw new Error('Child settled before readiness: ' + ('error' in result ? String(result.error) : 'success')) })])
      if (stage !== 'timeout') abort.abort()
      expect(await outcome).toMatchObject({ error: { code: 'SOURCE_FINGERPRINT_GIT_FAILED' } })
      expect(() => process.kill(pid, 0)).toThrow()
    } finally {
      abort.abort()
      if (pending !== undefined) await Promise.allSettled([pending])
      for (const socket of sockets) socket.destroy()
      try {
        if (server.listening) await new Promise<void>((resolve, reject) => server.close((error) => {
          if (error) reject(error)
          else resolve()
        }))
      } finally {
        vi.unstubAllEnvs()
      }
    }
  }, 30_000)
})
