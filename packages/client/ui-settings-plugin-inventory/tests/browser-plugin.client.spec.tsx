// @vitest-environment jsdom
import { Context, Service } from '@deepseek-ai/cordis'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import { resolveSlotLabel } from '@deepseek-ai/dsh-client-ui-slots'
import { usePinnedBrowserLanguages } from '@deepseek-ai/dsh-client-test-runtime'
import { apply, inject, NS } from '../src/client/index.ts'
import {
  ConnectorsCapabilityCenterTab,
  SkillConnectorSettingsTab,
  SkillsCapabilityCenterTab,
  type SkillConnectorSettingsTabInjected,
} from '../src/client/SkillConnectorSettingsTab.tsx'
import {
  PluginInventorySettingsTab,
  type PluginInventorySettingsTabInjected,
} from '../src/client/PluginInventorySettingsTab.tsx'
import { apply as hostApply } from '../src/index.ts'

usePinnedBrowserLanguages('zh-CN')
afterEach(cleanup)

const EMPTY = { entries: [] }
type ListResult =
  | { readonly ok: true; readonly value: typeof EMPTY }
  | { readonly ok: false; readonly error: { readonly code: string; readonly message: string } }

async function bench() {
  const ctx = new Context()
  await ctx.plugin(SlotRegistry).await()
  const locale = new LocaleRuntime(ctx)
  ctx.provide('locale', locale)
  class RemoteService extends Service {
    constructor(serviceCtx: Context) {
      super(serviceCtx, 'remote')
    }
  }
  new RemoteService(ctx)
  const list = vi.fn<() => Promise<ListResult>>()
    .mockResolvedValue({ ok: true, value: EMPTY })
  ctx.provide('remote.pluginInventory', { list })
  ctx.provide('remote.skills', { list: vi.fn() })
  ctx.provide('sessions', {
    list: { getSnapshot: () => ({ current: undefined }) },
    subagentAddress: () => undefined,
  })
  return { ctx, slots: ctx.get('slots') as SlotRegistry, locale, list }
}

function declare(slots: SlotRegistry): () => void {
  return slots.register({
    name: 'root',
    children: {
      'settings.plugins.tab': { kind: 'list', scope: 'root' },
      'capabilities.center.tab': { kind: 'keyed', scope: 'root' },
    },
  } as never, () => null)
}

describe('ui-settings-plugin-inventory browser plugin', () => {
  it('keeps the host Loader entry inert', () => {
    expect(hostApply).not.toThrow()
  })

  it('declares only the services used by the Settings Remote contribution', () => {
    expect(inject).toEqual([
      'slots', 'locale', 'remote', 'remote.pluginInventory', 'remote.skills', 'sessions',
    ])
  })

  it('registers a localized tab without reading the Remote eagerly', async () => {
    const b = await bench()
    declare(b.slots)
    await b.ctx.plugin({ inject: [...inject], apply }).await()

    const entry = b.slots.entries('settings.plugins.tab').find(item => item.options.id === 'all')!
    expect(entry.component).toBe(PluginInventorySettingsTab)
    expect(entry.options).toMatchObject({ id: 'all', order: 10 })
    expect(entry.locale).toBe(NS)
    expect(resolveSlotLabel(entry.options.label)).toBe('插件列表')
    expect(b.list).not.toHaveBeenCalled()

    // StoredEntry intentionally erases the registration face. Restore the
    // package contract at this test boundary before exercising the callbacks.
    const injected = entry.inject?.() as unknown as PluginInventorySettingsTabInjected | undefined
    expect(injected).toBeDefined()
    if (!injected) throw new Error('inventory entry did not provide its inject face')
    expect(typeof injected?.list).toBe('function')
    await expect(injected.list()).resolves.toEqual(EMPTY)
    expect(b.list).toHaveBeenCalledOnce()
    b.list.mockResolvedValueOnce({ ok: false, error: { code: 'REMOTE_ERROR', message: 'unavailable' } })
    await expect(injected.list()).rejects.toThrow('pluginInventory.list failed: REMOTE_ERROR: unavailable')
    expect(b.slots.entries('settings.plugins.tab')).toHaveLength(2)
    const settingsManagement = b.slots.entries('settings.plugins.tab').find(item => item.options.id === 'skill-connectors')!
    expect(settingsManagement.component).toBe(SkillConnectorSettingsTab)
    const settingsManagementInjected = settingsManagement.inject?.() as unknown as SkillConnectorSettingsTabInjected | undefined
    expect(settingsManagementInjected).toBeDefined()
    if (!settingsManagementInjected) throw new Error('management entry did not provide its inject face')
    expect(typeof settingsManagementInjected?.listMcp).toBe('function')
    const capabilityEntries = b.slots.entries('capabilities.center.tab')
    expect(capabilityEntries.map(entry => entry.options.key)).toEqual(['skills', 'connectors'])
    expect(capabilityEntries.map(entry => entry.component)).toEqual([
      SkillsCapabilityCenterTab,
      ConnectorsCapabilityCenterTab,
    ])
    const skillsInjected = capabilityEntries[0]!.inject?.() as unknown as SkillConnectorSettingsTabInjected | undefined
    const connectorsInjected = capabilityEntries[1]!.inject?.() as unknown as SkillConnectorSettingsTabInjected | undefined
    expect(skillsInjected).toBeDefined()
    expect(connectorsInjected).toBeDefined()
    if (!skillsInjected || !connectorsInjected) throw new Error('capability entries did not provide inject faces')
    expect(typeof skillsInjected?.listManagedSkills).toBe('function')
    expect(typeof connectorsInjected?.testMcpEntry).toBe('function')

    // Shipped preset names resolve over the agent-preset dictionaries the
    // real plugin registers; user-authored metadata stays untranslated.
    b.locale.register('settings.agentPreset', 'zh', { presetStandardName: '标准模式' } as never)
    expect(injected.presetName({ id: 'standard', trust: 'system', isDefault: true, rows: [] })).toBe('标准模式')
    expect(injected.presetName({ id: 'mine', trust: 'user', name: '我自己的', isDefault: false, rows: [] })).toBe('我自己的')
    await b.ctx.fiber.dispose()
  })

  it('follows locale and recovers across late declaration and declarer reload', async () => {
    const b = await bench()
    const fiber = b.ctx.plugin({ inject: [...inject], apply })
    await fiber.await()
    expect(b.slots.entries('settings.plugins.tab')).toHaveLength(0)
    expect(b.slots.entries('capabilities.center.tab')).toHaveLength(0)

    const stop = declare(b.slots)
    await vi.waitFor(() => {
      expect(b.slots.entries('settings.plugins.tab')).toHaveLength(2)
      expect(b.slots.entries('capabilities.center.tab')).toHaveLength(2)
    })
    b.locale.setLocale('en')
    const entries = b.slots.entries('settings.plugins.tab')
    expect(resolveSlotLabel(entries.find(item => item.options.id === 'all')!.options.label)).toBe('Plugin list')

    stop()
    expect(b.slots.entries('settings.plugins.tab')).toHaveLength(0)
    expect(b.slots.entries('capabilities.center.tab')).toHaveLength(0)
    declare(b.slots)
    await vi.waitFor(() => {
      expect(b.slots.entries('settings.plugins.tab').find(item => item.options.id === 'all')?.component).toBe(PluginInventorySettingsTab)
      expect(b.slots.entries('capabilities.center.tab').map(item => item.options.key)).toEqual(['skills', 'connectors'])
    })

    await fiber.dispose()
    expect(b.slots.entries('settings.plugins.tab')).toHaveLength(0)
    expect(b.slots.entries('capabilities.center.tab')).toHaveLength(0)
    expect(() => b.locale.register(NS, 'zh', {})).not.toThrow()
    await b.ctx.fiber.dispose()
  })
})
