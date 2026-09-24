/** Read-only projection of the current Cordis Loader plugin entries. */

import type { Context, FiberState } from '@deepseek-ai/cordis'
import type { Entry } from '@deepseek-ai/cordis-plugin-loader'
import type {} from '@deepseek-ai/cordis-plugin-loader'
// Type-only: the optional agent-preset roster resolved through `ctx.get`.
import type {} from '@deepseek-ai/dsh-agent-presets'
import { TypertRemoteService, Remote } from '@deepseek-ai/dsh-typert-protocol'
// Typert-generated ./typert and ./remote artifacts import Zod at runtime.
import type {} from 'zod'
import type {
  AgentPresetPluginGroup,
  PluginEntryId,
  PluginFiberPhase,
  PluginInventoryEntry,
  PluginInventorySnapshot,
  McpCreateRequest,
  McpInventorySnapshot,
  McpRemoveRequest,
  McpTestRequest,
  McpTestValue,
  McpUpdateRequest,
} from './types.ts'

export type * from './types.ts'

/** Brand an existing Loader-tree entry id at the owning boundary. */
function pluginEntryId(value: string): PluginEntryId {
  return value as PluginEntryId
}

/** Runtime mirror: FiberState is a cross-package const enum. */
const FIBER_STATE = {
  PENDING: 0 as FiberState.PENDING,
  LOADING: 1 as FiberState.LOADING,
  ACTIVE: 2 as FiberState.ACTIVE,
  FAILED: 3 as FiberState.FAILED,
  DISPOSED: 4 as FiberState.DISPOSED,
  UNLOADING: 5 as FiberState.UNLOADING,
} as const

/** Complete public projection of Cordis Fiber states. */
const FIBER_PHASE = {
  [FIBER_STATE.PENDING]: 'pending',
  [FIBER_STATE.LOADING]: 'loading',
  [FIBER_STATE.ACTIVE]: 'active',
  [FIBER_STATE.FAILED]: 'failed',
  [FIBER_STATE.DISPOSED]: null,
  [FIBER_STATE.UNLOADING]: 'unloading',
} as const satisfies Record<FiberState, PluginFiberPhase>

/** Remote-only service exposing the Loader's current non-group entry state. */
export class PluginInventoryGateway extends TypertRemoteService {
  static inject = ['loader']

  constructor(ctx: Context) {
    super(ctx, 'pluginInventory')
  }

  /**
   * Read the Loader directly on every call. Cordis's internal plugin/status
   * events already maintain Entry.fiber and Fiber.state, so a second cache
   * would only add another lifecycle truth to keep synchronized.
   *
   * When an agent-preset roster is composed, the snapshot also carries each
   * preset's composition rows, because those rows — not the Loader's own
   * entries — are where a deployment that mounts the roster runs its
   * model-facing plugins.
   * @returns Current non-group Loader entries in Loader order, with per-preset
   * compositions when a roster is composed.
   */
  @Remote('list')
  async list(): Promise<PluginInventorySnapshot> {
    const entries: PluginInventoryEntry[] = []
    for (const entry of this.ctx.loader.entries()) {
      if (entry.options.group) continue
      entries.push({
        entryId: pluginEntryId(entry.id),
        moduleName: entry.options.name,
        enabled: !entry.disabled,
        fiberPhase: entry.fiber === undefined ? null : FIBER_PHASE[entry.fiber.state],
      })
    }
    const presets = this.ctx.get('agentPresets')
    if (presets === undefined) return { entries }
    const agentPresets: AgentPresetPluginGroup[] = (await presets.compositionInventory()).map(
      composition => ({
        ...composition,
        rows: composition.rows.map(({ fiberState, ...row }) => ({
          ...row,
          fiberPhase: fiberState === undefined ? null : FIBER_PHASE[fiberState],
        })),
      }),
    )
    return { entries, agentPresets }
  }

  /**
   * List configured MCP clients and redact credentials before returning them.
   * @returns the current MCP Loader entries.
   */
  @Remote('listMcp')
  listMcp(): McpInventorySnapshot {
    return { servers: [...this.ctx.loader.entries()].filter(isMcpEntry).map(projectMcpEntry) }
  }

  /**
   * Add one MCP client to the live Loader tree.
   * @param request - validated MCP transport configuration.
   * @returns the created Loader entry id.
   */
  @Remote('createMcp')
  async createMcp(request: McpCreateRequest): Promise<{ entryId: PluginEntryId }> {
    const config = validateMcpConfig(request.config)
    const entryId = await this.ctx.loader.create({
      name: MCP_MODULE,
      config,
    })
    return { entryId: pluginEntryId(entryId) }
  }

  /**
   * Replace one MCP client configuration and restart its fiber.
   * @param request - entry id and replacement configuration.
   */
  @Remote('updateMcp')
  async updateMcp(request: McpUpdateRequest): Promise<void> {
    const entry = this.ctx.loader.resolve(request.entryId)
    if (!isMcpEntry(entry)) throw new Error(`pluginInventory: entry "${request.entryId}" is not an MCP client`)
    await this.ctx.loader.update(request.entryId, { config: validateMcpConfig(request.config) })
  }

  /**
   * Remove one MCP client from the live Loader tree.
   * @param request - MCP Loader entry id.
   */
  @Remote('removeMcp')
  async removeMcp(request: McpRemoveRequest): Promise<void> {
    const entry = this.ctx.loader.resolve(request.entryId)
    if (!isMcpEntry(entry)) throw new Error(`pluginInventory: entry "${request.entryId}" is not an MCP client`)
    await this.ctx.loader.remove(request.entryId)
  }

  /**
   * Probe an MCP configuration by mounting and immediately disposing it.
   * @param request - transport configuration to probe.
   * @returns connection and tool-discovery outcome.
   */
  @Remote('testMcp')
  async testMcp(request: McpTestRequest): Promise<McpTestValue> {
    const config = validateMcpConfig(request.config)
    let entryId: string | undefined
    try {
      entryId = await this.ctx.loader.create({ name: MCP_MODULE, config: { ...config, failOnStartupError: true } })
      return { ok: true, message: 'MCP server connected and tool discovery completed' }
    } catch (error: unknown) {
      return { ok: false, message: error instanceof Error ? error.message : String(error) }
    } finally {
      if (entryId !== undefined) await this.ctx.loader.remove(entryId)
    }
  }
}

const MCP_MODULE = '@deepseek-ai/dsh-mcp-client'

function isMcpEntry(entry: { options: { name: string; group?: boolean | null } }): boolean {
  return entry.options.group !== true && entry.options.name === MCP_MODULE
}

function validateMcpConfig(config: Record<string, unknown>): Record<string, unknown> {
  if (typeof config !== 'object' || config === null || Array.isArray(config)) throw new TypeError('MCP config must be an object')
  if (config.transport !== 'stdio' && config.transport !== 'streamable-http') throw new TypeError('MCP config transport must be stdio or streamable-http')
  if (typeof config.serverName !== 'string' || !/^[A-Za-z0-9_-]{1,32}$/u.test(config.serverName)) throw new TypeError('MCP serverName must match [A-Za-z0-9_-]{1,32}')
  if (config.transport === 'stdio' && typeof config.command !== 'string') throw new TypeError('stdio MCP config requires command')
  if (config.transport === 'streamable-http' && typeof config.url !== 'string') throw new TypeError('streamable-http MCP config requires url')
  return { ...config }
}

function projectMcpEntry(entry: Entry): import('./types.ts').McpServerEntry {
  const config = entry.options.config && typeof entry.options.config === 'object' ? entry.options.config as Record<string, unknown> : {}
  const safeConfig = { ...config }
  for (const key of ['env', 'headers']) {
    if (safeConfig[key] && typeof safeConfig[key] === 'object') {
      safeConfig[key] = Object.fromEntries(Object.keys(safeConfig[key] as object).map(name => [name, '••••••']))
    }
  }
  return {
    entryId: pluginEntryId(entry.id),
    serverName: typeof config.serverName === 'string' ? config.serverName : entry.id,
    transport: config.transport === 'stdio' || config.transport === 'streamable-http' ? config.transport : 'unknown',
    enabled: !entry.disabled,
    fiberPhase: entry.fiber === undefined ? null : FIBER_PHASE[entry.fiber.state],
    config: safeConfig,
  }
}

export default PluginInventoryGateway
