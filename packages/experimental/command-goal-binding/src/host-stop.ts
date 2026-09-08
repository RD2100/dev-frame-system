/**
 * Real host stop adapters for the goal-binding composition's stop chain: the
 * host-verified project tree face (dispatch lineage) and the owner-checked
 * single-writer release over the worktree registry. The apply face mounts
 * them whenever the corresponding host services are present on the fiber, so
 * a `stopChain` deployment gets real wiring instead of the fail-closed
 * unwired defaults; a fiber without the services keeps exactly the previous
 * fail-closed behavior. No process inventory is mounted: until a real
 * capture feed owns descendant processes, an empty inventory would fabricate
 * quiescence, so the chain fails closed on the absent face instead.
 * @module @deepseek-ai/dsh-experimental-command-goal-binding/host-stop
 */

import { realpathSync } from 'node:fs'
import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import type { Context } from '@deepseek-ai/cordis'
import type { WorkspaceRegistry } from '@deepseek-ai/dsh-workspace'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { ResolvedCommandGoalBindingConfig } from './config.ts'
import type { GoalBindingCompositionStores } from './composition.ts'

/**
 * Canonicalize a directory through the `fs.realpath` canon — the same canon
 * the workspace registry stores its rows under.
 * @param path - the directory spelling to canonicalize.
 * @returns the canonical absolute path.
 */
function canonicalDirectory(path: string): string {
  try {
    return realpathSync(path)
  } catch (error) {
    // A directory that no longer exists cannot be the configured worktree;
    // comparing the raw spelling keeps the row match refused by the ordinary
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
 * Whether one live agent belongs to the dispatch tree rooted at `root`: its
 * session's `parentSession` chain — walked through live registry agents only —
 * reaches the root's session. The walk is cycle-bounded; a lineage that
 * leaves the live registry is unprovable and excludes the candidate, so an
 * independent-worktree worker with an explicit parent binding is included and
 * a foreign project's session is never drained.
 * @param agent - the candidate agent.
 * @param root - the receiving root agent whose tree the chain drains.
 * @param registry - the live agent registry the walk resolves parents through.
 * @returns whether the candidate is the root or one of its descendants.
 */
function belongsToTree(agent: Agent, root: Agent, registry: AgentRegistry): boolean {
  let current = agent
  const visited = new Set<string>([String(agent.id)])
  while (true) {
    if (current.id === root.id) return true
    const parentId = current.session.header.parentSession
    if (parentId === undefined || visited.has(String(parentId))) return false
    visited.add(String(parentId))
    const parent = registry.get(parentId)
    if (parent === undefined) return false
    current = parent
  }
}

/**
 * Build the host-verified project tree face: the receiving root plus every
 * live dispatch-lineage descendant, re-resolved on every call so the chain's
 * drain and its recovery re-observation see the same live inventory.
 * Ownership is the binding, not the working directory — sessions of the same
 * repository outside the lineage are never drained.
 * @param agents - the fiber's agent registry (`ctx.agents`).
 * @returns the tree face for the composition's stop store.
 */
export function createHostStopTree(agents: AgentRegistry): (root: Agent) => readonly Agent[] {
  return root => agents.list().filter(agent => belongsToTree(agent, root, agents))
}

/** The host services the writer release needs; apply resolves them from the fiber. */
export interface HostWriterReleaseDependencies {
  readonly workspaceRegistry: WorkspaceRegistry
  readonly worktreeRegistry: WorktreeRegistry
}

/**
 * Build the owner-checked writer release over the worktree registry's
 * single-writer binding for the configured worktree. The face performs the
 * full owner gate and settles only when the registry has provably released
 * the binding: the worktree must be a registered row of the workspace that
 * owns the configured root, an unbound row is an already-completed release
 * (the confirmed-stop recovery path may re-enter), and a bound row releases
 * only when its holder is the session id of a live project-tree agent — a
 * foreign writer is never released. The asynchronous `unbind` is awaited, so
 * a rejected release propagates to the stop chain, which reports
 * `needs_attention` with the writer retained; the durable registry row stays
 * the truth and the repeat stop re-enters the release.
 * @param dependencies - the fiber's workspace and worktree registries.
 * @param options - the configured worktree root and the verified tree face.
 * @returns the release face; the receiving root argument scopes the live
 *   sessions that may own the writer.
 */
export function createHostWriterRelease(
  dependencies: HostWriterReleaseDependencies,
  options: {
    readonly workspaceRoot: string
    readonly tree: (root: Agent) => readonly Agent[]
  },
): (root: Agent) => Promise<void> {
  const canonicalRoot = canonicalDirectory(options.workspaceRoot)
  return async (root: Agent) => {
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
    const holders = new Set(options.tree(root).map(agent => WorktreeLockHolder(String(agent.session.id))))
    if (!holders.has(row.lockedBy)) {
      throw new Error(`the worktree writer '${String(row.lockedBy)}' is not a live project tree session; the writer release is refused`)
    }
    await dependencies.worktreeRegistry.unbind(row.id, row.lockedBy)
  }
}

/**
 * Resolve the composition's stop store from the fiber: the tree face mounts
 * when the fiber carries the agent registry, and the release face mounts
 * when the configuration names a worktree root and the fiber carries the
 * workspace and worktree registries. No process face mounts — until a real
 * capture feed owns descendant processes, an empty inventory would fabricate
 * quiescence, so the chain fails closed on the absent face. Absent faces stay
 * absent so the chain fails closed exactly as before.
 * @param ctx - the plugin fiber's context.
 * @param config - the resolved deployment configuration.
 * @returns the stop store for the composition constructor.
 */
export function resolveHostStopAdapters(
  ctx: Context,
  config: ResolvedCommandGoalBindingConfig,
): NonNullable<GoalBindingCompositionStores['stop']> {
  // Optional reads: the stop faces are host-wired when the fiber carries the
  // registries, not declared injections — a fiber without them keeps the
  // fail-closed unwired chain.
  const agents = ctx.get('agents') as AgentRegistry | undefined
  const stop: {
    tree?: (root: Agent) => readonly Agent[]
    releaseWriter?: (root: Agent) => Promise<void>
  } = {}
  if (agents !== undefined) {
    const tree = createHostStopTree(agents)
    stop.tree = tree
    const workspaceRoot = config.workspaceRoot
    const workspaceRegistry = ctx.get('workspaceRegistry') as WorkspaceRegistry | undefined
    const worktreeRegistry = ctx.get('worktreeRegistry') as WorktreeRegistry | undefined
    if (workspaceRoot !== undefined && workspaceRegistry !== undefined && worktreeRegistry !== undefined) {
      // The release face receives the receiving root at call time and builds
      // its owner gate from the live tree of that root.
      stop.releaseWriter = createHostWriterRelease(
        { workspaceRegistry, worktreeRegistry },
        { workspaceRoot, tree },
      )
    }
  }
  return stop
}
