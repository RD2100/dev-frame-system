/**
 * Host-designation evidence: the composition row's `shadowSessionId` config
 * is the production call site for the real `markShadow` invocation. The
 * router marks the declared agent at the earliest resolvable point — at
 * init when it is already live, otherwise on `agent/created` — installs
 * nothing when unconfigured or never created, fails loud on invalid config,
 * and the marking stays in-memory while binding rows stay durable across a
 * cold restart and a same-process dispose/recreate cycle.
 * @module tests/host-designation
 */

import { describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { AgentHandle } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import { MockAdapter } from '../../../core/agent-loop/tests/mock-adapter.ts'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { SHADOW_TOOL_NAMES, ShadowRouter } from '../src/index.ts'
// The harness types the mounted service by the abstract seam contract; the
// concrete class is only the plugin value mounted below.
import type { ShadowRouter as ShadowRouterSeam } from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { ShadowRouterConfig } from '../src/index.ts'
import { dispatch, failureText } from './helpers.ts'

/**
 * The spec-local designation harness: the real composition from
 * `tests/helpers.ts` WITHOUT the forced `router.markShadow(shadow)` call and
 * without mounting the router, so each scenario controls where the
 * declarative designation enters. The host creation path is the real
 * `ctx.agents.create` registry factory, not a helper shortcut.
 */
interface DesignationHarness {
  ctx: Context
  root: string
  /** Create one live agent through the real agent registry factory. */
  createAgent: (sessionId: string) => Promise<AgentHandle>
  /** Create one real directory under the root and return its path. */
  makeProjectDir: (name: string) => Promise<string>
  /** Mount the router row: the declarative designation enters here. */
  mountRouter: (config: ShadowRouterConfig) => Promise<ShadowRouterSeam>
  /** Stop the context but keep the root on disk, so a restart can reuse it. */
  close: () => Promise<void>
  /** Stop the context and delete the temp root. */
  dispose: () => Promise<void>
}

/**
 * Boot the real composition over a directory, up to (but excluding) the
 * shadow-router row.
 * @param root - Existing storage root to reuse (restart scenarios pass the
 *   previous process's root); a spec-scoped temp root is expected here.
 * @returns the booted harness; the caller owns disposal.
 */
async function boot(root: string): Promise<DesignationHarness> {
  const ctx = new Context()
  try {
    await mountAgentLoopTestDependencies(ctx)
    await ctx.plugin(SessionProjectionRegistry)
    await ctx.plugin(AgentLoop, { agents: [] })
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(JsonlSessionPersistence, { root: join(root, 'session-logs') })
    await ctx.plugin(WorkspaceRegistry)
    await ctx.plugin(AgentBindingRegistry)
    ctx.llm.registerAdapter(['mock'], new MockAdapter([]))
  } catch (error: unknown) {
    await ctx.fiber.dispose()
    throw error
  }
  return {
    ctx,
    root,
    createAgent: sessionId => ctx.agents.create({ sessionId: SessionId(sessionId), agentOptions: { provider: 'mock', model: 'mock' } }),
    async makeProjectDir(name: string) {
      const dir = join(root, name)
      await mkdir(dir, { recursive: true })
      return dir
    },
    async mountRouter(config) {
      await ctx.plugin(ShadowRouter, config)
      return ctx.shadowRouter
    },
    async close() {
      await ctx.fiber.dispose()
    },
    async dispose() {
      await ctx.fiber.dispose()
      await rm(root, { recursive: true, force: true })
    },
  }
}

describe('shadow-router host designation via config', () => {
  it('marks the declared agent at creation through the real agent/created path and leaves every other scope unmarked', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designation-created-'))
    const h = await boot(root)
    try {
      const router = await h.mountRouter({ shadowSessionId: 'session-shadow' })
      // No agent is live yet, so the mount installed nothing; the marking
      // happens through the real `agent/created` listener, not a host call.
      const shadow = (await h.createAgent('session-shadow')).agent
      expect(router.isShadow(shadow)).toBe(true)
      const worker = (await h.createAgent('session-worker')).agent
      expect(router.isShadow(worker)).toBe(false)

      // The declared scope carries exactly the four project tools; the
      // testkit mounts no global tools, so full equality is the whitelist face.
      expect(h.ctx.tools.schemas(shadow).map(schema => schema.name)).toEqual([...SHADOW_TOOL_NAMES])
      const workerNames = h.ctx.tools.schemas(worker).map(schema => schema.name)
      for (const name of SHADOW_TOOL_NAMES) {
        expect(workerNames, `the unmarked scope must not list "${name}"`).not.toContain(name)
      }

      // Dispatcher cross-check through the real tool runtime: the unmarked
      // call cannot resolve the name, the marked call reaches the service.
      const rejected = await dispatch(h.ctx, worker, 'project_status', {})
      expect(rejected.isError).toBe(true)
      expect(failureText(rejected)).toContain('unknown tool "project_status"')
      const accepted = await dispatch(h.ctx, shadow, 'project_status', {})
      expect(accepted.isError).toBe(false)
    } finally {
      await h.dispose()
    }
  })

  it('marks an agent that is already live when the router mounts (init scan path)', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designation-scan-'))
    const h = await boot(root)
    try {
      // The host creates the agent before the router row exists, so no
      // `agent/created` listener could have observed it.
      const shadow = (await h.createAgent('session-shadow')).agent
      const router = await h.mountRouter({ shadowSessionId: 'session-shadow' })
      expect(router.isShadow(shadow)).toBe(true)
      expect(h.ctx.tools.schemas(shadow).map(schema => schema.name)).toEqual([...SHADOW_TOOL_NAMES])
    } finally {
      await h.dispose()
    }
  })

  it('marks nothing when unconfigured and fails closed on direct service calls', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designation-unconfigured-'))
    const h = await boot(root)
    try {
      const router = await h.mountRouter({})
      // Even the id a composition would have designated gains nothing.
      const shadow = (await h.createAgent('session-shadow')).agent
      const worker = (await h.createAgent('session-worker')).agent
      expect(router.isShadow(shadow)).toBe(false)
      expect(router.isShadow(worker)).toBe(false)
      expect(router.isShadow(undefined)).toBe(false)
      for (const agent of [shadow, worker]) {
        const names = h.ctx.tools.schemas(agent).map(schema => schema.name)
        for (const name of SHADOW_TOOL_NAMES) {
          expect(names, `the unconfigured scope must not list "${name}"`).not.toContain(name)
        }
      }
      // Fail-closed service face: the unmarked caller is rejected before any
      // mutation, so no binding row appears either.
      await expect(router.openProject(shadow, { path: join(root, 'never-created'), requestId: 'designation-unconfigured-open' }))
        .rejects.toMatchObject({ code: 'SHADOW_CALLER_FORBIDDEN' })
      expect(router.listBindings()).toEqual([])
    } finally {
      await h.dispose()
    }
  })

  it('fails loud at boot on an invalid configured shadowSessionId', async () => {
    for (const invalid of ['', '   ']) {
      const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designation-invalid-'))
      const h = await boot(root)
      try {
        await expect(h.mountRouter({ shadowSessionId: invalid }))
          .rejects.toMatchObject({ code: 'SHADOW_INVALID_CONFIG' })
      } finally {
        await h.dispose()
      }
    }
  })

  it('re-marks the declared agent after a cold restart on the same root while the binding row restores identically', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designation-cold-'))

    // Process 1: the declared agent is marked at creation and opens one real
    // project, so a durable binding row exists before the restart.
    const before = await (async () => {
      const h = await boot(root)
      try {
        const router = await h.mountRouter({ authorizedRoots: [root], shadowSessionId: 'session-shadow' })
        const shadow = (await h.createAgent('session-shadow')).agent
        expect(router.isShadow(shadow)).toBe(true)
        const dir = await h.makeProjectDir('designation-project')
        const open = await router.openProject(shadow, { path: dir, requestId: 'designation-cold-open-1' })
        expect(open.state).toBe('ready')
        const record = router.findBinding(open.workspaceId)!
        expect(record.state).toBe('ready')
        return record
      } finally {
        // The JSON backend refuses a second live handle, so this settles first.
        await h.close()
      }
    })()

    // Process 2 over the same root: the row restores, the designation does
    // not — until the host recreates the same session id.
    const h2 = await boot(root)
    try {
      const router = await h2.mountRouter({ authorizedRoots: [root], shadowSessionId: 'session-shadow' })
      expect(router.listBindings().map(record => record.workspaceId)).toEqual([before.workspaceId])
      expect(router.findBinding(before.workspaceId)).toEqual(before)
      const recreated = (await h2.createAgent('session-shadow')).agent
      expect(router.isShadow(recreated)).toBe(true)
      expect(h2.ctx.tools.schemas(recreated).map(schema => schema.name)).toEqual([...SHADOW_TOOL_NAMES])
    } finally {
      await h2.dispose()
    }
  })

  it('removes the marking when the designated agent is disposed and re-marks a recreated same-id agent', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-designation-dispose-'))
    const h = await boot(root)
    try {
      const router = await h.mountRouter({ shadowSessionId: 'session-shadow' })
      const first = await h.createAgent('session-shadow')
      expect(router.isShadow(first.agent)).toBe(true)
      // The agent/disposed cleanup removes the in-memory designation.
      await first.dispose()
      expect(router.isShadow(first.agent)).toBe(false)
      const recreated = await h.createAgent('session-shadow')
      expect(router.isShadow(recreated.agent)).toBe(true)
      expect(h.ctx.tools.schemas(recreated.agent).map(schema => schema.name)).toEqual([...SHADOW_TOOL_NAMES])
    } finally {
      await h.dispose()
    }
  })
})
