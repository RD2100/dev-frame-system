/**
 * Shared test harness: the real tool registry, agent registry/loop, session
 * store, storage stack, binding registry, and hierarchy service every spec
 * runs on, over one temp JSON storage root. Every denial assertion observes
 * `ctx.tools.execute` — the real dispatcher — so a guard rejection is
 * evidence about the pipeline, not about a helper replay.
 * @module tests/helpers
 */

import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent, AgentHandle } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import type { AgentRole } from '@deepseek-ai/dsh-experimental-project-contracts'
import { PluginId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import AgentHierarchy, { type AgentHierarchyConfigInput } from '../src/index.ts'

/** Every probe tool the harness registers on the global surface. */
export const PROBE_TOOLS = [
  'project_read', 'subagent', 'fork', 'spawn_teammate', 'team_task_create', 'send_message', 'admin_panel',
] as const

/** Per-spec harness: one temp storage root and one booted real composition. */
export interface Harness {
  ctx: Context
  root: string
  /** Probe tool body invocation counts; a pre-execution denial leaves its counter at zero. */
  calls: Map<string, number>
  dispose: (options?: { readonly keepRoot?: boolean }) => Promise<void>
}

export interface HarnessOptions {
  /** Host config; defaults to {@link baseConfig}. */
  readonly config?: AgentHierarchyConfigInput
  /** Existing storage root to reuse (cold-recovery specs pass the previous root). */
  readonly root?: string
  /** Mount the hierarchy service lazily; deferred-mount specs mount it after the agents exist. */
  readonly mountHierarchy?: boolean
}

/** The default host config: every probe visible to controller and lead, worker keeps read and report only. */
export function baseConfig(): AgentHierarchyConfigInput {
  const all = [...PROBE_TOOLS]
  return {
    roleToolPolicies: {
      controller: { inheritedTools: all },
      lead: { inheritedTools: all },
      worker: { inheritedTools: ['project_read', 'send_message'] },
    },
  }
}

let probeCounter = 0
const probeSignal = new AbortController().signal

/**
 * Boot the real composition over a storage root. `admin_panel` sits outside
 * every deny face and outside the worker inherited list on purpose: it is
 * the observable for allow-face restriction installs.
 */
export async function harness(options: HarnessOptions = {}): Promise<Harness> {
  const root = options.root ?? await mkdtemp(join(tmpdir(), 'dsh-agent-hierarchy-'))
  const ctx = new Context()
  const calls = new Map<string, number>()
  try {
    await mountAgentLoopTestDependencies(ctx)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(AgentBindingRegistry)
    for (const name of PROBE_TOOLS) {
      ctx.tools.register(defineContentToolFixture({
        name,
        description: `agent-hierarchy probe ${name}`,
        parameters: {},
        async execute() {
          calls.set(name, (calls.get(name) ?? 0) + 1)
          return []
        },
      }))
    }
    if (options.mountHierarchy !== false) {
      await ctx.plugin(AgentHierarchy, options.config ?? baseConfig())
    }
  } catch (error: unknown) {
    await ctx.fiber.dispose()
    await rm(root, { recursive: true, force: true })
    throw error
  }
  return {
    ctx,
    root,
    calls,
    async dispose(disposeOptions) {
      await ctx.fiber.dispose()
      if (disposeOptions?.keepRoot !== true) await rm(root, { recursive: true, force: true })
    },
  }
}

/** Mount the hierarchy service on an already-running harness (deferred-mount cold-recovery spec). */
export async function mountHierarchy(ctx: Context, config?: AgentHierarchyConfigInput): Promise<void> {
  await ctx.plugin(AgentHierarchy, config ?? baseConfig())
}

/**
 * Create one real agent (session plus registry entry) with an optional
 * delegation depth stamped into the durable header.
 */
export async function createAgent(ctx: Context, id: string, delegationDepth?: number): Promise<Agent> {
  const handle = await createAgentHandle(ctx, id, delegationDepth)
  return handle.agent
}

/** Create one real agent and return its owning handle, for disposal assertions. */
export async function createAgentHandle(ctx: Context, id: string, delegationDepth?: number): Promise<AgentHandle> {
  return await ctx.agents.create({
    sessionId: SessionId(id),
    ...(delegationDepth === undefined ? {} : { meta: { delegationDepth } }),
  })
}

/** Bind one live agent into the hierarchy, optionally with its plugin scope. */
export async function bindAgent(ctx: Context, agent: Agent, role: AgentRole, pluginId?: string): Promise<void> {
  await ctx.agentBindings.bind({
    agentId: agent.id,
    role,
    ...(pluginId === undefined ? {} : { pluginId: PluginId(pluginId) }),
  })
}

/** Execute one probe tool through the real dispatcher as `agent`. */
export function executeProbe(ctx: Context, agent: Agent, name: string): Promise<ToolResultLike> {
  probeCounter += 1
  return ctx.tools.execute({
    callId: ToolCallId(`probe-${probeCounter}`),
    name,
    arguments: {},
    agent,
    signal: probeSignal,
  }) as Promise<ToolResultLike>
}

/** The part of a materialized tool result the assertions read. */
export interface ToolResultLike {
  readonly isError?: boolean
  readonly error?: { readonly message: string }
}
