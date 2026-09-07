/**
 * The fail-disarm consumption through a REAL Loader composition: a cordis.yml
 * with the full stack (session, persistence, projection, tools, project-memory
 * over an absent Vault, agent registry, native goal service, commands, the
 * command-goal-binding composition, and the goal-round-driver) is booted by
 * the actual Loader, so the mount face under test is the one the shipped
 * profiles use. The assertions are the ones the unit suites cannot see: the
 * composition really mounts the graded-listener family, a real memory-tool
 * failure grades into a fail-graded record, and the armed goal is actually
 * disarmed through the native port — while a tolerated grade and a
 * non-armed goal leave the goal state alone and the graded evidence lands in
 * every case.
 * @module tests/loader-composition
 */

import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import { createToolResultMessage, ToolCallId } from '@deepseek-ai/dsh-llm'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import type { Session } from '@deepseek-ai/dsh-session'
import type { SessionSeq } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import GoalService from '@deepseek-ai/dsh-goal'
import * as goalRoundDriver from '@deepseek-ai/dsh-goal-round-driver'
import * as projectMemory from '@deepseek-ai/dsh-experimental-project-memory'
import * as commandGoalBinding from '@deepseek-ai/dsh-experimental-command-goal-binding'
import { TaskId } from '../src/controller/goal-binding.ts'

let root: string | undefined
const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
  if (root !== undefined) await rm(root, { recursive: true, force: true })
  root = undefined
})

/** Write the cordis.yml under test: the full stack plus the composition mount. */
async function writeCompositionConfig(): Promise<string> {
  const configPath = join(root as string, 'cordis.yml')
  await writeFile(configPath, [
    "- name: '@deepseek-ai/dsh-session'",
    "- name: '@deepseek-ai/dsh-llm'",
    "- name: '@deepseek-ai/dsh-session-persistence-jsonl'",
    '  config:',
    `    root: ${JSON.stringify(join(root as string, 'sessions'))}`,
    '    compression: none',
    "- name: '@deepseek-ai/dsh-session-projection'",
    "- name: '@deepseek-ai/dsh-system-prompt'",
    "- name: '@deepseek-ai/dsh-tools'",
    "- name: '@deepseek-ai/dsh-agent'",
    "- name: '@deepseek-ai/dsh-agent-loop'",
    '  config:',
    '    agents: []',
    "- name: '@deepseek-ai/dsh-commands'",
    "- name: '@deepseek-ai/dsh-goal'",
    "- name: '@deepseek-ai/dsh-experimental-project-memory'",
    '  config:',
    '    workspaceId: ws-loader',
    `    vaultRoot: ${JSON.stringify(join(root as string, 'absent-vault'))}`,
    '    writeEnabled: true',
    "- name: '@deepseek-ai/dsh-experimental-command-goal-binding'",
    '  config:',
    '    workspaceId: ws-loader',
    `    workspaceRoot: ${JSON.stringify(root as string)}`,
    '    taskIds: [task-loader]',
    '    maxAttempts: 3',
    '    checks:',
    '      version: 1',
    '      checks:',
    `        - { checkId: loader-probe, executable: node, arguments: ['-e', 'process.exit(0)'], cwd: ${JSON.stringify(root as string)} }`,
    "- name: '@deepseek-ai/dsh-goal-round-driver'",
    '',
  ].join('\n'))
  return configPath
}

async function loadComposition(configPath: string): Promise<Context> {
  const ctx = new Context()
  contexts.push(ctx)
  ctx.baseUrl = pathToFileURL(root as string).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  const modules = new Map<string, unknown>([
    ['@deepseek-ai/dsh-session', SessionStore],
    ['@deepseek-ai/dsh-llm', LlmRuntime],
    ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
    ['@deepseek-ai/dsh-session-projection', SessionProjectionRegistry],
    ['@deepseek-ai/dsh-system-prompt', SystemPrompt],
    ['@deepseek-ai/dsh-tools', ToolRuntime],
    ['@deepseek-ai/dsh-agent', AgentRegistry],
    ['@deepseek-ai/dsh-agent-loop', AgentLoop],
    ['@deepseek-ai/dsh-commands', CommandRuntime],
    ['@deepseek-ai/dsh-goal', GoalService],
    ['@deepseek-ai/dsh-experimental-project-memory', projectMemory],
    ['@deepseek-ai/dsh-experimental-command-goal-binding', commandGoalBinding],
    ['@deepseek-ai/dsh-goal-round-driver', goalRoundDriver],
  ])
  ctx.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof ctx.loader.internal>
  await ctx.loader.create({
    name: 'cordis:include',
    config: { path: pathToFileURL(configPath).href },
  })
  await ctx.loader.await()
  const unloaded = [...ctx.loader.entries()]
    .filter(entry => entry.fiber === undefined && !entry.disabled)
    .map(entry => entry.options.name)
  expect(unloaded).toEqual([])
  return ctx
}

/** Boot the full stack and attach one live agent whose goal is armed. */
async function boot(): Promise<{ ctx: Context; agent: Agent; session: Session }> {
  root = await mkdtemp(join(tmpdir(), 'dsh-devframe-loader-'))
  const configPath = await writeCompositionConfig()
  const ctx = await loadComposition(configPath)
  const sessionId = SessionId(`loader-driver-${contexts.length}`)
  const { agent } = await ctx.agents.create({ sessionId, meta: { cwd: root } })
  const session = ctx.sessions.get(sessionId)
  if (session === undefined) throw new Error('the composition did not create the agent session')
  ctx.goals.create(agent, { objective: 'loader probe goal' })
  const goal = ctx.goals.get(agent)
  expect(goal?.phase).toBe('active')
  expect(goal?.activation).toBe('armed')
  return { ctx, agent, session }
}

/** The agent face the memory tools dispatch through: the live session only. */
function agentOn(session: Session): Agent {
  return { session } as unknown as Agent
}

/** Append the `tool/call` row exactly as the agent loop appends it. */
function appendToolCall(session: Session, turn: number, callId: string, name: string): SessionSeq {
  return session.append('tool/call', { turn, step: 1, callId: ToolCallId(callId), name, arguments: '{}' }).seq
}

/** Dispatch one real memory append against the unavailable Vault. */
function dispatchMemoryAppend(ctx: Context, session: Session, callId: string) {
  return ctx.tools.execute({
    callId: ToolCallId(callId),
    name: 'memory_append',
    arguments: { scope: 'project', source_ref: 'loader#event-1', kind: 'fact', body: 'the vault is absent.' },
    signal: new AbortController().signal,
    agent: agentOn(session),
  })
}

/** Append the `tool/result` row with the real dispatch outcome's error info. */
function appendToolResult(
  session: Session,
  turn: number,
  callId: string,
  callSeq: SessionSeq,
  outcome: { readonly isError: boolean; readonly error?: { readonly info?: { readonly name: string; readonly code: string } } },
): void {
  const message = createToolResultMessage({
    callId: ToolCallId(callId),
    content: [{ type: 'text', text: outcome.isError ? 'failed' : 'ok' }],
    isError: outcome.isError,
  })
  session.append('tool/result', {
    turn,
    step: 1,
    message,
    ...outcome.error?.info ? { error: outcome.error.info } : {},
  }, { surfaceOp: 'append', sourceEventSeqs: [callSeq] })
}

/** Drain the graded listener's deferred append: one macrotask settles both. */
async function drain(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
}

function taskWarningOf(session: Session) {
  return session.snapshotEvents().find(event => event.type === 'devframe/task-warning')
}

describe('fail-disarm through a real Loader composition', () => {
  it('grades a real memory failure and disarms the armed goal through the mounted family', async () => {
    const { ctx, agent, session } = await boot()
    ctx.devframeTaskGrading.declare(session.id, { taskId: TaskId('task-loader'), memory: 'required' })
    const callSeq = appendToolCall(session, 1, 'call-fail', 'memory_append')
    const outcome = await dispatchMemoryAppend(ctx, session, 'call-fail')
    expect(outcome.isError, 'the absent vault fails the append for real').toBe(true)
    appendToolResult(session, 1, 'call-fail', callSeq, outcome)
    await drain()

    const warning = taskWarningOf(session)
    expect(warning?.data).toMatchObject({ taskId: 'task-loader', warning: 'MEMORY_UNAVAILABLE', tool: 'memory_append', grade: 'fail' })
    expect(ctx.goals.get(agent)?.activation, 'the fail grade withdrew the automatic continuation').toBe('disarmed')
    expect(ctx.goals.get(agent)?.phase).toBe('active')
  })

  it('keeps the goal armed when the graded degradation is tolerated', async () => {
    const { ctx, agent, session } = await boot()
    ctx.devframeTaskGrading.declare(session.id, { taskId: TaskId('task-loader'), memory: 'optional' })
    const callSeq = appendToolCall(session, 1, 'call-tolerated', 'memory_append')
    const outcome = await dispatchMemoryAppend(ctx, session, 'call-tolerated')
    expect(outcome.isError).toBe(true)
    appendToolResult(session, 1, 'call-tolerated', callSeq, outcome)
    await drain()

    expect(taskWarningOf(session)?.data).toMatchObject({ grade: 'complete-with-warning' })
    expect(ctx.goals.get(agent)?.activation).toBe('armed')
    expect(ctx.goals.get(agent)?.phase).toBe('active')
  })

  it('lands the graded evidence without touching an already disarmed goal', async () => {
    const { ctx, agent, session } = await boot()
    ctx.goals.disarm(agent)
    ctx.devframeTaskGrading.declare(session.id, { taskId: TaskId('task-loader'), memory: 'required' })
    const callSeq = appendToolCall(session, 1, 'call-late', 'memory_append')
    const outcome = await dispatchMemoryAppend(ctx, session, 'call-late')
    expect(outcome.isError).toBe(true)
    appendToolResult(session, 1, 'call-late', callSeq, outcome)
    await drain()

    expect(taskWarningOf(session)?.data).toMatchObject({ grade: 'fail' })
    expect(ctx.goals.get(agent)?.activation).toBe('disarmed')
    expect(ctx.goals.get(agent)?.phase).toBe('active')
  })
})
