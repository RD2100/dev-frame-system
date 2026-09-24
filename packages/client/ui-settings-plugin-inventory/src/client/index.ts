/** Host plugin inventory and user capability management registered into Web Settings. */

import type {} from '@deepseek-ai/dsh-client-locale/client'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
// Type-only: pulls the 'settings.agentPreset' LocaleNamespaceMap merge, whose
// dictionaries the shipped-preset name resolution below reads.
import type {} from '@deepseek-ai/dsh-client-ui-agent-preset/client'
// Inline-safe shared fold: shipped ids map to dictionary keys in one home.
import { presetDisplayText } from '@deepseek-ai/dsh-agent-presets/display'
import { PluginInventorySettingsTab, type PluginInventorySettingsTabInjected } from './PluginInventorySettingsTab.tsx'
import { SkillConnectorSettingsTab, type SkillConnectorSettingsTabInjected } from './SkillConnectorSettingsTab.tsx'
import { en, zh, type PluginInventoryLocaleKey } from './locales.ts'

export type { PluginInventorySettingsTabInjected, PluginInventorySettingsTabProps } from './PluginInventorySettingsTab.tsx'
export type {
  SkillConnectorSettingsTabInjected,
  SkillConnectorSettingsTabProps,
  SkillConnectorSkillList,
} from './SkillConnectorSettingsTab.tsx'
export type { PluginInventoryLocaleKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Host plugin, Skill, and MCP management copy. */
    'settings.pluginInventory': PluginInventoryLocaleKey
  }
}

/** Dictionary namespace owned by this plugin. */
export const NS = 'settings.pluginInventory'

/** Services required by the Settings registration and generated Remote face. */
export const inject = [
  'slots', 'locale', 'remote', 'remote.pluginInventory', 'remote.skills', 'sessions',
]

/** Contribute the lazy inventory tab to the Plugins settings section. */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-plugin-inventory: dictionaries')

  const t = ctx.locale.bind(NS)
  const list: PluginInventorySettingsTabInjected['list'] = async () => {
    const result = await ctx.remote.pluginInventory.list()
    if (!result.ok) {
      throw new Error(`pluginInventory.list failed: ${result.error.code}: ${result.error.message}`)
    }
    return result.value
  }
  const listSkills: SkillConnectorSettingsTabInjected['listSkills'] = async () => {
    // The aggregate client face can merge a legacy SessionStore declaration;
    // this package consumes the published ISessions contract explicitly.
    const sessions = ctx.sessions as unknown as ISessions
    const sessionId = sessions.list.getSnapshot().current
    if (sessionId === undefined || sessions.subagentAddress(sessionId) !== undefined) return undefined
    const result = await ctx.remote.skills.list({ sessionId })
    if (!result.ok) {
      throw new Error(`skills/list failed: ${result.error.code}: ${result.error.message}`)
    }
    return result.value
  }
  const listManagedSkills: SkillConnectorSettingsTabInjected['listManagedSkills'] = async () => {
    const result = await ctx.remote.pluginInventory.listSkills()
    if (!result.ok) throw new Error(`pluginInventory.listSkills failed: ${result.error.code}: ${result.error.message}`)
    return result.value
  }
  const installSkill: SkillConnectorSettingsTabInjected['installSkill'] = async (request) => {
    const result = await ctx.remote.pluginInventory.installSkill(request)
    if (!result.ok) throw new Error(`pluginInventory.installSkill failed: ${result.error.code}: ${result.error.message}`)
    return result.value
  }
  const setSkillEnabled: SkillConnectorSettingsTabInjected['setSkillEnabled'] = async (request) => {
    const result = await ctx.remote.pluginInventory.setSkillEnabled(request)
    if (!result.ok) throw new Error(`pluginInventory.setSkillEnabled failed: ${result.error.code}: ${result.error.message}`)
    return result.value
  }
  const removeSkill: SkillConnectorSettingsTabInjected['removeSkill'] = async (name) => {
    const result = await ctx.remote.pluginInventory.removeSkill({ name })
    if (!result.ok) throw new Error(`pluginInventory.removeSkill failed: ${result.error.code}: ${result.error.message}`)
  }
  const listMcp: SkillConnectorSettingsTabInjected['listMcp'] = async () => {
    const result = await ctx.remote.pluginInventory.listMcp()
    if (!result.ok) throw new Error(`pluginInventory.listMcp failed: ${result.error.code}: ${result.error.message}`)
    return result.value
  }
  const createMcp: SkillConnectorSettingsTabInjected['createMcp'] = async (config) => {
    const result = await ctx.remote.pluginInventory.createMcp({ config })
    if (!result.ok) throw new Error(`pluginInventory.createMcp failed: ${result.error.code}: ${result.error.message}`)
  }
  const updateMcp: SkillConnectorSettingsTabInjected['updateMcp'] = async (entryId, config) => {
    const result = await ctx.remote.pluginInventory.updateMcp({ entryId, config })
    if (!result.ok) throw new Error(`pluginInventory.updateMcp failed: ${result.error.code}: ${result.error.message}`)
  }
  const removeMcp: SkillConnectorSettingsTabInjected['removeMcp'] = async (entryId) => {
    const result = await ctx.remote.pluginInventory.removeMcp({ entryId })
    if (!result.ok) throw new Error(`pluginInventory.removeMcp failed: ${result.error.code}: ${result.error.message}`)
  }
  const setMcpEnabled: SkillConnectorSettingsTabInjected['setMcpEnabled'] = async (entryId, enabled) => {
    const result = await ctx.remote.pluginInventory.setMcpEnabled({ entryId, enabled })
    if (!result.ok) throw new Error(`pluginInventory.setMcpEnabled failed: ${result.error.code}: ${result.error.message}`)
  }
  const testMcpEntry: SkillConnectorSettingsTabInjected['testMcpEntry'] = async (entryId) => {
    const result = await ctx.remote.pluginInventory.testMcpEntry({ entryId })
    if (!result.ok) throw new Error(`pluginInventory.testMcpEntry failed: ${result.error.code}: ${result.error.message}`)
    return result.value
  }
  // Resolved per call over ui-agent-preset's dictionaries, so a language
  // switch re-resolves shipped names; user-authored metadata passes through.
  const agentPresetCopy = ctx.locale.bind('settings.agentPreset')
  const presetName: PluginInventorySettingsTabInjected['presetName'] = preset =>
    presetDisplayText(preset, agentPresetCopy).name
  const injected = (): PluginInventorySettingsTabInjected => ({ list, presetName })

  ctx.slots.inject('settings.plugins.tab', () => ctx.slots.register({
    name: 'settings.plugins.tab',
    id: 'all',
    order: 10,
    label: () => t('tab'),
    locale: NS,
    inject: injected,
  }, PluginInventorySettingsTab))
  ctx.slots.inject('settings.plugins.tab', () => ctx.slots.register({
    name: 'settings.plugins.tab',
    id: 'skill-connectors',
    order: 20,
    label: () => t('capabilitiesTab'),
    locale: NS,
    inject: (): SkillConnectorSettingsTabInjected => ({
      listInventory: list,
      listSkills,
      listManagedSkills,
      installSkill,
      setSkillEnabled,
      removeSkill,
      listMcp,
      createMcp,
      updateMcp,
      removeMcp,
      setMcpEnabled,
      testMcpEntry,
    }),
  }, SkillConnectorSettingsTab))
}
