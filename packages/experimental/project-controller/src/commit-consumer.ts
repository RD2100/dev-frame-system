/**
 * Host-controlled Worker commit consumer: the `project_commit` role tool.
 *
 * Workers write task artifact files in their assigned worktree and call this
 * tool. The host derives every registry identity from the real binding,
 * authorizes each path against the task's host-registered commit-path scope,
 * checks caller job quiescence, observes HEAD as a read-only branch-ref lookup
 * on the owner workspace (never through the Worker's `.git` pointer), and
 * hands a fully authorized `WorktreeCommitRequest` to the worktree-registry
 * commit Service — the only Git owner of the worktree itself, whose hardened
 * sequence (pinned gitdir, no hooks, filter refusal, expected HEAD re-check,
 * explicit pathspec staging) performs every other Git operation. The Worker
 * shell never runs `git commit`.
 *
 * The consumer never enumerates the worktree's pending changes: a plain
 * `git status` executes checkout-controlled clean filters and is not a host
 * observation. Authorization comes from the host-registered scope, never
 * from the dirty set; remaining changes after the commit are reported as
 * unverified rather than classified.
 *
 * This module is not a Loader namespace: `delivery-consumer.ts` `apply()`
 * calls {@link registerProjectCommitTool} so the commit joins the delivery
 * consumer's per-task serial chain. A second loader here would fork the
 * quiescence chain the commit has to share with `project_deliver`.
 * @module @deepseek-ai/dsh-experimental-project-controller/commit-consumer
 */

import { execFile } from 'node:child_process'
import { lstat } from 'node:fs/promises'
import { isAbsolute, join, win32 } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import { brandString } from '@deepseek-ai/dsh-brand'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { realpathNormalize } from '@deepseek-ai/dsh-workspace'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { SessionId } from '@deepseek-ai/dsh-session'
import { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { TaskState } from '@deepseek-ai/dsh-experimental-project-contracts'
import type {
  WorktreeCommitId,
  WorktreeCommitRequest,
  WorktreeCommitResult,
  WorktreeId,
} from '@deepseek-ai/dsh-worktree-registry'

const execFileAsync = promisify(execFile)

/** Fixed model-input bounds of the tool contract; protocol constants, not deployment tunables. */
const MAX_COMMIT_PATHS = 64
/** Fixed per-path length bound of the tool contract. */
const MAX_COMMIT_PATH_LENGTH = 256
/** Fixed commit-message length bound of the tool contract. */
const MAX_MESSAGE_LENGTH = 512
/** Full Git object identity the registry Service requires for `expectedHead`. */
const FULL_OBJECT_ID = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/

/** Git process settings the delivery consumer already owns and validates. */
export interface ProjectCommitGitConfig {
  /** Host-selected Git executable. */
  readonly gitExecutable: string
  /** Per-Git-process timeout. */
  readonly gitTimeoutMs: number
  /** Per-Git-process output cap. */
  readonly gitMaxOutputBytes: number
}

/**
 * The authority slice the delivery consumer's Worker-role `resolve` already
 * produces. Every Service request field derives from this shape, never from
 * tool arguments.
 */
export interface ProjectCommitAuthority {
  /** Task under commit; only `developing` admits a commit. */
  readonly task: { readonly state: TaskState }
  /** Open Goal the task belongs to; anchors the deterministic default message. */
  readonly goal: { readonly goalId: unknown }
  /** The assigned Worker binding; `sessionId` mints the writer holder. */
  readonly worker: { readonly sessionId: SessionId }
  /** Canonical Worker worktree path as the registry observed it. */
  readonly sourcePath: string
  /** Registered Worker worktree id. */
  readonly sourceId: WorktreeId
  /** Resolve snapshot digest; a change between awaits refuses the commit. */
  readonly signature: string
}

/**
 * The trusted observation inputs for the owner-side HEAD pre-check: the owner
 * workspace directory (host trust boundary, resolved from registry rows) and
 * the branch registered for the Worker worktree.
 */
export interface ProjectCommitOwnerHead {
  /** Owner workspace path the branch ref is read from. */
  readonly ownerPath: string
  /** Branch name registered for the Worker worktree at create time. */
  readonly branch: string
}

/** The worktree-registry commit capability this consumer drives. */
export interface WorktreeCommitService {
  /**
   * Commit selected paths through the host provider while retaining the writer lock.
   * @param request - Trusted writer, registered target, expected HEAD and literal paths.
   * @param signal - Cancellation of queued or executing Git operations.
   * @returns The verified new commit and the remaining worktree cleanliness.
   */
  commit(request: WorktreeCommitRequest, signal?: AbortSignal): Promise<WorktreeCommitResult>
}

/** Caller-owned background-job view this consumer needs for its quiescence gate. */
export interface ProjectCommitJobView {
  /**
   * List caller-owned and unowned jobs.
   * @param caller - reading agent; a non-agent caller sees only unowned jobs.
   * @returns snapshots whose non-terminal statuses name live potential writers.
   */
  list(caller?: Agent): ReadonlyArray<{ readonly status: string }>
}

/** Closure state the commit tool shares with its delivery-consumer host. */
export interface ProjectCommitDeps {
  /** Tool registry the `project_commit` definition registers into. */
  readonly tools: Context['tools']
  /** Host commit Service; must implement `commit` (see the fail-loud gate). */
  readonly registry: WorktreeCommitService
  /**
   * The delivery consumer's Worker-role `resolve`: assigned-worker identity,
   * live hierarchy on its own worktrees, writer locks, and Goal admission.
   * @param agent - The calling Agent, when the execution context has one.
   * @param taskId - The task the caller claims.
   * @param signal - Cancellation of the tool execution.
   * @returns The authority snapshot for the assigned Worker.
   */
  readonly resolveWorker: (agent: Agent | undefined, taskId: TaskId, signal: AbortSignal) => ProjectCommitAuthority
  /** The delivery consumer's per-task serial chain; the commit joins key `String(taskId)`. */
  readonly serial: <T>(key: string, run: () => Promise<T>) => Promise<T>
  /** The delivery consumer's filtered process environment (no `GIT_*`, no secrets). */
  readonly gitEnvironment: () => Record<string, string | undefined>
  /**
   * Host-registered commit paths per task — the authorization source for what
   * `project_commit` may name. Registered by the deployment like the approved
   * checksets; a task without a scope refuses rather than trusting the model's
   * declaration. There is no dirty-set inference: the scope is the fact source.
   */
  readonly commitPathsByTask: ReadonlyMap<string, readonly string[]>
  /**
   * Resolve the background-job registry at call time. Absent is never quiet:
   * the tool refuses to prove quiescence without the registry instead of
   * assuming no job exists, and resolving per call admits a composition that
   * mounts the registry after this consumer.
   */
  readonly jobs: () => ProjectCommitJobView | undefined
  /**
   * Resolve the owner-workspace path and registered branch of one registered
   * worktree from registry rows — never from the Worker's `.git` pointer.
   * @param sourceId - Registered worktree id of the assigned Worker.
   * @returns The owner workspace path and registered branch.
   */
  readonly resolveOwnerHead: (sourceId: WorktreeId) => ProjectCommitOwnerHead
  /** Git process settings. */
  readonly config: ProjectCommitGitConfig
}

/**
 * Validate one path of a host-registered commit scope or model request:
 * relative, inside the Worker worktree, and free of traversal or Git-metadata
 * segments, mirroring the registry Service path grammar. Dedupes while
 * keeping the declared order.
 * @param values - Raw paths from the host scope or the calling model.
 * @returns Deduplicated normalized forward-slash paths, in declaration order.
 */
export function normalizeCommitPaths(values: readonly string[]): string[] {
  if (values.length === 0) throw new Error('Project commit requires at least one commit path')
  if (values.length > MAX_COMMIT_PATHS) {
    throw new Error(`Project commit accepts at most ${MAX_COMMIT_PATHS} commit paths per call`)
  }
  const normalized = new Set<string>()
  for (const value of values) {
    if (value.length === 0 || value.length > MAX_COMMIT_PATH_LENGTH) {
      throw new Error(`Project commit paths must be between 1 and ${MAX_COMMIT_PATH_LENGTH} characters`)
    }
    const parts = value.replaceAll('\\', '/').split('/')
    if (isAbsolute(value) || win32.isAbsolute(value) || value.includes('\0')
      || parts.some(part => part === '' || part === '.' || part === '..' || part.toLowerCase() === '.git')) {
      throw new Error(`Project commit path must be a relative path inside the Worker worktree: ${value}`)
    }
    normalized.add(parts.join('/'))
  }
  return [...normalized]
}

/**
 * Confirm every requested path currently exists as a file inside the Worker
 * worktree. Missing paths refuse here — the registry Service accepts tracked
 * deletions, but this consumer narrows to produced artifacts — and a realpath
 * containment check keeps symlinked entries from naming anything outside the
 * checkout. Pure filesystem probes: no Git runs.
 * @param worktreePath - Canonical Worker worktree path.
 * @param paths - Normalized commit paths.
 */
async function requirePathsInWorktree(worktreePath: string, paths: readonly string[]): Promise<void> {
  const root = await realpathNormalize(worktreePath)
  for (const path of paths) {
    const absolute = join(worktreePath, path)
    let stats
    try {
      stats = await lstat(absolute)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        throw new Error(`Project commit path does not exist in the Worker worktree: ${path}`)
      }
      /* v8 ignore next -- filesystem faults other than ENOENT have no natural trigger in a private temporary root */
      throw error
    }
    if (!stats.isFile()) throw new Error(`Project commit paths must name files, not directories: ${path}`)
    const real = await realpathNormalize(absolute)
    if (!real.startsWith(`${root}\\`) && !real.startsWith(`${root}/`)) {
      throw new Error(`Project commit path must stay inside the Worker worktree: ${path}`)
    }
  }
}

/**
 * Derive the commit message: the model's plain single-line text when
 * provided, otherwise the deterministic task-and-goal form.
 * @param taskId - The committed task.
 * @param goalId - The open Goal the task belongs to.
 * @param provided - Optional model-provided message text.
 * @returns The single-line commit message passed to the Service as one argument.
 */
function deriveMessage(taskId: TaskId, goalId: unknown, provided: string | undefined): string {
  if (provided === undefined) return `Commit task ${String(taskId)} (goal ${String(goalId)})`
  const message = provided.trim()
  if (message.length === 0) throw new Error('Project commit message must not be empty when provided')
  if (message.length > MAX_MESSAGE_LENGTH) {
    throw new Error(`Project commit message must be at most ${MAX_MESSAGE_LENGTH} characters`)
  }
  if (/\p{C}/u.test(message)) throw new Error('Project commit message must be plain single-line text')
  return message
}

/**
 * Register `project_commit` into the delivery consumer's tool family. Throws
 * at apply time when the loaded worktree-registry provider lacks the commit
 * Service (a stale provider build): the consumer never degrades to shell Git,
 * and a deployment that expects controlled commit must not silently strand
 * Workers with written-but-uncommittable files.
 * @param deps - Shared delivery-consumer closure state and the commit Service.
 */
export function registerProjectCommitTool(deps: ProjectCommitDeps): void {
  // Deployment-mismatch gate, not a static-interface re-check: a stale
  // provider build can still claim the merged types at compile time.
  if (typeof deps.registry.commit !== 'function') {
    throw new Error('Project commit requires the worktree-registry host commit Service; '
      + 'merge the dsh-worktree-registry commit Service before applying this consumer')
  }
  const git = async (path: string, signal: AbortSignal, ...args: string[]): Promise<string> =>
    (await execFileAsync(deps.config.gitExecutable, ['-C', path, ...args], {
      env: deps.gitEnvironment(), signal, windowsHide: true,
      timeout: deps.config.gitTimeoutMs, maxBuffer: deps.config.gitMaxOutputBytes, encoding: 'utf8',
    })).stdout
  deps.tools.register(defineTool({
    name: 'project_commit',
    description: 'Commit exactly the changed artifact files of your assigned task in your Worker worktree through the '
      + 'host-controlled commit. Pass the explicit relative paths of the files you produced; the host only commits '
      + 'paths registered for your task, verifies each one in the worktree, and refuses anything else you name, '
      + 'while your unfinished background jobs exist, or with forged identities. Pending changes that stay after the '
      + 'commit are unverified; call project_deliver only once the worktree is fully clean.',
    parameters: {
      taskId: { type: 'string', required: true, description: 'Your assigned task.' },
      paths: {
        type: 'array', required: true, items: { type: 'string' },
        description: 'The artifact file paths you changed, relative to the worktree root.',
      },
      message: {
        type: 'string',
        description: 'Optional single-line commit message; the host derives one from the task and goal otherwise.',
      },
    },
    output: {
      schema: { type: 'object' as const, additionalProperties: false, properties: {
        taskId: { type: 'string' as const, required: true as const }, state: { type: 'string' as const, required: true as const },
        outcome: { type: 'string' as const, required: true as const },
      } },
      render: (_args: unknown, value: { taskId: string; state: string; outcome: string }) => [{ type: 'text' as const,
        text: `Task ${value.taskId}: ${value.state}; ${value.outcome}.` }],
    },
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      if (args.taskId.trim() !== args.taskId) throw new Error('Task id must be trimmed')
      const taskId = TaskId(args.taskId)
      return await deps.serial(String(taskId), async () => {
        const initial = deps.resolveWorker(exec.agent, taskId, exec.signal)
        if (initial.task.state !== 'developing') throw new Error('Project commit requires a developing task')
        const guard = () => {
          if (deps.resolveWorker(exec.agent, taskId, exec.signal).signature !== initial.signature) {
            throw new Error('Commit authority changed')
          }
        }
        const paths = normalizeCommitPaths(args.paths)
        const scope = deps.commitPathsByTask.get(String(taskId))
        if (scope === undefined) {
          throw new Error(`Project commit requires a host-registered commit path scope for task ${String(taskId)}`)
        }
        const scopeSet = new Set(scope)
        const outside = paths.filter(path => !scopeSet.has(path))
        if (outside.length > 0) {
          throw new Error('Project commit paths outside the host-registered commit path scope for task '
            + `${String(taskId)}: ${JSON.stringify(outside)}`)
        }
        await requirePathsInWorktree(initial.sourcePath, paths)
        guard()
        // Quiescence gate, checked twice — before the HEAD observation and
        // again before the Service call. A live background job of the caller
        // may still write the worktree, and nothing here can prove otherwise,
        // so a non-terminal job refuses the commit instead of racing it; jobs
        // are never killed by this tool. The per-task serial chain excludes
        // the commit/deliver/review family, not arbitrary writers: the job
        // gate is evidence at an instant, not an operating-system lock, and a
        // job appearing after the second check surfaces through the Service's
        // own verification or the delivery gate.
        const requireQuiescence = () => {
          const registry = deps.jobs()
          if (registry === undefined) {
            throw new Error('Project commit requires the background job registry to prove quiescence; '
              + 'mount a dsh-jobs implementation in this composition')
          }
          const live = registry.list(exec.agent)
            .filter(snapshot => snapshot.status === 'running' || snapshot.status === 'stopping')
          if (live.length > 0) {
            throw new Error(`Project commit requires a quiet worktree: ${live.length} non-terminal background `
              + 'job(s) may still write it; wait for them to settle or cancel them before committing')
          }
        }
        requireQuiescence()
        guard()
        // One read-only Git command, against the owner workspace resolved from
        // registry rows — never the Worker checkout: a pure ref lookup of the
        // registered branch with no index refresh, filter execution, or
        // fsmonitor involvement, guarded by --end-of-options. One observation,
        // carried through the request unchanged: the registry Service
        // re-verifies branch and expected HEAD inside its pinned linked
        // gitdir, so a race or a redirected checkout surfaces as a Service
        // refusal. The Service remains the final Git owner.
        const owner = deps.resolveOwnerHead(initial.sourceId)
        const observed = (await git(owner.ownerPath, exec.signal,
          'rev-parse', '--verify', '--end-of-options', `refs/heads/${owner.branch}`)).trim()
        /* v8 ignore next 2 -- Git --verify either errors or prints a full object id; a non-OID success has no natural trigger */
        if (!FULL_OBJECT_ID.test(observed)) {
          throw new Error('Project commit requires a full HEAD object ID to authorize the commit')
        }
        const expectedHead = brandString<WorktreeCommitId>(observed)
        requireQuiescence()
        guard()
        const request: WorktreeCommitRequest = {
          id: initial.sourceId,
          holder: WorktreeLockHolder(String(initial.worker.sessionId)),
          expectedHead,
          paths,
          message: deriveMessage(taskId, initial.goal.goalId, args.message),
        }
        const result = await deps.registry.commit(request, exec.signal)
        // `clean` is the Service's own hardened post-commit observation. A
        // clean tree is host evidence the commit consumed exactly the pending
        // work of the requested scope; remaining changes cannot be classified
        // without another Git observation, so they are reported unverified
        // instead of guessed — the delivery gate refuses until they resolve.
        return {
          taskId: String(taskId),
          state: initial.task.state,
          outcome: result.clean
            ? `committed ${String(result.head)}; worktree clean`
            : `committed ${String(result.head)}; pending changes remain and their ownership is unverified; `
              + 'resolve them through the host before project_deliver',
        }
      })
    },
    presentCall: args => ({ card: 'generic', title: `Commit task ${args.taskId}` }), presentResult: () => ({ card: 'generic' }),
  }))
}
