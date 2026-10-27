// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { McpInventorySnapshot, PluginEntryId, PluginInventorySnapshot } from '@deepseek-ai/dsh-api-remotes/client'
import {
  ConnectorsCapabilityCenterTab,
  SkillConnectorSettingsTab,
  SkillsCapabilityCenterTab,
} from '../src/client/SkillConnectorSettingsTab.tsx'
import type {
  CapabilityCenterTabProps,
  SkillConnectorSettingsTabInjected,
  SkillConnectorSettingsTabProps,
} from '../src/client/SkillConnectorSettingsTab.tsx'
import { en, type PluginInventoryLocaleKey } from '../src/client/locales.ts'

afterEach(cleanup)

const t = ((key: PluginInventoryLocaleKey, params?: Record<string, string>): string =>
  Object.entries(params ?? {}).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value), en[key])) as SkillConnectorSettingsTabProps['t']

const INVENTORY = { entries: [] } as unknown as PluginInventorySnapshot
const SKILLS = { skills: [{ name: 'ship-it', description: 'Ship a change', modelInvocable: true }] }
const MANAGED = { skills: [{ name: 'ship-it', description: 'Ship a change', enabled: true, modelInvocable: true, userInvocable: true }] }
const MCP: McpInventorySnapshot = {
  servers: [{
    entryId: 'mcp-github' as PluginEntryId,
    serverName: 'github',
    transport: 'stdio',
    enabled: true,
    fiberPhase: 'active',
    config: { serverName: 'github', transport: 'stdio', command: 'node server.js' },
  }],
}

function props(overrides: Partial<SkillConnectorSettingsTabInjected> = {}): SkillConnectorSettingsTabProps {
  return {
    listInventory: async () => INVENTORY,
    listSkills: async () => SKILLS,
    listManagedSkills: async () => MANAGED,
    installSkill: async () => ({ name: 'new-skill', enabled: true }),
    setSkillEnabled: async request => ({ name: request.name, enabled: request.enabled }),
    removeSkill: async () => {},
    listMcp: async () => MCP,
    createMcp: async () => {},
    updateMcp: async () => {},
    removeMcp: async () => {},
    setMcpEnabled: async () => {},
    testMcpEntry: async () => ({ ok: true, message: 'connected' }),
    t,
    ...overrides,
  } as SkillConnectorSettingsTabProps
}

function capabilityProps(overrides: Partial<SkillConnectorSettingsTabInjected> = {}): CapabilityCenterTabProps {
  return props(overrides)
}

async function ready(overrides: Partial<SkillConnectorSettingsTabInjected> = {}): Promise<void> {
  render(<SkillConnectorSettingsTab {...props(overrides)} />)
  await screen.findByRole('tab', { name: /Skills/iu })
  await screen.findByText('/ship-it')
}

describe('SkillConnectorSettingsTab', () => {
  it('shows Skill install and enable/disable/uninstall controls', async () => {
    const setEnabled = vi.fn<SkillConnectorSettingsTabInjected['setSkillEnabled']>()
    const remove = vi.fn<SkillConnectorSettingsTabInjected['removeSkill']>()
    await ready({ setSkillEnabled: setEnabled, removeSkill: remove })

    expect(screen.getByRole('heading', { name: en.installSkill })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: en.disable }))
    await waitFor(() => { expect(setEnabled).toHaveBeenCalledWith({ name: 'ship-it', enabled: false }) })
    await screen.findByText('/ship-it')
    fireEvent.click(screen.getByRole('button', { name: en.uninstall }))
    await waitFor(() => { expect(remove).toHaveBeenCalledWith('ship-it') })
  })

  it('shows MCP add/edit/test/toggle/remove controls', async () => {
    const setEnabled = vi.fn<SkillConnectorSettingsTabInjected['setMcpEnabled']>()
    const test = vi.fn<SkillConnectorSettingsTabInjected['testMcpEntry']>().mockResolvedValue({ ok: true, message: 'connected' })
    const listMcp = vi.fn<SkillConnectorSettingsTabInjected['listMcp']>().mockResolvedValue(MCP)
    await ready({ setMcpEnabled: setEnabled, testMcpEntry: test, listMcp })
    fireEvent.click(screen.getByRole('tab', { name: /MCP connectors/iu }))
    expect(screen.getByText('github')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: en.disable }))
    await waitFor(() => { expect(setEnabled).toHaveBeenCalledWith('mcp-github', false) })
    await screen.findByText('github')
    listMcp.mockClear()
    fireEvent.click(screen.getByRole('button', { name: en.test }))
    await waitFor(() => { expect(test).toHaveBeenCalled() })
    await waitFor(() => { expect(listMcp).toHaveBeenCalledOnce() })
    expect(screen.getByRole('status').textContent).toBe('connected')
    expect(screen.getByRole('button', { name: en.edit })).toBeTruthy()
    expect(screen.getByRole('button', { name: en.remove })).toBeTruthy()
  })

  it('mounts Skills as a fixed capability-center page without nested tabs', async () => {
    render(<SkillsCapabilityCenterTab {...capabilityProps()} />)

    expect(await screen.findByText('/ship-it')).toBeTruthy()
    expect(screen.getByRole('heading', { name: en.installSkill })).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('heading', { name: en.addMcp })).toBeNull()
  })

  it('loads only Skill data in the fixed Skills page', async () => {
    const listInventory = vi.fn<SkillConnectorSettingsTabInjected['listInventory']>().mockRejectedValue(new Error('inventory unavailable'))
    const listMcp = vi.fn<SkillConnectorSettingsTabInjected['listMcp']>().mockRejectedValue(new Error('connector unavailable'))
    const listSkills = vi.fn<SkillConnectorSettingsTabInjected['listSkills']>().mockResolvedValue(SKILLS)
    render(<SkillsCapabilityCenterTab {...capabilityProps({ listInventory, listMcp, listSkills })} />)

    expect(await screen.findByText('/ship-it')).toBeTruthy()
    expect(listInventory).not.toHaveBeenCalled()
    expect(listMcp).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('reports an unavailable current-session catalog without inventing entries', async () => {
    const listSkills = vi.fn<SkillConnectorSettingsTabInjected['listSkills']>().mockResolvedValue(undefined)
    render(<SkillsCapabilityCenterTab {...capabilityProps({ listSkills })} />)

    expect(await screen.findByText(en.skillsNoSession)).toBeTruthy()
    expect(listSkills).toHaveBeenCalledOnce()
    expect(screen.queryByText('/undefined')).toBeNull()
  })

  it('mounts Connectors as a fixed capability-center page without nested tabs', async () => {
    render(<ConnectorsCapabilityCenterTab {...capabilityProps()} />)

    expect(await screen.findByText('github')).toBeTruthy()
    expect(screen.getByRole('heading', { name: en.addMcp })).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('heading', { name: en.installSkill })).toBeNull()
  })

  it('loads only MCP data in the fixed Connectors page', async () => {
    const listInventory = vi.fn<SkillConnectorSettingsTabInjected['listInventory']>().mockRejectedValue(new Error('inventory unavailable'))
    const listSkills = vi.fn<SkillConnectorSettingsTabInjected['listSkills']>().mockRejectedValue(new Error('session unavailable'))
    const listManagedSkills = vi.fn<SkillConnectorSettingsTabInjected['listManagedSkills']>().mockRejectedValue(new Error('skills unavailable'))
    render(<ConnectorsCapabilityCenterTab {...capabilityProps({ listInventory, listSkills, listManagedSkills })} />)

    expect(await screen.findByText('github')).toBeTruthy()
    expect(listInventory).not.toHaveBeenCalled()
    expect(listSkills).not.toHaveBeenCalled()
    expect(listManagedSkills).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('refreshes the four management reads after an operation failure and hides details', async () => {
    const list = vi.fn<SkillConnectorSettingsTabInjected['listManagedSkills']>().mockResolvedValue(MANAGED)
    const install = vi.fn<SkillConnectorSettingsTabInjected['installSkill']>().mockRejectedValue(new Error('secret transport detail'))
    await ready({ listManagedSkills: list, installSkill: install })
    const name = screen.getByRole('textbox', { name: en.skillName })
    fireEvent.change(name, { target: { value: 'new-skill' } })
    fireEvent.click(screen.getByRole('button', { name: en.install }))
    expect((await screen.findByRole('alert')).textContent).toBe(en.operationError)
    expect(screen.queryByText('secret transport detail')).toBeNull()
  })
})
