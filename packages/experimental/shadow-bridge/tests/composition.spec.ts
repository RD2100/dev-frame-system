/**
 * Real-Loader composition evidence for the shadow delivery bridge, keyless:
 * the cordis.yml boots the real storage, session, agent-loop, workspace,
 * binding-registry, shadow-router, and bridge rows with a scripted mock model
 * as the only external stand-in. The scenarios drive the router's real host
 * send path or crash-residue seeded rows, assert the controller's durable
 * session log, and restart over the same root to pin exactly-once forwarding.
 * @module tests/composition
 */

import { mkdir, mkdtemp, realpath, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId, SessionSeq } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import WorkspaceRegistry, { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import {
  AcceptanceHash,
  ShadowMessageId,
  ShadowRequestId,
} from '@deepseek-ai/dsh-experimental-shadow-routing'
import type { ShadowBindingRecord, ShadowDeliveryRecord } from '@deepseek-ai/dsh-experimental-shadow-routing'
// Loader plugin values: the concrete provider class and its domain spec.
import { ShadowRouter, shadowRouterDomainSpec } from '@deepseek-ai/dsh-experimental-shadow-router'
import { MockAdapter, textResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import * as bridge from '../src/index.ts'

const MOCK_RESPONSES = 8

interface Boot {
  ctx: Context
  adapter: MockAdapter
  close: () => Promise<void>
}

/**
 * Boot the real composition over one storage root. The Loader imports every
 * row through the module map, so the bridge and router rows run through the
 * same namespace/config resolution a shipped composition uses.
 * @param root - Existing storage root shared by JSON storage and session logs.
 * @param bridgeConfig - The bridge row's config; the happy default keeps a
 *   fast safety net and bounds forwarded text generously. A partial config
 *   must fail the boot.
 * @returns the booted context, its scripted adapter, and the disposer.
 */
async function boot(root: string, bridgeConfig: Record<string, unknown> = { intervalMs: 5, followupMaxChars: 4000 }): Promise<Boot> {
  const ctx = new Context()
  let closed = false
  const close = async (): Promise<void> => {
    if (closed) return
    closed = true
    await ctx.fiber.dispose()
  }
  const adapter = new MockAdapter(Array.from({ length: MOCK_RESPONSES }, () => () => textResponse('ack')))
  try {
    const modules = new Map<string, unknown>([
      ['@deepseek-ai/dsh-llm', LlmRuntime],
      ['@deepseek-ai/dsh-session', SessionStore],
      ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
      ['@deepseek-ai/dsh-system-prompt', SystemPrompt],
      ['@deepseek-ai/dsh-tools', ToolRuntime],
      ['@deepseek-ai/dsh-agent', AgentRegistry],
      ['@deepseek-ai/dsh-agent-loop', AgentLoop],
      ['@deepseek-ai/dsh-session-projection', SessionProjectionRegistry],
      ['@deepseek-ai/dsh-storage', Storage],
      ['@deepseek-ai/dsh-storage-json', StorageJson],
      ['@deepseek-ai/dsh-storage-domain', StorageDomain],
      ['@deepseek-ai/dsh-workspace', WorkspaceRegistry],
      ['@deepseek-ai/dsh-experimental-session-identity', AgentBindingRegistry],
      ['@deepseek-ai/dsh-experimental-shadow-router', ShadowRouter],
      ['@deepseek-ai/dsh-experimental-shadow-bridge', bridge],
    ])
    const settings: Record<string, unknown> = {
      '@deepseek-ai/dsh-agent-loop': { agents: [] },
      '@deepseek-ai/dsh-session-persistence-jsonl': { root: join(root, 'sessions'), compression: 'none', writeBatchMaxDelayMs: 1 },
      '@deepseek-ai/dsh-storage-json': { root },
      '@deepseek-ai/dsh-storage-domain': { backend: 'json' },
      '@deepseek-ai/dsh-experimental-shadow-router': { authorizedRoots: [root], shadowSessionId: 'session-shadow' },
      '@deepseek-ai/dsh-experimental-shadow-bridge': bridgeConfig,
    }
    const configPath = join(root, 'cordis.yml')
    await writeFile(configPath, JSON.stringify([...modules.keys()].map(name => ({ name, config: settings[name] }))))
    ctx.baseUrl = pathToFileURL(root).href + '/'
    await ctx.plugin(Loader)
    ctx.loader.builtins.include = Include
    ctx.loader.internal = {
      version: 'v2',
      async import(specifier: string) {
        if (!modules.has(specifier)) throw new Error(`Unexpected Loader import ${specifier}`)
        return modules.get(specifier)
      },
    } as unknown as NonNullable<typeof ctx.loader.internal>
    await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
    await ctx.loader.await()
    expect([...ctx.loader.entries()].filter(entry => entry.fiber === undefined && !entry.disabled)
      .map(entry => entry.options.name)).toEqual([])
    ctx.llm.registerAdapter(['mock'], adapter)
  } catch (error: unknown) {
    await close()
    throw error
  }
  return { ctx, adapter, close }
}

/**
 * Seed the `shadow_router` domain through the real storage stack, as a
 * previous process would have left it: bindings and deliveries are written
 * with schema validation and closed before the router opens the same unit.
 */
async function seedRouterState(root: string, rows: {
  readonly bindings: readonly ShadowBindingRecord[]
  readonly deliveries: readonly ShadowDeliveryRecord[]
}): Promise<void> {
  const ctx = new Context()
  try {
    await ctx.plugin(Storage)
    await ctx.plugin(StorageJson, { root })
    await ctx.plugin(StorageDomain, { backend: 'json' })
    const domain = await ctx.storageDomain.open(shadowRouterDomainSpec)
    const bindings = domain.table('bindings')
    const deliveries = domain.table('deliveries')
    for (const record of rows.bindings) await bindings.put(record.workspaceId, record)
    for (const record of rows.deliveries) await deliveries.put(record.messageId, record)
    await domain.close()
  } finally {
    await ctx.fiber.dispose()
  }
}

/** One ready controller binding with an authorized open run; overrides replace any field. */
function seededBinding(overrides: Partial<ShadowBindingRecord> & { readonly workspaceId: WorkspaceId }): ShadowBindingRecord {
  return {
    canonicalPath: overrides.canonicalPath ?? '/seeded/project',
    controllerSessionId: overrides.controllerSessionId ?? ('session-seeded-ctrl' as SessionId),
    profileKey: 'devframe',
    bindingRevision: 1,
    requestId: 'req-seed-open',
    state: 'ready',
    createdAt: '2026-09-11T00:00:00.000Z',
    updatedAt: '2026-09-11T00:00:00.000Z',
    ...overrides,
  }
}

/** One received work delivery row; overrides replace any field. */
function seededDelivery(overrides: Partial<ShadowDeliveryRecord> & { readonly messageId: ShadowMessageId }): ShadowDeliveryRecord {
  return {
    requestId: ShadowRequestId(`req-${overrides.messageId}`),
    sourceSessionId: 'session-shadow' as SessionId,
    workspaceId: overrides.workspaceId ?? WorkspaceId('ws-seeded'),
    bindingRevision: 1,
    goalId: 'goal-seeded',
    acceptanceHash: AcceptanceHash('hash-seeded-001'),
    mode: 'work',
    text: 'Seeded instruction from a previous process.',
    state: 'received',
    createdAt: '2026-09-11T00:00:01.000Z',
    updatedAt: '2026-09-11T00:00:02.000Z',
    receivedAt: '2026-09-11T00:00:02.000Z',
    ...overrides,
  }
}

/** Every `user/message` text in one session's durable log, oldest first. */
function userMessageTexts(ctx: Context, sessionId: SessionId): string[] {
  const session = ctx.sessions.get(sessionId)
  if (session === undefined) return []
  const texts: string[] = []
  for (let seq = 0; seq < session.seq; seq++) {
    const event = session.eventAt(SessionSeq(seq))
    if (event === undefined || event.type !== 'user/message') continue
    texts.push(event.data.content.flatMap(block => block.type === 'text' ? [block.text] : []).join(''))
  }
  return texts
}

/** Create the designated Shadow session through the real agent factory. */
async function createShadow(ctx: Context): Promise<Agent> {
  return (await ctx.agents.create({
    sessionId: SessionId('session-shadow'),
    agentOptions: { provider: 'mock', model: 'mock' },
  })).agent
}

/** Create one live controller session through the real agent factory. */
async function createController(ctx: Context, sessionId: string, cwd: string): Promise<Agent> {
  return (await ctx.agents.create({
    sessionId: SessionId(sessionId),
    agentOptions: { provider: 'mock', model: 'mock' },
    meta: { cwd },
  })).agent
}

const sleep = (ms: number): Promise<void> => new Promise<void>((resolve) => { setTimeout(resolve, ms) })

describe('the shadow delivery bridge through a real Loader composition', () => {
  it('exports the function-plugin face with no default export', () => {
    expect('default' in bridge).toBe(false)
    expect(bridge.name).toBe('shadow-bridge')
    expect(bridge.inject).toEqual(['agents', 'storageDomain'])
    expect(typeof bridge.apply).toBe('function')
  })

  it('fails the load when the bridge row omits a required config field', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-bridge-misconfig-'))
    try {
      await expect(boot(root, { intervalMs: 5 })).rejects.toThrow(/shadow-bridge.*missing required/s)
    } finally {
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  it('forwards a sent work delivery into the live controller turn and never re-forwards it after a restart', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-bridge-forward-'))
    const boots: Boot[] = []
    try {
      const projectDir = join(root, 'project-a')
      await mkdir(projectDir)
      const canonicalDir = await realpath(projectDir)
      await seedRouterState(root, {
        bindings: [seededBinding({
          workspaceId: WorkspaceId('ws-project-a'),
          canonicalPath: canonicalDir,
          controllerSessionId: SessionId('session-ctrl-a'),
          activeGoalId: 'goal-a',
          activeAcceptanceHash: AcceptanceHash('hash-a-0000001'),
        })],
        deliveries: [],
      })

      const first = await boot(root)
      boots.push(first)
      await createShadow(first.ctx)
      const controller = await createController(first.ctx, 'session-ctrl-a', canonicalDir)
      const send = await first.ctx.shadowRouter.sendToProjectForHost({
        workspaceId: 'ws-project-a',
        text: 'Verify the delivery loop end to end.',
        requestId: 'send-a-1',
      })
      expect(send).toMatchObject({ messageId: 'msg-send-a-1', status: 'received' })
      const firstTexts = await vi.waitFor(() => {
        const rows = userMessageTexts(first.ctx, SessionId('session-ctrl-a'))
        expect(rows).toHaveLength(1)
        return rows
      })
      expect(firstTexts[0]).toContain('[Shadow delivery msg-send-a-1 for workspace ws-project-a]')
      expect(firstTexts[0]).toContain('Verify the delivery loop end to end.')
      await controller.whenIdle()
      expect(first.adapter.requests.length).toBeGreaterThanOrEqual(1)
      // Forwarding never settles the delivery: completed stays a controller-side fact.
      const [forwardedRow] = first.ctx.shadowRouter.listDeliveries(WorkspaceId('ws-project-a'))
      expect(forwardedRow?.state).toBe('received')
      await first.close()

      const second = await boot(root)
      boots.push(second)
      await createShadow(second.ctx)
      const resumed = await second.ctx.agents.resume({
        resumeSessionId: SessionId('session-ctrl-a'),
        agentOptions: { provider: 'mock', model: 'mock' },
      })
      await second.ctx.shadowRouter.sendToProjectForHost({
        workspaceId: 'ws-project-a',
        text: 'Second, fresh instruction.',
        requestId: 'send-a-2',
      })
      await vi.waitFor(() => {
        expect(userMessageTexts(second.ctx, SessionId('session-ctrl-a')).filter(text => text.includes('msg-send-a-2')))
          .toHaveLength(1)
      })
      await resumed.agent.whenIdle()
      // Let many polls run: the restarted bridge must replay neither delivery.
      await sleep(150)
      const restartedTexts = userMessageTexts(second.ctx, SessionId('session-ctrl-a'))
      expect(restartedTexts.filter(text => text.includes('msg-send-a-1'))).toHaveLength(1)
      expect(restartedTexts.filter(text => text.includes('msg-send-a-2'))).toHaveLength(1)
      expect(second.adapter.requests.length).toBe(1)
    } finally {
      for (const instance of boots.reverse()) await instance.close()
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  it('forwards a work delivery after a host open establishes the authorized run', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-bridge-openauth-'))
    const boots: Boot[] = []
    try {
      const projectDir = join(root, 'project-open-auth')
      await mkdir(projectDir)
      // First process: the panel/conversation open path with no seeded binding
      // and no manual setActiveGoal — the host bridge itself records the
      // authorized run and provisions the controller session.
      const first = await boot(root)
      boots.push(first)
      await createShadow(first.ctx)
      const opened = await first.ctx.shadowRouter.openProjectForHost({ path: projectDir, requestId: 'host-open-auth-1' })
      expect(opened.state).toBe('ready')
      expect(first.ctx.shadowRouter.findBinding(opened.workspaceId)).toMatchObject({
        activeGoalId: 'host-run-1',
        activeAcceptanceHash: 'open-run-1',
      })
      // The host duty this exercise depends on: persistence is lazy, so the
      // freshly provisioned controller session is materialized before the
      // restart, the way an adopting host surface persists it.
      await first.ctx.sessionPersistence.ensureMaterialized(first.ctx.sessions.get(opened.controllerSessionId)!)
      await first.close()

      // Restart: the run record and the provisioned controller session survive,
      // so a host send forwards into the resumed controller without any
      // re-authorization.
      const second = await boot(root)
      boots.push(second)
      await createShadow(second.ctx)
      await second.ctx.agents.resume({
        resumeSessionId: opened.controllerSessionId,
        agentOptions: { provider: 'mock', model: 'mock' },
      })
      const send = await second.ctx.shadowRouter.sendToProjectForHost({
        workspaceId: opened.workspaceId,
        text: 'Verify the open path authorizes the run.',
        requestId: 'send-open-auth-1',
      })
      expect(send).toMatchObject({ messageId: 'msg-send-open-auth-1', status: 'received' })
      const texts = await vi.waitFor(() => {
        const rows = userMessageTexts(second.ctx, opened.controllerSessionId)
        expect(rows).toHaveLength(1)
        return rows
      })
      expect(texts[0]).toContain(`[Shadow delivery msg-send-open-auth-1 for workspace ${opened.workspaceId}]`)
      expect(texts[0]).toContain('Verify the open path authorizes the run.')
    } finally {
      for (const instance of boots.reverse()) await instance.close()
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  it('does not forward without an authorized open run or into a stopped project', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-bridge-gates-'))
    const boots: Boot[] = []
    try {
      await seedRouterState(root, {
        bindings: [
          // b1 is ready but records no authorized open run.
          seededBinding({ workspaceId: WorkspaceId('ws-b1'), controllerSessionId: SessionId('session-ctrl-b1') }),
          // b2 is stopped and admits nothing even though a run is on record.
          seededBinding({
            workspaceId: WorkspaceId('ws-b2'),
            controllerSessionId: SessionId('session-ctrl-b2'),
            state: 'stopped',
            bindingRevision: 2,
            activeGoalId: 'goal-b2',
            activeAcceptanceHash: AcceptanceHash('hash-b2-000001'),
          }),
        ],
        deliveries: [
          seededDelivery({ messageId: ShadowMessageId('msg-seed-b1'), workspaceId: WorkspaceId('ws-b1'), text: 'Unowned work.' }),
          seededDelivery({ messageId: ShadowMessageId('msg-seed-b2'), workspaceId: WorkspaceId('ws-b2'), goalId: 'goal-b2', acceptanceHash: AcceptanceHash('hash-b2-000001'), text: 'Stopped project work.' }),
        ],
      })
      const instance = await boot(root)
      boots.push(instance)
      await createShadow(instance.ctx)
      await createController(instance.ctx, 'session-ctrl-b1', root)
      await createController(instance.ctx, 'session-ctrl-b2', root)
      // Many polls run; neither gate ever opens.
      await sleep(250)
      expect(userMessageTexts(instance.ctx, SessionId('session-ctrl-b1'))).toEqual([])
      expect(userMessageTexts(instance.ctx, SessionId('session-ctrl-b2'))).toEqual([])
      const states = instance.ctx.shadowRouter.listDeliveries().map(record => record.state)
      expect(states).toEqual(['received', 'received'])
    } finally {
      for (const instance of boots.reverse()) await instance.close()
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })

  it('leaves a delivery for the next poll while no controller is live and forwards once one appears', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-bridge-defer-'))
    const boots: Boot[] = []
    try {
      await seedRouterState(root, {
        // The binding carries the authorized open run the seeded delivery asserts;
        // only the live controller is missing, which is the deferral under test.
        bindings: [seededBinding({
          workspaceId: WorkspaceId('ws-defer'),
          controllerSessionId: SessionId('session-ctrl-c'),
          activeGoalId: 'goal-seeded',
          activeAcceptanceHash: AcceptanceHash('hash-seeded-001'),
        })],
        deliveries: [seededDelivery({ messageId: ShadowMessageId('msg-seed-c1'), workspaceId: WorkspaceId('ws-defer'), text: 'Deferred instruction.' })],
      })
      const instance = await boot(root)
      boots.push(instance)
      await createShadow(instance.ctx)
      // No controller is live: the delivery stays put across many polls.
      await sleep(150)
      expect(userMessageTexts(instance.ctx, SessionId('session-ctrl-c'))).toEqual([])
      await createController(instance.ctx, 'session-ctrl-c', root)
      await vi.waitFor(() => {
        const rows = userMessageTexts(instance.ctx, SessionId('session-ctrl-c'))
        expect(rows).toHaveLength(1)
        expect(rows[0]).toContain('[Shadow delivery msg-seed-c1 for workspace ws-defer]')
        expect(rows[0]).toContain('Deferred instruction.')
      })
    } finally {
      for (const instance of boots.reverse()) await instance.close()
      await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
    }
  })
})
