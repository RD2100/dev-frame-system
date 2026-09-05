/**
 * DevFrame three-tier hierarchy assembly: the spawn-time role policy that turns
 * the delegation seam's existing mechanisms into the product rule "the
 * controller builds leads, a lead builds workers, a worker builds nothing".
 *
 * The seam already enforces both halves at the executor: a `toolFilter` deny
 * removes the spawn tool from the child's prompt AND refuses its execution
 * (`UNKNOWN_TOOL` at the executor, not merely schema absence), and the
 * delegation-depth budget refuses a spawn whose resolved child depth would
 * exceed the cap (`SubagentDepthError` before any child is published). This
 * module only fixes WHICH overrides a DevFrame parent passes for each child
 * tier, so every tier-1 and tier-2 spawn carries the same policy.
 *
 * @module @deepseek-ai/dsh-experimental-devframe/hierarchy
 */

/**
 * The child tier a DevFrame parent spawns. The controller itself is the root
 * (depth 0) and is never spawned through this policy.
 */
export type DevFrameSpawnTier = 'lead' | 'worker'

/**
 * Absolute delegation-depth budget of the DevFrame tree: controller = 0,
 * lead = 1, worker = 2. Every DevFrame spawn passes this as `maxDepth`, so a
 * worker (depth 2) that somehow reaches a spawn-capable tool is still refused
 * by `SubagentDepthError` — independent of the worker's tool filter.
 */
export const DEVFRAME_DELEGATION_DEPTH_BUDGET = 2

/**
 * The model-facing name of the delegation tool whose spawn capability workers
 * lose. Matches the delegation tool's default `toolName`; deployments that
 * renamed it pass the deployed name through {@link devframeSpawnOverrides}.
 */
export const DEVFRAME_SPAWN_TOOL_NAME = 'subagent'

/**
 * Spawn-request overrides one DevFrame parent merges into its delegation
 * start request (`SubagentStartRequest`) for a child of the given tier. The
 * shape is a structural subset of the delegation request fields, so callers
 * spread it verbatim into `request`.
 */
export interface DevFrameSpawnOverrides {
  /** The DevFrame tree's absolute depth budget. */
  readonly maxDepth: number
  /** Tool restriction for the child, present only for workers. */
  readonly toolFilter?: { readonly deny: readonly string[] }
}

/**
 * Resolve the spawn overrides a DevFrame parent passes for one child tier.
 * A lead keeps the spawn capability (it must build workers) and only carries
 * the depth budget; a worker loses the spawn tool entirely and carries the
 * same budget as its second, independent refusal path. The deny filter names
 * ONLY the spawn tool: a worker keeps `send_message` and the control tools so
 * it can report to its lead over the authorized parent-child routes.
 * @param tier - the tier of the child being spawned.
 * @param options - deployment overrides, notably a renamed delegation tool.
 * @returns detached overrides to spread into the delegation request.
 */
export function devframeSpawnOverrides(
  tier: DevFrameSpawnTier,
  options: { readonly spawnToolName?: string } = {},
): DevFrameSpawnOverrides {
  const maxDepth = DEVFRAME_DELEGATION_DEPTH_BUDGET
  if (tier === 'lead') return { maxDepth }
  return { maxDepth, toolFilter: { deny: [options.spawnToolName ?? DEVFRAME_SPAWN_TOOL_NAME] } }
}
