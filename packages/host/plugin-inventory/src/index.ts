/** Host management surface for Loader plugins, MCP connectors, and user Skills. */

import { lstat, mkdir, readFile, readdir, rename, rm, unlink, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { dirname, join, resolve, sep } from 'node:path'
import { FiberState, type Context } from '@deepseek-ai/cordis'
import type { Entry } from '@deepseek-ai/cordis-plugin-loader'
import type {} from '@deepseek-ai/cordis-plugin-loader'
// Type-only: the optional agent-preset roster resolved through `ctx.get`.
import type {} from '@deepseek-ai/dsh-agent-presets'
import { resolveDshHome } from '@deepseek-ai/dsh-home-paths'
import { TypertRemoteService, Remote } from '@deepseek-ai/dsh-typert-protocol'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
// Typert-generated ./typert and ./remote artifacts import Zod at runtime.
import type {} from 'zod'
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml'
import type {
  AgentPresetPluginGroup,
  PluginEntryId,
  PluginFiberPhase,
  PluginInventoryEntry,
  PluginInventorySnapshot,
  McpCreateRequest,
  McpInventorySnapshot,
  McpRemoveRequest,
  McpSetEnabledRequest,
  McpTestEntryRequest,
  McpTestRequest,
  McpTestValue,
  McpUpdateRequest,
  SkillInstallRequest,
  SkillManagementEntry,
  SkillManagementSnapshot,
  SkillManagementValue,
  SkillRemoveRequest,
  SkillSetEnabledRequest,
  McpServerConfig,
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

  private readonly dshHome = resolveDshHome()
  private readonly mcpStorePath = join(this.dshHome, 'storages', 'mcp-servers.json')
  private readonly restorePromise: Promise<void>
  private writeTail: Promise<void> = Promise.resolve()

  constructor(ctx: Context) {
    super(ctx, 'pluginInventory')
    this.restorePromise = this.restoreMcpStore()
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
  async listMcp(): Promise<McpInventorySnapshot> {
    await this.ensureMcpRestored()
    return { servers: [...this.ctx.loader.entries()].filter(isMcpEntry).map(projectMcpEntry) }
  }

  /**
   * Add one MCP client to the live Loader tree.
   * @param request - validated MCP transport configuration.
   * @returns the created Loader entry id.
   */
  @Remote('createMcp')
  async createMcp(request: McpCreateRequest): Promise<{ entryId: PluginEntryId }> {
    await this.ensureMcpRestored()
    const config = validateMcpConfig(request.config)
    const entryId = await this.ctx.loader.create({
      name: MCP_MODULE,
      config,
    })
    await this.persistMcpStore()
    return { entryId: pluginEntryId(entryId) }
  }

  /**
   * Replace one MCP client configuration and restart its fiber.
   * @param request - entry id and replacement configuration.
   */
  @Remote('updateMcp')
  async updateMcp(request: McpUpdateRequest): Promise<void> {
    await this.ensureMcpRestored()
    const entry = this.ctx.loader.resolve(request.entryId)
    if (!isMcpEntry(entry)) throw new Error(`pluginInventory: entry "${request.entryId}" is not an MCP client`)
    const config = mergeMcpConfig(mcpConfig(entry), request.config)
    await this.ctx.loader.update(request.entryId, { config })
    await this.persistMcpStore()
  }

  /**
   * Remove one MCP client from the live Loader tree.
   * @param request - MCP Loader entry id.
   */
  @Remote('removeMcp')
  async removeMcp(request: McpRemoveRequest): Promise<void> {
    await this.ensureMcpRestored()
    const entry = this.ctx.loader.resolve(request.entryId)
    if (!isMcpEntry(entry)) throw new Error(`pluginInventory: entry "${request.entryId}" is not an MCP client`)
    await this.ctx.loader.remove(request.entryId)
    await this.persistMcpStore()
  }

  /**
   * Enable or disable one MCP client and persist the choice across restarts.
   * @param request - MCP entry id and desired enabled state.
   * @returns A promise that settles after the Loader and durable store agree.
   */
  @Remote('setMcpEnabled')
  async setMcpEnabled(request: McpSetEnabledRequest): Promise<void> {
    await this.ensureMcpRestored()
    const entry = this.ctx.loader.resolve(request.entryId)
    if (!isMcpEntry(entry)) throw new Error(`pluginInventory: entry "${request.entryId}" is not an MCP client`)
    await this.ctx.loader.update(request.entryId, { disabled: !request.enabled })
    await this.persistMcpStore()
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

  /**
   * Probe an existing MCP entry without sending redacted credentials to the client.
   * @param request - MCP entry id to probe.
   * @returns Connection and tool-discovery outcome.
   */
  @Remote('testMcpEntry')
  async testMcpEntry(request: McpTestEntryRequest): Promise<McpTestValue> {
    await this.ensureMcpRestored()
    const entry = this.ctx.loader.resolve(request.entryId)
    if (!isMcpEntry(entry)) throw new Error(`pluginInventory: entry "${request.entryId}" is not an MCP client`)
    const config = mcpConfig(entry)
    const serverName = typeof config.serverName === 'string' ? config.serverName : 'mcp'
    return this.testMcp({
      config: { ...config, serverName: `${serverName.slice(0, 16)}-probe-${randomUUID().slice(0, 8)}` },
    })
  }

  /**
   * List user-owned Skills in the durable DSH home.
   * @returns The managed Skill metadata visible to the settings client.
   */
  @Remote('listSkills')
  async listSkills(): Promise<SkillManagementSnapshot> {
    const skillsRoot = join(this.dshHome, 'skills')
    let names: string[]
    try {
      names = (await readdir(skillsRoot, { withFileTypes: true }))
        .filter(entry => entry.isDirectory() && isSkillName(entry.name))
        .map(entry => entry.name)
    } catch (error: unknown) {
      if (isMissingFile(error)) return { skills: [] }
      throw error
    }
    const skills: SkillManagementEntry[] = []
    for (const name of names.sort()) {
      const parsed = await readManagedSkill(join(skillsRoot, name, 'SKILL.md'), name)
      if (parsed === undefined) continue
      skills.push(projectManagedSkill(parsed))
    }
    return { skills }
  }

  /**
   * Install one user-owned Skill under the DSH home.
   * @param request - Skill metadata and Markdown content to install.
   * @returns The installed Skill name and enabled state.
   */
  @Remote('installSkill')
  async installSkill(request: SkillInstallRequest): Promise<SkillManagementValue> {
    const name = validateSkillName(request.name)
    const description = validateSkillText(request.description, 'Skill description')
    const content = validateSkillText(request.content, 'Skill content', false)
    const whenToUse = request.whenToUse === undefined ? undefined : validateSkillText(request.whenToUse, 'Skill usage hint')
    const directory = join(this.dshHome, 'skills', name)
    const file = join(directory, 'SKILL.md')
    await mkdir(directory, { recursive: true })
    try {
      await writeFile(file, renderSkillFile({
        name,
        description,
        content,
        ...(whenToUse === undefined ? {} : { whenToUse }),
        enabled: true,
      }), { encoding: 'utf8', flag: 'wx' })
    } catch (error: unknown) {
      if (isAlreadyExists(error)) throw new Error(`Skill "${name}" is already installed`)
      throw error
    }
    return { name, enabled: true }
  }

  /**
   * Enable or disable both model and user invocation for one Skill.
   * @param request - Skill name and desired enabled state.
   * @returns The updated Skill name and enabled state.
   */
  @Remote('setSkillEnabled')
  async setSkillEnabled(request: SkillSetEnabledRequest): Promise<SkillManagementValue> {
    const name = validateSkillName(request.name)
    const file = join(this.dshHome, 'skills', name, 'SKILL.md')
    const current = await readManagedSkill(file, name)
    if (current === undefined) throw new Error(`Skill "${name}" is not installed`)
    await replaceFile(file, renderSkillFile({ ...current, enabled: request.enabled }))
    return { name, enabled: request.enabled }
  }

  /**
   * Remove one user-owned Skill directory.
   * @param request - Skill name to remove.
   * @returns The removed Skill name and confirmation marker.
   */
  @Remote('removeSkill')
  async removeSkill(request: SkillRemoveRequest): Promise<{ name: string; removed: true }> {
    const name = validateSkillName(request.name)
    const root = resolve(join(this.dshHome, 'skills'))
    const directory = resolve(join(root, name))
    if (!directory.startsWith(`${root}${sep}`)) throw new Error('Skill path escapes the managed root')
    try {
      const info = await lstat(directory)
      if (info.isSymbolicLink()) await unlink(directory)
      else await rm(directory, { recursive: true, force: true })
    } catch (error: unknown) {
      if (!isMissingFile(error)) throw error
    }
    return { name, removed: true }
  }

  private async ensureMcpRestored(): Promise<void> {
    await this.restorePromise
  }

  private async restoreMcpStore(): Promise<void> {
    if (contextIsInactive(this.ctx)) return
    let raw: string
    try {
      raw = await readFile(this.mcpStorePath, 'utf8')
    } catch (error: unknown) {
      if (isMissingFile(error)) return
      throw error
    }
    const decoded: unknown = JSON.parse(raw)
    if (!Array.isArray(decoded)) throw new Error('pluginInventory: MCP store must contain an array')
    let known: Set<string>
    try {
      known = new Set([...this.ctx.loader.entries()].filter(isMcpEntry).map(entry => mcpServerName(entry)))
    } catch (error: unknown) {
      if (isInactiveContext(error)) return
      throw error
    }
    for (const item of decoded) {
      if (contextIsInactive(this.ctx)) return
      const persisted = parsePersistedMcp(item)
      if (known.has(persisted.serverName)) continue
      try {
        await this.ctx.loader.create({
          name: MCP_MODULE,
          config: persisted.config,
          disabled: !persisted.enabled,
        })
      } catch (error: unknown) {
        if (isInactiveContext(error)) return
        throw error
      }
      known.add(persisted.serverName)
    }
  }

  private persistMcpStore(): Promise<void> {
    const next = this.writeTail.then(async () => {
      const entries = [...this.ctx.loader.entries()].filter(isMcpEntry).map(entry => ({
        serverName: mcpServerName(entry),
        config: mcpConfig(entry),
        enabled: !entry.disabled,
      }))
      await mkdir(dirname(this.mcpStorePath), { recursive: true, mode: 0o700 })
      const temporary = `${this.mcpStorePath}.${randomUUID()}.tmp`
      try {
        await writeFile(temporary, `${JSON.stringify(entries, null, 2)}\n`, { encoding: 'utf8', flag: 'wx', mode: 0o600 })
        await rename(temporary, this.mcpStorePath)
      } finally {
        await rm(temporary, { force: true })
      }
    })
    this.writeTail = next.catch(() => {})
    return next
  }
}

const MCP_MODULE = '@deepseek-ai/dsh-mcp-client'

function isMcpEntry(entry: { options: { name: string; group?: boolean | null } }): boolean {
  return entry.options.group !== true && entry.options.name === MCP_MODULE
}

function validateMcpConfig(config: Record<string, unknown>): McpServerConfig {
  if (typeof config !== 'object' || config === null || Array.isArray(config)) throw new TypeError('MCP config must be an object')
  if (config.transport !== 'stdio' && config.transport !== 'streamable-http') throw new TypeError('MCP config transport must be stdio or streamable-http')
  if (typeof config.serverName !== 'string' || !/^[A-Za-z0-9_-]{1,32}$/u.test(config.serverName)) throw new TypeError('MCP serverName must match [A-Za-z0-9_-]{1,32}')
  if (config.transport === 'stdio' && typeof config.command !== 'string') throw new TypeError('stdio MCP config requires command')
  if (config.transport === 'streamable-http' && typeof config.url !== 'string') throw new TypeError('streamable-http MCP config requires url')
  return { ...config } as McpServerConfig
}

function mergeMcpConfig(current: McpServerConfig, patch: McpServerConfig): McpServerConfig {
  const merged: Record<string, JsonValue> = { ...current, ...patch }
  if (patch.transport === 'stdio') {
    delete merged.url
    delete merged.headers
  } else if (patch.transport === 'streamable-http') {
    delete merged.command
    delete merged.args
    delete merged.env
    delete merged.cwd
  }
  return validateMcpConfig(merged)
}

function projectMcpEntry(entry: Entry): import('./types.ts').McpServerEntry {
  const config = entry.options.config && typeof entry.options.config === 'object' ? entry.options.config as Record<string, JsonValue> : {}
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

interface ParsedManagedSkill {
  readonly name: string
  readonly description: string
  readonly content: string
  readonly whenToUse?: string
  readonly modelInvocable: boolean
  readonly userInvocable: boolean
}

interface RenderedSkill extends Omit<ParsedManagedSkill, 'modelInvocable' | 'userInvocable'> {
  readonly enabled: boolean
}

function isSkillName(value: string): boolean {
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(value)
}

function validateSkillName(value: string): string {
  if (!isSkillName(value)) throw new TypeError('Skill name must use lowercase kebab-case')
  return value
}

function validateSkillText(value: string, label: string, required = true): string {
  const normalized = value.trim()
  if (required && normalized.length === 0) throw new TypeError(`${label} must not be empty`)
  return required ? normalized : value
}

async function readManagedSkill(file: string, expectedName: string): Promise<ParsedManagedSkill | undefined> {
  let source: string
  try {
    source = await readFile(file, 'utf8')
  } catch (error: unknown) {
    if (isMissingFile(error)) return undefined
    throw error
  }
  const match = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n?([\s\S]*)$/u.exec(source)
  if (match === null) return undefined
  const frontmatter: unknown = parseYaml(match[1] ?? '')
  if (typeof frontmatter !== 'object' || frontmatter === null || Array.isArray(frontmatter)) return undefined
  const values = frontmatter as Record<string, unknown>
  const name = typeof values.name === 'string' ? values.name : expectedName
  const description = typeof values.description === 'string' ? values.description : ''
  if (name !== expectedName || !isSkillName(name) || description.trim().length === 0) return undefined
  const whenToUse = typeof values.whenToUse === 'string' ? values.whenToUse : undefined
  return {
    name,
    description,
    content: match[2] ?? '',
    ...(whenToUse === undefined ? {} : { whenToUse }),
    modelInvocable: values['disable-model-invocation'] !== true,
    userInvocable: values['user-invocable'] !== false,
  }
}

function projectManagedSkill(skill: ParsedManagedSkill): SkillManagementEntry {
  return {
    name: skill.name,
    description: skill.description,
    enabled: skill.modelInvocable || skill.userInvocable,
    modelInvocable: skill.modelInvocable,
    userInvocable: skill.userInvocable,
    ...(skill.whenToUse === undefined ? {} : { whenToUse: skill.whenToUse }),
  }
}

function renderSkillFile(skill: RenderedSkill): string {
  return `---\n${stringifyYaml({
    name: skill.name,
    description: skill.description,
    ...(skill.whenToUse === undefined ? {} : { whenToUse: skill.whenToUse }),
    'disable-model-invocation': !skill.enabled,
    'user-invocable': skill.enabled,
  }).trimEnd()}\n---\n${skill.content}`
}

async function replaceFile(file: string, content: string): Promise<void> {
  const temporary = `${file}.${randomUUID()}.tmp`
  try {
    await writeFile(temporary, content, { encoding: 'utf8', flag: 'wx' })
    await rename(temporary, file)
  } finally {
    await rm(temporary, { force: true })
  }
}

function isMissingFile(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'code' in error && (error as { code?: unknown }).code === 'ENOENT'
}

function isAlreadyExists(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'code' in error && (error as { code?: unknown }).code === 'EEXIST'
}

function isInactiveContext(error: unknown): boolean {
  return error instanceof Error && error.message.startsWith('cannot get required service ')
}

function contextIsInactive(ctx: Context): boolean {
  return ctx.fiber.state === FiberState.UNLOADING || ctx.fiber.state === FiberState.DISPOSED
}

interface PersistedMcp {
  readonly serverName: string
  readonly config: McpServerConfig
  readonly enabled: boolean
}

function parsePersistedMcp(value: unknown): PersistedMcp {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error('pluginInventory: invalid MCP store entry')
  const row = value as Record<string, unknown>
  if (typeof row.serverName !== 'string' || typeof row.enabled !== 'boolean') throw new Error('pluginInventory: invalid MCP store entry')
  const config = validateMcpConfig(row.config as Record<string, unknown>)
  if (config.serverName !== row.serverName) throw new Error('pluginInventory: MCP store serverName does not match config')
  return { serverName: row.serverName, config, enabled: row.enabled }
}

function mcpConfig(entry: Entry): McpServerConfig {
  const config = entry.options.config
  return config !== null && typeof config === 'object' && !Array.isArray(config)
    ? { ...(config as Record<string, JsonValue>) }
    : {}
}

function mcpServerName(entry: Entry): string {
  const config = mcpConfig(entry)
  return typeof config.serverName === 'string' ? config.serverName : entry.id
}

export default PluginInventoryGateway
