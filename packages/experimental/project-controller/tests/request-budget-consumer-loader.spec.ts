/** Real Loader and AgentLoop requests share durable admission before the external model adapter. */
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createServer } from 'node:http'
import { once } from 'node:events'
import { afterEach, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry, { type Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import LlmRuntime, { createUserMessage, LlmAdapter, LlmError, resolveRetryPolicy, type GenerateOptions, type StreamChunk } from '@deepseek-ai/dsh-llm'
import * as retry from '@deepseek-ai/dsh-llm-retry'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import ProjectController from '../src/index.ts'
import * as consumer from '../src/request-budget-consumer.ts'

const cleanups: (() => Promise<void>)[] = []
afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup()
})

class Adapter extends LlmAdapter {
  constructor(readonly endpoint: string, readonly calls: string[]) { super() }
  failFirst = false
  holdResponse = false
  readonly responseStarted = Promise.withResolvers<undefined>()
  readonly responseClosed = Promise.withResolvers<undefined>()
  override providerRetryPolicy() {
    return resolveRetryPolicy({ mode: 'normal', maxRetries: 1, retryableCodes: ['RATE_LIMIT'],
      backoff: { initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 } }, 'request budget fixture')
  }
  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const response = await fetch(this.endpoint, { method: 'POST', body: String(options.sessionId),
      ...(options.signal === undefined ? {} : { signal: options.signal }) })
    await response.text()
    if (response.status === 429) throw new LlmError('rate limited', 'RATE_LIMIT')
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text: 'done' }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: 'done' } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

async function load(requestBudget: number) {
  const root = await mkdtemp(join(tmpdir(), 'dsh-request-budget-loader-'))
  cleanups.push(() => rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 }))
  const calls: string[] = []
  const server = createServer((request, response) => {
    let body = ''
    request.setEncoding('utf8')
    request.on('data', (chunk: string) => { body += chunk })
    request.on('end', () => {
      calls.push(body)
      response.writeHead(adapter.failFirst && calls.length === 1 ? 429 : 200)
      if (adapter.holdResponse) {
        response.on('close', () => { adapter.responseClosed.resolve(undefined) })
        response.flushHeaders()
        adapter.responseStarted.resolve(undefined)
        return
      }
      response.end('done')
    })
  })
  cleanups.push(async () => {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => { if (error === undefined) resolve(); else reject(error) })
      server.closeAllConnections()
    })
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('Expected a loopback TCP listener')
  const adapter = new Adapter(`http://127.0.0.1:${address.port}/`, calls)
  const ctx = new Context()
  cleanups.push(() => ctx.fiber.dispose())
  const modules = new Map<string, unknown>([
    ['llm', LlmRuntime], ['sessions', SessionStore], ['projections', SessionProjectionRegistry],
    ['prompt', SystemPrompt], ['tools', ToolRuntime], ['agents', AgentRegistry], ['loop', AgentLoop],
    ['storage', Storage], ['json', StorageJson], ['domain', StorageDomain],
    ['bindings', AgentBindingRegistry], ['controller', ProjectController], ['retry', retry], ['budget', consumer],
  ])
  const settings: Record<string, unknown> = { loop: { agents: [] }, json: { root: join(root, 'storage') },
    domain: { backend: 'json' }, controller: { requestBudget }, budget: { controllerSessionId: 'root' } }
  const configPath = join(root, 'cordis.yml')
  await writeFile(configPath, JSON.stringify([...modules.keys()].map(name => ({ name, config: settings[name] }))))
  ctx.baseUrl = pathToFileURL(root).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  ctx.loader.internal = { version: 'v2', async import(specifier: string) {
    if (!modules.has(specifier)) throw new Error(`Unexpected Loader import ${specifier}`)
    return modules.get(specifier)
  } } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
  await ctx.loader.await()
  expect([...ctx.loader.entries()].filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)).toEqual([])
  ctx.llm.registerAdapter(['test'], adapter)
  const agents: Agent[] = []
  for (const id of ['root', 'lead', 'worker-a', 'worker-b', 'foreign']) {
    const agent = (await ctx.agents.create({ sessionId: SessionId(id), agentOptions: { provider: 'test', model: 'test' } })).agent
    agents.push(agent)
    await ctx.agentBindings.bind({ agentId: agent.id,
      role: id === 'root' || id === 'foreign' ? 'controller' : id === 'lead' ? 'lead' : 'worker',
      ...(id === 'lead' ? { parentSessionId: SessionId('root'), pluginId: PluginId('plugin') }
        : id.startsWith('worker') ? { parentSessionId: SessionId('lead'), pluginId: PluginId('plugin'), taskId: TaskId(id) } : {}),
    })
  }
  ctx.projectController.startProject()
  return { ctx, adapter, agents }
}

async function turn(agent: Agent) {
  agent.followup(createUserMessage({ content: [{ type: 'text', text: 'work' }], source: { kind: 'user' } }))
  await agent.whenIdle()
}

it('charges root, Lead and Workers against the same durable project allowance', async () => {
  const { ctx, adapter, agents } = await load(4)
  for (const agent of agents.slice(0, 4)) await turn(agent)
  expect(adapter.calls, JSON.stringify(agents[0]!.session.snapshotEvents())).toEqual(['root', 'lead', 'worker-a', 'worker-b'])
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(4)
  await turn(agents[2]!)
  expect(adapter.calls).toHaveLength(4)
})

it('admits only one of two concurrent Workers competing for the last request', async () => {
  const { ctx, adapter, agents } = await load(1)
  await Promise.all([turn(agents[2]!), turn(agents[3]!)])
  expect(adapter.calls).toHaveLength(1)
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(1)
})

it('charges each AgentLoop retry before the adapter receives it', async () => {
  const { ctx, adapter, agents } = await load(2)
  adapter.failFirst = true
  await turn(agents[2]!)
  expect(adapter.calls).toEqual(['worker-a', 'worker-a'])
  expect(agents[2]!.session.snapshotEvents().filter(event => event.type === 'llm/retry')).toHaveLength(1)
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(2)
})

it('stops a scheduled retry when its first attempt consumed the last allowance', async () => {
  const { ctx, adapter, agents } = await load(1)
  adapter.failFirst = true
  await turn(agents[2]!)
  expect(adapter.calls).toEqual(['worker-a'])
  expect(agents[2]!.session.snapshotEvents().filter(event => event.type === 'llm/retry')).toHaveLength(1)
  expect(agents[2]!.session.snapshotEvents().at(-1)).toMatchObject({ type: 'turn/end', data: {
    reason: { kind: 'error', error: { message: 'the request budget of 1 is exhausted (1 charged)' } },
  } })
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(1)
})

it('rejects foreign roots, unbound requests and forged request Sessions before the adapter', async () => {
  const { ctx, adapter, agents } = await load(4)
  await turn(agents[4]!)
  const options: GenerateOptions = { provider: 'test', model: 'test', messages: [], sessionId: SessionId('root') }
  const drain = async () => { for await (const _chunk of ctx.llm.stream(options)) { /* Consume the lazy admission. */ } }
  await expect(drain()).rejects.toThrow('actual live initiating Agent')
  await expect(ctx.agents.withInitiator(agents[2]!, drain)).rejects.toThrow('matching request Session')
  expect(adapter.calls).toEqual([])
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(0)
})

it('does not charge an already cancelled request', async () => {
  const { ctx, adapter, agents } = await load(1)
  await expect(ctx.agents.withInitiator(agents[0]!, async () => {
    for await (const _chunk of ctx.llm.stream({ provider: 'test', model: 'test', messages: [],
      sessionId: agents[0]!.session.id, signal: AbortSignal.abort(new Error('cancelled')) })) { /* Consume the lazy admission. */ }
  })).rejects.toThrow('cancelled')
  expect(adapter.calls).toEqual([])
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(0)
})

it('keeps a persisted charge when cancellation wins before adapter dispatch', async () => {
  const { ctx, adapter, agents } = await load(1)
  const cancellation = new AbortController()
  const original = ctx.projectController.chargeModelRequest.bind(ctx.projectController)
  const charged = vi.spyOn(ctx.projectController, 'chargeModelRequest').mockImplementation(async (options) => {
    const receipt = await original(options)
    cancellation.abort(new Error('cancelled after persistence'))
    return receipt
  })
  try {
    await expect(ctx.agents.withInitiator(agents[0]!, async () => {
      for await (const _chunk of ctx.llm.stream({ provider: 'test', model: 'test', messages: [],
        sessionId: agents[0]!.session.id, signal: cancellation.signal })) { /* Consume the lazy admission. */ }
    })).rejects.toThrow('cancelled after persistence')
    expect(adapter.calls).toEqual([])
    expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(1)
  } finally { charged.mockRestore() }
})

it('cancels an admitted HTTP response through its caller signal without refunding it', async () => {
  const { ctx, adapter, agents } = await load(1)
  adapter.holdResponse = true
  const cancellation = new AbortController()
  const chunks: StreamChunk[] = []
  const pending = ctx.agents.withInitiator(agents[0]!, async () => {
    for await (const chunk of ctx.llm.stream({ provider: 'test', model: 'test', messages: [],
      sessionId: agents[0]!.session.id, signal: cancellation.signal })) chunks.push(chunk)
  })
  await adapter.responseStarted.promise
  cancellation.abort(new Error('cancel HTTP response'))
  await pending
  await adapter.responseClosed.promise
  expect(adapter.calls).toEqual(['root'])
  expect(chunks.at(-1)).toMatchObject({ type: 'finish', reason: { kind: 'aborted' } })
  expect(ctx.projectController.requestBudgetUsage().chargedRequests).toBe(1)
})

it('sends no HTTP after an uncertain persisted charge, including subsequent Workers', async () => {
  const { ctx, adapter, agents } = await load(3)
  const domain = ctx.storageDomain.get('project_tasks')!
  const original = domain.global.set.bind(domain.global)
  const write = vi.spyOn(domain.global, 'set').mockImplementationOnce(async (value) => {
    await original(value)
    throw new Error('acknowledgement lost after durable write')
  })
  try {
    await turn(agents[2]!)
    await turn(agents[3]!)
    expect(adapter.calls).toEqual([])
    expect(write).toHaveBeenCalledTimes(1)
    for (const agent of agents.slice(2, 4)) {
      expect(agent.session.snapshotEvents().at(-1)).toMatchObject({ type: 'turn/end', data: {
        reason: { kind: 'error' },
      } })
    }
  } finally { write.mockRestore() }
})
