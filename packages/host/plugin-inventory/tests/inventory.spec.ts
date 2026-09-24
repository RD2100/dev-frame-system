import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { Context, FiberState, type Plugin } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import type { AgentPresets } from '@deepseek-ai/dsh-agent-presets'
import PluginInventoryGateway from '../src/index.ts'

const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
})

const activePlugin: Plugin.Function = () => {}
const pendingPlugin: Plugin.Object = {
  inject: ['neverReady'],
  apply() {},
}

async function harness(): Promise<{
  ctx: Context
  inventory: PluginInventoryGateway
}> {
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(Loader)
  ctx.loader.builtins.active = activePlugin
  ctx.loader.builtins.pending = pendingPlugin
  await ctx.plugin(PluginInventoryGateway)
  const inventory = ctx.get('pluginInventory') as PluginInventoryGateway
  return { ctx, inventory }
}

describe('PluginInventoryGateway', () => {
  it('publishes one direct list method under the pluginInventory namespace', async () => {
    const { inventory } = await harness()
    expect(inventory.typertRemote).toMatchObject({
      serviceKey: 'pluginInventory',
      namespace: 'pluginInventory',
    })
    expect(remoteMethods(inventory)).toEqual(expect.arrayContaining([
      { method: 'list', invocation: { kind: 'direct' } },
      { method: 'listMcp', invocation: { kind: 'direct' } },
      { method: 'createMcp', invocation: { kind: 'direct' } },
      { method: 'updateMcp', invocation: { kind: 'direct' } },
      { method: 'removeMcp', invocation: { kind: 'direct' } },
      { method: 'setMcpEnabled', invocation: { kind: 'direct' } },
      { method: 'testMcp', invocation: { kind: 'direct' } },
      { method: 'testMcpEntry', invocation: { kind: 'direct' } },
      { method: 'listSkills', invocation: { kind: 'direct' } },
      { method: 'installSkill', invocation: { kind: 'direct' } },
      { method: 'setSkillEnabled', invocation: { kind: 'direct' } },
      { method: 'removeSkill', invocation: { kind: 'direct' } },
    ]))
  })

  it('projects current non-group Loader entries without a second cache', async () => {
    const { ctx, inventory } = await harness()
    const activeId = await ctx.loader.create({ name: 'cordis:active' })
    const pendingId = await ctx.loader.create({ name: 'cordis:pending' })
    const disabledId = await ctx.loader.create({
      name: 'cordis:not-installed',
      disabled: true,
    })
    await ctx.loader.create({ name: 'cordis:active', group: true })

    const snapshot = await inventory.list()
    // No agent-preset roster is composed, so the snapshot carries no presets.
    expect(snapshot.agentPresets).toBeUndefined()
    expect(snapshot.entries).toHaveLength(3)
    expect(snapshot.entries).toEqual(expect.arrayContaining([
      {
        entryId: activeId,
        moduleName: 'cordis:active',
        enabled: true,
        fiberPhase: 'active',
      },
      {
        entryId: pendingId,
        moduleName: 'cordis:pending',
        enabled: true,
        fiberPhase: 'pending',
      },
      {
        entryId: disabledId,
        moduleName: 'cordis:not-installed',
        enabled: false,
        fiberPhase: null,
      },
    ]))

    await ctx.loader.update(activeId, { disabled: true })
    expect((await inventory.list()).entries.find(entry => entry.entryId === activeId)).toEqual({
      entryId: activeId,
      moduleName: 'cordis:active',
      enabled: false,
      fiberPhase: null,
    })

    await ctx.loader.remove(pendingId)
    expect((await inventory.list()).entries.some(entry => entry.entryId === pendingId)).toBe(false)
  })

  it('carries each composed preset with root-fiber states mapped to phases', async () => {
    const { ctx, inventory } = await harness()
    ctx.provide('agentPresets', {
      compositionInventory: async () => [
        {
          id: 'standard',
          trust: 'system',
          name: '标准模式',
          isDefault: true,
          rows: [
            { entryId: 'alpha', moduleName: 'pkg-alpha', enabled: true, fiberState: FiberState.ACTIVE },
            { entryId: null, moduleName: 'pkg-file', enabled: 'conditional', condition: 'x' },
          ],
        },
        { id: 'damaged', trust: 'user', isDefault: false, broken: 'the composition file is missing', rows: [] },
      ],
    } as Partial<AgentPresets> as never)

    const snapshot = await inventory.list()
    expect(snapshot.agentPresets).toEqual([
      {
        id: 'standard',
        trust: 'system',
        name: '标准模式',
        isDefault: true,
        rows: [
          { entryId: 'alpha', moduleName: 'pkg-alpha', enabled: true, fiberPhase: 'active' },
          { entryId: null, moduleName: 'pkg-file', enabled: 'conditional', condition: 'x', fiberPhase: null },
        ],
      },
      { id: 'damaged', trust: 'user', isDefault: false, broken: 'the composition file is missing', rows: [] },
    ])
  })

  it('installs, toggles, lists, and removes user-owned Skills durably', async () => {
    const home = await mkdtemp(join(tmpdir(), 'dsh-plugin-inventory-'))
    const previous = process.env.DSH_HOME
    process.env.DSH_HOME = home
    try {
      const { inventory } = await harness()
      expect(await inventory.listSkills()).toEqual({ skills: [] })
      await expect(inventory.installSkill({
        name: 'ship-it',
        description: 'Ship a change',
        whenToUse: 'When shipping',
        content: '# Ship it\n',
      })).resolves.toEqual({ name: 'ship-it', enabled: true })
      expect(await readFile(join(home, 'skills', 'ship-it', 'SKILL.md'), 'utf8')).toContain('disable-model-invocation: false')
      await inventory.setSkillEnabled({ name: 'ship-it', enabled: false })
      expect((await inventory.listSkills()).skills[0]).toMatchObject({
        name: 'ship-it', enabled: false, modelInvocable: false, userInvocable: false,
      })
      await inventory.removeSkill({ name: 'ship-it' })
      expect(await inventory.listSkills()).toEqual({ skills: [] })
    } finally {
      if (previous === undefined) delete process.env.DSH_HOME
      else process.env.DSH_HOME = previous
      await rm(home, { recursive: true, force: true })
    }
  })

  it('preserves private MCP transport options when the settings form edits visible fields', async () => {
    const { ctx, inventory } = await harness()
    const entryId = await ctx.loader.create({
      name: '@deepseek-ai/dsh-mcp-client',
      disabled: true,
      config: {
        transport: 'stdio',
        serverName: 'private-mcp',
        command: 'node',
        args: ['server.js'],
        env: { MCP_TOKEN: 'secret' },
        cwd: 'D:/servers',
        toolCallTimeoutMs: 12_000,
      },
    })
    await inventory.updateMcp({
      entryId: entryId as never,
      config: { transport: 'stdio', serverName: 'private-mcp-renamed', command: 'bun' },
    })
    const entry = [...ctx.loader.entries()].find(item => item.id === entryId)
    expect(entry?.options.config).toMatchObject({
      serverName: 'private-mcp-renamed',
      command: 'bun',
      args: ['server.js'],
      env: { MCP_TOKEN: 'secret' },
      cwd: 'D:/servers',
      toolCallTimeoutMs: 12_000,
    })
  })

})
