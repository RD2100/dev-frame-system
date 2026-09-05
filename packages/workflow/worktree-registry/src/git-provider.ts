/**
 * Local git Service Provider for the worktree registry seam. Every worktree
 * operation spawns `git` through `ctx.subprocess` — bounded output collection,
 * tree-scoped termination, and deadline fusion are the subprocess service's
 * mechanics — and the provider owns config defaulting, failure
 * classification, and the durable `worktree_registry` domain rows.
 *
 * git is never invoked with the target worktree as its working directory for
 * mutating commands: on Windows a process cannot delete the directory tree
 * that contains its own cwd, so `remove` runs from the owner workspace
 * directory while `status` (read-only) runs from inside the worktree.
 *
 * @module @deepseek-ai/dsh-worktree-registry/src/git-provider
 */

import { randomUUID } from 'node:crypto'
import { stat } from 'node:fs/promises'
import { resolve } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { Workspace, WorkspaceId } from '@deepseek-ai/dsh-workspace'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import type { KvTable } from '@deepseek-ai/dsh-storage-domain'

import type { CollectedOutput, SubprocessHandle, SubprocessOutcome, SubprocessOutputReader } from '@deepseek-ai/dsh-subprocess'
import { MAX_TIMER_DELAY_MS, deadline, timeoutOf } from '@deepseek-ai/dsh-timeout'
import z from '@deepseek-ai/schemastery'
import { worktreeDomainSpec } from './spec.ts'
import type { WorktreeRecord } from './spec.ts'
import { WorktreeRegistry } from './registry.ts'
import { parseWorktreeList, sameGitPath } from './porcelain.ts'
import type {
  Worktree,
  WorktreeCreateRequest,
  WorktreeDanglingRegistration,
  WorktreeId,
  WorktreeReconcileOptions,
  WorktreeReconcileReport,
  WorktreeRemoveOptions,
  WorktreeStatus,
  WorktreeUnregisteredWorktree,
} from './types.ts'

/** Plugin config (all optional — `static Config` supplies the defaults). */
export interface GitWorktreeRegistryConfig {
  /** Explicit git executable (default: `git`, resolved through PATH). */
  gitPath?: string
  /** Default per-invocation timeout in milliseconds. */
  timeoutMs?: number
  /** Upper bound for the applied timeout. */
  maxTimeoutMs?: number
  /** SIGTERM→SIGKILL grace period for the git process tree. */
  graceMs?: number
  /** Per-stream in-memory output cap; overflow keeps the tail. */
  maxOutputBytes?: number
}

/** The shape after schemastery applied the defaults (gitPath has none). */
type ResolvedConfig = Required<Omit<GitWorktreeRegistryConfig, 'gitPath'>> & Pick<GitWorktreeRegistryConfig, 'gitPath'>

/** Default per-invocation timeout (the `timeoutMs` config). */
const DEFAULT_TIMEOUT_MS = 60_000

/** Default timeout upper bound (the `maxTimeoutMs` config). */
const DEFAULT_MAX_TIMEOUT_MS = 600_000

/** Default SIGTERM→SIGKILL grace period (the `graceMs` config). */
const DEFAULT_GRACE_MS = 3_000

/** Default per-stream output cap (the `maxOutputBytes` config). */
const DEFAULT_MAX_OUTPUT_BYTES = 64_000

/**
 * Reject a resolved config this provider could not run with. The schema
 * expresses neither "positive and finite" nor the timer bound `graceMs` has
 * to fit, so a stored value is refused where it is written instead of failing
 * at the first git invocation.
 * @param config - The resolved config, schema-valid by construction.
 */
export function assertServiceableGitConfig(config: GitWorktreeRegistryConfig): void {
  const resolved = config as ResolvedConfig
  assertPositiveFinite('timeoutMs', resolved.timeoutMs)
  assertPositiveFinite('maxTimeoutMs', resolved.maxTimeoutMs)
  assertPositiveFinite('graceMs', resolved.graceMs)
  assertPositiveFinite('maxOutputBytes', resolved.maxOutputBytes)
  if (resolved.graceMs > MAX_TIMER_DELAY_MS) {
    throw new Error(`worktree-registry: graceMs must be no greater than ${MAX_TIMER_DELAY_MS}`)
  }
}

function assertPositiveFinite(name: string, value: number): void {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`worktree-registry: ${name} must be a positive finite number`)
  }
}

/** Whether `path` is an existing directory. Only a definite miss reports `false`; other stat failures propagate. */
async function directoryExists(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isDirectory()
  } catch (error) {
    // ENOENT is the reported missing-directory observation; every other stat
    // failure (permissions, corruption) must stay loud.
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false
    throw error
  }
}

/** Project a settled collect-mode reader into the final CollectedOutput shape. */
function finalOutput(reader: SubprocessOutputReader | undefined): CollectedOutput {
  /* v8 ignore start -- collect dispositions expose the reader by the seam contract; defensive. */
  if (reader === undefined) {
    throw new Error('worktree-registry: subprocess implementation dropped a requested collect stream')
  }
  /* v8 ignore stop */
  const read = reader.readFrom(0)
  return {
    text: read.text,
    truncated: read.lossy,
    ...read.spillPath !== undefined ? { spillPath: read.spillPath } : {},
  }
}

/** The local git worktree registry: one durable `worktree_registry` domain, git over the subprocess seam. */
export class GitWorktreeRegistry extends WorktreeRegistry {
  static inject = ['workspaceRegistry', 'subprocess', 'storageDomain']

  static Config: z<GitWorktreeRegistryConfig> = z.object({
    gitPath: z.string(),
    timeoutMs: z.number().default(DEFAULT_TIMEOUT_MS),
    maxTimeoutMs: z.number().default(DEFAULT_MAX_TIMEOUT_MS),
    graceMs: z.number().default(DEFAULT_GRACE_MS),
    maxOutputBytes: z.number().default(DEFAULT_MAX_OUTPUT_BYTES),
  })

  /** Validated config (schemastery applied the defaults before construction). */
  private readonly config: ResolvedConfig

  private table?: KvTable<WorktreeId, WorktreeRecord>
  private operationTail: Promise<unknown> = Promise.resolve()

  constructor(ctx: Context, config: GitWorktreeRegistryConfig) {
    super(ctx)
    // Schemastery fills these fields before construction; the type does not encode that step.
    this.config = config as ResolvedConfig
    assertServiceableGitConfig(this.config)
  }

  /** Open the registry domain and tie its lifetime to the service fiber. */
  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(worktreeDomainSpec)
    this.ctx.effect(() => () => domain.close(), 'worktree-registry.domainClose')
    this.table = domain.table('worktrees')
  }

  async create(request: WorktreeCreateRequest): Promise<Worktree> {
    return await this.enqueue(() => this.createQueued(request))
  }

  list(workspaceId: WorkspaceId): readonly Worktree[] {
    this.requireWorkspace(workspaceId)
    return [...this.requireTable().entries()]
      .filter(([, record]) => record.workspaceId === workspaceId)
      .sort(([leftId, left], [rightId, right]) =>
        left.createdAt.localeCompare(right.createdAt) || String(leftId).localeCompare(String(rightId)))
      .map(([id, record]) => toWorktree(id, record))
  }

  async status(id: WorktreeId): Promise<WorktreeStatus> {
    const record = this.requireRecord(id)
    if (!(await directoryExists(record.path))) {
      return { directoryExists: false }
    }
    const branch = (await this.runGit(['rev-parse', '--abbrev-ref', 'HEAD'], record.path)).trim()
    const porcelain = await this.runGit(['status', '--porcelain=v1'], record.path)
    return { directoryExists: true, branch, clean: porcelain.length === 0 }
  }

  async remove(id: WorktreeId, options?: WorktreeRemoveOptions): Promise<void> {
    await this.enqueue(async () => {
      const record = this.requireRecord(id)
      // The owner workspace supplies the git working directory, so it resolves
      // before the directory observation; a missing owner wedges the row on purpose.
      const workspace = this.requireWorkspace(record.workspaceId)
      if (!(await directoryExists(record.path))) {
        throw new Error(
          `cannot remove worktree '${id}': directory '${record.path}' no longer exists; `
          + 'unregister the stale row through reconcile (pruneRows) or restore the directory',
        )
      }
      const args = options?.force === true
        ? ['worktree', 'remove', '--force', record.path]
        : ['worktree', 'remove', record.path]
      await this.runGit(args, workspace.path)
      if (!(await this.requireTable().delete(id))) {
        throw new Error(`worktree '${id}' was removed from git but its registration vanished before deletion`)
      }
    })
  }

  async reconcile(
    workspaceId: WorkspaceId,
    options?: WorktreeReconcileOptions,
  ): Promise<WorktreeReconcileReport> {
    return await this.enqueue(() => this.reconcileQueued(workspaceId, options ?? {}))
  }

  /**
   * The reconcile body, serialized behind the mutation chain so detection,
   * row drops, and adoptions cannot interleave with create/remove.
   * @param workspaceId - Owner workspace whose rows are reconciled.
   * @param options - The opt-in reconcile actions.
   * @returns the observed differences and the applied changes.
   */
  private async reconcileQueued(
    workspaceId: WorkspaceId,
    options: WorktreeReconcileOptions,
  ): Promise<WorktreeReconcileReport> {
    const workspace = this.requireWorkspace(workspaceId)
    // Every observation happens in the registry's canonical-path canon so
    // spellings git rewrote (short names, junctions, separators) still match
    // the rows; an entry whose directory is gone keeps git's spelling.
    const observed: WorktreeUnregisteredWorktree[] = []
    for (const entry of await this.listGitWorktrees(workspace.path)) {
      let path = entry.path
      try {
        path = await realpathNormalize(entry.path)
      } catch (error) {
        // ENOENT is the vanished-worktree observation; every other resolution
        // failure (permissions, corruption) must stay loud.
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      }
      observed.push(entry.branch === undefined ? { path } : { path, branch: entry.branch })
    }
    // git reports the repository's main worktree first; it is a root checkout,
    // never a second checkout another workspace would register.
    const linked = observed.slice(1)
    const knownPaths = observed.map(entry => entry.path)

    // A row is dangling when its directory is gone (git may still list the
    // dead admin entry as prunable) or when git no longer tracks its path.
    const dangling: WorktreeDanglingRegistration[] = []
    for (const [id, record] of this.rowsOf(workspaceId)) {
      if (!(await directoryExists(record.path))) {
        dangling.push({ id, path: record.path, reason: 'directory-missing' })
      } else if (!knownPaths.some(path => sameGitPath(path, record.path))) {
        dangling.push({ id, path: record.path, reason: 'git-unknown' })
      }
    }

    // Unregistered means git tracks a linked worktree that no row of any
    // workspace holds; the reconciling workspace's own checkout is not a
    // stray either, whatever position git lists it in.
    const registeredAnywhere = [...this.requireTable().entries()].map(([, record]) => record.path)
    const unregistered = linked
      .filter(entry => !sameGitPath(entry.path, workspace.path))
      .filter(entry => !registeredAnywhere.some(known => sameGitPath(known, entry.path)))

    const removedRows: WorktreeId[] = []
    if (options.pruneRows === true) {
      for (const stale of dangling) {
        if (!(await this.requireTable().delete(stale.id))) continue
        removedRows.push(stale.id)
      }
      // git's own admin entries for the vanished directories are dead weight
      // only git can clean; one prune covers every dropped directory-missing row.
      if (dangling.some(stale => stale.reason === 'directory-missing')) {
        await this.runGit(['worktree', 'prune'], workspace.path)
      }
    }

    const adoptedPaths: string[] = []
    if (options.adoptUnregistered === true) {
      for (const entry of unregistered) {
        const branch = (await this.runGit(['rev-parse', '--abbrev-ref', 'HEAD'], entry.path)).trim()
        const id = brandString<WorktreeId>(randomUUID())
        const now = new Date().toISOString()
        await this.requireTable().put(id, {
          workspaceId,
          path: entry.path,
          branch,
          createdAt: now,
          updatedAt: now,
        })
        adoptedPaths.push(entry.path)
      }
    }

    return { dangling, unregistered, removedRows, adoptedPaths }
  }

  /** The stored rows of one workspace, with their ids. */
  private rowsOf(workspaceId: WorkspaceId): [WorktreeId, WorktreeRecord][] {
    return [...this.requireTable().entries()]
      .filter(([, record]) => record.workspaceId === workspaceId)
  }

  /**
   * List the worktrees git reports for the workspace's repository.
   * @param workspacePath - The workspace checkout, which resolves the shared repository.
   * @returns the parsed entries; truncated output rejects rather than half-reporting.
   */
  private async listGitWorktrees(workspacePath: string) {
    const stdout = await this.runGitOut(['worktree', 'list', '--porcelain', '-z'], workspacePath)
    if (stdout.truncated) {
      throw new Error(
        `worktree-registry: 'git worktree list' output exceeded ${this.config.maxOutputBytes} bytes per stream; `
        + 'raise maxOutputBytes to reconcile a repository with this many worktrees',
      )
    }
    return parseWorktreeList(stdout.text)
  }

  private async createQueued(request: WorktreeCreateRequest): Promise<Worktree> {
    const workspace = this.requireWorkspace(request.workspaceId)
    const target = resolve(request.path)
    if (target === workspace.path) {
      throw new Error(`cannot create a worktree at '${target}': it is the owner workspace directory`)
    }
    const known = this.findRegisteredPath(target)
    if (known !== undefined) {
      throw new Error(`cannot create a worktree at '${target}': worktree '${known}' is already registered there`)
    }
    const args = request.branch === undefined
      ? ['worktree', 'add', target]
      : ['worktree', 'add', '-b', request.branch, target]
    await this.runGit(args, workspace.path)

    // git created the directory, so the realpath canon now applies.
    const canonical = await realpathNormalize(target)
    const duplicate = this.findRegisteredPath(canonical)
    if (duplicate !== undefined) {
      throw new Error(
        `canonical path '${canonical}' is already registered as worktree '${duplicate}'; `
        + `the newly created worktree at '${target}' is registered with git but not with this registry`,
      )
    }
    const branch = (await this.runGit(['rev-parse', '--abbrev-ref', 'HEAD'], canonical)).trim()
    const id = brandString<WorktreeId>(randomUUID())
    const now = new Date().toISOString()
    const record: WorktreeRecord = {
      workspaceId: request.workspaceId,
      path: canonical,
      branch,
      createdAt: now,
      updatedAt: now,
    }
    await this.requireTable().put(id, record)
    return toWorktree(id, record)
  }

  /** The registered worktree id holding exactly `path`, when one exists. */
  private findRegisteredPath(path: string): WorktreeId | undefined {
    for (const [id, record] of this.requireTable().entries()) {
      if (record.path === path) return id
    }
    return undefined
  }

  private requireWorkspace(workspaceId: WorkspaceId): Workspace {
    const workspace = this.ctx.workspaceRegistry.get(workspaceId)
    if (workspace === undefined) {
      throw new Error(`worktree registry cannot operate on unknown workspace '${workspaceId}'`)
    }
    return workspace
  }

  private requireRecord(id: WorktreeId): WorktreeRecord {
    const record = this.requireTable().get(id)
    if (record === undefined) {
      throw new Error(`worktree registry holds no worktree '${id}'`)
    }
    return record
  }

  private requireTable(): KvTable<WorktreeId, WorktreeRecord> {
    if (this.table === undefined) throw new Error('worktree registry is not started yet')
    return this.table
  }

  /** Serialize registry mutations on one chain so check-then-act pairs cannot interleave. */
  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.operationTail.then(operation)
    this.operationTail = result.then(() => {}, () => {})
    return result
  }

  /**
   * Run one git invocation to completion and collect its stdout.
   * @param args - git arguments after the executable.
   * @param cwd - Working directory for the invocation.
   * @returns the collected stdout, with its truncation flag.
   */
  private async runGitOut(args: readonly string[], cwd: string): Promise<CollectedOutput> {
    using d = deadline(undefined, this.config.timeoutMs, 'WORKTREE_GIT_TIMEOUT')
    const handle: SubprocessHandle = this.ctx.subprocess.spawn({
      argv: [this.config.gitPath ?? 'git', ...args],
      cwd,
      stdio: {
        stdin: 'ignore',
        stdout: { maxBytes: this.config.maxOutputBytes },
        stderr: { maxBytes: this.config.maxOutputBytes },
      },
      graceMs: this.config.graceMs,
      signal: d.signal,
    })
    let outcome: SubprocessOutcome
    try {
      outcome = await handle.done
    } catch (error) {
      throw new Error(`worktree-registry: git '${this.config.gitPath ?? 'git'}' could not be spawned: ${String(error)}`)
    }
    const stderr = finalOutput(handle.collected.stderr)
    if (timeoutOf(d.signal, 'WORKTREE_GIT_TIMEOUT') !== undefined) {
      throw new Error(
        `worktree-registry: git ${describeArgs(args)} in '${cwd}' timed out after ${this.config.timeoutMs}ms`,
      )
    }
    if (outcome.exitCode !== 0) {
      const tail = stderr.text.trim()
      throw new Error(
        `worktree-registry: git ${describeArgs(args)} in '${cwd}' failed with exit code ${outcome.exitCode}`
        + (tail.length > 0 ? `: ${tail}` : ''),
      )
    }
    return finalOutput(handle.collected.stdout)
  }

  /**
   * Run one git invocation to completion.
   * @param args - git arguments after the executable.
   * @param cwd - Working directory for the invocation.
   * @returns the collected stdout text.
   */
  private async runGit(args: readonly string[], cwd: string): Promise<string> {
    return (await this.runGitOut(args, cwd)).text
  }
}

function describeArgs(args: readonly string[]): string {
  return args.map(arg => /[\s"]/.test(arg) ? JSON.stringify(arg) : arg).join(' ')
}

/** The readonly consumer view of one stored record. */
function toWorktree(id: WorktreeId, record: WorktreeRecord): Worktree {
  return {
    id,
    workspaceId: record.workspaceId,
    path: record.path,
    branch: record.branch,
    createdAt: record.createdAt,
    updatedAt: record.updatedAt,
  }
}

export default GitWorktreeRegistry
