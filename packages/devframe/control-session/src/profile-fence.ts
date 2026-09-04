/** Single-writer lifecycle fence for the canonical DevFrame Profile Host. */

import { randomUUID } from 'node:crypto'
import {
  closeSync,
  fstatSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
  type Stats,
} from 'node:fs'
import { hostname as readHostname } from 'node:os'
import { dirname, join } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { resolveDshHome } from '@deepseek-ai/dsh-home-paths'

const PROFILE_HOST_DIRECTORY = 'devframe'
const PROFILE_HOST_LEASE_FILENAME = 'host-lease.json'
const PROFILE_HOST_TRANSITION_FILENAME = 'host-lease.transition.json'
const RECORD_KEYS = ['hostname', 'pid', 'startedAt', 'token', 'version'] as const
const SORTED_RECORD_KEYS = [...RECORD_KEYS].sort()
const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const HOSTNAME_CONTROL_PATTERN = /[\u0000-\u001f\u007f]/
const TRANSIENT_RETRY_LIMIT = 16
const TAKEOVER_CREATE_RETRY_LIMIT = 50
const TAKEOVER_CREATE_RETRY_MS = 10

/** Root-context key populated only while a canonical DevFrame Profile Host owns the fence. */
export const DSH_PROFILE_HOST_FENCE_KEY = 'profileHostFence'

/** Stable failure categories that never expose hostnames, paths, PIDs, or tokens. */
export type ProfileHostFenceErrorCode =
  | 'ACTIVE'
  | 'FOREIGN_HOST'
  | 'INVALID_RECORD'
  | 'NOT_OWNER'
  | 'OWNER_UNCERTAIN'
  | 'FILESYSTEM'

/** Bounded lifecycle-fence failure safe to surface without local owner details. */
export class ProfileHostFenceError extends Error {
  /**
   * @param code - Stable failure category.
   * @param options - Optional Host-only cause.
   */
  constructor(readonly code: ProfileHostFenceErrorCode, options?: ErrorOptions) {
    super(`DevFrame Profile Host blocked: ${code}`, options)
    this.name = 'ProfileHostFenceError'
  }
}

/** Non-secret owner facts available to Host plugins and readiness checks. */
export interface ProfileHostFenceOwner {
  readonly pid: number
  readonly hostname: string
  readonly startedAt: string
}

/** Read-only root-context proof that this process owns the Profile Host fence. */
export interface ProfileHostFence {
  readonly owner: ProfileHostFenceOwner
}

/** Launcher-owned lifecycle handle. Only the launcher releases the fence. */
export interface ProfileHostFenceLease extends ProfileHostFence {
  /** Release ownership after every Host plugin has reached quiescence. */
  release(): Promise<void>
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Present only on the canonical DevFrame Profile Host. */
    profileHostFence?: ProfileHostFence
  }
}

interface ProfileHostFenceRecord extends ProfileHostFenceOwner {
  readonly version: 1
  readonly token: string
}

interface OwnedFile {
  readonly path: string
  readonly record: ProfileHostFenceRecord
  readonly raw: string
  readonly stat: Stats
}

interface InspectedFile extends OwnedFile {}

function errorCode(failure: unknown): string | undefined {
  return typeof failure === 'object' && failure !== null && 'code' in failure
    ? String((failure as NodeJS.ErrnoException).code)
    : undefined
}

function fenceFailure(failure: unknown, fallback: ProfileHostFenceErrorCode): ProfileHostFenceError {
  return failure instanceof ProfileHostFenceError
    ? failure
    : new ProfileHostFenceError(fallback, { cause: failure })
}

function sameFile(left: Stats, right: Stats): boolean {
  return left.dev === right.dev && left.ino === right.ino
}

function localHostname(): string {
  const value = readHostname().trim().toLowerCase()
  if (value.length === 0 || value.length > 255 || HOSTNAME_CONTROL_PATTERN.test(value)) {
    throw new ProfileHostFenceError('OWNER_UNCERTAIN')
  }
  return value
}

function exactKeys(value: Record<string, unknown>): boolean {
  const actual = Object.keys(value).sort()
  return actual.length === RECORD_KEYS.length
    && actual.every((key, index) => key === SORTED_RECORD_KEYS[index])
}

function parseRecord(raw: string): ProfileHostFenceRecord {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch (failure) {
    throw new ProfileHostFenceError('INVALID_RECORD', { cause: failure })
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)
    || !exactKeys(value as Record<string, unknown>)) {
    throw new ProfileHostFenceError('INVALID_RECORD')
  }
  const record = value as Record<string, unknown>
  if (record.version !== 1
    || typeof record.token !== 'string' || !UUID_V4_PATTERN.test(record.token)
    || typeof record.pid !== 'number' || !Number.isSafeInteger(record.pid) || record.pid <= 0
    || typeof record.hostname !== 'string' || record.hostname.length === 0 || record.hostname.length > 255
    || record.hostname !== record.hostname.toLowerCase() || HOSTNAME_CONTROL_PATTERN.test(record.hostname)
    || typeof record.startedAt !== 'string') {
    throw new ProfileHostFenceError('INVALID_RECORD')
  }
  const startedAt = Date.parse(record.startedAt)
  if (!Number.isFinite(startedAt) || new Date(startedAt).toISOString() !== record.startedAt) {
    throw new ProfileHostFenceError('INVALID_RECORD')
  }
  return record as unknown as ProfileHostFenceRecord
}

function lstatOptional(path: string): Stats | undefined {
  try {
    return lstatSync(path)
  } catch (failure) {
    if (errorCode(failure) === 'ENOENT') return undefined
    throw fenceFailure(failure, 'FILESYSTEM')
  }
}

function inspectFile(path: string): InspectedFile | undefined {
  const before = lstatOptional(path)
  if (before === undefined) return undefined
  if (!before.isFile() || before.isSymbolicLink() || before.nlink !== 1) {
    throw new ProfileHostFenceError('INVALID_RECORD')
  }
  let raw: string
  try {
    raw = readFileSync(path, 'utf8')
  } catch (failure) {
    if (errorCode(failure) === 'ENOENT') return undefined
    throw fenceFailure(failure, 'FILESYSTEM')
  }
  const after = lstatOptional(path)
  if (after === undefined) return undefined
  if (!after.isFile() || after.isSymbolicLink() || after.nlink !== 1) {
    throw new ProfileHostFenceError('INVALID_RECORD')
  }
  if (!sameFile(before, after)) throw new ProfileHostFenceError('OWNER_UNCERTAIN')
  return { path, raw, stat: after, record: parseRecord(raw) }
}

function uniqueTombstone(path: string, phase: string, token: string): string {
  for (let attempt = 0; attempt < TRANSIENT_RETRY_LIMIT; attempt += 1) {
    const candidate = `${path}.${phase}.${token}.${randomUUID()}`
    if (lstatOptional(candidate) === undefined) return candidate
  }
  throw new ProfileHostFenceError('OWNER_UNCERTAIN')
}

function cleanupCreatedFile(path: string, stat: Stats, token: string): void {
  const current = lstatOptional(path)
  if (current === undefined || !current.isFile() || current.isSymbolicLink()
    || current.nlink !== 1 || !sameFile(current, stat)) return
  const tombstone = uniqueTombstone(path, 'incomplete', token)
  renameSync(path, tombstone)
  unlinkSync(tombstone)
}

function createOwnedFile(path: string): OwnedFile | undefined {
  const record: ProfileHostFenceRecord = {
    version: 1,
    token: randomUUID(),
    pid: process.pid,
    hostname: localHostname(),
    startedAt: new Date().toISOString(),
  }
  const raw = `${JSON.stringify(record)}\n`
  let descriptor: number
  try {
    descriptor = openSync(path, 'wx', 0o600)
  } catch (failure) {
    if (errorCode(failure) === 'EEXIST') return undefined
    throw fenceFailure(failure, 'FILESYSTEM')
  }
  let stat: Stats | undefined
  let writeFailure: unknown
  try {
    stat = fstatSync(descriptor)
    writeFileSync(descriptor, raw, { encoding: 'utf8' })
    fsyncSync(descriptor)
  } catch (failure) {
    writeFailure = failure
  }
  try {
    closeSync(descriptor)
  } catch (failure) {
    writeFailure = writeFailure === undefined
      ? failure
      : new AggregateError([writeFailure, failure], 'Profile Host fence publication failed')
  }
  if (writeFailure !== undefined) {
    try {
      if (stat !== undefined) cleanupCreatedFile(path, stat, record.token)
    } catch (cleanupFailure) {
      throw new ProfileHostFenceError('FILESYSTEM', {
        cause: new AggregateError([writeFailure, cleanupFailure], 'Profile Host fence publication cleanup failed'),
      })
    }
    throw fenceFailure(writeFailure, 'FILESYSTEM')
  }
  if (stat === undefined) throw new ProfileHostFenceError('FILESYSTEM')
  const published = inspectFile(path)
  if (published === undefined || published.record.token !== record.token
    || published.raw !== raw || !sameFile(published.stat, stat)) {
    throw new ProfileHostFenceError('NOT_OWNER')
  }
  return published
}

function retireOwnedFile(owned: OwnedFile, phase: string): void {
  const current = inspectFile(owned.path)
  if (current === undefined || current.record.token !== owned.record.token
    || current.raw !== owned.raw || !sameFile(current.stat, owned.stat)) {
    throw new ProfileHostFenceError('NOT_OWNER')
  }
  const tombstone = uniqueTombstone(owned.path, phase, owned.record.token)
  try {
    renameSync(owned.path, tombstone)
  } catch (failure) {
    throw fenceFailure(failure, errorCode(failure) === 'ENOENT' ? 'NOT_OWNER' : 'FILESYSTEM')
  }
  const retired = inspectFile(tombstone)
  if (retired === undefined || retired.record.token !== owned.record.token
    || retired.raw !== owned.raw || !sameFile(retired.stat, owned.stat)) {
    throw new ProfileHostFenceError('NOT_OWNER')
  }
  try {
    unlinkSync(tombstone)
  } catch (failure) {
    if (errorCode(failure) !== 'ENOENT') throw fenceFailure(failure, 'FILESYSTEM')
  }
}

function processIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (failure) {
    const code = errorCode(failure)
    if (code === 'ESRCH') return false
    if (code === 'EPERM') return true
    throw new ProfileHostFenceError('OWNER_UNCERTAIN', { cause: failure })
  }
}

function assertDeadLocalOwner(file: InspectedFile): void {
  if (file.record.hostname !== localHostname()) throw new ProfileHostFenceError('FOREIGN_HOST')
  if (processIsAlive(file.record.pid)) throw new ProfileHostFenceError('ACTIVE')
}

function transitionPath(home?: string): string {
  return join(dirname(profileHostFencePath(home)), PROFILE_HOST_TRANSITION_FILENAME)
}

function ensureFenceDirectory(home?: string): void {
  const directory = dirname(profileHostFencePath(home))
  try {
    mkdirSync(directory, { recursive: true, mode: 0o700 })
  } catch (failure) {
    throw fenceFailure(failure, 'FILESYSTEM')
  }
  const stat = lstatOptional(directory)
  if (stat === undefined || !stat.isDirectory() || stat.isSymbolicLink()) {
    throw new ProfileHostFenceError('FILESYSTEM')
  }
}

function combineFailures(primary: unknown, cleanup: unknown): ProfileHostFenceError {
  const bounded = fenceFailure(primary, 'FILESYSTEM')
  return new ProfileHostFenceError(bounded.code, {
    cause: new AggregateError([bounded, cleanup], 'Profile Host fence cleanup failed'),
  })
}

class OwnedProfileHostFence implements ProfileHostFenceLease {
  readonly owner: ProfileHostFenceOwner
  private releaseOperation: Promise<void> | undefined
  private released = false
  private transitionFile: OwnedFile | undefined

  constructor(
    private readonly lease: OwnedFile,
    private readonly transition: string,
  ) {
    this.owner = Object.freeze({
      pid: lease.record.pid,
      hostname: lease.record.hostname,
      startedAt: lease.record.startedAt,
    })
  }

  release(): Promise<void> {
    if (this.released) return Promise.resolve()
    if (this.releaseOperation !== undefined) return this.releaseOperation
    const operation = Promise.resolve().then(() => { this.releaseOnce() })
    this.releaseOperation = operation
    void operation.then(
      () => {
        this.released = true
        this.releaseOperation = undefined
      },
      () => { this.releaseOperation = undefined },
    )
    return operation
  }

  private releaseOnce(): void {
    const transition = this.acquireTransition()
    let failure: unknown
    try {
      retireOwnedFile(this.lease, 'released')
    } catch (caught) {
      failure = caught
    }
    try {
      retireOwnedFile(transition, 'complete')
      this.transitionFile = undefined
    } catch (cleanupFailure) {
      if (failure === undefined) throw fenceFailure(cleanupFailure, 'FILESYSTEM')
      throw combineFailures(failure, cleanupFailure)
    }
    if (failure !== undefined) throw fenceFailure(failure, 'FILESYSTEM')
  }

  /**
   * Reuse a transition record left by a failed release instead of creating a
   * second marker. A different record at the same path is never ours and must
   * fail closed; an absent record means the previous transition was retired
   * successfully and a fresh marker is safe.
   */
  private acquireTransition(): OwnedFile {
    if (this.transitionFile !== undefined) {
      const current = inspectFile(this.transition)
      if (current !== undefined) {
        if (current.record.token !== this.transitionFile.record.token) {
          throw new ProfileHostFenceError('OWNER_UNCERTAIN')
        }
        this.transitionFile = current
        return current
      }
      this.transitionFile = undefined
    }
    const created = createOwnedFile(this.transition)
    if (created === undefined) throw new ProfileHostFenceError('OWNER_UNCERTAIN')
    this.transitionFile = created
    return created
  }
}

async function reclaimDeadOwner(
  leasePath: string,
  transition: string,
): Promise<OwnedFile | undefined> {
  const claim = createOwnedFile(transition)
  if (claim === undefined) throw new ProfileHostFenceError('OWNER_UNCERTAIN')
  let next: OwnedFile | undefined
  let failure: unknown
  let retry = false
  try {
    const existing = inspectFile(leasePath)
    if (existing === undefined) {
      retry = true
    } else {
      assertDeadLocalOwner(existing)
      retireOwnedFile(existing, 'stale')
      for (let attempt = 0; attempt < TAKEOVER_CREATE_RETRY_LIMIT; attempt += 1) {
        next = createOwnedFile(leasePath)
        if (next !== undefined) break
        await delay(TAKEOVER_CREATE_RETRY_MS)
      }
      if (next === undefined) throw new ProfileHostFenceError('OWNER_UNCERTAIN')
    }
  } catch (caught) {
    failure = caught
  }
  try {
    retireOwnedFile(claim, 'complete')
  } catch (cleanupFailure) {
    failure = failure === undefined
      ? fenceFailure(cleanupFailure, 'FILESYSTEM')
      : combineFailures(failure, cleanupFailure)
  }
  if (failure !== undefined) {
    if (next !== undefined) {
      try {
        retireOwnedFile(next, 'abandoned')
      } catch (cleanupFailure) {
        throw combineFailures(failure, cleanupFailure)
      }
    }
    throw fenceFailure(failure, 'FILESYSTEM')
  }
  return retry ? undefined : next
}

/**
 * Resolve the canonical lifecycle-fence file under the Harness home.
 * @param home - Optional explicit Harness home, primarily for isolated launchers and tests.
 * @returns the absolute lease-file path.
 */
export function profileHostFencePath(home?: string): string {
  return join(resolveDshHome(home), PROFILE_HOST_DIRECTORY, PROFILE_HOST_LEASE_FILENAME)
}

/**
 * Acquire the single-writer DevFrame Profile Host fence. A same-host record is
 * reclaimable only when `kill(pid, 0)` reports `ESRCH`; live, inaccessible,
 * foreign-host, malformed, and uncertain owners fail closed. Acquisition and
 * release use exclusive-create records plus a serialized rename tombstone.
 * @param home - Optional explicit Harness home, primarily for isolated launchers and tests.
 * @returns a launcher-owned lease whose public owner projection excludes its token and path.
 */
export async function acquireProfileHostFence(home?: string): Promise<ProfileHostFenceLease> {
  ensureFenceDirectory(home)
  const leasePath = profileHostFencePath(home)
  const transition = transitionPath(home)
  for (let attempt = 0; attempt < TRANSIENT_RETRY_LIMIT; attempt += 1) {
    if (inspectFile(transition) !== undefined) throw new ProfileHostFenceError('OWNER_UNCERTAIN')
    const direct = createOwnedFile(leasePath)
    if (direct !== undefined) {
      try {
        if (inspectFile(transition) === undefined) return new OwnedProfileHostFence(direct, transition)
      } catch (postcheckFailure) {
        try {
          retireOwnedFile(direct, 'abandoned')
        } catch (cleanupFailure) {
          throw combineFailures(postcheckFailure, cleanupFailure)
        }
        throw fenceFailure(postcheckFailure, 'OWNER_UNCERTAIN')
      }
      try {
        retireOwnedFile(direct, 'abandoned')
      } catch (cleanupFailure) {
        throw new ProfileHostFenceError('OWNER_UNCERTAIN', { cause: cleanupFailure })
      }
      throw new ProfileHostFenceError('OWNER_UNCERTAIN')
    }
    const existing = inspectFile(leasePath)
    if (existing === undefined) continue
    assertDeadLocalOwner(existing)
    const recovered = await reclaimDeadOwner(leasePath, transition)
    if (recovered !== undefined) return new OwnedProfileHostFence(recovered, transition)
  }
  throw new ProfileHostFenceError('OWNER_UNCERTAIN')
}
