/**
 * Read-only source evidence over HEAD, index records, and actual tracked and
 * nonignored untracked files. Raw contents, repository-relative paths, entry
 * types, and executable bits contribute; timestamps do not. Symlinks contribute
 * only their link target. Missing tracked paths contribute deletion records.
 * Ignored untracked paths are outside this source scope. Submodules, special
 * files, non-UTF-8 paths, and observed concurrent changes fail closed. Callers
 * retain writer ownership through the operation that consumes the fingerprint.
 * @module @deepseek-ai/dsh-experimental-devframe/source-fingerprint
 */

import { execFile } from 'node:child_process'
import { createHash } from 'node:crypto'
import { constants, type Stats } from 'node:fs'
import { lstat, open, readlink, realpath, stat } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import { promisify } from 'node:util'
import { SourceFingerprint as makeSourceFingerprint } from './shared/types.ts'
import type { SourceFingerprint } from './shared/types.ts'

const execFileAsync = promisify(execFile)

/** Stable machine-routable classifications emitted by this engine. */
export type SourceFingerprintErrorCode =
  | 'SOURCE_FINGERPRINT_INVALID_REQUEST'
  | 'SOURCE_FINGERPRINT_NOT_A_WORKTREE'
  | 'SOURCE_FINGERPRINT_NO_COMMIT'
  | 'SOURCE_FINGERPRINT_GIT_UNAVAILABLE'
  | 'SOURCE_FINGERPRINT_GIT_FAILED'
  | 'SOURCE_FINGERPRINT_SOURCE_FAILED'

/** Structured failure from fingerprint computation; never a silent fallback. */
export class SourceFingerprintError extends Error {
  /** Stable machine-routable classification of this failure. */
  readonly code: SourceFingerprintErrorCode

  /**
   * @param message - human-readable failure reason with git diagnostics where available.
   * @param code - stable machine-routable error classification.
   * @param options - standard Error options carrying the underlying cause.
   */
  constructor(message: string, code: SourceFingerprintErrorCode, options?: ErrorOptions) {
    super(message, options)
    this.name = 'SourceFingerprintError'
    this.code = code
  }
}

/** Input for one fingerprint computation. */
export interface SourceFingerprintRequest {
  /**
   * Absolute path to any directory inside the target git worktree (a nested
   * subdirectory is evaluated as its containing worktree, because the index
   * is repository-wide). A `WorkspaceId` → path mapping belongs to the caller.
   */
  readonly worktreePath: string
  /**
   * git executable name or path to run; defaults to `'git'`. Injection seam
   * for testability (an unavailable git is asserted through a nonexistent
   * command name) without mutating process-global PATH state.
   */
  readonly gitCommand?: string
  /**
   * Per-Git-output collection cap in bytes; defaults to 64 MiB.
   * Exceeding it fails rather than truncating fingerprint input.
   */
  readonly maxOutputBytes?: number
  /** Optional positive aggregate file-content and symlink-target byte cap; omitted means no total byte cap. */
  readonly maxSourceBytes?: number
  /** Cancel Git children and file streams, closing owned resources before settling. */
  readonly signal?: AbortSignal
  /** Positive deadline in milliseconds per Git child and for the whole file-reading phase. */
  readonly timeoutMs?: number
}

/** One computed fingerprint plus the human-readable facts behind it. */
export interface ComputedSourceFingerprint {
  /**
   * Branded fingerprint value `dsh-source-fp-v2-<headCommit>-<stateHash>`;
   * fits every `ProjectWorkBinding.sourceFingerprint` consumer. Equal worktree
   * contents, paths, types, index state and executable bits produce equal values.
   */
  readonly fingerprint: SourceFingerprint
  /** Resolved HEAD commit id (hex), as reported by `rev-parse --verify`. */
  readonly headCommit: string
  /** sha256 over framed index records and actual source entries. */
  readonly stateHash: string
  /** Number of distinct tracked and nonignored untracked paths, including tracked deletions. */
  readonly entryCount: number
  /**
   * Normalization algorithm generation. Moves together with the
   * {@link FINGERPRINT_PREFIX} value generation: a normalization change is a
   * fingerprint value change by construction.
   */
  readonly algorithm: 'v2'
}

/** Pass arm of a verify verdict: the recorded fingerprint was re-derived from the worktree. */
export interface SourceFingerprintMatch {
  /** Discriminant tag of the discriminated {@link VerifyVerdict} union. */
  readonly kind: 'match'
  /**
   * The verified value — equal to the recorded fingerprint and to the fresh
   * computation, so it can stand in for either in downstream evidence.
   */
  readonly fingerprint: SourceFingerprint
}

/** Reject arm of a verify verdict: the fresh computation diverged from the record. */
export interface SourceFingerprintMismatch {
  /** Discriminant tag of the discriminated {@link VerifyVerdict} union. */
  readonly kind: 'mismatch'
  /**
   * The recorded value exactly as passed in — evidence of what was claimed,
   * never a description of the current worktree state; the trustworthy side
   * of this arm is {@link SourceFingerprintMismatch.computed}.
   */
  readonly recordedFingerprint: SourceFingerprint
  /** Fresh computation read from the worktree at verify time; `computed.fingerprint` is the current value. */
  readonly computed: ComputedSourceFingerprint
}

/** Discriminated union returned by {@link verifySourceFingerprint}. */
export type VerifyVerdict = SourceFingerprintMatch | SourceFingerprintMismatch

const DEFAULT_GIT_COMMAND = 'git'
const DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
const FINGERPRINT_PREFIX = 'dsh-source-fp-v2'
const HEAD_HEX_PATTERN = /^[0-9a-f]{40,64}$/
const NOT_A_REPOSITORY_MESSAGE = /not a git repository/i

interface GitSuccess {
  readonly ok: true
  readonly stdout: Buffer
  readonly stderr: string
}

interface GitFailure {
  readonly ok: false
  readonly stdout: Buffer
  readonly stderr: string
  /** The execFile-layer rejection; `code` is a string for spawn-level failures and the exit number otherwise. */
  readonly error: unknown
}

type GitRun = GitSuccess | GitFailure

/**
 * Compute the source worktree fingerprint for one git worktree directory.
 * Read-only: no git state is mutated. Fail-loud on every unusable input or
 * git failure — there is no fallback value.
 * @param request - worktree directory, optional Git command, output cap, cancellation, and per-child timeout.
 * @returns the branded fingerprint with its readable digest fields.
 * @throws {@link SourceFingerprintError} with one of the documented {@link SourceFingerprintErrorCode} values.
 */
export async function computeSourceFingerprint(
  request: SourceFingerprintRequest,
): Promise<ComputedSourceFingerprint> {
  const worktreePath = request.worktreePath
  if (worktreePath.trim().length === 0) {
    throw new SourceFingerprintError('worktreePath must be a non-empty string', 'SOURCE_FINGERPRINT_INVALID_REQUEST')
  }
  if (!isAbsolute(worktreePath)) {
    throw new SourceFingerprintError(
      `worktreePath must be absolute, received "${worktreePath}"`,
      'SOURCE_FINGERPRINT_INVALID_REQUEST',
    )
  }
  const gitCommand = request.gitCommand ?? DEFAULT_GIT_COMMAND
  if (gitCommand.trim().length === 0) {
    throw new SourceFingerprintError('gitCommand must be a non-empty string', 'SOURCE_FINGERPRINT_INVALID_REQUEST')
  }
  const maxOutputBytes = request.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES
  if (!Number.isSafeInteger(maxOutputBytes) || maxOutputBytes < 1) {
    throw new SourceFingerprintError(
      'maxOutputBytes must be a positive safe integer',
      'SOURCE_FINGERPRINT_INVALID_REQUEST',
    )
  }

  if (request.timeoutMs !== undefined && (!Number.isSafeInteger(request.timeoutMs) || request.timeoutMs < 1)) {
    throw new SourceFingerprintError('timeoutMs must be a positive safe integer', 'SOURCE_FINGERPRINT_INVALID_REQUEST')
  }
  if (request.maxSourceBytes !== undefined && (!Number.isSafeInteger(request.maxSourceBytes) || request.maxSourceBytes < 1)) {
    throw new SourceFingerprintError('maxSourceBytes must be a positive safe integer', 'SOURCE_FINGERPRINT_INVALID_REQUEST')
  }

  const directory = await stat(worktreePath).catch(() => undefined)
  if (directory === undefined || !directory.isDirectory()) {
    throw new SourceFingerprintError(
      `"${worktreePath}" is not an existing directory`,
      'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    )
  }

  const probeArgs = ['rev-parse', '--is-inside-work-tree'] as const
  const probe = await runGit(gitCommand, worktreePath, probeArgs, maxOutputBytes, request)
  if (!probe.ok) {
    throw classifyFailure(gitCommand, probeArgs, probe, `"${worktreePath}" is not inside a git worktree`)
  }
  const insideWorkTree = probe.stdout.toString('utf8').trim()
  if (insideWorkTree !== 'true') {
    throw new SourceFingerprintError(
      `git reports "${worktreePath}" is not inside a work tree (bare repository or git directory)`,
      'SOURCE_FINGERPRINT_NOT_A_WORKTREE',
    )
  }

  const headArgs = ['rev-parse', '--verify', '--quiet', 'HEAD'] as const
  const head = await runGit(gitCommand, worktreePath, headArgs, maxOutputBytes, request)
  if (!head.ok) throw classifyHeadFailure(worktreePath, gitCommand, headArgs, head)
  const headCommit = head.stdout.toString('utf8').trim()
  if (!HEAD_HEX_PATTERN.test(headCommit)) {
    throw new SourceFingerprintError(
      `git rev-parse returned an unexpected HEAD value "${headCommit}"`,
      'SOURCE_FINGERPRINT_GIT_FAILED',
    )
  }

  // `:/` scopes the listing to the whole repository regardless of the input
  // directory, and `--full-name` prints repository-relative paths, so the
  // byte stream — and therefore the fingerprint — is identical from any
  // entry point inside the same worktree.
  const listingArgs = ['ls-files', '-s', '-z', '--full-name', '--', ':/'] as const
  const listing = await runGit(gitCommand, worktreePath, listingArgs, maxOutputBytes, request)
  if (!listing.ok) {
    throw classifyFailure(gitCommand, listingArgs, listing)
  }
  const topArgs = ['rev-parse', '--show-toplevel'] as const
  const top = await runGit(gitCommand, worktreePath, topArgs, maxOutputBytes, request)
  if (!top.ok) throw classifyFailure(gitCommand, topArgs, top)
  const root = await realpath(top.stdout.toString('utf8').replace(/\r?\n$/, ''))
  const pathsArgs = ['ls-files', '--cached', '--others', '--exclude-standard', '-z', '--full-name', '--', ':/'] as const
  const paths = await runGit(gitCommand, root, pathsArgs, maxOutputBytes, request)
  if (!paths.ok) throw classifyFailure(gitCommand, pathsArgs, paths)
  const state = await hashSourceEntries(root, listing.stdout, paths.stdout, request)
  for (const [args, expected] of [[headArgs, head.stdout], [listingArgs, listing.stdout], [pathsArgs, paths.stdout]] as const) {
    const after = await runGit(gitCommand, root, args, maxOutputBytes, request)
    if (!after.ok) throw classifyFailure(gitCommand, args, after)
    if (!after.stdout.equals(expected)) throw sourceFailure('Git source inventory changed while computing its fingerprint')
  }
  return Object.freeze({
    fingerprint: makeSourceFingerprint(`${FINGERPRINT_PREFIX}-${headCommit}-${state.stateHash}`),
    headCommit,
    ...state,
    algorithm: 'v2',
  })
}

/**
 * Explicit verify surface: recompute the worktree fingerprint and compare it
 * with a recorded value under branded-string equality — the same semantics as
 * the stored `ProjectWorkBinding.sourceFingerprint` comparison, which is why
 * `recorded` is that bare branded string rather than a full
 * {@link ComputedSourceFingerprint}: the durable record holds exactly that
 * string, and digest fields besides the value must not vote in the equality.
 * Read-only and off the binding hot path: the git subprocess cost is paid
 * only when this function is called.
 *
 * Which side to trust per arm: on `match`, `fingerprint` is both the recorded
 * claim and the fresh reading; on `mismatch`, `recordedFingerprint` is only
 * the stale claim and `computed` is the fresh, trustworthy digest.
 *
 * @param worktreePath - absolute path to any directory inside the target git worktree.
 * @param recorded - the previously recorded branded fingerprint (e.g. `ProjectWorkBinding.sourceFingerprint`).
 * @returns a {@link SourceFingerprintMatch} when the fresh value equals
 *   `recorded`; otherwise a {@link SourceFingerprintMismatch} carrying both sides.
 * @throws {@link SourceFingerprintError} with one of the documented
 *   {@link SourceFingerprintErrorCode} values, passed through unmodified from
 *   {@link computeSourceFingerprint} (never wrapped, never swallowed):
 *   - `SOURCE_FINGERPRINT_INVALID_REQUEST` — `worktreePath` is empty or relative;
 *   - `SOURCE_FINGERPRINT_NOT_A_WORKTREE` — path missing or not a directory, outside any git worktree, or a bare repository;
 *   - `SOURCE_FINGERPRINT_NO_COMMIT` — the repository has an unborn HEAD (no commits);
 *   - `SOURCE_FINGERPRINT_GIT_UNAVAILABLE` — the git executable is missing (ENOENT) or not executable (EACCES);
 *   - `SOURCE_FINGERPRINT_GIT_FAILED` — any other git failure, including index corruption and output-cap overflow.
 *   - `SOURCE_FINGERPRINT_SOURCE_FAILED` — unreadable, unsupported, changing, cancelled, or over-budget source input.
 */
export async function verifySourceFingerprint(
  worktreePath: string,
  recorded: SourceFingerprint,
): Promise<VerifyVerdict> {
  const computed = await computeSourceFingerprint({ worktreePath })
  if (computed.fingerprint === recorded) {
    return { kind: 'match', fingerprint: computed.fingerprint }
  }
  return { kind: 'mismatch', recordedFingerprint: recorded, computed }
}

/**
 * Run one git invocation against the worktree with a pinned C locale (stderr
 * message classification only; success-path output shape is flag-determined).
 * Never shell-interpreted: fixed argv with `-C <dir>`, so the process cwd is
 * irrelevant to the result.
 */
async function runGit(
  gitCommand: string,
  worktreePath: string,
  args: readonly string[],
  maxOutputBytes: number,
  limits: Pick<SourceFingerprintRequest, 'signal' | 'timeoutMs'>,
): Promise<GitRun> {
  try {
    const pending = execFileAsync(gitCommand, ['-C', worktreePath, ...args], {
      encoding: 'buffer',
      maxBuffer: maxOutputBytes,
      windowsHide: true,
      ...(limits.signal === undefined ? {} : { signal: limits.signal }),
      ...(limits.timeoutMs === undefined ? {} : { timeout: limits.timeoutMs }),
      env: { ...Object.fromEntries(Object.entries(process.env)
        .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))), LC_ALL: 'C' },
    })
    // Abort can reject the operation before the child closes its stdio.
    const closed = new Promise<void>(resolve => pending.child.once('close', () => { resolve() }))
    let result: Awaited<typeof pending>
    try {
      result = await pending
    } finally {
      await closed
    }
    const { stdout, stderr } = result
    return { ok: true, stdout, stderr: stderr.toString('utf8') }
  } catch (error: unknown) {
    const output = error as Partial<{ stdout: unknown; stderr: unknown }>
    return {
      ok: false,
      stdout: Buffer.isBuffer(output.stdout) ? output.stdout : Buffer.alloc(0),
      stderr: Buffer.isBuffer(output.stderr) ? output.stderr.toString('utf8') : '',
      error,
    }
  }
}

/**
 * Classify one failed HEAD resolution. Documented `--verify --quiet`
 * semantics: exit status 1 with no message when HEAD cannot be resolved — an
 * unborn repository (no commits yet).
 */
function classifyHeadFailure(
  worktreePath: string,
  gitCommand: string,
  args: readonly string[],
  run: GitFailure,
): SourceFingerprintError {
  if ((run.error as { readonly code?: unknown }).code === 1) {
    return new SourceFingerprintError(
      `repository at "${worktreePath}" has no commits (unborn HEAD)`,
      'SOURCE_FINGERPRINT_NO_COMMIT',
    )
  }
  return classifyFailure(gitCommand, args, run)
}

/**
 * Classify one failed git run. Spawn-level failures and collection-cap
 * overflow are code-classified; the locale-pinned "not a git repository"
 * stderr message discriminates repository discovery from other fatals (git
 * has no dedicated exit code for it); everything else fails generically.
 */
function classifyFailure(
  gitCommand: string,
  args: readonly string[],
  run: GitFailure,
  notARepository?: string,
): SourceFingerprintError {
  if (spawnUnavailable(run.error)) return unavailable(gitCommand, run.error)
  if (maxBufferExceeded(run.error)) return outputCapExceeded(args)
  if (notARepository !== undefined && NOT_A_REPOSITORY_MESSAGE.test(run.stderr)) {
    return new SourceFingerprintError(notARepository, 'SOURCE_FINGERPRINT_NOT_A_WORKTREE', { cause: run.error })
  }
  return gitFailed(args, run)
}

/** Spawn-level unavailability: git missing or not executable. */
function spawnUnavailable(error: unknown): boolean {
  const code = (error as { readonly code?: unknown }).code
  return code === 'ENOENT' || code === 'EACCES'
}

/** The git stream exceeded the caller's collection cap. */
function maxBufferExceeded(error: unknown): boolean {
  return (error as { readonly code?: unknown }).code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER'
}

function unavailable(gitCommand: string, error: unknown): SourceFingerprintError {
  return new SourceFingerprintError(
    `git executable "${gitCommand}" is unavailable (spawn error "${String((error as { readonly code?: unknown }).code)}")`,
    'SOURCE_FINGERPRINT_GIT_UNAVAILABLE',
    { cause: error },
  )
}

function outputCapExceeded(args: readonly string[]): SourceFingerprintError {
  return new SourceFingerprintError(
    `git ${args.join(' ')} output exceeded the configured collection cap`,
    'SOURCE_FINGERPRINT_GIT_FAILED',
  )
}

function gitFailed(args: readonly string[], run: GitFailure): SourceFingerprintError {
  const code = (run.error as { readonly code?: unknown }).code
  const diagnostics = [run.stderr.trim(), run.stdout.toString('utf8').trim()]
    .filter(part => part.length > 0)
    .join(' | ')
  return new SourceFingerprintError(
    `git ${args.join(' ')} failed with code ${String(code)}: ${diagnostics}`,
    'SOURCE_FINGERPRINT_GIT_FAILED',
    { cause: run.error },
  )
}

/** Preserve file-read and inventory failures without disclosing source contents. */
function sourceFailure(message: string, cause?: unknown): SourceFingerprintError {
  return new SourceFingerprintError(message, 'SOURCE_FINGERPRINT_SOURCE_FAILED', { cause })
}

/** Observe a path without following its final symlink; only absence is a deletion. */
async function observe(path: string): Promise<Stats | undefined> {
  try { return await lstat(path) } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined
    throw error
  }
}

/** Metadata detects replacement or mutation during a read; it is never fingerprint input. */
function sameObservation(left: Stats | undefined, right: Stats | undefined): boolean {
  if (left === undefined || right === undefined) return left === right
  return left.dev === right.dev && left.ino === right.ino && left.mode === right.mode
    && left.size === right.size && left.mtimeMs === right.mtimeMs && left.ctimeMs === right.ctimeMs
}

/** Hash one Git-selected source inventory without spawning a process per file. */
async function hashSourceEntries(
  root: string, index: Buffer, inventory: Buffer, request: SourceFingerprintRequest,
): Promise<{ stateHash: string; entryCount: number }> {
  const deadline = request.timeoutMs === undefined ? undefined : AbortSignal.timeout(request.timeoutMs)
  const signals = [request.signal, deadline].filter((signal): signal is AbortSignal => signal !== undefined)
  const signal = AbortSignal.any(signals)
  try {
    if (index.toString('utf8').split('\0').some(record => record.startsWith('160000 '))) {
      throw sourceFailure('Submodules require an explicit source snapshot policy')
    }
    const raw = new TextDecoder('utf-8', { fatal: true }).decode(inventory)
    if (raw.length > 0 && !raw.endsWith('\0')) throw sourceFailure('Git source inventory is not NUL terminated')
    const paths = [...new Set(raw.length === 0 ? [] : raw.slice(0, -1).split('\0'))].sort()
    const hash = createHash('sha256')
    const field = (value: string | Buffer) => {
      const bytes = typeof value === 'string' ? Buffer.from(value) : value
      hash.update(String(bytes.length)).update(':').update(bytes)
    }
    field(index)
    let consumed = 0
    const consume = (bytes: number) => {
      consumed += bytes
      if (request.maxSourceBytes !== undefined && consumed > request.maxSourceBytes) {
        throw sourceFailure('Source contents exceed the configured byte cap')
      }
    }
    const observations = new Map<string, Stats | undefined>()
    for (const path of paths) {
      signal.throwIfAborted()
      const segments = path.split('/')
      if (isAbsolute(path) || segments.some(segment => segment === '' || segment === '.' || segment === '..')
        || (process.platform === 'win32' && /[:\\]/.test(path))) throw sourceFailure('Git source inventory contains an unsafe path')
      let parent = root
      for (const segment of segments.slice(0, -1)) {
        parent = join(parent, segment)
        const directory = await observe(parent)
        if (directory !== undefined && !directory.isDirectory()) throw sourceFailure('Source path traverses a non-directory entry')
        if (observations.has(parent) && !sameObservation(observations.get(parent), directory)) throw sourceFailure('Source directory changed')
        observations.set(parent, directory)
      }
      const absolute = join(root, path)
      const before = await observe(absolute)
      observations.set(absolute, before)
      field(path)
      if (before === undefined) {
        field('missing')
      } else if (before.isSymbolicLink()) {
        field('symlink')
        const target = await readlink(absolute, { encoding: 'buffer' })
        consume(target.length)
        field(target)
      } else if (before.isFile()) {
        field('file')
        field(String(before.mode & 0o111))
        consume(before.size)
        const handle = await open(absolute, constants.O_RDONLY | constants.O_NOFOLLOW)
        try {
          if (!sameObservation(before, await handle.stat())) throw sourceFailure('Source file changed before reading')
          signal.throwIfAborted()
          const contents = createHash('sha256')
          let read = 0
          for await (const chunk of handle.createReadStream({ autoClose: false, signal })) {
            if (!Buffer.isBuffer(chunk)) throw sourceFailure('Source stream returned non-binary data')
            read += chunk.length
            if (read > before.size) throw sourceFailure('Source file grew while reading')
            contents.update(chunk)
          }
          if (read !== before.size || !sameObservation(before, await handle.stat())) throw sourceFailure('Source file changed while reading')
          field(contents.digest())
        } finally { await handle.close() }
      } else {
        throw sourceFailure('Source inventory contains an unsupported file type or submodule')
      }
      if (!sameObservation(before, await observe(absolute))) throw sourceFailure('Source entry changed while reading')
    }
    for (const [path, before] of observations) {
      signal.throwIfAborted()
      if (!sameObservation(before, await observe(path))) throw sourceFailure('Source inventory changed while reading')
    }
    signal.throwIfAborted()
    return { stateHash: hash.digest('hex'), entryCount: paths.length }
  } catch (error) {
    if (error instanceof SourceFingerprintError) throw error
    throw sourceFailure('Source contents could not be fingerprinted', error)
  }
}
