/**
 * Shared task-start authority: the live root-controller/Goal checks and the
 * Worker admission assertions of `project_task start`, factored out of the
 * task consumer so the tool face and the host approve RPC enforce the same
 * single truth. `resolveControllerAuthority` covers the controller/Goal
 * domain a `plan` needs before its task exists; `resolveTaskStartAuthority`
 * adds the planned/assigned task, the exactly-one Worker with its parent
 * lead, and the three independent locked worktrees; `taskStartUnchanged`
 * re-resolves and compares the admission signature for write-boundary drift
 * checks. All three take the consumer's stopped state as a callback so the
 * tool's teardown latch and the host RPC path share one implementation.
 * @module @deepseek-ai/dsh-experimental-project-controller/start-authority
 */

import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type {
  AgentBindingRecord,
  TaskRecord,
} from '@deepseek-ai/dsh-experimental-project-contracts'
import type { TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { GoalBinding } from '@deepseek-ai/dsh-experimental-devframe/controller/goal-binding'
import type { Worktree } from '@deepseek-ai/dsh-worktree-registry'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from './controller.ts'

/** The controller/Goal half of task-start authority, shared by plan and start. */
export interface GoalAuthority {
  /** The live registered root-controller binding. */
  readonly root: AgentBindingRecord
  /** The current open Goal that admits the task id. */
  readonly goal: GoalBinding
  /** Every registered worktree row across workspaces. */
  readonly rows: readonly Worktree[]
  /** The controller's own worktree row with its writer lock. */
  readonly target: Worktree
}

/** The complete task-start admission, returned to callers that then start the task. */
export interface TaskStartAuthority extends GoalAuthority {
  /** The planned or assigned task being started. */
  readonly task: TaskRecord
  /** The exactly-one Worker binding registered for the task. */
  readonly worker: AgentBindingRecord
  /** The Worker's parent lead binding. */
  readonly lead: AgentBindingRecord
  /** The Worker's worktree row with its writer lock. */
  readonly source: Worktree
  /** The lead's worktree row with its writer lock. */
  readonly reviewer: Worktree
  /** The live Worker agent on its registered worktree. */
  readonly workerAgent: Agent
  /** Serialized identity of the admission, for drift re-checks at the write boundary. */
  readonly signature: string
}

/** The consumer's teardown latch; true once its effect disposal has run. */
export type StoppedState = () => boolean

/**
 * Resolve the controller/Goal authority for one task: the actual live root
 * controller with its registered worktree, the current open Goal admitting
 * the task id, and the controller writer lock in the Goal workspace.
 * @param ctx - Host context with the live authorities.
 * @param controllerAgent - The exact live root controller Agent.
 * @param taskId - Task id already authorized by the current Goal.
 * @param isStopped - Consumer teardown latch; a stopped consumer fails loud.
 * @returns the resolved controller/Goal authority.
 */
export function resolveControllerAuthority(
  ctx: Context,
  controllerAgent: Agent | undefined,
  taskId: TaskId,
  isStopped: StoppedState,
): GoalAuthority {
  if (isStopped()) throw new Error('project_task consumer is stopped')
  if (controllerAgent === undefined || ctx.agents.get(controllerAgent.id) !== controllerAgent) throw new Error('project_task requires the actual live root controller')
  const root = ctx.agentBindings.find(controllerAgent.session.id)
  if (root?.role !== 'controller' || root.parentSessionId !== undefined || root.agentId !== controllerAgent.id
    || root.sessionId !== controllerAgent.session.id || root.worktreeId === undefined || root.worktreePath === undefined
    || controllerAgent.session.header.cwd !== root.worktreePath) throw new Error('project_task requires the registered root controller worktree')
  const state = ctx.sessionProjections.stateOf(controllerAgent.session, 'devframe')
  const goal = state?.bindings.at(-1)
  if (state === undefined || state.failure !== null || goal?.lifecycle !== 'admission_open'
    || (state.lifecycle !== null && state.lifecycle.binding.goalId === goal.goalId && state.lifecycle.state !== 'admission_open')
    || String(goal.controllerSessionId) !== String(root.sessionId)
    || !goal.taskIds.some(id => String(id) === String(taskId))) throw new Error('project_task requires the task in the current open Goal')
  const rows = ctx.workspaceRegistry.list().flatMap(workspace => ctx.worktreeRegistry.list(workspace.id))
  const target = rows.find(row => row.id === root.worktreeId)
  if (target === undefined || target.path !== root.worktreePath || String(target.lockedBy) !== String(root.sessionId)
    || String(target.workspaceId) !== String(goal.workspaceId)) throw new Error('project_task requires the controller writer lock in the Goal workspace')
  return { root, goal, rows, target }
}

/**
 * Resolve the complete task-start admission: the controller/Goal authority
 * plus the planned/assigned task, exactly one Worker with its parent lead,
 * and the three independent registered worktrees with their writer locks.
 * @param ctx - Host context with the live authorities.
 * @param controllerAgent - The exact live root controller Agent.
 * @param taskId - Task to start.
 * @param isStopped - Consumer teardown latch; a stopped consumer fails loud.
 * @returns the resolved admission with its drift signature.
 */
export function resolveTaskStartAuthority(
  ctx: Context,
  controllerAgent: Agent | undefined,
  taskId: TaskId,
  isStopped: StoppedState,
): TaskStartAuthority {
  const initial = resolveControllerAuthority(ctx, controllerAgent, taskId, isStopped)
  const task = ctx.projectController.find(taskId)
  if (task === undefined || (task.state !== 'planned' && task.state !== 'assigned')) throw new Error('project_task start requires a planned or assigned task; a started task cannot be re-briefed')
  const workers = ctx.agentBindings.list().filter(binding => binding.role === 'worker' && binding.taskId === taskId && binding.pluginId === task.pluginId)
  const worker = workers[0]
  if (workers.length !== 1 || worker === undefined) throw new Error('project_task start requires exactly one registered task Worker')
  const lead = worker.parentSessionId === undefined ? undefined : ctx.agentBindings.find(worker.parentSessionId)
  const workerAgent = ctx.agents.get(worker.agentId)
  const source = initial.rows.find(row => row.id === worker.worktreeId)
  const reviewer = initial.rows.find(row => row.id === lead?.worktreeId)
  if (lead?.role !== 'lead' || lead.parentSessionId !== initial.root.sessionId || lead.pluginId !== task.pluginId
    || workerAgent === undefined || workerAgent.session.id !== worker.sessionId
    || workerAgent.session.header.cwd !== worker.worktreePath
    || source === undefined || reviewer === undefined || source.path !== worker.worktreePath || reviewer.path !== lead.worktreePath
    || source.workspaceId !== initial.target.workspaceId || reviewer.workspaceId !== initial.target.workspaceId
    || String(source.lockedBy) !== String(worker.sessionId) || String(reviewer.lockedBy) !== String(lead.sessionId)
    || new Set([initial.target.id, source.id, reviewer.id]).size !== 3
    || new Set([initial.target.path, source.path, reviewer.path]).size !== 3) throw new Error('project_task start requires independent registered controller, lead, and live Worker worktrees with writer locks')
  const signature = JSON.stringify({ root: initial.root, target: initial.target, worker, lead, source, reviewer })
  return { ...initial, task, worker, lead, source, reviewer, workerAgent, signature }
}

/**
 * Build the write-boundary drift re-check for a resolved admission: re-resolve
 * the full authority and compare the admission signature and the live Worker
 * agent identity. A change fails loud so a concurrent mutation cannot slip a
 * task into development.
 * @param ctx - Host context with the live authorities.
 * @param start - The admission captured at the caller's first resolution.
 * @param isStopped - Consumer teardown latch.
 * @returns a synchronous re-check to run before each task write.
 */
/**
 * Build the write-boundary drift re-check for a resolved admission: re-resolve
 * the controller/Goal authority and the Worker/lead bindings and compare the
 * admission signature plus the live Worker agent identity. Task state is
 * deliberately not re-asserted: the re-check runs after the task has already
 * moved (assigned/developing), so only ownership drift fails loud.
 * @param ctx - Host context with the live authorities.
 * @param start - The admission captured at the caller's first resolution.
 * @param isStopped - Consumer teardown latch.
 * @returns a synchronous re-check to run before and after each task write.
 */
export function taskStartUnchanged(
  ctx: Context,
  start: TaskStartAuthority,
  isStopped: StoppedState,
): () => void {
  return () => {
    const controller = ctx.agents.get(start.root.agentId)
    if (controller === undefined) throw new Error('project_task requires the actual live root controller')
    const current = resolveControllerAuthority(ctx, controller, start.task.taskId, isStopped)
    const nextWorker = ctx.agentBindings.find(start.worker.sessionId)
    const nextLead = ctx.agentBindings.find(start.lead.sessionId)
    if (ctx.agents.get(start.worker.agentId) !== start.workerAgent || JSON.stringify({
      root: current.root, target: current.target, worker: nextWorker, lead: nextLead,
      source: current.rows.find(row => row.id === start.worker.worktreeId),
      reviewer: current.rows.find(row => row.id === start.lead.worktreeId),
    }) !== start.signature) throw new Error(
      'project_task ownership changed during start; inspect task state before retrying')
  }
}
