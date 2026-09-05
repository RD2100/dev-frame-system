import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import type { ContentBlock, GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import { ToolCallId, LlmAdapter } from '@deepseek-ai/dsh-llm'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import { delegationDepthOf } from '@deepseek-ai/dsh-subagent'
import { MockAdapter, textResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import * as SubagentSpawn from '@deepseek-ai/dsh-subagent-spawn-in-process'
import SubagentRuntime from '../src/index.ts'
import { TestSessionQuery } from './test-session-query.ts'

/** One scripted response that may wait on a caller-released gate before streaming. */
interface GatedEntry {
  chunks: StreamChunk[]
  gate?: Promise<undefined>
}

/** Adapter whose entries can hold a model call open until the test releases it. */
class HierarchyGatedAdapter extends LlmAdapter {
  readonly requests: GenerateOptions[] = []

  constructor(private script: GatedEntry[]) {
    super()
  }

  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    this.requests.push(options)
    const entry = this.script.shift()
    if (!entry) throw new Error('HierarchyGatedAdapter: script exhausted')
    if (entry.gate) await entry.gate
    for (const chunk of entry.chunks) {
      if (options.signal?.aborted) throw new Error('aborted')
      yield chunk
    }
  }
}

// Each persistence-backed temp root cleans up by closing its handle before
// removing the directory: Windows rmSync over a dir holding a still-open handle
// fails with EPERM.
const cleanups: Array<() => Promise<void>> = []
afterEach(async () => {
  const errors: unknown[] = []
  for (const cleanup of cleanups.splice(0)) {
    try { await cleanup() } catch (error) { errors.push(error) }
  }
  if (errors.length === 1) throw errors[0]
  if (errors.length > 1) throw new AggregateError(errors, 'temp-root cleanup failed')
})

/** Boot the continuable stack with persistence: the cold-resume tests need durable logs. */
async function setup(adapter: LlmAdapter) {
  const ctx = new Context()
  await mountAgentLoopTestDependencies(ctx)
  await ctx.plugin(SessionProjectionRegistry)
  const root = mkdtempSync(join(tmpdir(), 'dsh-subagent-hierarchy-'))
  const persistedRoot = root
  const persistenceFiber = await ctx.plugin(JsonlSessionPersistence, { root })
  cleanups.push(async () => {
    await persistenceFiber.dispose()
    rmSync(persistedRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
  })
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(TestSessionQuery)
  await ctx.plugin(SubagentRuntime)
  await ctx.plugin(SubagentSpawn, { providerName: 'spawn' })
  ctx.llm.registerAdapter(['mock'], adapter)
  const controller = ctx.agentLoop.create(SessionId('controller'), { provider: 'mock', model: 'mock' })
  return { ctx, controller }
}

const testSignal = new AbortController().signal

function startSpec(parent: Agent, label: string, overrides: object = {}) {
  return {
    provider: 'spawn',
    label,
    request: {
      prompt: [{ type: 'text' as const, text: `${label} task` }],
      parent,
      ...overrides,
    },
    signal: testSignal,
  }
}

function message(text: string): ContentBlock[] {
  return [{ type: 'text' as const, text }]
}

/** Keep the controller from spending scripted responses on settlement notices. */
function parkController(ctx: Context, controller: Agent): void {
  ctx.on('agent/pre-step', async ({ agent: subject }, next) => {
    if (subject !== controller) return next()
    return { kind: 'reject' as const }
  })
}

function waitResident(ctx: Context, childId: string): Promise<Agent> {
  return vi.waitFor(() => {
    const found = ctx.agents.get(SessionId(childId))
    expect(found).toBeDefined()
    return found!
  }, { timeout: 5_000 })
}

async function waitNoActivation(ctx: Context, childId: string): Promise<void> {
  await vi.waitFor(() => {
    expect(ctx.agents.get(SessionId(childId))).toBeUndefined()
  }, { timeout: 5_000 })
}

/** Exercise manager-wide teardown through the package-private owner. */
function drainManager(ctx: Context): Promise<void> {
  const manager = (ctx.subagents as unknown as {
    continuations?: { drain(): Promise<void> }
  }).continuations
  if (manager === undefined) throw new Error('expected a bound continuation manager')
  return manager.drain()
}

/** Queue one host-authored prompt through the package-private owner. */
function queuePrompt(ctx: Context, parent: Agent, childId: string, content: ContentBlock[]): Promise<string> {
  const manager = (ctx.subagents as unknown as {
    continuations?: {
      queuePrompt(parent: Agent, childId: SessionId, content: ContentBlock[], source: { kind: 'user' }, signal: AbortSignal): Promise<string>
    }
  }).continuations
  if (manager === undefined) throw new Error('expected a bound continuation manager')
  return manager.queuePrompt(parent, SessionId(childId), content, { kind: 'user' }, testSignal)
}

/** Agent-authored relay messages one agent's log received, in order. */
function relayMessages(agent: Agent): { sender: string; text: string }[] {
  return agent.session.snapshotEvents().flatMap((event: SessionEvent) => {
    if (event.type !== 'user/message' || event.data.source.kind !== 'agent-message') return []
    return [{
      sender: event.data.source.senderSessionId,
      text: event.data.content.flatMap(block => block.type === 'text' ? [block.text] : []).join(''),
    }]
  })
}

/** One executor-scope probe of the spawn tool through the tools registry. */
async function probeSpawnTool(ctx: Context, agent: Agent): Promise<{ isError: boolean; code?: string; message?: string }> {
  const result = await ctx.tools.execute({
    callId: ToolCallId(`probe-${agent.id}`),
    name: 'subagent',
    arguments: {},
    agent,
    signal: testSignal,
  })
  return result.isError
    ? { isError: true, code: result.error.info?.code, message: result.error.message }
    : { isError: false }
}

describe('DevFrame three-tier hierarchy', () => {
  it('builds controller → lead → worker and refuses every skipped-tier spawn and message route', async () => {
    const releaseLead = Promise.withResolvers<undefined>()
    const releaseWorker = Promise.withResolvers<undefined>()
    const adapter = new HierarchyGatedAdapter([
      { chunks: textResponse('lead answer'), gate: releaseLead.promise },
      { chunks: textResponse('worker answer'), gate: releaseWorker.promise },
      { chunks: textResponse('worker2 answer') },
      { chunks: textResponse('worker processes lead message') },
      { chunks: textResponse('lead processes worker report') },
      { chunks: textResponse('lead processes controller message') },
    ])
    const { ctx, controller } = await setup(adapter)
    parkController(ctx, controller)

    // Controller builds the lead; the live lead builds two workers.
    const lead = await ctx.subagents.startContinuable(startSpec(controller, 'lead'))
    const leadAgent = await waitResident(ctx, lead.childId)
    await vi.waitFor(() => {
      expect(adapter.requests.filter(request => request.sessionId === lead.childId)).toHaveLength(1)
    })
    const worker = await ctx.subagents.startContinuable(startSpec(leadAgent, 'worker'))
    const workerAgent = await waitResident(ctx, worker.childId)
    const worker2 = await ctx.subagents.startContinuable(startSpec(leadAgent, 'worker2'))
    await waitResident(ctx, worker2.childId)

    // The nesting is real: durable depths 0 → 1 → 2.
    expect(delegationDepthOf(controller)).toBe(0)
    expect(delegationDepthOf(leadAgent)).toBe(1)
    expect(delegationDepthOf(workerAgent)).toBe(2)

    // A worker at the DevFrame budget cannot spawn: depth 3 exceeds maxDepth 2,
    // refused before any child is published.
    const agentsBeforeSpawnAttempt = ctx.agents.list().length
    await expect(ctx.subagents.startContinuable(startSpec(workerAgent, 'grandchild', { maxDepth: 2 })))
      .rejects.toMatchObject({ name: 'SubagentDepthError', attemptedDepth: 3, maxDepth: 2 })
    expect(ctx.agents.list()).toHaveLength(agentsBeforeSpawnAttempt)

    // Skipped-tier message routes are refused: worker→grandparent,
    // controller→grandchild, worker→settled sibling.
    await waitNoActivation(ctx, worker2.childId)
    await expect(ctx.subagents.sendMessage(workerAgent, controller.id, message('skip up'), {
      signal: testSignal,
    })).rejects.toMatchObject({ code: 'UNAUTHORIZED' })
    await expect(ctx.subagents.sendMessage(controller, worker.childId, message('skip down'), {
      signal: testSignal,
    })).rejects.toMatchObject({ code: 'UNAUTHORIZED' })
    await expect(ctx.subagents.sendMessage(workerAgent, SessionId(worker2.childId), message('sibling'), {
      signal: testSignal,
    })).rejects.toMatchObject({ code: 'UNAUTHORIZED' })

    // Every adjacent route is authorized in both directions.
    expect(await ctx.subagents.sendMessage(controller, lead.childId, message('controller to lead'), {
      signal: testSignal,
    })).toBeDefined()
    expect(await ctx.subagents.sendMessage(leadAgent, worker.childId, message('lead to worker'), {
      signal: testSignal,
    })).toBeDefined()
    expect(await ctx.subagents.sendMessage(workerAgent, lead.childId, message('worker report'), {
      signal: testSignal,
    })).toBeDefined()
    expect(await ctx.subagents.sendMessage(leadAgent, controller.id, message('lead to controller'), {
      signal: testSignal,
    })).toBeDefined()

    // Release the parked turns; each steered message becomes a further step.
    releaseWorker.resolve(undefined)
    releaseLead.resolve(undefined)
    await waitNoActivation(ctx, worker.childId)
    await waitNoActivation(ctx, lead.childId)

    // Relay attribution arrived on the right sides of each adjacent pair.
    const leadRelays = relayMessages(leadAgent)
    expect(leadRelays).toContainEqual({
      sender: controller.id,
      text: `Agent ${controller.id} sent a message:controller to lead`,
    })
    expect(leadRelays).toContainEqual({
      sender: worker.childId,
      text: `Agent ${worker.childId} sent a message:worker report`,
    })
    expect(relayMessages(workerAgent)).toContainEqual({
      sender: lead.childId,
      text: `Agent ${lead.childId} sent a message:lead to worker`,
    })

    await drainManager(ctx)
  })

  it('cold-resumes a filtered worker still denied the spawn tool and pinned at its persisted depth', async () => {
    const adapter = new MockAdapter([textResponse('worker answer')])
    const { ctx, controller } = await setup(adapter)
    parkController(ctx, controller)
    // The spawn tool stands in for the delegation tool the worker must lose.
    const releaseFixture = ctx.tools.register(defineContentToolFixture({
      name: 'subagent',
      description: 'spawn tool stand-in',
      parameters: {},
      execute: () => Promise.resolve([{ type: 'text' as const, text: 'spawned' }]),
    }))

    const worker = await ctx.subagents.startContinuable(startSpec(controller, 'worker', {
      toolFilter: { deny: ['subagent'] },
      maxDepth: 2,
    }))
    const workerAgent = await waitResident(ctx, worker.childId)
    expect(delegationDepthOf(workerAgent)).toBe(1)

    // Executor-level refusal on the fresh worker: not merely prompt absence.
    expect(await probeSpawnTool(ctx, workerAgent)).toEqual({
      isError: true,
      code: 'UNKNOWN_TOOL',
      message: 'unknown tool "subagent"',
    })

    await waitNoActivation(ctx, worker.childId)
    await queuePrompt(ctx, controller, worker.childId, message('resume it'))
    const resumed = await waitResident(ctx, worker.childId)

    // The cold-resumed worker is still the persisted depth-1 child: its budget
    // cannot reset to top-level, proven by a cap a top-level parent satisfies.
    await expect(ctx.subagents.startContinuable(startSpec(resumed, 'grandchild', { maxDepth: 1 })))
      .rejects.toMatchObject({ name: 'SubagentDepthError', attemptedDepth: 2, maxDepth: 1 })

    // The role survives resume: the descriptor's toolFilter is reapplied, so
    // the spawn tool is still refused at the executor.
    expect(await probeSpawnTool(ctx, resumed)).toEqual({
      isError: true,
      code: 'UNKNOWN_TOOL',
      message: 'unknown tool "subagent"',
    })
    expect(delegationDepthOf(resumed)).toBe(1)

    await waitNoActivation(ctx, worker.childId)
    const loaded = await ctx.sessionPersistence.load(SessionId(worker.childId))
    expect(loaded.events.some(event => event.type === 'user/message'
      && event.data.content.some(block => block.type === 'text' && block.text === 'resume it'))).toBe(true)
    releaseFixture()
    await drainManager(ctx)
  })
})
