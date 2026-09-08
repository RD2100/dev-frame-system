import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { afterEach, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import AgentRegistry, { Inbox, type Agent } from '@deepseek-ai/dsh-agent'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SubagentRuntime from '@deepseek-ai/dsh-subagent'
import * as acp from '@deepseek-ai/dsh-subagent-acp'
import LocalSubprocessRuntime from '@deepseek-ai/dsh-subprocess-local'
import TerminalSessionService from '@deepseek-ai/dsh-terminal'
import { createHostStopResources } from '../src/host-stop.ts'

const contexts: Context[] = []
const roots: string[] = []
afterEach(async () => {
  for (const ctx of contexts.splice(0)) await ctx.fiber.dispose()
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

function agent(ctx: Context, id: string, parent?: Agent): Agent {
  const session = ctx.sessions.create(SessionId(id), parent === undefined ? {} : { meta: { parentSession: parent.session.id } })
  const owner: Agent = {
    id: session.id, session, options: {}, ctx: ctx.plugin(() => {}).ctx,
    inbox: new Inbox(session, { inserted() {}, discarded() {}, claimed() {} }),
    status: 'idle', send() {}, followup() {}, steer() {}, inject() {}, cancel() {},
    whenIdle: async () => {}, runMaintenance: task => task(new AbortController().signal),
  }
  ctx.agents.register(owner)
  return owner
}

function alive(pid: number): boolean {
  try { process.kill(pid, 0); return true }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ESRCH') return false
    throw error
  }
}

it('drains a selected ACP process and its child/grandchild while retaining a foreign run', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-owned-stop-'))
  roots.push(root)
  const ctx = new Context()
  contexts.push(ctx)
  const modules = new Map<string, unknown>([
    ['agents', AgentRegistry], ['sessions', SessionStore], ['projections', SessionProjectionRegistry],
    ['subagents', SubagentRuntime], ['subprocess', LocalSubprocessRuntime], ['terminals', TerminalSessionService], ['acp', acp],
  ])
  const entries: { name: string; config?: object }[] = [...modules.keys()].filter(name => name !== 'acp').map(name => ({ name }))
  const selectedPids = join(root, 'selected.json')
  const foreignPids = join(root, 'foreign.json')
  for (const [providerName, path] of [['selected', selectedPids], ['foreign', foreignPids]] as const) {
    entries.push({ name: 'acp', config: {
      providerName, command: process.execPath,
      args: [fileURLToPath(new URL('./fixtures/owned-acp-tree.ts', import.meta.url))],
      cwd: root, permission: 'reject',
      env: { OWNED_TREE_PID_PATH: path, MOCK_HANG: '1', MOCK_IGNORE_CANCEL: '1', MOCK_IGNORE_EOF: '1' },
      disposeEofGraceMs: 20, disposeGraceMs: 1000,
    } })
  }
  const configPath = join(root, 'cordis.yml')
  writeFileSync(configPath, JSON.stringify(entries))
  ctx.baseUrl = pathToFileURL(root).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  ctx.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`unexpected Loader module ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
  await ctx.loader.await()
  expect([...ctx.loader.entries()].filter(entry => entry.fiber === undefined && !entry.disabled)).toEqual([])
  const controller = agent(ctx, 'controller')
  const lead = agent(ctx, 'lead', controller)
  const unrelated = agent(ctx, 'foreign')
  const request = (parent: Agent) => ({ parent, signal: new AbortController().signal, prompt: [{ type: 'text' as const, text: 'wait' }] })
  await ctx.subagents.start('selected', request(lead))
  await ctx.subagents.start('foreign', request(unrelated))
  let selected: number[] = []
  let foreign: number[] = []
  await expect.poll(() => {
    try {
      selected = JSON.parse(readFileSync(selectedPids, 'utf8')) as number[]
      foreign = JSON.parse(readFileSync(foreignPids, 'utf8')) as number[]
      return selected.length === 3 && foreign.length === 3
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false
      throw error
    }
  }, { timeout: 10000 }).toBe(true)
  expect(selected.every(alive)).toBe(true)
  expect(foreign.every(alive)).toBe(true)
  const { processes: inventory, prepareResumeResources } = createHostStopResources(ctx.agents, ctx.subagents, ctx.terminals)
  const resources = inventory(controller)
  expect(resources.every(resource => resource.ownerSession !== unrelated.id)).toBe(true)
  await Promise.all(resources
    .filter(resource => resource.ownerSession === controller.id)
    .map(resource => Promise.resolve(resource.drain?.())))
  expect(() => prepareResumeResources(controller)).toThrow('retained resources')
  await expect(ctx.subagents.start('selected', request(controller))).rejects.toMatchObject({ code: 'OWNER_DRAINING' })
  await Promise.all(resources.map(resource => Promise.resolve(resource.drain?.())))
  await expect.poll(() => selected.some(alive), { timeout: 10000 }).toBe(false)
  expect(foreign.every(alive)).toBe(true)
  expect(inventory(controller)).toEqual([])
  const commitResume = prepareResumeResources(controller)
  await expect(ctx.subagents.start('selected', request(lead))).rejects.toMatchObject({ code: 'OWNER_DRAINING' })
  agent(ctx, 'late-child', controller)
  expect(commitResume).toThrow('owner tree changed')
  await expect(ctx.subagents.start('selected', request(lead))).rejects.toMatchObject({ code: 'OWNER_DRAINING' })
  prepareResumeResources(controller)()
  const resumed = await ctx.subagents.start('selected', request(lead))
  expect(ctx.subagents.hasOwnerActivity(lead)).toBe(true)
  await resumed.dispose()
  await Promise.all(inventory(controller).map(resource => Promise.resolve(resource.drain?.())))
  expect(ctx.subagents.hasOwnerActivity(unrelated)).toBe(true)
  await ctx.subagents.drainOwnedRuns(unrelated)
  await expect.poll(() => foreign.some(alive), { timeout: 10000 }).toBe(false)
})
