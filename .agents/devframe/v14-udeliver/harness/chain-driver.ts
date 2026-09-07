/**
 * V14-udeliver B1 real-chain driver: plays the UI-adapter role inside a real
 * shipped-profile web boot. Sessions are created through the real
 * session-controller face (`ctx.get('sessionController').create`) — the same
 * remote the Web client calls — so the agent runs under the composition's
 * standard preset (subagent/workflow/shell tools mounted); goal commands go
 * through `ctx.commands.execute`, the boundary the command-goal-binding
 * composition spec names for "a UI adapter". Every step lands JSONL evidence.
 * This is NOT the browser pixel path; every record says so.
 *
 * Mode `start`: await the composition, create the 总控 session+agent under the
 * standard preset, execute `/devframe-start <objective>` (real binding + real
 * required-check subprocess), write the handshake flag, deliver the chain
 * task as a real user message, wait for quiescence, flush.
 *
 * Mode `resume`: await the composition, re-create the recorded session through
 * the same idempotent create-or-adopt face (the Web resume path), execute
 * `/devframe-resume`, record, flush.
 * @module harness/chain-driver
 */

import { appendFileSync } from 'node:fs'
import { writeFileSync } from 'node:fs'
import type { SessionController } from '@deepseek-ai/dsh-api-session-controller'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { Context } from '@deepseek-ai/cordis'

/** Loader plugin name. */
export const name = 'v14-udeliver-chain-driver'

/** Services the driver needs at the same boundary a UI adapter uses. */
export const inject = [
  'commands',
  'agents',
  'sessions',
  'sessionController',
  'goals',
  'agentLoop',
  'sessionProjections',
  'agentDefaultModel',
]

/** Driver configuration supplied by the loader patch row. */
export interface DriverConfig {
  /** Which chain half this boot runs. */
  mode: 'start' | 'resume' | 'b2b3' | 'b2b3verify'
  /** Evidence JSONL file (absolute) every step appends to. */
  evidencePath: string
  /** Mode start: the chain task text delivered as the real user message. */
  taskText?: string
  /** Mode start: the /devframe-start objective line. */
  objective?: string
  /** Mode start: handshake flag written after the goal binds. */
  flagPath?: string
  /** Mode resume: the session id restored across the restart. */
  resumeSessionId?: string
  /** Modes b2b3/b2b3verify: the declared Shadow session id (pre-created by the driver). */
  shadowSessionId?: string
  /** Modes b2b3/b2b3verify: the second project root the Shadow opens. */
  secondRoot?: string
  /** Modes b2b3/b2b3verify: unique boot label keeping request ids replay-safe across boots. */
  bootLabel?: string
  /** Mode b2b3: the memory note body appended into the project Vault. */
  memoryBody?: string
}

/** Append one evidence line; the file is the driver's only side channel. */
function log(path: string, entry: Record<string, unknown>): void {
  appendFileSync(path, `${JSON.stringify({ at: new Date().toISOString(), ...entry })}\n`, 'utf8')
}

/** Read one command execution down to the evidence fields the chain needs. */
function outcomeOf(execution: { commandId: { toString(): string }, result: { kind: string, text?: string } }): Record<string, unknown> {
  return {
    commandId: String(execution.commandId),
    kind: execution.result.kind,
    text: execution.result.text,
  }
}

/**
 * Activate the driver on the booting composition.
 * @param ctx - the driver plugin fiber's context.
 * @param config - loader-supplied driver configuration.
 */
export function apply(ctx: Context, config: DriverConfig): void {
  log(config.evidencePath, { event: 'driver-applied', mode: config.mode })
  if (config.mode === 'start') void start(ctx, config)
  else if (config.mode === 'resume') void resume(ctx, config)
  else if (config.mode === 'b2b3') void b2b3(ctx, config)
  else void b2b3verify(ctx, config)
}

/** Read the devframe projection's goal binding off one session. */
function bindingOf(ctx: Context, session: { id: { toString(): string } }): Record<string, unknown> {
  const state = ctx.sessionProjections.stateOf(session as never, 'devframe') as {
    bindings?: Array<{ goalId?: string, acceptanceHash?: string, controllerSessionId?: string }>
  } | undefined
  const last = state?.bindings?.at(-1)
  return {
    goalId: last?.goalId,
    acceptanceHash: last?.acceptanceHash,
    controllerSessionId: last?.controllerSessionId,
    bindingCount: state?.bindings?.length ?? 0,
  }
}

/** Modes b2b3: shadow open → second-root goal binding → host setActiveGoal → send → status → memory append/read. */
async function b2b3(ctx: Context, config: DriverConfig): Promise<void> {
  try {
    await ctx.get('loader')?.await()
    if (config.shadowSessionId === undefined || config.secondRoot === undefined || config.bootLabel === undefined) {
      throw new Error('b2b3 mode requires shadowSessionId, secondRoot, bootLabel')
    }
    const router = ctx.get('shadowRouter') as {
      openProject(caller: Agent | undefined, request: { path: string, requestId: string }): Promise<Record<string, unknown>>
      setActiveGoal(workspaceId: string, goalId: string, acceptanceHash: string): Promise<Record<string, unknown>>
      sendToProject(caller: Agent | undefined, request: Record<string, unknown>): Promise<Record<string, unknown>>
      projectStatus(caller: Agent | undefined, request: { workspaceId: string }): Promise<Record<string, unknown>>
    } | undefined
    if (router === undefined) throw new Error('shadowRouter service unavailable')

    const shadow = await ensureAgent(ctx, config.evidencePath, config.shadowSessionId)
    log(config.evidencePath, { event: 'shadow-marked-check', shadowSessionId: config.shadowSessionId })

    const opened = await router.openProject(shadow, { path: config.secondRoot, requestId: `${config.bootLabel}-open-1` })
    log(config.evidencePath, { event: 'b2-open', result: opened })
    const workspaceId = opened.workspaceId as string
    const controllerSessionId = opened.controllerSessionId as string

    const live = ctx.agents.get(SessionId(controllerSessionId))
    const controller = live ?? await ensureAgent(ctx, config.evidencePath, controllerSessionId, opened.canonicalPath as string, undefined)
    const line = `/devframe-start B2 第二项目根验证目标：确认 shadow 投递旅程与 goal 绑定（boot ${config.bootLabel}）`
    const execution = await ctx.commands.execute(controller as Agent, line, [], new AbortController().signal)
    if (execution === undefined) throw new Error('/devframe-start is not registered in this composition')
    log(config.evidencePath, { event: 'b2-controller-start', ...outcomeOf(execution) })
    const binding = bindingOf(ctx, controller.session)
    log(config.evidencePath, { event: 'b2-controller-binding', ...binding })
    if (typeof binding.goalId !== 'string' || typeof binding.acceptanceHash !== 'string') {
      throw new Error(`b2: controller goal binding incomplete: ${JSON.stringify(binding)}`)
    }

    const goalBinding = await router.setActiveGoal(workspaceId, binding.goalId, binding.acceptanceHash)
    log(config.evidencePath, { event: 'b2-set-active-goal', result: goalBinding, note: 'host-side seam call; no model tool reaches setActiveGoal per service JSDoc' })
    const bindingRevision = goalBinding.bindingRevision as number

    const sent = await router.sendToProject(shadow, {
      workspaceId,
      bindingRevision,
      goalId: binding.goalId,
      acceptanceHash: binding.acceptanceHash,
      mode: 'work',
      text: `B2 投递旅程验证（boot ${config.bootLabel}）：报告第二项目根的当前分支与 HEAD SHA`,
      requestId: `${config.bootLabel}-send-1`,
    })
    log(config.evidencePath, { event: 'b2-send', result: sent })
    const status = await router.projectStatus(shadow, { workspaceId })
    log(config.evidencePath, { event: 'b2-status', result: status })

    const memory = ctx.get('projectMemory') as unknown
    const appendTool = shadow.ctx.tools.get('memory_append', shadow)
    if (appendTool === undefined) throw new Error('memory_append tool not resolvable for the shadow agent scope')
    const appended = await appendTool.execute({
      scope: 'project',
      source_ref: `${config.bootLabel}-b3-note`,
      kind: 'fact',
      body: config.memoryBody ?? `B3 真实写入验证 ${config.bootLabel}`,
    }, { agent: shadow })
    log(config.evidencePath, { event: 'b3-append', result: appended, servicePresent: memory !== undefined })
    const readTool = shadow.ctx.tools.get('memory_read', shadow)
    if (readTool === undefined) throw new Error('memory_read tool not resolvable for the shadow agent scope')
    const read = await readTool.execute({ scope: 'project', note_id: (appended as { noteId: string }).noteId }, { agent: shadow })
    log(config.evidencePath, { event: 'b3-read', result: read })
    await ctx.sessions.flush(shadow.session)
    await ctx.sessions.flush(controller.session)
    log(config.evidencePath, { event: 'b2b3-boot-complete', bootLabel: config.bootLabel })
    const exit = ctx.get('appExit') as ((code: number) => void) | undefined
    if (exit !== undefined) exit(0)
  } catch (error) {
    log(config.evidencePath, { event: 'b2b3-error', error: String(error instanceof Error ? error.stack : error) })
    const exit = ctx.get('appExit') as ((code: number) => void) | undefined
    if (exit !== undefined) exit(1)
  }
}

/** Mode b2b3verify: cold-recovery read-back — status binding + memory note after restart. */
async function b2b3verify(ctx: Context, config: DriverConfig): Promise<void> {
  try {
    await ctx.get('loader')?.await()
    if (config.shadowSessionId === undefined || config.secondRoot === undefined || config.bootLabel === undefined) {
      throw new Error('b2b3verify mode requires shadowSessionId, secondRoot, bootLabel')
    }
    const router = ctx.get('shadowRouter') as {
      projectStatus(caller: Agent | undefined, request: { workspaceId?: string }): Promise<Record<string, unknown>>
    } | undefined
    if (router === undefined) throw new Error('shadowRouter service unavailable')
    const shadow = await ensureAgent(ctx, config.evidencePath, config.shadowSessionId)
    const status = await router.projectStatus(shadow, {})
    log(config.evidencePath, { event: 'verify-status-cold', result: status })
    const searchTool = shadow.ctx.tools.get('memory_search', shadow)
    if (searchTool === undefined) throw new Error('memory_search tool not resolvable for the shadow agent scope')
    const search = await searchTool.execute({ scope: 'project', query: 'B3 真实写入验证' }, { agent: shadow })
    log(config.evidencePath, { event: 'verify-memory-search-cold', result: search })
    await ctx.sessions.flush(shadow.session)
    log(config.evidencePath, { event: 'b2b3verify-boot-complete', bootLabel: config.bootLabel })
    const exit = ctx.get('appExit') as ((code: number) => void) | undefined
    if (exit !== undefined) exit(0)
  } catch (error) {
    log(config.evidencePath, { event: 'b2b3verify-error', error: String(error instanceof Error ? error.stack : error) })
    const exit = ctx.get('appExit') as ((code: number) => void) | undefined
    if (exit !== undefined) exit(1)
  }
}

/** Create (or adopt) one session through the real session-controller face. */
async function ensureAgent(ctx: Context, evidencePath: string, sessionId: string | undefined, cwd = process.cwd(), preset: string | undefined = 'standard'): Promise<Agent> {
  const controller = ctx.get('sessionController') as SessionController | undefined
  if (controller === undefined) throw new Error('chain-driver: sessionController unavailable')
  const created = await controller.create({
    ...(sessionId === undefined ? {} : { sessionId: SessionId(sessionId) }),
    cwd,
    ...(preset === undefined ? {} : { agentPreset: preset }),
  })
  const agent = ctx.agents.get(created.sessionId)
  if (agent === undefined) throw new Error(`chain-driver: agent ${created.sessionId.toString()} not live after create`)
  await agent.whenIdle()
  log(evidencePath, {
    event: 'agent-created',
    agentId: agent.id.toString(),
    sessionId: agent.session.id.toString(),
    agentPreset: created.agentPreset,
  })
  return agent
}

/** Mode start: full self-driven chain opening on the booted web profile. */
async function start(ctx: Context, config: DriverConfig): Promise<void> {
  try {
    await ctx.get('loader')?.await()
    const defaultModel = ctx.get('agentDefaultModel')
    const sessions = ctx.get('sessions')
    if (defaultModel === undefined || sessions === undefined) {
      throw new Error('chain-driver: core services unavailable at start time')
    }
    const selection = defaultModel.currentSelection()
    log(config.evidencePath, { event: 'composition-ready', provider: selection.provider, model: selection.model })

    const agent = await ensureAgent(ctx, config.evidencePath, undefined)
    const line = `/devframe-start ${config.objective ?? ''}`
    const execution = await ctx.commands.execute(agent as Agent, line, [], new AbortController().signal)
    if (execution === undefined) throw new Error('/devframe-start is not registered in this composition')
    log(config.evidencePath, { event: 'start-result', ...outcomeOf(execution) })
    if (config.flagPath !== undefined) {
      writeFileSync(config.flagPath, `${new Date().toISOString()} goal bound\n`, 'utf8')
      log(config.evidencePath, { event: 'flag-written', flagPath: config.flagPath })
    }

    agent.followup(createUserMessage({
      content: [{ type: 'text', text: config.taskText ?? '' }],
      source: { kind: 'user' },
    }))
    await agent.whenIdle()
    await sessions.flush(agent.session)
    log(config.evidencePath, { event: 'task-idle', sessionId: agent.session.id.toString() })
  } catch (error) {
    log(config.evidencePath, { event: 'start-error', error: String(error instanceof Error ? error.stack : error) })
  }
}

/** Mode resume: adopt the recorded session, then /devframe-resume it. */
async function resume(ctx: Context, config: DriverConfig): Promise<void> {
  try {
    await ctx.get('loader')?.await()
    if (config.resumeSessionId === undefined) throw new Error('resume mode requires resumeSessionId')
    log(config.evidencePath, { event: 'resume-begin', resumeSessionId: config.resumeSessionId })
    const agent = await ensureAgent(ctx, config.evidencePath, config.resumeSessionId)
    const execution = await ctx.commands.execute(agent, '/devframe-resume', [], new AbortController().signal)
    if (execution === undefined) throw new Error('/devframe-resume is not registered in this composition')
    log(config.evidencePath, { event: 'resume-result', ...outcomeOf(execution) })
    await ctx.sessions.flush(agent.session)
  } catch (error) {
    log(config.evidencePath, { event: 'resume-error', error: String(error instanceof Error ? error.stack : error) })
  }
}
