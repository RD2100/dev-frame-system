/**
 * Shared test harness: one temp storage root and the real
 * agent-loop/session/storage/storage-domain/JSON/persistence/workspace/
 * binding-registry/router composition every spec runs on. `seedHarness`
 * boots only the storage stack so a spec can write crash-residue rows
 * through the real domain before a router process cold-restores them.
 * @module tests/helpers
 */

import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import * as StorageSqlite from '@deepseek-ai/dsh-storage-sqlite'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import { MockAdapter } from '../../../core/agent-loop/tests/mock-adapter.ts'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import ShadowRouter, { shadowRouterDomainSpec } from '../src/index.ts'
import { workspaceDomainSpec, WorkspaceId } from '@deepseek-ai/dsh-workspace'
// The harness types the mounted service by the abstract seam contract; the
// concrete class is only the plugin value mounted below.
import type { ShadowRouter as ShadowRouterSeam } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { ShadowRouterConfig } from '../src/index.ts'

/** The per-spec harness: one temp root, one booted context, one marked Shadow. */
export interface Harness {
  ctx: Context
  root: string
  router: ShadowRouterSeam
  /** The host-designated Shadow session every authorized call goes through. */
  shadow: Agent
  /** A live agent that is never marked as Shadow (the worker probe). */
  worker: Agent
  /** Create one real directory under the root and return its path. */
  makeProjectDir: (name: string) => Promise<string>
  /** Stop the context but keep the root on disk, so a spec can reopen it. */
  close: () => Promise<void>
  /** Stop the context and delete the temp root. */
  dispose: () => Promise<void>
}

/** Storage backends the delivery anchors run over: the suite default and the sqlite medium. */
export type HarnessBackend = 'json' | 'sqlite'
export const HARNESS_BACKENDS: readonly HarnessBackend[] = ['json', 'sqlite']

/** Harness mount options: which storage backend serves the shadow-router domain. */
export interface HarnessOptions {
  /** Storage backend name; defaults to the suite's json medium. */
  backend?: HarnessBackend
}

/**
 * Boot the real composition over a directory.
 * @param root - Existing storage root to reuse (cold-restore specs pass the
 *   previous harness's root); omitted, a fresh temp root is created.
 * @param routerConfig - Router config forwarded without mutation.
 * @param options - Mount options; every reopen of one root must pass the same
 *   backend or the cold restore reads a different medium than the crash wrote.
 * @returns the booted harness; the caller owns disposal.
 */
export async function harness(root?: string, routerConfig: ShadowRouterConfig = {}, options: HarnessOptions = {}): Promise<Harness> {
  const resolved = root ?? await mkdtemp(join(tmpdir(), 'dsh-shadow-router-'))
  const backend = options.backend ?? 'json'
  const ctx = new Context()
  let shadow: Agent | undefined
  try {
    await mountAgentLoopTestDependencies(ctx)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    await ctx.plugin(Storage)
    if (backend === 'sqlite') await ctx.plugin(StorageSqlite, { path: join(resolved, 'shadow-state.db') })
    else await ctx.plugin(StorageJson, { root: resolved })
    await ctx.plugin(StorageDomain, { backend })
    await ctx.plugin(JsonlSessionPersistence, { root: join(resolved, 'session-logs') })
    await ctx.plugin(WorkspaceRegistry)
    await ctx.plugin(AgentBindingRegistry)
    await ctx.plugin(ShadowRouter, routerConfig)
    ctx.llm.registerAdapter(['mock'], new MockAdapter([]))
    shadow = ctx.agentLoop.create(SessionId('session-shadow'), { provider: 'mock', model: 'mock' })
  } catch (error) {
    await ctx.fiber.dispose()
    await rm(resolved, { recursive: true, force: true })
    throw error
  }
  const router = ctx.shadowRouter
  router.markShadow(shadow)
  const worker = ctx.agentLoop.create(SessionId('session-worker'), { provider: 'mock', model: 'mock' })
  return {
    ctx,
    root: resolved,
    router,
    shadow,
    worker,
    async makeProjectDir(name: string) {
      const dir = join(resolved, name)
      await mkdir(dir, { recursive: true })
      return dir
    },
    async close() {
      await ctx.fiber.dispose()
    },
    async dispose() {
      await ctx.fiber.dispose()
      await rm(resolved, { recursive: true, force: true })
    },
  }
}

/**
 * Boot only the real storage stack over an existing root, so a spec can write
 * crash-residue rows through the real domain (schema-validated on write and on
 * restore) before a router process cold-restores them. The caller closes the
 * returned domain before disposing.
 * @param root - Existing storage root shared with the router harness.
 * @param options - Mount options; must match the backend the router harness
 *   reopens the same root with.
 * @returns the open domain handle and the harness disposal.
 */
export async function seedHarness(root: string, options: HarnessOptions = {}): Promise<{
  domain: StorageDomain.Domain<typeof shadowRouterDomainSpec>
  workspaceDomain: StorageDomain.Domain<typeof workspaceDomainSpec>
  dispose: () => Promise<void>
}> {
  const backend = options.backend ?? 'json'
  const ctx = new Context()
  try {
    await ctx.plugin(Storage)
    if (backend === 'sqlite') await ctx.plugin(StorageSqlite, { path: join(root, 'shadow-state.db') })
    else await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend })
  } catch (error) {
    await ctx.fiber.dispose()
    throw error
  }
  const domain = await ctx.storageDomain.open(shadowRouterDomainSpec)
  const workspaceDomain = await ctx.storageDomain.open(workspaceDomainSpec)
  return {
    domain,
    workspaceDomain,
    async dispose() {
      await domain.close()
      await workspaceDomain.close()
      await ctx.fiber.dispose()
    },
  }
}

/**
 * Seed one workspace registry fact: the durable record plus the authoritative
 * order entry, mirroring what `WorkspaceRegistry.create` writes before a
 * binding reservation can crash.
 * @param workspaceDomain - The open workspace domain from `seedHarness`.
 * @param workspaceId - The workspace id the binding row will reference.
 * @param canonicalPath - The canonical project root.
 */
export async function seedWorkspaceFact(
  workspaceDomain: StorageDomain.Domain<typeof workspaceDomainSpec>,
  workspaceId: string,
  canonicalPath: string,
): Promise<void> {
  const now = new Date().toISOString()
  await workspaceDomain.table('workspaces').put(WorkspaceId(workspaceId), {
    path: canonicalPath,
    title: `seeded-${workspaceId}`,
    sessionIds: [],
    createdAt: now,
    updatedAt: now,
  })
  await workspaceDomain.global.set({
    initialized: true,
    workspaceIds: [WorkspaceId(workspaceId)],
    archivedSessionIds: [],
  })
}

/** Dispatch one tool call through the real tool runtime as one agent. */
export function dispatch(
  ctx: Context,
  agent: Agent,
  name: string,
  args: Record<string, unknown>,
  callId = `shadow-call-${Math.random().toString(36).slice(2, 8)}`,
): ReturnType<Context['tools']['execute']> {
  return ctx.tools.execute({
    callId: ToolCallId(callId),
    name,
    arguments: args,
    signal: new AbortController().signal,
    agent,
  })
}

/** Flatten a tool result's text blocks; failures may carry no content blocks. */
export function resultText(result: { readonly content?: readonly { readonly type: string; readonly text?: string }[] }): string {
  return result.content?.flatMap(block => block.type === 'text' && typeof block.text === 'string' ? [block.text] : []).join('') ?? ''
}

/** The rejection text of one failed dispatch: the typed failure message, or the rendered blocks. */
export function failureText(result: {
  readonly isError: boolean
  readonly error?: { readonly message?: string }
  readonly content?: readonly { readonly type: string; readonly text?: string }[]
}): string {
  return result.isError ? (result.error?.message ?? resultText(result)) : ''
}

/** The structured HarnessError code a failed dispatch carried, when any. */
export function failureCode(result: {
  readonly isError: boolean
  readonly error?: { readonly info?: { readonly code?: string } }
}): string | undefined {
  return result.isError ? result.error?.info?.code : undefined
}

export { shadowRouterDomainSpec }
