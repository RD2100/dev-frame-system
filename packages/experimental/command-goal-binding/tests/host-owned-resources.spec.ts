import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { afterEach, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import Group from '@deepseek-ai/cordis-plugin-group'
import AgentRegistry, { Inbox, type Agent } from '@deepseek-ai/dsh-agent'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SubagentRuntime from '@deepseek-ai/dsh-subagent'
import * as acp from '@deepseek-ai/dsh-subagent-acp'
import LocalSubprocessRuntime from '@deepseek-ai/dsh-subprocess-local'
import TerminalSessionService, { TerminalOwnershipRegistry } from '@deepseek-ai/dsh-terminal'
import type { TerminalBackend, TerminalBackendSession } from '@deepseek-ai/dsh-terminal'
import { createHostStopResources, resolveHostStopAdapters } from '../src/host-stop.ts'
import { resolveCommandGoalBindingConfig } from '../src/config.ts'
import { harness } from '../../project-controller/tests/helpers.ts'

const contexts: Context[] = []
const roots: string[] = []

it('opens the real project request admission only when prepared resume resources commit', async () => {
  const h = await harness({ requestBudget: 3 })
  try {
    await h.ctx.plugin(AgentRegistry)
    await h.ctx.plugin(SessionProjectionRegistry)
    await h.ctx.plugin(SubagentRuntime)
    await h.ctx.plugin(TerminalOwnershipRegistry)
    const owner = agent(h.ctx, 'resume-board-owner')
    const adapters = resolveHostStopAdapters(h.ctx, resolveCommandGoalBindingConfig({
      workspaceId: 'resume-board', requiredChecksPath: join(h.root, 'checks.json'),
      checks: { version: 1, checks: [{ checkId: 'probe', executable: 'node', arguments: ['--version'], cwd: h.root }] },
      taskIds: ['task-board'], maxAttempts: 3,
    }))
    await Promise.all(adapters.processes!(owner).map(async resource => resource.drain?.()))
    const commit = adapters.prepareResumeResources!(owner)
    expect(h.ctx.projectController.lifecycle).toBe('stopped')
    await expect(h.ctx.projectController.chargeModelRequest()).rejects.toThrow('admission is stopped')
    commit()
    expect(h.ctx.projectController.lifecycle).toBe('admission_open')
    await expect(h.ctx.projectController.chargeModelRequest()).resolves.toMatchObject({ chargedRequests: 1 })
    const stale = adapters.prepareResumeResources!(owner)
    h.ctx.projectController.requestStop()
    expect(stale).toThrow('project admission changed during resume preparation')
    expect(h.ctx.projectController.lifecycle).toBe('stop_requested')
    await expect(h.ctx.projectController.chargeModelRequest()).rejects.toThrow('admission is stop_requested')
    expect(() => adapters.prepareResumeResources!(owner)).toThrow('project admission cannot resume from stop_requested')
  } finally {
    await h.dispose()
  }
})
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

async function loadResources(root: string, extra: object[]): Promise<Context> {
  const ctx = new Context()
  contexts.push(ctx)
  const modules = new Map<string, unknown>([
    ['agents', AgentRegistry], ['sessions', SessionStore], ['projections', SessionProjectionRegistry],
    ['subagents', SubagentRuntime], ['subprocess', LocalSubprocessRuntime], ['terminal-ownership', TerminalOwnershipRegistry], ['terminals', TerminalSessionService], ['acp', acp],
  ])
  const entries = [...[...modules.keys()].filter(name => name !== 'acp' && name !== 'terminals').map(name => ({ name })), ...extra]
  const configPath = join(root, 'cordis.yml')
  writeFileSync(configPath, JSON.stringify(entries))
  ctx.baseUrl = pathToFileURL(root).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  ctx.loader.builtins.group = Group
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
  return ctx
}

it('drains a selected ACP process and its child/grandchild while retaining a foreign run', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-owned-stop-'))
  roots.push(root)
  const entries: { name: string; config?: object }[] = []
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
  const ctx = await loadResources(root, entries)
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
  const { processes: inventory, prepareResumeResources } = createHostStopResources(ctx.agents, ctx.subagents, ctx.terminalOwnership)
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

/** Real child handles exercise cleanup while the terminal protocol stays idle. */
const processTerminalBackend: TerminalBackend = {
  type: 'owned-process',
  async spawn(): Promise<TerminalBackendSession> {
    const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { windowsHide: true, stdio: 'ignore' })
    const closed = once(child, 'close')
    await once(child, 'spawn')
    return {
      ...(child.pid === undefined ? {} : { pid: child.pid }),
      motd: 'ready',
      startSend() { throw new Error('idle fixture does not send') },
      read() { return { text: '', totalLines: 0, lineBegin: 0, lineEnd: 0, truncated: false } },
      async signal() { throw new Error('idle fixture does not signal') },
      status() { return child.exitCode === null && child.signalCode === null ? { kind: 'running' } : { kind: 'exited', exitCode: child.exitCode, signal: child.signalCode } },
      async close() {
        if (child.exitCode === null && child.signalCode === null) child.kill()
        await closed
      },
    }
  },
}

it('drains actual terminals across isolated Loader realms and keeps a foreign owner live', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-scoped-terminal-stop-'))
  roots.push(root)
  const ctx = await loadResources(root, ['first', 'second'].map(id => ({
    id: `${id}-realm`, name: 'cordis:group', group: true, isolate: { terminals: true },
    config: [{ id, name: 'terminals' }],
  })))
  const service = (id: string): TerminalSessionService => {
    const entry = [...ctx.loader.entries()].find(entry => entry.options.id === id)
    const terminals = entry?.fiber?.ctx.get('terminals')
    if (terminals === undefined) throw new Error(`missing isolated terminal ${id}`)
    return terminals
  }
  const first = service('first')
  const second = service('second')
  expect(first).not.toBe(second)
  expect(ctx.get('terminals')).toBeUndefined()
  first.registerBackend(processTerminalBackend)
  second.registerBackend(processTerminalBackend)
  const controller = agent(ctx, 'terminal-controller')
  const lead = agent(ctx, 'terminal-lead', controller)
  const foreign = agent(ctx, 'terminal-foreign')
  const opened = await first.spawn(controller, { type: 'owned-process' })
  const child = await second.spawn(lead, { type: 'owned-process' })
  const unrelated = await second.spawn(foreign, { type: 'owned-process' })
  expect([opened.pid, child.pid, unrelated.pid].every(pid => pid !== undefined && alive(pid))).toBe(true)
  const resources = createHostStopResources(ctx.agents, ctx.subagents, ctx.terminalOwnership)
  await Promise.all(resources.processes(controller).map(async resource => resource.drain?.()))
  expect(alive(opened.pid!)).toBe(false)
  expect(alive(child.pid!)).toBe(false)
  expect(alive(unrelated.pid!)).toBe(true)
  expect(resources.processes(controller)).toEqual([])
  await expect(second.spawn(controller, { type: 'owned-process' })).rejects.toMatchObject({ code: 'OWNER_NOT_LIVE', message: 'PTY owner admission is closed' })
  const commit = resources.prepareResumeResources(controller)
  await expect(first.spawn(lead, { type: 'owned-process' })).rejects.toMatchObject({ code: 'OWNER_NOT_LIVE', message: 'PTY owner admission is closed' })
  await ctx.loader.create({
    name: 'cordis:group', group: true, isolate: { terminals: true },
    config: [{ id: 'late', name: 'terminals' }],
  })
  await ctx.loader.await()
  const late = service('late')
  late.registerBackend(processTerminalBackend)
  await expect(late.spawn(controller, { type: 'owned-process' })).rejects.toMatchObject({ code: 'OWNER_NOT_LIVE', message: 'PTY owner admission is closed' })
  expect(commit).toThrow('terminal instance directory changed')
  await expect(first.spawn(controller, { type: 'owned-process' })).rejects.toMatchObject({ code: 'OWNER_NOT_LIVE', message: 'PTY owner admission is closed' })
  await expect(second.spawn(lead, { type: 'owned-process' })).rejects.toMatchObject({ code: 'OWNER_NOT_LIVE', message: 'PTY owner admission is closed' })
  resources.prepareResumeResources(controller)()
  const resumed = await second.spawn(controller, { type: 'owned-process' })
  expect(alive(resumed.pid!)).toBe(true)
  await Promise.all(resources.processes(controller).map(async resource => resource.drain?.()))
  expect(alive(resumed.pid!)).toBe(false)
  expect(alive(unrelated.pid!)).toBe(true)
})
