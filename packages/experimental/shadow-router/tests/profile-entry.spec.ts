/** The profile-config entry face: the declared session id, fail-closed default, and load-time validation. */

import { mkdir, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import { describe, expect, it } from 'vitest'
import { MockAdapter } from '../../../core/agent-loop/tests/mock-adapter.ts'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import ShadowRouter from '../src/index.ts'
import type { ShadowRouterConfig } from '../src/index.ts'
import { dispatch, failureText } from './helpers.ts'

/** Mount the real profile-shaped composition: every dep the router needs, no manual markShadow. */
async function mount(root: string, routerConfig: ShadowRouterConfig): Promise<Context> {
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
    await ctx.plugin(ShadowRouter, routerConfig)
    ctx.llm.registerAdapter(['mock'], new MockAdapter([]))
  } catch (error) {
    await ctx.fiber.dispose()
    throw error
  }
  return ctx
}

describe('shadow-router profile-config entry', () => {
  it('a declared shadowSessionId installs the four project tools for that scope only, and project_open runs for real', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-entry-open-'))
    const ctx = await mount(root, { shadowSessionId: 'session-declared', authorizedRoots: [root] })
    try {
      // A worker created before the declared session stays toolless: the
      // entry opens exactly one scope, the declared one.
      const worker = ctx.agentLoop.create(SessionId('session-worker'), { provider: 'mock', model: 'mock' })
      const declared = ctx.agentLoop.create(SessionId('session-declared'), { provider: 'mock', model: 'mock' })
      const workerStatus = await dispatch(ctx, worker, 'project_status', {})
      expect(workerStatus.isError).toBe(true)
      expect(failureText(workerStatus)).toContain('unknown tool "project_status"')

      // The declared session reaches the real entry face: open a project
      // under the authorized root and read the board back through status.
      const dir = join(root, 'project-a')
      await mkdir(dir, { recursive: true })
      const open = await dispatch(ctx, declared, 'project_open', { path: dir, request_id: 'entry-open-1' })
      expect(open.isError).toBe(false)
      const status = await dispatch(ctx, declared, 'project_status', {})
      expect(status.isError).toBe(false)
    } finally {
      await ctx.fiber.dispose()
      await rm(root, { recursive: true, force: true })
    }
  })

  it('an unconfigured router installs no project tools anywhere (fail-closed)', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-entry-closed-'))
    const ctx = await mount(root, {})
    try {
      const agent = ctx.agentLoop.create(SessionId('session-anyone'), { provider: 'mock', model: 'mock' })
      const status = await dispatch(ctx, agent, 'project_status', {})
      expect(status.isError).toBe(true)
      expect(failureText(status)).toContain('unknown tool "project_status"')
      expect(ctx.shadowRouter.listBindings()).toEqual([])
    } finally {
      await ctx.fiber.dispose()
      await rm(root, { recursive: true, force: true })
    }
  })

  it('a relative or missing authorizedRoot fails the load loud instead of booting half-configured', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-entry-invalid-'))
    try {
      const cases: [authorizedRoots: string[], message: string][] = [
        [['./relative-root'], 'must be an absolute path'],
        [[join(root, 'missing-root')], 'must be an existing directory at load'],
      ]
      for (const [authorizedRoots, message] of cases) {
        // The full dependency mount is required: on a bare context the
        // router's injected services never arrive, the fiber stays PENDING,
        // and no validation runs at all.
        await expect(mount(root, { authorizedRoots })).rejects.toThrow(message)
      }
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })
})
