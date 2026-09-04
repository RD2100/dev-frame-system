/**
 * DevFrame's one-shot project-task runner.
 *
 * It resolves an id or path through the native Workspace Registry, then calls
 * the Host-owned Project Controller. Output deliberately contains no cwd or
 * other caller/persistence values.
 * @module @deepseek-ai/dsh-devframe/task-runner
 */

import type { Context } from '@deepseek-ai/cordis'
import { ControlSessionError, type DevFrameProjectGoalDispatchTrace } from '@deepseek-ai/dsh-devframe-control-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { Workspace } from '@deepseek-ai/dsh-workspace'
import type { DevFrameTaskStartupValues } from './task-startup.ts'

/** Stable Cordis plugin name. */
export const name = 'devframe-task-runner'

/** The runner is inert unless the task command provider published a request. */
export const inject = []

interface WorkspaceRegistryLike {
  get(id: ReturnType<typeof WorkspaceId>): Workspace | undefined
  resolveByPath(path: string): Promise<Workspace | undefined>
  create(path: string): Promise<Workspace>
}

interface ControlSessionsLike {
  dispatchProjectGoal(options: {
    profileId: string
    projectId: string
    projectRoot: string
    objective: string
    maxGoalRounds: number
  }): Promise<DevFrameProjectGoalDispatchTrace>
}

/** Loader config for the one-shot runner; the startup provider is injected by the patch. */
export interface DevFrameTaskRunnerConfig {
  readonly request?: DevFrameTaskStartupValues
}

/** Process-facing effects kept injectable for the compose smoke and CLI tests. */
export const internals: {
  stdout: { write(chunk: string): unknown }
  stderr: { write(chunk: string): unknown }
} = {
  stdout: process.stdout,
  stderr: process.stderr,
}

/** Stable result shape; never include a filesystem path in either branch. */
export interface DevFrameTaskResult {
  readonly ok: boolean
  readonly projectId?: string
  readonly goalId?: string
  readonly sessionId?: string
  readonly outcome?: DevFrameProjectGoalDispatchTrace['outcome']
  readonly error?: string
}

/**
 * Resolve or register a project selector. A registered id wins; an unowned
 * selector is treated as an explicit directory path and registered once.
 * @param registry - native Workspace Registry facade.
 * @param selector - workspace id or directory path supplied by the caller.
 * @returns the canonical registered Workspace.
 */
export async function resolveProject(
  registry: WorkspaceRegistryLike,
  selector: string,
): Promise<Workspace> {
  const value = selector.trim()
  if (value === '') throw new ControlSessionError('UNKNOWN_WORKSPACE')
  // Workspace ids are native branded strings rather than a CLI-specific
  // format. Always try the registry first, so future/non-UUID ids keep working.
  const byId = registry.get(WorkspaceId(value))
  if (byId !== undefined) return byId
  try {
    const existing = await registry.resolveByPath(value)
    if (existing !== undefined) return existing
  } catch (error) {
    // A missing path is expected before create() performs the authoritative
    // existing-directory check. Storage/permission failures must propagate so
    // they cannot be mistaken for an unregistered project.
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
  return await registry.create(value)
}

function resultFromTrace(trace: DevFrameProjectGoalDispatchTrace): DevFrameTaskResult {
  return {
    ok: trace.outcome === 'completed',
    projectId: trace.projectId,
    goalId: trace.goalId,
    sessionId: trace.sessionId,
    outcome: trace.outcome,
  }
}

function errorCode(error: unknown): string {
  return error instanceof ControlSessionError ? error.code : 'TASK_FAILED'
}

function emitResult(result: DevFrameTaskResult): void {
  internals.stdout.write(`${JSON.stringify(result)}\n`)
}

/**
 * Execute the task after the composed Loader tree has settled.
 * @param ctx - composed DSH Host context.
 * @param request - validated one-shot task request.
 * @returns the pathless task result.
 */
export async function runTask(ctx: Context, request: DevFrameTaskStartupValues): Promise<DevFrameTaskResult> {
  const loader = ctx.get('loader') as { await(): Promise<unknown> } | undefined
  await loader?.await()
  const registry = ctx.get('workspaceRegistry') as WorkspaceRegistryLike | undefined
  const controlSessions = ctx.get('devframeControlSessions') as ControlSessionsLike | undefined
  const identity = ctx.get('profileIdentity') as { id?: string } | undefined
  if (registry === undefined || controlSessions === undefined || identity?.id === undefined) {
    throw new ControlSessionError('MODEL_UNAVAILABLE')
  }
  const workspace = await resolveProject(registry, request.project)
  return resultFromTrace(await controlSessions.dispatchProjectGoal({
    profileId: identity.id,
    projectId: String(workspace.id),
    projectRoot: workspace.path,
    objective: request.objective,
    maxGoalRounds: request.rounds,
  }))
}

/** Mount the one-shot task runner and request bounded process teardown. */
export function apply(ctx: Context, config: DevFrameTaskRunnerConfig): void {
  if (config.request === undefined) return
  const exit = ctx.get('appExit')
  if (exit === undefined) {
    throw new Error('devframe-task-runner: the launcher must provide ctx.appExit before the tree mounts')
  }
  let settled = false
  const finish = (code: number): void => {
    if (settled) return
    settled = true
    exit(code)
  }
  void runTask(ctx, config.request).then((result) => {
    emitResult(result)
    finish(result.ok ? 0 : 1)
  }).catch((error: unknown) => {
    const result: DevFrameTaskResult = { ok: false, error: errorCode(error) }
    emitResult(result)
    internals.stderr.write(`dsh: DevFrame task failed: ${result.error}\n`)
    finish(1)
  })
}
