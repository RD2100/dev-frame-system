/**
 * Real host stop adapters for the goal-binding composition's stop chain: the
 * host-verified project tree face, the captured descendant process inventory,
 * and the owner-checked single-writer release over the worktree registry. The
 * apply face mounts them whenever the corresponding host services are present
 * on the fiber, so a `stopChain` deployment gets real wiring instead of the
 * fail-closed unwired defaults; a fiber without the services keeps exactly
 * the previous fail-closed behavior.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/host-stop
 */

import { realpathSync } from 'node:fs'
import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import type { Context } from '@deepseek-ai/cordis'
import type { WorkspaceRegistry } from '@deepseek-ai/dsh-workspace'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { StopProcess } from '@deepseek-ai/dsh-experimental-devframe'
import type { ResolvedCommandGoalBindingConfig } from './config.ts'
import type { GoalBindingCompositionStores } from './composition.ts'

/**
 * Canonicalize a directory through the `fs.realpath` canon — the same canon
 * the workspace registry stores its rows under — synchronously, because the
 * stop chain's tree and release faces are synchronous.
 * @param path - the directory spelling to canonicalize.
 * @returns the canonical absolute path.
 */
function canonicalDirectory(path: string): string {
  try {
    return realpathSync(path)
  } catch (error) {
    // A directory that no longer exists cannot be the configured worktree;
    // comparing the raw spelling keeps the candidate excluded by the ordinary
    // identity comparison instead of crashing the stop chain. Any other
    // resolution failure (permissions, corruption) stays loud.
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    return path
  }
}

/**
 * Compare two canonical directory spellings as one directory; Windows paths
 * are case-insensitive, POSIX paths are not.
 */
function sameDirectory(left: string, right: string): boolean {
  /* v8 ignore next -- native Windows coverage exercises this platform dispatch; POSIX lanes compare case-sensitively */
  return process.platform === 'win32'
    ? left.toLowerCase() === right.toLowerCase()
    : left === right
}

/**
 * Build the host-verified project tree face: every live agent whose session
 * cwd canonically equals the configured worktree. Worktree identity is the
 * project boundary — agents of other worktrees are never drained — and the
 * chain adds its own live-identity owner filter on top. The face returns a
 * fresh array on every call so the chain's drain and its pre-release
 * re-observation see the same live inventory.
 * @param agents - the fiber's agent registry (`ctx.agents`).
 * @param options - the configured worktree root the project owns.
 * @returns the zero-argument tree face for the composition's stop store.
 */
export function createHostStopTree(
  agents: AgentRegistry,
  options: { readonly workspaceRoot: string },
): () => readonly Agent[] {
  const root = canonicalDirectory(options.workspaceRoot)
  return () => agents.list().filter(agent => {
    const cwd = agent.session.header.cwd
    return cwd !== undefined && sameDirectory(canonicalDirectory(cwd), root)
  })
}

/**
 * The captured descendant process inventory: the host capture point for the
 * stop chain's process drain. Dispatch faces that take ownership of a
 * descendant process record it here; the stop chain drains exactly what the
 * inventory holds, and entries with absent handles reconcile by identity.
 * Capturing the same identity twice replaces the earlier entry so an
 * inventory refresh never duplicates a drain target.
 */
export class HostStopProcessInventory {
  private readonly entries = new Map<string, StopProcess>()

  private key(entry: Pick<StopProcess, 'ownerSession' | 'label' | 'operationId'>): string {
    return `${String(entry.ownerSession)}\u0000${entry.label}\u0000${entry.operationId ?? ''}`
  }

  /**
   * Record one owned process; an entry with the same owner, label, and
   * operation id replaces the earlier record.
   */
  capture(entry: StopProcess): void {
    this.entries.set(this.key(entry), entry)
  }

  /** Forget one captured process by identity; an unknown identity is a no-op. */
  forget(entry: Pick<StopProcess, 'ownerSession' | 'label' | 'operationId'>): void {
    this.entries.delete(this.key(entry))
  }

  /** The current captured processes in capture order. */
  list(): readonly StopProcess[] {
    return [...this.entries.values()]
  }
}

/** The inventories mounted by `resolveHostStopAdapters`, keyed by their fiber. */
const mountedInventories = new WeakMap<Context, HostStopProcessInventory>()

/**
 * The capture point `resolveHostStopAdapters` mounted on the fiber's stop
 * store, so dispatch faces that take ownership of a descendant process can
 * feed it without reaching into the composition. Undefined before the
 * plugin's apply face ran on this fiber.
 * @param ctx - the fiber whose stop store the inventory backs.
 * @returns the mounted inventory, or undefined when it is not mounted.
 */
export function hostStopInventoryOf(ctx: Context): HostStopProcessInventory | undefined {
  return mountedInventories.get(ctx)
}

/** The host services the writer release needs; apply resolves them from the fiber. */
export interface HostWriterReleaseDependencies {
  readonly agents: AgentRegistry
  readonly workspaceRegistry: WorkspaceRegistry
  readonly worktreeRegistry: WorktreeRegistry
  /** The fiber's warning log for a release the registry later refused. */
  readonly log: (message: string) => void
}

/**
 * Build the owner-checked writer release over the worktree registry's
 * single-writer binding for the configured worktree. The synchronous face
 * performs the full owner gate: the worktree must be a registered row of the
 * workspace that owns the configured root, an unbound row is a completed
 * release (the confirmed-stop recovery path may re-enter), and a bound row
 * releases only when its holder is the session id of a live project-tree
 * agent — a foreign writer is never released, and the throw retains the
 * writer for the chain. The registry's `unbind` is asynchronous, so the face
 * hands the checked release to the registry and reports a rejected unbind
 * through the logger: the durable registry row is the release truth, the
 * writer stays bound, and the repeat stop re-enters the release and
 * reconciles against the row.
 * @param dependencies - the fiber's agent, workspace, and worktree registries.
 * @param options - the configured worktree root and the verified tree face
 *   whose live sessions may own the writer.
 * @returns the zero-argument release face for the composition's stop store.
 */
export function createHostWriterRelease(
  dependencies: HostWriterReleaseDependencies,
  options: {
    readonly workspaceRoot: string
    readonly tree: () => readonly Agent[]
  },
): () => void {
  const canonicalRoot = canonicalDirectory(options.workspaceRoot)
  return () => {
    const workspace = dependencies.workspaceRegistry.list()
      .find(entry => sameDirectory(entry.path, canonicalRoot))
    if (workspace === undefined) {
      throw new Error(`the configured worktree '${canonicalRoot}' is not a registered workspace; the writer release is refused`)
    }
    const row = dependencies.worktreeRegistry.list(workspace.id)
      .find(entry => sameDirectory(entry.path, canonicalRoot))
    if (row === undefined) {
      throw new Error(`the configured worktree '${canonicalRoot}' has no registered worktree row; the writer release is refused`)
    }
    if (row.lockedBy === undefined) return
    const holders = new Set(options.tree().map(agent => WorktreeLockHolder(String(agent.session.id))))
    if (!holders.has(row.lockedBy)) {
      throw new Error(`the worktree writer '${String(row.lockedBy)}' is not a live project tree session; the writer release is refused`)
    }
    const holder = row.lockedBy
    void dependencies.worktreeRegistry.unbind(row.id, holder).catch(error => {
      const message = error instanceof Error ? error.message : String(error)
      dependencies.log(
        `command-goal-binding: the writer release for '${canonicalRoot}' failed; the writer remains bound and the next stop re-enters the release: ${message}`,
      )
    })
  }
}

/**
 * Resolve the composition's stop store from the fiber: the process inventory
 * is always mounted (it starts empty), and the tree and release faces mount
 * when the fiber carries the agent, workspace, and worktree registries and
 * the configuration names a worktree root. Absent faces stay absent so the
 * chain fails closed exactly as before.
 * @param ctx - the plugin fiber's context.
 * @param config - the resolved deployment configuration.
 * @returns the stop store for the composition constructor.
 */
export function resolveHostStopAdapters(
  ctx: Context,
  config: ResolvedCommandGoalBindingConfig,
): NonNullable<GoalBindingCompositionStores['stop']> {
  const inventory = new HostStopProcessInventory()
  mountedInventories.set(ctx, inventory)
  const stop: { tree?: () => readonly Agent[]; processes?: () => readonly StopProcess[]; releaseWriter?: () => void } = {
    processes: () => inventory.list(),
  }
  // Optional reads: the stop faces are host-wired when the fiber carries the
  // registries, not declared injections — a fiber without them keeps the
  // fail-closed unwired chain.
  const agents = ctx.get('agents') as AgentRegistry | undefined
  const workspaceRoot = config.workspaceRoot
  if (agents !== undefined && workspaceRoot !== undefined) {
    stop.tree = createHostStopTree(agents, { workspaceRoot })
    const workspaceRegistry = ctx.get('workspaceRegistry') as WorkspaceRegistry | undefined
    const worktreeRegistry = ctx.get('worktreeRegistry') as WorktreeRegistry | undefined
    if (workspaceRegistry !== undefined && worktreeRegistry !== undefined) {
      stop.releaseWriter = createHostWriterRelease(
        {
          agents,
          workspaceRegistry,
          worktreeRegistry,
          log: message => { ctx.logger.warn(message) },
        },
        { workspaceRoot, tree: stop.tree },
      )
    }
  }
  return stop
}
