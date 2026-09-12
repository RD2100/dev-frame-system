/**
 * The Shadow conversation host over the real composition: the designated
 * session is created (or restored), the four conversational tools are visible
 * only in its scope, the design tool allowlist governs the composed session's
 * model face (inherited tools hidden except enabled memory, execution denied
 * outside the allowlist), a posted message drives a real agent turn that can
 * open a project through the router bridges, and the conversation surface
 * survives restarts through session persistence.
 */

import { describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import type { AgentLoopTestDependenciesOptions } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentDefaultModelConfig from '@deepseek-ai/dsh-agent-default-model'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import AgentHierarchy, { type AgentHierarchyConfigInput } from '../../agent-hierarchy/src/index.ts'
import ShadowRouter from '@deepseek-ai/dsh-experimental-shadow-router'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import { MockAdapter, textResponse, toolCallResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import ShadowAgent from '../src/shadow-agent.ts'
import type { Agent } from '@deepseek-ai/dsh-agent'

type ScriptEntry = StreamChunk[] | ((options: GenerateOptions) => StreamChunk[])

/** Flattened conversation facts for assertions. */
function rows(page: { messages: ReadonlyArray<{ role: string; text: string }> }): Array<{ role: string; text: string }> {
  return page.messages.map(row => ({ role: row.role, text: row.text }))
}

/** Dispatch one tool call through the real tool runtime as one agent. */
function dispatch(ctx: Context, agent: Agent, name: string, args: Record<string, unknown>): ReturnType<Context['tools']['execute']> {
  return ctx.tools.execute({
    callId: ToolCallId(`shadow-agent-${Math.random().toString(36).slice(2, 8)}`),
    name,
    arguments: args,
    signal: new AbortController().signal,
    agent,
  })
}

/** Flatten a tool result's text blocks. */
function resultText(result: { readonly content?: readonly { readonly type: string; readonly text?: string }[] }): string {
  return result.content?.flatMap(block => block.type === 'text' && typeof block.text === 'string' ? [block.text] : []).join('') ?? ''
}

/** One minimal no-op tool under a fixed name, for global-layer face assertions. */
function namedTool(name: string) {
  return defineTool({
    name,
    description: `test stub ${name}`,
    parameters: {},
    output: {
      schema: { type: 'object', additionalProperties: false, properties: {} },
      render: () => [{ type: 'text', text: name }],
    },
    async execute() { return {} },
  })
}

/** The tool names the design allowlist admits as explicitly enabled memory access. */
const MEMORY_TOOL_STUBS = ['memory_search', 'memory_read', 'memory_append'] as const

interface Bench {
  ctx: Context
  root: string
  host: ShadowAgent
  adapter: MockAdapter
  projectDirs: Record<string, string>
  /** Unload the conversation host's own plugin row: the lifecycle owner of the designated agent. */
  disposeHost: () => Promise<void>
  dispose: () => Promise<void>
}

interface BenchOptions {
  /** Router designation; omit to compose the fail-closed router. */
  designation?: string
  /** Mount JSONL session persistence (default true). */
  persistence?: boolean
  /** Mount the default-model service (default true). */
  defaultModel?: boolean
  /** Hierarchy policy config; the empty-face default keeps unbound sessions unrestricted. */
  hierarchyConfig?: AgentHierarchyConfigInput
  /** Legacy whole-unit binding records seeded into the storage root before mount, mirroring a hand-written durable table. */
  seedBindings?: readonly Record<string, unknown>[]
  /** Project directory names to pre-create under the root. */
  projects?: readonly string[]
  /** No-op tools registered into the global layer before the conversation host mounts. */
  globalTools?: readonly string[]
  /** Configuration forwarded to the tool registry (presentation mode under test). */
  tools?: AgentLoopTestDependenciesOptions['tools']
  /** Model script; built after the project dirs exist. */
  script?: (dirs: Record<string, string>) => readonly ScriptEntry[]
}

/** Minimal valid hierarchy config: every role face empty, the guard still active. */
const HIERARCHY_EMPTY_FACES: AgentHierarchyConfigInput = {
  roleToolPolicies: {
    controller: { inheritedTools: [] },
    lead: { inheritedTools: [] },
    worker: { inheritedTools: [] },
  },
}

/** Boot the real composition over a temp root: loop, storage, router, default model, conversation host. */
async function bench(options: BenchOptions = {}, existingRoot?: string): Promise<Bench> {
  const root = existingRoot ?? await mkdtemp(join(tmpdir(), 'dsh-shadow-agent-'))
  const ctx = new Context()
  const projectDirs: Record<string, string> = {}
  try {
    if (options.seedBindings !== undefined) {
      const document = {
        unit: { name: 'session_identity', version: 1 },
        global: null,
        tables: {
          bindings: Object.fromEntries(options.seedBindings.map(record => [String(record.agentId), record])),
        },
      }
      await writeFile(join(root, 'session_identity.json'), JSON.stringify(document, null, 2))
    }
    for (const name of options.projects ?? []) {
      const dir = join(root, name)
      await mkdir(dir, { recursive: true })
      projectDirs[name] = dir
    }
    await mountAgentLoopTestDependencies(ctx, { ...(options.tools === undefined ? {} : { tools: options.tools }) })
    for (const name of options.globalTools ?? []) {
      ctx.tools.register(namedTool(name))
    }
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    if (options.persistence !== false) {
      await ctx.plugin(JsonlSessionPersistence, { root: join(root, 'session-logs') })
    }
    await ctx.plugin(WorkspaceRegistry)
    await ctx.plugin(AgentBindingRegistry)
    await ctx.plugin(AgentHierarchy, options.hierarchyConfig ?? HIERARCHY_EMPTY_FACES)
    await ctx.plugin(ShadowRouter, {
      authorizedRoots: [root],
      ...(options.designation === undefined ? {} : { shadowSessionId: options.designation }),
    })
    const adapter = new MockAdapter([...(options.script?.(projectDirs) ?? [])])
    ctx.llm.registerAdapter(['mock'], adapter)
    if (options.defaultModel !== false) {
      await ctx.plugin(AgentDefaultModelConfig, { provider: 'mock', model: 'mock' })
    }
    const hostFiber = ctx.plugin(ShadowAgent)
    await hostFiber
    return {
      ctx,
      root,
      host: ctx.shadowAgent,
      adapter,
      projectDirs,
      async disposeHost() {
        await hostFiber.dispose()
      },
      async dispose() {
        await hostFiber.dispose()
        await ctx.fiber.dispose()
        if (existingRoot === undefined) await rm(root, { recursive: true, force: true })
      },
    }
  } catch (error: unknown) {
    await ctx.fiber.dispose()
    if (existingRoot === undefined) await rm(root, { recursive: true, force: true })
    throw error
  }
}

describe('the Shadow conversation host', () => {
  it('creates the designated session and exposes the conversational tools to its scope only', async () => {
    const b = await bench({ designation: 'session-shadow' })
    try {
      const agent = await b.host.ensure()
      expect(agent.id).toBe('session-shadow')
      expect(b.ctx.sessions.get(agent.id)).toBeDefined()

      // The status tool resolves in the Shadow's scope and reports live facts.
      const status = await dispatch(b.ctx, agent, 'shadow_status', {})
      expect(status.isError).toBe(false)
      const facts = JSON.parse(resultText(status)) as { shadow_live: boolean; authorized_roots: string[]; projects: unknown[] }
      expect(facts.shadow_live).toBe(true)
      expect(facts.authorized_roots).toEqual([b.root])
      expect(facts.projects).toEqual([])

      // Another agent's scope resolves none of the conversational tools.
      const worker = b.ctx.agentLoop.create(SessionId('session-worker'), { provider: 'mock', model: 'mock' })
      const denied = await dispatch(b.ctx, worker, 'shadow_status', {})
      expect(denied.isError).toBe(true)
    } finally {
      await b.dispose()
    }
  })

  it('creates the session with no role binding while the hierarchy guard is active', async () => {
    // Incident regression: a hand-written durable controller binding for the
    // designated session once made the hierarchy restrict creation to a tool
    // face the composition never registered globally, rolling the session
    // back. The shadow's authority is the designation, not a hierarchy role,
    // so the unbound session must create cleanly under an active guard.
    const b = await bench({ designation: 'session-shadow' })
    try {
      expect(b.ctx.agentBindings.find(SessionId('session-shadow'))).toBeUndefined()
      const agent = await b.host.ensure()
      expect(agent.id).toBe('session-shadow')
      const status = await dispatch(b.ctx, agent, 'shadow_status', {})
      expect(status.isError).toBe(false)
      expect((JSON.parse(resultText(status)) as { shadow_live: boolean }).shadow_live).toBe(true)
    } finally {
      await b.dispose()
    }
  })

  it('fails creation loud when a durable role binding drags the hierarchy tool face into it', async () => {
    const b = await bench({
      designation: 'session-shadow',
      hierarchyConfig: {
        roleToolPolicies: {
          controller: { inheritedTools: ['pwsh'] },
          lead: { inheritedTools: [] },
          worker: { inheritedTools: [] },
        },
      },
      seedBindings: [{
        agentId: 'session-shadow',
        sessionId: 'session-shadow',
        role: 'controller',
        createdAt: '2026-09-10T12:00:00.000Z',
      }],
    })
    try {
      await expect(b.host.ensure()).rejects.toThrow('unknown global tool')
    } finally {
      await b.dispose()
    }
  })

  it('posts a message, drives a real turn, and reads the persisted surface back', async () => {
    const b = await bench({
      designation: 'session-shadow',
      script: () => [textResponse('Tell me the project path and I will open it.')],
    })
    try {
      const accepted = await b.host.postMessage('Open the alpha project.')
      expect(accepted.messageId).toMatch(/^[0-9a-f-]{36}$/)
      const agent = await b.host.ensure()
      await agent.whenIdle()

      const page = await b.host.readConversation({})
      expect(rows(page)).toEqual([
        { role: 'user', text: 'Open the alpha project.' },
        { role: 'shadow', text: 'Tell me the project path and I will open it.' },
      ])
      expect(page.cursor).toBe(agent.session.seq)

      // The cursor reads incrementally: nothing new yet.
      const next = await b.host.readConversation({ after: page.cursor })
      expect(next.messages).toEqual([])
      expect(next.cursor).toBe(agent.session.seq)
    } finally {
      await b.dispose()
    }
  })

  it('opens a real project because the model called shadow_open_project', async () => {
    const b = await bench({
      designation: 'session-shadow',
      projects: ['alpha'],
      script: dirs => [
        toolCallResponse('shadow-call-1', 'shadow_open_project', { path: dirs.alpha ?? '' }),
        textResponse('Project opened; its controller session is ready.'),
      ],
    })
    try {
      await b.host.postMessage('Open the alpha project.')
      const agent = await b.host.ensure()
      await agent.whenIdle()

      // The tool really ran the router's host bridge: one ready binding exists.
      const status = await dispatch(b.ctx, agent, 'shadow_status', {})
      const facts = JSON.parse(resultText(status)) as {
        projects: Array<{ canonical_path: string; state: string; binding_revision: number }>
      }
      expect(facts.projects).toEqual([{
        workspace_id: expect.any(String) as string,
        canonical_path: b.projectDirs.alpha,
        binding_revision: 1,
        state: 'ready',
      }])

      // The turn itself completed with the follow-up reply.
      const page = await b.host.readConversation({})
      expect(rows(page)).toEqual([
        { role: 'user', text: 'Open the alpha project.' },
        { role: 'shadow', text: 'Project opened; its controller session is ready.' },
      ])
    } finally {
      await b.dispose()
    }
  })

  it('lands tool failures in the turn honestly without creating a binding', async () => {
    const b = await bench({
      designation: 'session-shadow',
      script: () => [
        toolCallResponse('shadow-call-2', 'shadow_open_project', { path: 'D:/elsewhere/gamma' }),
        textResponse('That path is outside the authorized roots; I cannot open it.'),
      ],
    })
    try {
      await b.host.postMessage('Open D:/elsewhere/gamma.')
      const agent = await b.host.ensure()
      await agent.whenIdle()

      const status = await dispatch(b.ctx, agent, 'shadow_status', {})
      expect((JSON.parse(resultText(status)) as { projects: unknown[] }).projects).toEqual([])
      const page = await b.host.readConversation({})
      expect(page.messages.at(-1)?.text).toBe('That path is outside the authorized roots; I cannot open it.')
    } finally {
      await b.dispose()
    }
  })

  it('restores the conversation and the tool face across a restart', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-agent-resume-'))
    try {
      const first = await bench({ designation: 'session-shadow', script: () => [textResponse('Noted.')] }, root)
      await first.host.postMessage('Remember this exchange.')
      const firstAgent = await first.host.ensure()
      await firstAgent.whenIdle()
      await first.dispose()

      const second = await bench({ designation: 'session-shadow' }, root)
      try {
        const agent = await second.host.ensure()
        expect(agent.id).toBe('session-shadow')
        const page = await second.host.readConversation({})
        expect(rows(page)).toEqual([
          { role: 'user', text: 'Remember this exchange.' },
          { role: 'shadow', text: 'Noted.' },
        ])
      } finally {
        await second.dispose()
      }
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })

  it('restores the tool face on the resumed session', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-agent-resume-tools-'))
    try {
      const first = await bench({ designation: 'session-shadow' }, root)
      await first.dispose()

      const second = await bench({ designation: 'session-shadow' }, root)
      try {
        const agent = await second.host.ensure()
        const status = await dispatch(second.ctx, agent, 'shadow_status', {})
        expect(status.isError).toBe(false)
      } finally {
        await second.dispose()
      }
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })

  it('keeps pages bounded and validates the read cursor', async () => {
    const b = await bench({
      designation: 'session-shadow',
      script: () => [
        textResponse('one'), textResponse('two'), textResponse('three'),
      ],
    })
    try {
      for (const text of ['first', 'second', 'third']) {
        await b.host.postMessage(text)
        await (await b.host.ensure()).whenIdle()
      }
      const tail = await b.host.readConversation({ limit: 2 })
      expect(rows(tail)).toEqual([
        { role: 'user', text: 'third' },
        { role: 'shadow', text: 'three' },
      ])
      const page = await b.host.readConversation({ after: tail.messages[0]?.seq ?? 0 })
      expect(rows(page)).toEqual([{ role: 'shadow', text: 'three' }])
      await expect(b.host.readConversation({ limit: 0 })).rejects.toThrow('limit must be an integer')
      await expect(b.host.readConversation({ limit: 201 })).rejects.toThrow('limit must be an integer')
      await expect(b.host.readConversation({ after: -1 })).rejects.toThrow('after must be an integer')
      await expect(b.host.readConversation({ after: (await b.host.ensure()).session.seq + 1 }))
        .rejects.toThrow('after must be an integer')
    } finally {
      await b.dispose()
    }
  })

  it('rejects an empty message before touching the session', async () => {
    const b = await bench({ designation: 'session-shadow' })
    try {
      await expect(b.host.postMessage('   ')).rejects.toThrow('message text must be a non-empty string')
    } finally {
      await b.dispose()
    }
  })

  it('fails the conversation loud when the deployment declares no Shadow session', async () => {
    const b = await bench({})
    try {
      await expect(b.host.postMessage('hello')).rejects.toThrow('declares no Shadow session')
      await expect(b.host.readConversation({})).rejects.toThrow('declares no Shadow session')
    } finally {
      await b.dispose()
    }
  })

  it('fails the conversation loud when no default model is composed', async () => {
    const b = await bench({ designation: 'session-shadow', defaultModel: false })
    try {
      await expect(b.host.postMessage('hello')).rejects.toThrow('provides no default model')
    } finally {
      await b.dispose()
    }
  })
})

describe('the Shadow conversation host tool allowlist', () => {
  it('hides every inherited global tool from the designated face and leaves other agents untouched', async () => {
    const b = await bench({ designation: 'session-shadow', globalTools: ['probe_tool'] })
    try {
      const agent = await b.host.ensure()

      // The composed designated face: the host's four conversational tools
      // plus the router's same-layer project_* whitelist — own registrations
      // are exempt from the restriction, the documented residual — and the
      // inherited probe tool is restricted away.
      const names = b.ctx.tools.schemas(agent).map(schema => schema.name).sort()
      expect(names).toEqual([
        'project_open',
        'project_send',
        'project_status',
        'project_stop',
        'shadow_message_controller',
        'shadow_open_project',
        'shadow_release_project',
        'shadow_status',
      ])

      // The restriction is scope-local: the global view and an un-designated
      // agent keep the deployment tool.
      expect(b.ctx.tools.schemas().map(schema => schema.name)).toEqual(['probe_tool'])
      const worker = b.ctx.agentLoop.create(SessionId('session-worker'), { provider: 'mock', model: 'mock' })
      expect(b.ctx.tools.schemas(worker).map(schema => schema.name)).toEqual(['probe_tool'])
      const workerRan = await dispatch(b.ctx, worker, 'probe_tool', {})
      expect(workerRan.isError).toBe(false)
    } finally {
      await b.dispose()
    }
  })

  it('admits explicitly enabled memory tools into the designated face', async () => {
    const b = await bench({
      designation: 'session-shadow',
      globalTools: [...MEMORY_TOOL_STUBS, 'probe_tool'],
    })
    try {
      const agent = await b.host.ensure()
      const names = b.ctx.tools.schemas(agent).map(schema => schema.name).sort()
      expect(names).toEqual([
        'memory_append',
        'memory_read',
        'memory_search',
        'project_open',
        'project_send',
        'project_status',
        'project_stop',
        'shadow_message_controller',
        'shadow_open_project',
        'shadow_release_project',
        'shadow_status',
      ])
    } finally {
      await b.dispose()
    }
  })

  it('denies execution outside the allowlist on the designated scope through the executor', async () => {
    const b = await bench({
      designation: 'session-shadow',
      globalTools: [...MEMORY_TOOL_STUBS, 'probe_tool'],
    })
    try {
      const agent = await b.host.ensure()

      // The router's own-layer project_* whitelist stays schema-visible (the
      // registry exempts own registrations from restrictions), so the
      // executor gate is what closes the bypass: a model-supplied request_id
      // would dodge the host-minted delivery contract the conversational
      // tools enforce.
      const project = await dispatch(b.ctx, agent, 'project_open', { path: b.root, request_id: 'probe-open' })
      expect(project.isError).toBe(true)
      expect(resultText(project)).toBe('Error: tool "project_open" is outside this session\'s allowlist')

      // A restricted-away inherited tool never dispatches: guards run before
      // the dispatch stage for every ready execution, so the allowlist gate
      // denies it too rather than surfacing the generic unknown-tool error.
      const inherited = await dispatch(b.ctx, agent, 'probe_tool', {})
      expect(inherited.isError).toBe(true)
      expect(resultText(inherited)).toBe('Error: tool "probe_tool" is outside this session\'s allowlist')

      // The allowlist itself executes: memory access and the conversational
      // tools.
      const memory = await dispatch(b.ctx, agent, 'memory_search', {})
      expect(memory.isError).toBe(false)
      const status = await dispatch(b.ctx, agent, 'shadow_status', {})
      expect(status.isError).toBe(false)
    } finally {
      await b.dispose()
    }
  })

  it('pins native presentation so a PTC deployment cannot collapse or widen the designated face', async () => {
    const b = await bench({ designation: 'session-shadow', tools: { mode: 'both' } })
    try {
      const agent = await b.host.ensure()
      expect(b.ctx.tools.schemas(agent).map(schema => schema.name)).not.toContain('run_code')
      const worker = b.ctx.agentLoop.create(SessionId('session-worker'), { provider: 'mock', model: 'mock' })
      expect(b.ctx.tools.schemas(worker).map(schema => schema.name)).toContain('run_code')
    } finally {
      await b.dispose()
    }
  })

  it('unwinds the enforcement when the conversation host row unloads and leaves the deployment face intact', async () => {
    const b = await bench({ designation: 'session-shadow', globalTools: ['probe_tool'] })
    try {
      const agent = await b.host.ensure()
      expect(b.ctx.tools.get('shadow_status', agent)).toBeDefined()
      expect(b.ctx.tools.get('probe_tool', agent)).toBeUndefined()

      // Unload the conversation host's own registered row: its lifecycle
      // effect disposes the owned agent, and the agent scope — the four
      // conversational registrations, the restriction, the guard — unwinds
      // with it. The global deployment face is untouched.
      await b.disposeHost()
      expect(b.ctx.tools.get('shadow_status', agent)).toBeUndefined()
      expect(b.ctx.tools.get('probe_tool', agent)).toBeDefined()
      expect(b.ctx.tools.get('probe_tool')).toBeDefined()
    } finally {
      await b.dispose()
    }
  })
})
