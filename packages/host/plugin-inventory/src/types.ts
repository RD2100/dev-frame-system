import type { Branded } from '@deepseek-ai/dsh-brand'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'

/** Stable Loader-tree identity of one configured plugin entry. */
export type PluginEntryId = Branded<'PluginEntryId'>

/** Lifecycle state of an entry's root Fiber, or null when it has no live root Fiber. */
export type PluginFiberPhase =
  | 'pending'
  | 'loading'
  | 'active'
  | 'failed'
  | 'unloading'
  | null

/** One non-group Loader entry exposed to trusted clients. */
export interface PluginInventoryEntry {
  readonly entryId: PluginEntryId
  /** Exact module specifier imported by the Loader entry. */
  readonly moduleName: string
  /** Effective Loader enablement, including disabled ancestor groups. */
  readonly enabled: boolean
  readonly fiberPhase: PluginFiberPhase
}

/** Effective enablement of one preset composition row. */
export type PresetPluginEnablement = boolean | 'conditional'

/** One plugin row an agent preset's composition names. */
export interface AgentPresetPluginRow {
  /** Composition row id, or null when the row declares none. */
  readonly entryId: string | null
  /** Module specifier the row names. */
  readonly moduleName: string
  /**
   * Effective enablement, including disabled ancestor groups. `'conditional'`
   * marks a `!!js` disabled expression on a composition no session has
   * mounted, which only a Loader context can decide.
   */
  readonly enabled: PresetPluginEnablement
  /** The row's own `!!js` disabled expression, when it carries one. */
  readonly condition?: string
  /** Root-fiber phase when the composition is live; null otherwise. */
  readonly fiberPhase: PluginFiberPhase
}

/** One agent preset's identity and flattened composition in the inventory. */
export interface AgentPresetPluginGroup {
  /** Stable preset id. */
  readonly id: string
  /** Whether the deployment ships the preset or the user owns it. */
  readonly trust: 'system' | 'user'
  /** Display name the preset published; a reader falls back to the id. */
  readonly name?: string
  /** Whether a session naming no preset composes this one. */
  readonly isDefault: boolean
  /** Why this preset's composition cannot be read; absent when rows answer. */
  readonly broken?: string
  /** Plugin rows in composition order; empty when the preset is broken. */
  readonly rows: readonly AgentPresetPluginRow[]
}

/** Point-in-time inventory returned by the plugin inventory Remote. */
export interface PluginInventorySnapshot {
  readonly entries: readonly PluginInventoryEntry[]
  /**
   * Per-preset compositions, present only when an agent-preset roster is
   * composed in this deployment.
   */
  readonly agentPresets?: readonly AgentPresetPluginGroup[]
}

/** MCP transport configuration accepted by the management Remote. */
export type McpServerConfig = Readonly<Record<string, JsonValue>>

/** A configured MCP Loader entry with secrets removed from its projection. */
export interface McpServerEntry {
  readonly entryId: PluginEntryId
  readonly serverName: string
  readonly transport: 'stdio' | 'streamable-http' | 'unknown'
  readonly enabled: boolean
  readonly fiberPhase: PluginFiberPhase
  readonly config: McpServerConfig
}

/** MCP management snapshot. */
export interface McpInventorySnapshot {
  readonly servers: readonly McpServerEntry[]
}

/** Create request for one MCP Loader entry. */
export interface McpCreateRequest {
  readonly config: McpServerConfig
}

/** Update request for one MCP Loader entry. */
export interface McpUpdateRequest {
  readonly entryId: PluginEntryId
  readonly config: McpServerConfig
}

/** Remove request for one MCP Loader entry. */
export interface McpRemoveRequest {
  readonly entryId: PluginEntryId
}

/** Request to change one MCP client's effective Loader enablement. */
export interface McpSetEnabledRequest {
  readonly entryId: PluginEntryId
  readonly enabled: boolean
}

/** Connectivity probe request. */
export interface McpTestRequest {
  readonly config: McpServerConfig
}

/** Probe a configured MCP client using its private stored transport values. */
export interface McpTestEntryRequest {
  readonly entryId: PluginEntryId
}

/** Result of an MCP connectivity probe. */
export interface McpTestValue {
  readonly ok: boolean
  readonly message: string
}

/** A user-owned Skill discovered under the durable DSH home. */
export interface SkillManagementEntry {
  readonly name: string
  readonly description: string
  readonly enabled: boolean
  readonly modelInvocable: boolean
  readonly userInvocable: boolean
  readonly whenToUse?: string
}

/** User-owned Skill management snapshot. */
export interface SkillManagementSnapshot {
  readonly skills: readonly SkillManagementEntry[]
}

/** Request to install a user-owned Skill from authored Markdown content. */
export interface SkillInstallRequest {
  readonly name: string
  readonly description: string
  readonly content: string
  readonly whenToUse?: string
}

/** Request to change one user-owned Skill's invocation state. */
export interface SkillSetEnabledRequest {
  readonly name: string
  readonly enabled: boolean
}

/** Request to remove one user-owned Skill. */
export interface SkillRemoveRequest {
  readonly name: string
}

/** Result returned after installing or changing a Skill. */
export interface SkillManagementValue {
  readonly name: string
  readonly enabled: boolean
}
