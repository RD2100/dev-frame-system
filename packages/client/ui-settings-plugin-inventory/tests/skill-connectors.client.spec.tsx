// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PluginInventorySnapshot } from '@deepseek-ai/dsh-api-remotes/client'
import { SkillConnectorSettingsTab } from '../src/client/SkillConnectorSettingsTab.tsx'
import type { SkillConnectorSettingsTabInjected, SkillConnectorSettingsTabProps } from '../src/client/SkillConnectorSettingsTab.tsx'
import { en, type PluginInventoryLocaleKey } from '../src/client/locales.ts'

afterEach(cleanup)

const t = ((key: PluginInventoryLocaleKey, params?: Record<string, string>): string =>
  Object.entries(params ?? {}).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value), en[key])) as SkillConnectorSettingsTabProps['t']

const INVENTORY = { entries: [] } as unknown as PluginInventorySnapshot
const SKILLS = { skills: [{ name: 'ship-it', description: 'Ship a change', modelInvocable: true }] }
const MANAGED = { skills: [{ name: 'ship-it', description: 'Ship a change', enabled: true, modelInvocable: true, userInvocable: true }] }
const MCP = {
  servers: [{ entryId: 'mcp-github', serverName: 'github', transport: 'stdio', enabled: true, fiberPhase: 'active', config: { serverName: 'github', transport: 'stdio', command: 'node server.js' } }],
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
    await ready({ setMcpEnabled: setEnabled, testMcpEntry: test })
    fireEvent.click(screen.getByRole('tab', { name: /MCP connectors/iu }))
    expect(screen.getByText('github')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: en.disable }))
    await waitFor(() => { expect(setEnabled).toHaveBeenCalledWith('mcp-github', false) })
    fireEvent.click(screen.getByRole('button', { name: en.test }))
    await waitFor(() => { expect(test).toHaveBeenCalled() })
    expect(screen.getByRole('button', { name: en.edit })).toBeTruthy()
    expect(screen.getByRole('button', { name: en.remove })).toBeTruthy()
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
