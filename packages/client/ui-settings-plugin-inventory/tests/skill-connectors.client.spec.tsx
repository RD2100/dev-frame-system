// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PluginInventorySnapshot } from '@deepseek-ai/dsh-api-remotes/client'
import { SkillConnectorSettingsTab } from '../src/client/SkillConnectorSettingsTab.tsx'
import type {
  SkillConnectorSettingsTabInjected,
  SkillConnectorSettingsTabProps,
} from '../src/client/SkillConnectorSettingsTab.tsx'
import { en, type PluginInventoryLocaleKey } from '../src/client/locales.ts'

afterEach(cleanup)

const t = ((key: PluginInventoryLocaleKey, params?: Record<string, string>): string =>
  Object.entries(params ?? {}).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, value),
    en[key],
  )) as SkillConnectorSettingsTabProps['t']

const INVENTORY = {
  entries: [
    { entryId: 'mcp-github', moduleName: '@deepseek-ai/dsh-mcp-client', enabled: true, fiberPhase: 'active' },
    { entryId: 'other', moduleName: '@deepseek-ai/dsh-tool-bash', enabled: true, fiberPhase: 'active' },
  ],
  agentPresets: [{
    id: 'standard', trust: 'system', isDefault: true,
    rows: [{ entryId: 'mcp-files', moduleName: '@deepseek-ai/dsh-mcp-client', enabled: true, fiberPhase: 'pending' }],
  }],
} as unknown as PluginInventorySnapshot

const SKILLS = {
  skills: [
    { name: 'ship-it', description: 'Ship a change', modelInvocable: true },
    { name: 'review-only', description: 'Review without model access', modelInvocable: false, whenToUse: 'When reviewing' },
  ],
}

function props(
  listInventory: SkillConnectorSettingsTabInjected['listInventory'] = async () => INVENTORY,
  listSkills: SkillConnectorSettingsTabInjected['listSkills'] = async () => SKILLS,
): SkillConnectorSettingsTabProps {
  return { listInventory, listSkills, t } as SkillConnectorSettingsTabProps
}

async function ready(
  listInventory?: SkillConnectorSettingsTabInjected['listInventory'],
  listSkills?: SkillConnectorSettingsTabInjected['listSkills'],
): Promise<void> {
  render(<SkillConnectorSettingsTab {...props(listInventory, listSkills)} />)
  await screen.findByRole('tab', { name: /Skills/iu })
}

describe('SkillConnectorSettingsTab', () => {
  it('reads current skills and profile-owned connectors without mutation controls', async () => {
    await ready()

    expect(screen.getByText('/ship-it')).toBeTruthy()
    expect(screen.getByText(en.profileOwnedNotice)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /enable|disable|remove|add/iu })).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: /MCP connectors/iu }))
    expect(screen.getAllByText('mcp-client')).toHaveLength(2)
    expect(screen.getByText('Composed by the application profile')).toBeTruthy()
    expect(screen.getByText('standard')).toBeTruthy()
    expect(screen.getByText('Waiting for dependencies')).toBeTruthy()
  })

  it('filters both panels by search text', async () => {
    await ready()
    const search = screen.getByRole('searchbox', { name: en.capabilitiesSearch })

    fireEvent.change(search, { target: { value: 'review-only' } })
    expect(screen.getByText('/review-only')).toBeTruthy()
    expect(screen.queryByText('/ship-it')).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: /MCP connectors/iu }))
    expect(screen.getByText(en.emptySearch)).toBeTruthy()
    fireEvent.change(search, { target: { value: 'mcp-files' } })
    expect(screen.getByText('mcp-client')).toBeTruthy()
  })

  it('refreshes both Remotes and hides transport details after failure', async () => {
    const inventory = vi.fn<SkillConnectorSettingsTabInjected['listInventory']>()
      .mockRejectedValueOnce(new Error('secret transport detail'))
      .mockResolvedValueOnce({ entries: [] })
    const skills = vi.fn<SkillConnectorSettingsTabInjected['listSkills']>()
      .mockResolvedValue({ skills: [] })
    render(<SkillConnectorSettingsTab {...props(inventory, skills)} />)

    expect((await screen.findByRole('alert')).textContent).toBe(en.error)
    expect(screen.queryByText('secret transport detail')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: en.retry }))
    await waitFor(() => { expect(inventory).toHaveBeenCalledTimes(2) })
    expect(await screen.findByText(en.skillsEmpty)).toBeTruthy()
    expect(skills).toHaveBeenCalledTimes(2)
  })

  it('explains why no skill catalog is shown without a current session', async () => {
    await ready(async () => ({ entries: [] }), async () => undefined)
    expect(screen.getByText(en.skillsNoSession)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: en.refresh }))
    await act(async () => {})
  })
})
