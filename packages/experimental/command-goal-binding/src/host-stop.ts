/** Host-owned lineage, resource drainage, and owner-checked writer release. */

import { realpathSync } from 'node:fs'
import type { Agent, AgentRegistry } from '@deepseek-ai/dsh-agent'
import type { Context } from '@deepseek-ai/cordis'
import type { WorkspaceRegistry } from '@deepseek-ai/dsh-workspace'
import { WorktreeLockHolder } from '@deepseek-ai/dsh-worktree-registry'
import type { WorktreeRegistry } from '@deepseek-ai/dsh-worktree-registry'
import type { StopProcess } from '@deepseek-ai/dsh-experimental-devframe'
import type { SubagentRuntime } from '@deepseek-ai/dsh-subagent'
import type { TerminalOwnershipRegistry } from '@deepseek-ai/dsh-terminal'
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

/**
 * Enumerate provider-owned cleanup for exactly the selected dispatch lineage.
 * Each service first fences its owner's admission, even when presently idle;
 * only successful cleanup plus a fresh activity observation removes its entry.
 * @param agents - live registry used to resolve exact owners and lineage.
 * @param subagents - service retaining one-shot starts through run disposal.
 * @param terminals - Host directory fencing every terminal provider for the exact owner.
 * @returns scoped drain inventory and a resume preflight that defers admission until its returned closure runs.
 */
export function createHostStopResources(
  agents: AgentRegistry,
  subagents: SubagentRuntime,
  terminals: TerminalOwnershipRegistry,
): {
  processes: (root: Agent) => readonly StopProcess[]
  prepareResumeResources: (root: Agent) => () => void
} {
  const drainedRuns = new WeakSet<Agent>()
  const drainedTerminals = new WeakSet<Agent>()
  const tree = createHostStopTree(agents)
  const processes = (root: Agent): readonly StopProcess[] => tree(root).flatMap((owner) => {
    const resources: StopProcess[] = []
    if (!drainedRuns.has(owner) || subagents.hasOwnerActivity(owner)) {
      resources.push({
        ownerSession: owner.session.id,
        label: 'owned subagents',
        operationId: `subagents:${owner.session.id}`,
        drain: async () => {
          await subagents.drainOwnedRuns(owner)
          drainedRuns.add(owner)
        },
      })
    }
    if (!drainedTerminals.has(owner) || terminals.hasOwnerActivity(owner)) {
      resources.push({
        ownerSession: owner.session.id,
        label: 'owned terminals',
        operationId: `terminals:${owner.session.id}`,
        drain: async () => {
          await terminals.drainOwned(owner)
          drainedTerminals.add(owner)
        },
      })
    }
    return resources
  })
  return {
    processes,
    prepareResumeResources: (root) => {
      if (agents.get(root.id) !== root) throw new Error('stop resource owner is not live')
      const owners = tree(root)
      // Complete preflight before any service admission changes. These checks
      // and reopen operations are synchronous and invoke no user callbacks.
      const prepare = () => owners.map(owner => subagents.prepareReopenOwnedRuns(owner))
      prepare()
      const reopenTerminals = terminals.prepareReopenOwners(owners)
      return () => {
        if (agents.get(root.id) !== root) throw new Error('stop resource owner is not live')
        const current = tree(root)
        if (current.length !== owners.length || current.some(owner => !owners.includes(owner))) {
          throw new Error('stop resource owner tree changed during resume preparation')
        }
        const reopen = prepare()
        reopenTerminals()
        for (const commit of reopen) commit()
        for (const owner of owners) {
          drainedRuns.delete(owner)
          drainedTerminals.delete(owner)
        }
      }
    },
  }
}

/** The host services the writer release and acquisition need; apply resolves them from the fiber. */
export interface HostWriterReleaseDependencies {
  readonly workspaceRegistry: WorkspaceRegistry
  readonly worktreeRegistry: WorktreeRegistry
}

/** The host services the writer acquisition needs, including the live-owner gate. */
export interface HostWriterAcquireDependencies {
  readonly agents: AgentRegistry
  readonly workspaceRegistry: WorkspaceRegistry
  readonly worktreeRegistry: WorktreeRegistry
}

/**
 * Build the owner-checked writer release over the worktree registry's
 * single-writer binding for the configured worktree. The face performs the
 * full owner gate and settles only when the registry has provably released
 * the binding: the worktree must be a registered row of the configured
 * workspace, an unbound row is an already-completed release
 * (the confirmed-stop recovery path may re-enter), and a bound row releases
 * only when its holder is the session id of a live project-tree agent — a
 * foreign writer is never released. The asynchronous `unbind` is awaited, so
 * a rejected release propagates to the stop chain, which reports
 * `needs_attention` with the writer retained; the durable registry row stays
 * the truth and the repeat stop re-enters the release.
 * @param dependencies - the fiber's workspace and worktree registries.
 * @param options - the configured workspace id, the configured worktree
 *   root, and the verified tree face.
 * @returns the release face; the receiving root argument scopes the live
 *   sessions that may own the writer.
 */
export function createHostWriterRelease(
  dependencies: HostWriterReleaseDependencies,
  options: {
    readonly workspaceId: ResolvedCommandGoalBindingConfig['workspaceId']
    readonly workspaceRoot: string
    readonly tree: (root: Agent) => readonly Agent[]
  },
): (root: Agent) => Promise<void> {
  const canonicalRoot = canonicalDirectory(options.workspaceRoot)
  return async (root: Agent) => {
    const workspace = dependencies.workspaceRegistry.list()
      .find(entry => entry.id === options.workspaceId)
    if (workspace === undefined) {
      throw new Error(`the configured workspace '${options.workspaceId}' is not registered; the writer release is refused`)
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
 * Build the owner-checked writer acquisition — the resume face of the
 * release. After a confirmed stop released the binding, the same receiving
 * root re-takes it under the host's fresh authorization: the receiving root
 * must be live, the worktree must be a registered row of the configured
 * workspace, and the registry's `bind` accepts an unbound row
 * or a re-bind by the same holder while refusing to displace a foreign
 * writer with `WorktreeLockError` (`already-locked`). The refusal propagates,
 * so a resume under a foreign-held worktree fails without stealing the
 * binding; the durable row stays the truth and the repeat resume re-enters
 * the acquisition.
 * @param dependencies - the fiber's agent, workspace, and worktree registries.
 * @param options - the configured workspace id and worktree root.
 * @returns the acquisition face; the receiving root argument names the
 *   writer that re-takes the binding.
 */
export function createHostWriterAcquire(
  dependencies: HostWriterAcquireDependencies,
  options: {
    readonly workspaceId: ResolvedCommandGoalBindingConfig['workspaceId']
    readonly workspaceRoot: string
  },
): (root: Agent) => Promise<void> {
  const canonicalRoot = canonicalDirectory(options.workspaceRoot)
  return async (root: Agent) => {
    if (dependencies.agents.get(root.id) !== root) {
      throw new Error('the receiving root is not a live agent; the writer acquisition is refused')
    }
    const workspace = dependencies.workspaceRegistry.list()
      .find(entry => entry.id === options.workspaceId)
    if (workspace === undefined) {
      throw new Error(`the configured workspace '${options.workspaceId}' is not registered; the writer acquisition is refused`)
    }
    const row = dependencies.worktreeRegistry.list(workspace.id)
      .find(entry => sameDirectory(entry.path, canonicalRoot))
    if (row === undefined) {
      throw new Error(`the configured worktree '${canonicalRoot}' has no registered worktree row; the writer acquisition is refused`)
    }
    await dependencies.worktreeRegistry.bind(row.id, WorktreeLockHolder(String(root.session.id)))
  }
}

/**
 * Resolve the composition's stop store from the fiber: the tree face mounts
 * when the fiber carries the agent registry, and the release face mounts
 * when the configuration names a worktree root and the fiber carries the
 * workspace and worktree registries. The resource face requires the one-shot
 * child runtime and the host terminal ownership directory. When the fiber
 * also carries a project controller, the returned `prepareResumeResources`
 * additionally fences its admission: preparation requires the controller
 * lifecycle to be `stopped` or `admission_open` (anything else throws), and
 * the commit rechecks the unchanged lifecycle before reopening resources,
 * starting the project when it prepared from `stopped`. Missing coverage
 * leaves that face absent so stop fails closed.
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
  const agents = ctx.get('agents')
  const subagents = ctx.get('subagents')
  const terminals = ctx.get('terminalOwnership')
  const stop: {
    tree?: (root: Agent) => readonly Agent[]
    processes?: (root: Agent) => readonly StopProcess[]
    prepareResumeResources?: (root: Agent) => () => void
    releaseWriter?: (root: Agent) => Promise<void>
    acquireWriter?: (root: Agent) => Promise<void>
  } = {}
  if (agents !== undefined) {
    if (subagents !== undefined && terminals !== undefined) {
      Object.assign(stop, createHostStopResources(agents, subagents, terminals))
    }
    const tree = createHostStopTree(agents)
    stop.tree = tree
    const workspaceRoot = config.workspaceRoot
    const workspaceRegistry = ctx.get('workspaceRegistry')
    const worktreeRegistry = ctx.get('worktreeRegistry')
    if (workspaceRoot !== undefined && workspaceRegistry !== undefined && worktreeRegistry !== undefined) {
      // The release face receives the receiving root at call time and builds
      // its owner gate from the live tree of that root; the acquisition face
      // gates on the live receiving root itself and names it as the writer.
      stop.releaseWriter = createHostWriterRelease(
        { workspaceRegistry, worktreeRegistry },
        { workspaceId: config.workspaceId, workspaceRoot, tree },
      )
      stop.acquireWriter = createHostWriterAcquire(
        { agents, workspaceRegistry, worktreeRegistry },
        { workspaceId: config.workspaceId, workspaceRoot },
      )
    }
  }
  const controller = ctx.get('projectController')
  const prepareResources = stop.prepareResumeResources
  if (controller !== undefined && prepareResources !== undefined) {
    stop.prepareResumeResources = (root) => {
      const lifecycle = controller.lifecycle
      if (lifecycle !== 'stopped' && lifecycle !== 'admission_open') {
        throw new Error(`project admission cannot resume from ${lifecycle}`)
      }
      const commit = prepareResources(root)
      return () => {
        if (controller.lifecycle !== lifecycle) throw new Error('project admission changed during resume preparation')
        commit()
        if (lifecycle === 'stopped') controller.startProject()
      }
    }
  }
  return stop
}
