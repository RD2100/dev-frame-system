/**
 * Stable, Host-owned controller sessions for DevFrame.
 *
 * @module @deepseek-ai/dsh-devframe-control-session
 */

import { Context } from '@deepseek-ai/cordis'
import type { Agent, AgentHandle, AgentOptions, AgentSetupCommit } from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-agent-default-model'
import type {} from '@deepseek-ai/dsh-agent-loop'
import { resolveSessionPreset } from '@deepseek-ai/dsh-agent-presets'
import { canonicalizeWatchPath, dshHomePath } from '@deepseek-ai/dsh-home-paths'
import { isAbsolute, relative, sep } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { Session, SessionEvent } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-goal'
import type {} from '@deepseek-ai/dsh-session-persistence'
import type {} from '@deepseek-ai/dsh-tools'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { Workspace } from '@deepseek-ai/dsh-workspace/types'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import { DevFrameReadinessState } from './readiness.ts'
import {
  type ControllerIdentityV1,
  type ControllerRole,
  type DevFrameReadinessBlockedCode,
  type DevFrameReadinessSnapshot,
} from './types.ts'

export * from './types.ts'
export * from './profile-fence.ts'

const ID_PART_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const CONTROLLER_IDENTITY_EVENT_TYPE = 'controller/identity' as const
const CONTROLLER_GUARD_REASON = 'DevFrame Slice 0 controller execution is not enabled'
/** Native DSH coding preset required by every fresh Project Controller. */
const PROJECT_AGENT_PRESET = 'standard' as const
/** Hard upper bound for one model turn started by the Slice 1 adapter. */
/** Per-round wall-clock budget; bounded continuation gets one budget per round. */
const DISPATCH_TIMEOUT_PER_ROUND_MS = 60_000

/** Slice 0 keeps project execution disabled while retaining the future path. */
function isProjectDispatchEnabled(): boolean {
  return false
}

function isBoundedGoalRounds(value: number): value is 1 | 2 {
  return value === 1 || value === 2
}

/** Stable failure categories safe to project without including paths or credentials. */
export type ControlSessionErrorCode =
  | 'INVALID_ID'
  | 'INVALID_PROJECT_ROOT'
  | 'PROJECT_ROOT_MISMATCH'
  | 'UNKNOWN_WORKSPACE'
  | 'WORKSPACE_UNAVAILABLE'
  | 'PRESET_UNAVAILABLE'
  | 'PROJECT_DISPATCH_DISABLED'
  | 'CONTROL_CWD_UNAVAILABLE'
  | 'GLOBAL_CWD_CONFLICT'
  | 'LIVE_COLLISION'
  | 'HOST_STOPPING'
  | 'PERSISTENCE_UNAVAILABLE'
  | 'IDENTITY_INVALID'
  | 'DURABILITY_FAILED'
  | 'MODEL_UNAVAILABLE'
  | 'GOALS_UNAVAILABLE'
  | 'INVALID_GOAL_BUDGET'
  | 'DISPATCH_TIMEOUT'
  | 'DISPATCH_CANCELLED'

/** A bounded Host error whose message never echoes caller or persistence values. */
export class ControlSessionError extends Error {
  /**
   * @param code - Stable failure category.
   * @param options - Optional internal cause retained on the Host only.
   */
  constructor(readonly code: ControlSessionErrorCode, options?: ErrorOptions) {
    super(`DevFrame controller session blocked: ${code}`, options)
    this.name = 'ControlSessionError'
  }
}

function controlSessionFailure(
  failure: unknown,
  fallback: Exclude<ControlSessionErrorCode, 'INVALID_ID' | 'LIVE_COLLISION'>,
): ControlSessionError {
  return failure instanceof ControlSessionError
    ? failure
    : new ControlSessionError(fallback, { cause: failure })
}

/** Input for opening the profile-scoped Global Controller. */
export interface OpenGlobalControllerOptions {
  readonly profileId: string
  readonly signal?: AbortSignal
}

/** Input for opening the workspace-scoped Project Controller. */
export interface OpenProjectControllerOptions extends OpenGlobalControllerOptions {
  readonly workspaceId: string
}

/** A controller proven live and durable by this service instance. */
export interface ControlSessionResult {
  readonly id: SessionId
  readonly role: ControllerRole
  readonly agent: Agent
}

/** One bounded Goal → Task → Run trace over the native DSH log. */
export interface DevFrameGoalDispatchTrace {
  /** Native Goal id from the durable `goal/change` event. */
  readonly goalId: string
  /** Goal revision observed after the bounded round settles. */
  readonly revision: number
  /** Task mapping: the number of admitted Goal Rounds. */
  readonly round: number
  /** Number of model turns that reached a durable `turn/end`. */
  readonly roundsCompleted: number
  /** Run mapping: the Global Controller's native Agent Session. */
  readonly sessionId: SessionId
  /** Provider route selected by `ctx.agentDefaultModel`. */
  readonly provider: string
  /** Provider model selected by `ctx.agentDefaultModel`. */
  readonly model: string
  /** Bounded review outcome for the one admitted turn. */
  readonly outcome: 'completed' | 'failed' | 'aborted'
}

/** Input for one bounded Global Controller dispatch. */
export interface DispatchGlobalGoalOptions {
  readonly profileId: string
  readonly objective: string
  /** Slice 1 admits exactly one round; larger budgets are rejected. */
  readonly maxGoalRounds?: number
  readonly signal?: AbortSignal
}

/** Input for one bounded Project Controller dispatch through native DSH tools. */
export interface DispatchProjectGoalOptions {
  readonly profileId: string
  /** Native DSH Workspace id used as the stable project id. */
  readonly projectId: string
  /** The caller's expected project root; it must match the registered Workspace. */
  readonly projectRoot: string
  readonly objective: string
  /** The project MVP admits at most two bounded rounds. */
  readonly maxGoalRounds?: number
  readonly signal?: AbortSignal
}

/** A bounded Project Controller dispatch trace with no absolute path fields. */
export interface DevFrameProjectGoalDispatchTrace extends DevFrameGoalDispatchTrace {
  readonly projectId: string
}

interface ExpectedIdentity {
  readonly role: ControllerRole
  readonly sessionId: SessionId
  readonly profileId: string
  readonly cwd: string
  readonly workspace?: Workspace
}

interface ReadyEntry {
  readonly expected: ExpectedIdentity
  readonly handle: AgentHandle
  readonly result: ControlSessionResult
}

interface PendingEntry {
  readonly expected: ExpectedIdentity
  readonly operation: Promise<ControlSessionResult>
}

interface BootstrapRecord {
  readonly generation: number
  operation?: Promise<void>
  result?: ControlSessionResult
  stopping: boolean
}

/** Host-owned lifecycle for one Global Controller bootstrap generation. */
export interface DevFrameGlobalBootstrapGeneration {
  readonly generation: number
  readonly signal: AbortSignal
  /** Open the stable Global Controller and publish readiness. */
  open(profileId: string): Promise<void>
  /** Publish a bounded prerequisite failure. */
  block(code: DevFrameReadinessBlockedCode): void
  /** Stop admission, settle pending open, and release the owned Agent. */
  stop(): Promise<void>
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    devframeControlSessions: DevFrameControlSessions
  }
}

function requireIdPart(value: string): string {
  if (typeof value !== 'string' || !ID_PART_PATTERN.test(value)) {
    throw new ControlSessionError('INVALID_ID')
  }
  return value
}

function containsPath(parent: string, child: string): boolean {
  const segment = relative(parent, child)
  return segment === ''
    || (segment !== '..' && !segment.startsWith(`..${sep}`) && !isAbsolute(segment))
}

function pathsOverlap(left: string, right: string): boolean {
  return containsPath(left, right) || containsPath(right, left)
}

/**
 * Derive the stable Global Controller session id.
 * @param profileId - Validated persistent profile id.
 * @returns the deterministic session id.
 */
export function globalControllerSessionId(profileId: string): SessionId {
  return SessionId(`devframe-global:${requireIdPart(profileId)}`)
}

/**
 * Derive the stable Project Controller session id.
 * @param workspaceId - Validated native DSH workspace id.
 * @returns the deterministic session id.
 */
export function projectControllerSessionId(workspaceId: string): SessionId {
  return SessionId(`devframe-controller:${requireIdPart(workspaceId)}`)
}

function sameExpected(left: ExpectedIdentity, right: ExpectedIdentity): boolean {
  return left.role === right.role
    && left.sessionId === right.sessionId
    && left.profileId === right.profileId
    && left.cwd === right.cwd
    && left.workspace?.id === right.workspace?.id
    && left.workspace?.path === right.workspace?.path
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype: unknown = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index])
}

function expectedPayload(expected: ExpectedIdentity): ControllerIdentityV1 {
  if (expected.role === 'global') {
    return {
      schemaVersion: 1,
      role: 'global',
      sessionId: expected.sessionId,
      profileId: expected.profileId,
      cwd: expected.cwd,
    }
  }
  const workspace = expected.workspace
  if (workspace === undefined) throw new ControlSessionError('IDENTITY_INVALID')
  return {
    schemaVersion: 1,
    role: 'project',
    sessionId: expected.sessionId,
    profileId: expected.profileId,
    workspaceId: workspace.id,
    cwd: expected.cwd,
  }
}

function parseIdentity(value: unknown, expected: ExpectedIdentity): ControllerIdentityV1 {
  if (!isPlainRecord(value)) throw new ControlSessionError('IDENTITY_INVALID')
  const expectedKeys = expected.role === 'global'
    ? ['cwd', 'profileId', 'role', 'schemaVersion', 'sessionId']
    : ['cwd', 'profileId', 'role', 'schemaVersion', 'sessionId', 'workspaceId']
  if (!exactKeys(value, expectedKeys)) throw new ControlSessionError('IDENTITY_INVALID')
  const wanted = expectedPayload(expected)
  if (value.schemaVersion !== wanted.schemaVersion
    || value.role !== wanted.role
    || value.sessionId !== wanted.sessionId
    || value.profileId !== wanted.profileId
    || value.cwd !== wanted.cwd
    || (wanted.role === 'project' && value.workspaceId !== wanted.workspaceId)) {
    throw new ControlSessionError('IDENTITY_INVALID')
  }
  return value as unknown as ControllerIdentityV1
}

/**
 * Validate the complete stable identity relationship of one controller session.
 * @param agent - Candidate live Agent.
 * @param expected - Host-owned profile/workspace expectation.
 * @returns the validated identity payload.
 */
export function validateControllerSession(agent: Agent, expected: ExpectedIdentity): ControllerIdentityV1 {
  const session = agent.session
  if (agent.id !== expected.sessionId || session.id !== expected.sessionId || agent.id !== session.id) {
    throw new ControlSessionError('IDENTITY_INVALID')
  }
  if (session.header.cwd !== expected.cwd) {
    throw new ControlSessionError('IDENTITY_INVALID')
  }
  const identities = session.events.filter(event => event.type === CONTROLLER_IDENTITY_EVENT_TYPE)
  const first = session.events[0]
  if (identities.length !== 1
    || first === undefined
    || first !== identities[0]
    || first.seq !== 0) {
    throw new ControlSessionError('IDENTITY_INVALID')
  }
  return parseIdentity(first.data, expected)
}

function validateControllerSessionRecord(session: Session, expected: ExpectedIdentity): ControllerIdentityV1 {
  if (session.id !== expected.sessionId || session.header.cwd !== expected.cwd) {
    throw new ControlSessionError('IDENTITY_INVALID')
  }
  const identities = session.events.filter(event => event.type === CONTROLLER_IDENTITY_EVENT_TYPE)
  const first = session.events[0]
  if (identities.length !== 1
    || first === undefined
    || first !== identities[0]
    || first.seq !== 0) {
    throw new ControlSessionError('IDENTITY_INVALID')
  }
  return parseIdentity(first.data, expected)
}

/**
 * Fail before materializing a project session when the shipped coding preset
 * is not available. This keeps a missing/broken roster from leaving behind an
 * unpublished identity that can never be resumed safely.
 */
async function ensureProjectPresetAvailable(hostCtx: Context): Promise<void> {
  const presets = hostCtx.get('agentPresets')
  if (presets === undefined) throw new ControlSessionError('PRESET_UNAVAILABLE')
  try {
    const preset = await presets.resolve(PROJECT_AGENT_PRESET)
    if (preset.broken !== undefined) throw new Error(preset.broken)
  } catch (failure) {
    if (failure instanceof ControlSessionError) throw failure
    throw new ControlSessionError('PRESET_UNAVAILABLE', { cause: failure })
  }
}

function configureControllerAgent(
  hostCtx: Context,
  agentCtx: Context,
  expected: ExpectedIdentity,
): AgentSetupCommit | Promise<AgentSetupCommit> {
  const agent = agentCtx.agent
  if (agent === undefined) throw new ControlSessionError('IDENTITY_INVALID')
  if (expected.role === 'global') {
    // The Global Controller is a coordinator identity, never a project
    // worker. Keep its tool surface empty even when project agents are live.
    agentCtx.tools.restrict({ allow: [] })
    agentCtx.tools.guard(() => CONTROLLER_GUARD_REASON)
    validateControllerSession(agent, expected)
    return {
      commit() {
        if (hostCtx.agents.get(expected.sessionId) !== undefined
          || hostCtx.sessions.get(expected.sessionId) !== undefined) {
          throw new ControlSessionError('LIVE_COLLISION')
        }
        validateControllerSession(agent, expected)
      },
    }
  }

  const presets = hostCtx.get('agentPresets')
  if (presets === undefined) throw new ControlSessionError('PRESET_UNAVAILABLE')
  const recordedPreset = resolveSessionPreset(agent.session)
  // A session with history but no recorded preset cannot be reconstructed
  // honestly. A blank legacy identity can still be adopted under `standard`.
  if (recordedPreset === undefined && agent.session.events.length !== 1) {
    throw new ControlSessionError('PRESET_UNAVAILABLE')
  }
  const presetId = recordedPreset ?? PROJECT_AGENT_PRESET
  return presets.mount(agentCtx, presetId).then((mounted) => {
    if (mounted.id !== presetId) throw new ControlSessionError('PRESET_UNAVAILABLE')
    if (recordedPreset === undefined) {
      agent.session.append('agent-preset/selected', { agentPreset: mounted.id })
    }
    validateControllerSession(agent, expected)
    return {
      commit() {
        if (hostCtx.agents.get(expected.sessionId) !== undefined
          || hostCtx.sessions.get(expected.sessionId) !== undefined) {
          throw new ControlSessionError('LIVE_COLLISION')
        }
        validateControllerSession(agent, expected)
      },
    }
  }, (failure: unknown) => {
    if (failure instanceof ControlSessionError) throw failure
    throw new ControlSessionError('PRESET_UNAVAILABLE', { cause: failure })
  })
}

async function disposeAfterFailure(handle: AgentHandle, failure: unknown): Promise<never> {
  const boundedFailure = controlSessionFailure(failure, 'DURABILITY_FAILED')
  try {
    await handle.dispose()
  } catch (disposeFailure: unknown) {
    throw new ControlSessionError(boundedFailure.code, {
      cause: new AggregateError([boundedFailure, disposeFailure], 'DevFrame controller cleanup failed'),
    })
  }
  throw boundedFailure
}

/**
 * Host-owned stable Controller Session service.
 *
 * This Slice 0 tracer deliberately supports one Host process. It serializes
 * same-id opens inside that process and refuses to adopt a live Agent it did
 * not create or resume itself. Durable multi-process writer fencing is deferred.
 */
export class DevFrameControlSessions extends TypertRemoteService {
  static inject = ['agents', 'sessions', 'sessionPersistence', 'workspaceRegistry', 'tools']

  /** Stable owner context; Cordis traces `Service.ctx` to each caller fiber. */
  private readonly hostCtx: Context
  private readonly pending = new Map<SessionId, PendingEntry>()
  private readonly ready = new Map<SessionId, ReadyEntry>()
  private readonly unmaterialized = new Map<SessionId, ExpectedIdentity>()
  private readonly readinessState = new DevFrameReadinessState()
  private bootstrap: BootstrapRecord | undefined

  constructor(ctx: Context) {
    super(ctx, 'devframeControlSessions')
    this.hostCtx = ctx
  }

  /**
   * Begin one HMR-safe Global Controller bootstrap generation.
   * @returns the generation-owned start/block/stop controls.
   */
  beginGlobalBootstrap(): DevFrameGlobalBootstrapGeneration {
    const ticket = this.readinessState.begin()
    const record: BootstrapRecord = { generation: ticket.generation, stopping: false }
    this.bootstrap = record

    const open = async (profileId: string): Promise<void> => {
      if (record.operation !== undefined) return record.operation
      const operation = this.openGlobal({ profileId, signal: ticket.signal })
        .then((result) => {
          record.result = result
          this.readinessState.ready(record.generation, result.id)
        })
        .catch(() => {
          if (!ticket.signal.aborted) {
            this.readinessState.blocked(record.generation, 'CONTROLLER_UNAVAILABLE')
          }
        })
      record.operation = operation
      await operation
    }

    const stop = async (): Promise<void> => {
      if (record.stopping) {
        await record.operation
        return
      }
      record.stopping = true
      this.readinessState.stopping(record.generation)
      await record.operation
      const result = record.result
      if (result !== undefined) await this.releaseOwned(result)
      if (this.bootstrap === record) this.bootstrap = undefined
    }

    return {
      generation: record.generation,
      signal: ticket.signal,
      open,
      block: (code) => { this.readinessState.blocked(record.generation, code) },
      stop,
    }
  }

  /**
   * Return the current pathless readiness projection for Host diagnostics and tests.
   * @returns a detached readiness snapshot without absolute paths or credentials.
   */
  readinessSnapshot(): DevFrameReadinessSnapshot {
    return this.readinessState.snapshot()
  }

  /**
   * Long-poll the pathless Global Controller readiness projection.
   * @param afterRevision - caller's last observed revision, or -1 initially.
   * @param signal - transport cancellation.
   * @returns current state after a change or bounded timeout.
   */
  @Remote('readiness')
  async remoteReadiness(afterRevision: number, signal: AbortSignal): Promise<DevFrameReadinessSnapshot> {
    return await this.readinessState.wait(afterRevision, signal)
  }

  /**
   * Dispatch one direct human objective through the existing Goal Round driver.
   *
   * The adapter deliberately does not append a second task/run event family:
   * Goal creation and the admitted Goal Round are already durable Session
   * events, and the Agent turn carries the model request/identity. The returned
   * trace names those existing records so a Client or CLI can correlate them.
   * @param options - bounded objective, profile identity, and optional cancellation signal.
   * @returns a pathless trace after the Goal Round and Session flush complete.
   */
  async dispatchGlobalGoal(options: DispatchGlobalGoalOptions): Promise<DevFrameGoalDispatchTrace> {
    const objective = typeof options.objective === 'string' ? options.objective.trim() : ''
    if (objective.length === 0) throw new ControlSessionError('GOALS_UNAVAILABLE')
    if (options.maxGoalRounds !== undefined && options.maxGoalRounds !== 1) {
      throw new ControlSessionError('INVALID_GOAL_BUDGET')
    }
    const model = this.resolveModelOptions()
    const goals = this.hostCtx.get('goals')
    if (goals === undefined || this.hostCtx.get('agentLoop') === undefined) {
      throw new ControlSessionError('MODEL_UNAVAILABLE')
    }
    const controller = await this.openGlobal({
      profileId: options.profileId,
      ...options.signal === undefined ? {} : { signal: options.signal },
    })
    if (controller.agent.options.provider !== model.provider || controller.agent.options.model !== model.model) {
      // A controller opened without a configured route cannot be upgraded in
      // place: fail closed instead of silently dispatching through an empty or
      // stale model identity.
      throw new ControlSessionError('MODEL_UNAVAILABLE')
    }

    return await this.dispatchGoal(controller, objective, options.signal, model, 1)
  }

  /**
   * Dispatch one bounded objective through a project-scoped Agent.
   *
   * Slice 0 hard-fails this entry point: project execution needs the Slice 1A
   * authority (identity, `project-authority/bound`, resume pointer) and Slice
   * 1C policy gates (ContextPacket, PolicyDecision, frozen assets) that do not
   * exist yet, and a Project Controller mounts the shipped coding preset with
   * project File/Shell tools. The identity-only {@link openProject} path
   * remains available; the full dispatch machinery below stays in place for
   * the gated Slice 1 slice and is intentionally unreachable until then.
   * @param options - project identity, expected root, objective, and signal.
   * @returns a pathless trace after the native Session flush succeeds.
   */
  async dispatchProjectGoal(options: DispatchProjectGoalOptions): Promise<DevFrameProjectGoalDispatchTrace> {
    // Fail closed before any validation or materialization: no project tool or
    // model execution may run until the Slice 1A/1C gates exist. Removing this
    // gate is a separate, human-approved slice, not a config toggle.
    if (!isProjectDispatchEnabled()) {
      throw new ControlSessionError('PROJECT_DISPATCH_DISABLED')
    }
    const objective = typeof options.objective === 'string' ? options.objective.trim() : ''
    if (objective.length === 0) throw new ControlSessionError('GOALS_UNAVAILABLE')
    const maxGoalRounds = options.maxGoalRounds ?? 1
    if (!isBoundedGoalRounds(maxGoalRounds)) {
      throw new ControlSessionError('INVALID_GOAL_BUDGET')
    }
    const projectId = requireIdPart(options.projectId)
    const projectRoot = typeof options.projectRoot === 'string' ? options.projectRoot.trim() : ''
    if (projectRoot.length === 0) throw new ControlSessionError('INVALID_PROJECT_ROOT')
    let canonicalRoot: string
    try {
      canonicalRoot = await canonicalizeWatchPath(projectRoot)
    } catch (failure) {
      throw new ControlSessionError('INVALID_PROJECT_ROOT', { cause: failure })
    }
    const workspace = this.hostCtx.workspaceRegistry.get(WorkspaceId(projectId))
    if (workspace === undefined) throw new ControlSessionError('UNKNOWN_WORKSPACE')
    if (canonicalRoot !== workspace.path) throw new ControlSessionError('PROJECT_ROOT_MISMATCH')
    let status: Awaited<ReturnType<Workspace['status']>>
    try {
      status = await workspace.status()
    } catch (failure) {
      throw controlSessionFailure(failure, 'WORKSPACE_UNAVAILABLE')
    }
    if (status !== 'ok') throw new ControlSessionError('WORKSPACE_UNAVAILABLE')

    const model = this.resolveModelOptions()
    const goals = this.hostCtx.get('goals')
    if (goals === undefined || this.hostCtx.get('agentLoop') === undefined) {
      throw new ControlSessionError('MODEL_UNAVAILABLE')
    }
    const controller = await this.openProject({
      profileId: options.profileId,
      workspaceId: projectId,
      ...options.signal === undefined ? {} : { signal: options.signal },
    })
    if (controller.agent.options.provider !== model.provider || controller.agent.options.model !== model.model) {
      throw new ControlSessionError('MODEL_UNAVAILABLE')
    }
    const trace = await this.dispatchGoal(
      controller,
      objective,
      options.signal,
      model,
      maxGoalRounds,
    )
    return { ...trace, projectId }
  }

  /** Drive the native Goal Round lifecycle shared by Global and Project calls. */
  private async dispatchGoal(
    controller: ControlSessionResult,
    objective: string,
    signal: AbortSignal | undefined,
    model: Required<Pick<AgentOptions, 'provider' | 'model'>>,
    maxGoalRounds: 1 | 2,
  ): Promise<DevFrameGoalDispatchTrace> {
    const beforeSeq = controller.agent.session.seq
    const turnEnds: SessionEvent<'turn/end'>[] = []
    const turnEnd = Promise.withResolvers<SessionEvent<'turn/end'>>()
    const disposeEvent = this.hostCtx.on('session/event', (session, event) => {
      if (session !== controller.agent.session || event.seq <= beforeSeq || event.type !== 'turn/end') return
      turnEnds.push(event)
      if (event.data.reason.kind !== 'completed' || turnEnds.length >= maxGoalRounds) turnEnd.resolve(event)
    })
    const timeoutSignal = AbortSignal.timeout(DISPATCH_TIMEOUT_PER_ROUND_MS * maxGoalRounds)
    const dispatchSignal = signal === undefined
      ? timeoutSignal
      : AbortSignal.any([signal, timeoutSignal])
    let goal
    let lifecycleSettled = false
    try {
      dispatchSignal.throwIfAborted()
      const goals = this.hostCtx.get('goals')
      if (goals === undefined) throw new ControlSessionError('GOALS_UNAVAILABLE')
      const current = goals.get(controller.agent)
      if (current !== undefined && current.phase !== 'complete') {
        // A prior bounded invocation can leave its durable goal blocked or
        // paused after reaching its cap, cancellation, or a driver failure.
        // A new explicit task may close that historical goal before creating
        // its own; an armed active goal still owns the Agent and must not be
        // silently replaced by a concurrent caller.
        const recoverable = current.phase === 'blocked'
          || current.phase === 'paused'
          || current.activation === 'disarmed'
        if (!recoverable) throw new ControlSessionError('GOALS_UNAVAILABLE')
        goals.complete(controller.agent, { id: current.id, revision: current.revision })
      }
      goal = goals.create(controller.agent, { objective, maxGoalRounds })
      let onAbort: (() => void) | undefined
      const abortPromise = new Promise<never>((_resolve, reject) => {
        onAbort = (): void => {
          const reason: unknown = dispatchSignal.reason
          reject(reason instanceof Error
            ? reason
            : new Error('Global Goal dispatch aborted', { cause: reason }))
        }
        dispatchSignal.addEventListener('abort', onAbort, { once: true })
      })
      const ended = await Promise.race([
        turnEnd.promise,
        abortPromise,
      ])
      lifecycleSettled = true
      if (onAbort !== undefined) dispatchSignal.removeEventListener('abort', onAbort)
      await controller.agent.whenIdle()
      if (!await this.hostCtx.sessions.flush(controller.agent.session)) {
        throw new ControlSessionError('DURABILITY_FAILED')
      }
      if (ended.data.reason.kind === 'aborted') {
        return this.dispatchTrace(controller.agent, goal, 'aborted', model, turnEnds.length)
      }
      if (ended.data.reason.kind === 'completed') {
        return this.dispatchTrace(controller.agent, goal, 'completed', model, turnEnds.length)
      }
      return this.dispatchTrace(controller.agent, goal, 'failed', model, turnEnds.length)
    } catch (failure) {
      if (goal !== undefined && !lifecycleSettled) {
        controller.agent.cancel({ kind: 'parent' })
        await controller.agent.whenIdle().catch(() => undefined)
      }
      if (dispatchSignal.aborted) {
        const code = timeoutSignal.aborted && !(signal?.aborted ?? false)
          ? 'DISPATCH_TIMEOUT'
          : 'DISPATCH_CANCELLED'
        throw new ControlSessionError(code, { cause: failure })
      }
      throw controlSessionFailure(failure, 'DURABILITY_FAILED')
    } finally {
      disposeEvent()
    }
  }

  /** Resolve the configured model route used by newly opened controllers. */
  private resolveModelOptions(): Required<Pick<AgentOptions, 'provider' | 'model'>> {
    const defaults = this.hostCtx.get('agentDefaultModel')
    if (defaults === undefined) throw new ControlSessionError('MODEL_UNAVAILABLE')
    const selection = defaults.currentSelection()
    if (selection.provider.length === 0 || selection.model.length === 0) {
      throw new ControlSessionError('MODEL_UNAVAILABLE')
    }
    return { provider: selection.provider, model: selection.model }
  }

  /** Build a detached, pathless trace from the settled Goal Round turn. */
  private dispatchTrace(
    agent: Agent,
    goal: {
      readonly id: string
      readonly revision: number
      readonly phase: 'active' | 'paused' | 'blocked' | 'complete'
      readonly roundsStarted: number
      readonly maxGoalRounds: number
    },
    status: 'completed' | 'failed' | 'aborted',
    model: Required<Pick<AgentOptions, 'provider' | 'model'>>,
    roundsCompleted: number,
  ): DevFrameGoalDispatchTrace {
    const header = agent.session.events.findLast(event => event.type === 'request/header')
    const provider = header?.type === 'request/header' ? header.data.header.config.provider : model.provider
    const modelId = header?.type === 'request/header' ? header.data.header.config.model : model.model
    return {
      goalId: goal.id,
      revision: goal.revision,
      round: roundsCompleted,
      roundsCompleted,
      sessionId: agent.session.id,
      provider,
      model: modelId,
      outcome: status,
    }
  }

  /**
   * Open the stable Global Controller for one provisioned profile.
   * @param options - Explicit persistent profile identity and cancellation.
   * @returns the ready identity-only controller.
   */
  async openGlobal(options: OpenGlobalControllerOptions): Promise<ControlSessionResult> {
    if (this.bootstrap?.stopping) throw new ControlSessionError('HOST_STOPPING')
    const profileId = requireIdPart(options.profileId)
    let cwd: string
    try {
      cwd = await canonicalizeWatchPath(dshHomePath('devframe-control'))
    } catch (failure) {
      throw new ControlSessionError('CONTROL_CWD_UNAVAILABLE', { cause: failure })
    }
    if (this.hostCtx.workspaceRegistry.list().some(workspace => pathsOverlap(cwd, workspace.path))) {
      throw new ControlSessionError('GLOBAL_CWD_CONFLICT')
    }
    return this.open({
      role: 'global',
      profileId,
      cwd,
      sessionId: globalControllerSessionId(profileId),
    }, options.signal)
  }

  /**
   * Open the stable Project Controller for one native DSH workspace.
   * @param options - Explicit persistent profile and workspace identities.
   * @returns the ready identity-only controller.
   */
  async openProject(options: OpenProjectControllerOptions): Promise<ControlSessionResult> {
    const profileId = requireIdPart(options.profileId)
    const workspaceId = requireIdPart(options.workspaceId)
    const workspace = this.hostCtx.workspaceRegistry.get(WorkspaceId(workspaceId))
    if (workspace === undefined) throw new ControlSessionError('UNKNOWN_WORKSPACE')
    let status: Awaited<ReturnType<Workspace['status']>>
    try {
      status = await workspace.status()
    } catch (failure) {
      throw controlSessionFailure(failure, 'WORKSPACE_UNAVAILABLE')
    }
    if (status !== 'ok') throw new ControlSessionError('WORKSPACE_UNAVAILABLE')
    await ensureProjectPresetAvailable(this.hostCtx)
    return this.open({
      role: 'project',
      profileId,
      cwd: workspace.path,
      workspace,
      sessionId: projectControllerSessionId(workspaceId),
    }, options.signal)
  }

  private open(expected: ExpectedIdentity, signal?: AbortSignal): Promise<ControlSessionResult> {
    const ready = this.ready.get(expected.sessionId)
    if (ready !== undefined) {
      if (!sameExpected(ready.expected, expected)) throw new ControlSessionError('LIVE_COLLISION')
      const liveAgent = this.hostCtx.agents.get(expected.sessionId)
      const liveSession = this.hostCtx.sessions.get(expected.sessionId)
      if (liveAgent === undefined && liveSession === undefined) {
        // A caller-owned Cordis generation may have disposed the handle while
        // this longer-lived service survived. Retire only a fully absent entry;
        // any partial or replacement owner remains a hard collision.
        this.ready.delete(expected.sessionId)
      } else if (liveAgent !== ready.handle.agent
        || liveSession !== ready.handle.agent.session) {
        throw new ControlSessionError('LIVE_COLLISION')
      } else {
        validateControllerSession(ready.handle.agent, expected)
        return Promise.resolve(ready.result)
      }
    }
    const active = this.pending.get(expected.sessionId)
    if (active !== undefined) {
      if (!sameExpected(active.expected, expected)) {
        return Promise.reject(new ControlSessionError('LIVE_COLLISION'))
      }
      return active.operation
    }
    if (this.hostCtx.agents.get(expected.sessionId) !== undefined
      || this.hostCtx.sessions.get(expected.sessionId) !== undefined) {
      return Promise.reject(new ControlSessionError('LIVE_COLLISION'))
    }
    const operation = this.restoreOrCreate(expected, signal)
      .finally(() => this.pending.delete(expected.sessionId))
    this.pending.set(expected.sessionId, { expected, operation })
    return operation
  }

  private async restoreOrCreate(expected: ExpectedIdentity, signal?: AbortSignal): Promise<ControlSessionResult> {
    let handle: AgentHandle
    const configuredModel = this.optionalModelOptions()
    try {
      handle = await this.hostCtx.agents.resume({
        resumeSessionId: expected.sessionId,
        ...configuredModel === undefined ? {} : { agentOptions: configuredModel },
        ...signal === undefined ? {} : { signal },
        setup: (agentCtx) => {
          return configureControllerAgent(this.hostCtx, agentCtx, expected)
        },
      })
    } catch (resumeFailure) {
      let headers
      try {
        headers = await this.hostCtx.sessionPersistence.list(signal)
      } catch (listFailure) {
        throw new ControlSessionError('PERSISTENCE_UNAVAILABLE', { cause: listFailure })
      }
      if (headers.some(header => header.id === expected.sessionId)) {
        throw new ControlSessionError('IDENTITY_INVALID', { cause: resumeFailure })
      }
      if (this.hostCtx.agents.get(expected.sessionId) !== undefined
        || this.hostCtx.sessions.get(expected.sessionId) !== undefined) {
        throw new ControlSessionError('LIVE_COLLISION')
      }
      try {
        signal?.throwIfAborted()
        const session = this.hostCtx.sessions.prepare(expected.sessionId, {
          meta: {
            cwd: expected.cwd,
            ...expected.role === 'project' ? { agentPreset: PROJECT_AGENT_PRESET } : {},
          },
        })
        session.append(CONTROLLER_IDENTITY_EVENT_TYPE, expectedPayload(expected))
        validateControllerSessionRecord(session, expected)
        const previous = this.unmaterialized.get(expected.sessionId)
        if (previous === undefined) {
          await this.hostCtx.sessionPersistence.create(session.header)
          this.unmaterialized.set(expected.sessionId, expected)
        } else if (!sameExpected(previous, expected)) {
          throw new ControlSessionError('LIVE_COLLISION')
        }
        await this.hostCtx.sessionPersistence.append(session.id, session.events)
        this.unmaterialized.delete(expected.sessionId)
        handle = await this.hostCtx.agents.resume({
          resumeSessionId: expected.sessionId,
          ...configuredModel === undefined ? {} : { agentOptions: configuredModel },
          ...signal === undefined ? {} : { signal },
          setup: (agentCtx) => {
            return configureControllerAgent(this.hostCtx, agentCtx, expected)
          },
        })
      } catch (materializeFailure) {
        throw controlSessionFailure(materializeFailure, 'DURABILITY_FAILED')
      }
    }

    try {
      validateControllerSession(handle.agent, expected)
      if (!await this.hostCtx.sessions.flush(handle.agent.session)) {
        throw new ControlSessionError('DURABILITY_FAILED')
      }
      if (expected.workspace !== undefined) await expected.workspace.attachSession(expected.sessionId)
      const result: ControlSessionResult = {
        id: expected.sessionId,
        role: expected.role,
        agent: handle.agent,
      }
      const entry: ReadyEntry = { expected, handle, result }
      this.ready.set(expected.sessionId, entry)
      handle.agent.ctx.effect(() => () => {
        if (this.ready.get(expected.sessionId) === entry) {
          this.ready.delete(expected.sessionId)
        }
      }, `devframeControlSessions.ready(${expected.sessionId})`)
      return result
    } catch (failure) {
      return disposeAfterFailure(handle, controlSessionFailure(failure, 'DURABILITY_FAILED'))
    }
  }

  /** Best-effort model options for identity-only opens; dispatch requires them. */
  private optionalModelOptions(): AgentOptions | undefined {
    const defaults = this.hostCtx.get('agentDefaultModel')
    if (defaults === undefined) return undefined
    const selection = defaults.currentSelection()
    if (selection.provider.length === 0 || selection.model.length === 0) return undefined
    return { provider: selection.provider, model: selection.model }
  }

  private async releaseOwned(result: ControlSessionResult): Promise<void> {
    const entry = this.ready.get(result.id)
    if (entry === undefined || entry.result.agent !== result.agent) return
    this.ready.delete(result.id)
    try {
      await entry.handle.dispose()
    } catch (failure) {
      throw new ControlSessionError('DURABILITY_FAILED', { cause: failure })
    }
  }
}

export default DevFrameControlSessions
