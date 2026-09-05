/**
 * Shared type vocabulary of the pluginized agent hierarchy: roles, task
 * states, durable records, creation intents, and the persistence seams the
 * session-identity, agent-hierarchy, project-controller, and agent-evidence
 * plugins build on. Types only — the branded-id factories live in
 * `./ids.ts`, the closed-union guards in `./guards.ts`, and the stable error
 * type in `./errors.ts`.
 * @module @deepseek-ai/dsh-experimental-project-contracts/types
 */

import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'
import type { PluginId, TaskId } from './ids.ts'

/**
 * The three roles of the pluginized hierarchy. `controller` owns the project
 * and is the only role that may trigger a main-tree integration; `lead` owns
 * one plugin scope and may create workers inside it; `worker` executes work
 * and may create nothing. The retired `reviewer` role is deliberately absent:
 * its semantics moved into lead and worker tool policies.
 */
export type AgentRole = 'controller' | 'lead' | 'worker'

/**
 * Lifecycle states of one project task, in dispatch order:
 * `planned → assigned → developing → reviewing → submitted → integrated →
 * completed`, with `blocked` and `failed` as side exits that must carry a
 * reason, a next action, and a wake condition. A worker report uses
 * `submitted`; only a controller decision moves a task to `integrated`.
 * There is no `idle` state: a task that is not being worked says so through
 * `planned` or `blocked`, never through a resting placeholder.
 */
export type TaskState =
  | 'planned'
  | 'assigned'
  | 'developing'
  | 'reviewing'
  | 'submitted'
  | 'integrated'
  | 'completed'
  | 'blocked'
  | 'failed'

/**
 * One agent's durable place in the hierarchy, written once at creation and
 * restored on cold recovery. `agentId` is the identity the live Agent
 * registry answers to; `sessionId` is the durable Session that owns the
 * conversation. The two coincide for local agents and may diverge for remote
 * providers that mint run ids in the parent namespace. `parentSessionId`
 * records the delegating session when the agent was created by another
 * agent. `worktreeId`, `worktreePath`, and `branch` are present when the
 * agent owns a registered worktree; `worktreePath` is the canonical path the
 * registry observed, never the caller's spelling.
 */
export interface AgentBindingRecord {
  /** Live Agent registry identity (a Session id for local agents). */
  readonly agentId: SessionId
  /** Durable Session identity that owns the agent's conversation. */
  readonly sessionId: SessionId
  /** Delegating session, present when a parent agent created this one. */
  readonly parentSessionId?: SessionId
  /** The hierarchy role fixed at creation; immutable for the agent's life. */
  readonly role: AgentRole
  /** Plugin scope the agent operates in, when its role grants one. */
  readonly pluginId?: PluginId
  /** Task the agent is bound to, when created for one specific task. */
  readonly taskId?: TaskId
  /** Registered worktree the agent owns, when the host assigned one. */
  readonly worktreeId?: WorktreeId
  /** Canonical worktree path as the registry recorded it. */
  readonly worktreePath?: string
  /** Branch checked out in the agent's worktree, when known. */
  readonly branch?: string
  /** ISO-8601 creation instant, stamped once and never rewritten. */
  readonly createdAt: string
}

/**
 * One task on the project board. A move to `blocked` or `failed` must set
 * `blockedReason`, `nextAction`, and `wakeCondition` together; a controller
 * that cannot state all three keeps the task in its previous state and
 * records the uncertainty instead of silently parking it.
 */
export interface TaskRecord {
  /** Stable task identity; the store's primary key. */
  readonly taskId: TaskId
  /** Plugin scope the task belongs to. */
  readonly pluginId: PluginId
  /** Human-authored title carried to dispatch and evidence. */
  readonly title: string
  /** Current lifecycle state; see the type for the dispatch order. */
  readonly state: TaskState
  /** Why the task is `blocked` or `failed`; required in exactly those states. */
  readonly blockedReason?: string
  /** What must happen next; required when `blocked` or `failed`. */
  readonly nextAction?: string
  /** What unblocks the task; required when `blocked` or `failed`. */
  readonly wakeCondition?: string
  /** Session bound to execute the task, present from `assigned` onward. */
  readonly assigneeSessionId?: SessionId
  /** Worktree the task executes in, when the host assigned one. */
  readonly worktreeId?: WorktreeId
  /** ISO-8601 creation instant, stamped once and never rewritten. */
  readonly createdAt: string
  /** ISO-8601 instant of the last durable mutation, including create. */
  readonly updatedAt: string
}

/**
 * What one creation entry records before a child agent exists: the parent
 * session that attempted the creation, the role it requested for the child,
 * and — for leads — the plugin scope the child would operate in. The
 * hierarchy guard validates every creation against the creator's own role
 * and, for a lead, against the plugin scope the lead was granted.
 */
export interface CreationIntent {
  /** Session that attempted the creation. */
  readonly parentSessionId: SessionId
  /** Role requested for the child. */
  readonly requestedRole: AgentRole
  /** Plugin scope requested for the child; a lead may only request its own. */
  readonly pluginScope?: PluginId
}

/**
 * Minimal persistence seam for agent bindings. Implementations live with the
 * owning plugin (JSON storage under the plugin's own storages directory, an
 * in-memory store for tests); this interface fixes only the operations.
 * `read` answers `undefined` for a missing record instead of failing.
 */
export interface BindingStore {
  /**
   * Read one agent's binding.
   * @param agentId - Live Agent registry identity selecting the record.
   * @returns the stored record, or `undefined` when none exists.
   */
  read(agentId: SessionId): Promise<AgentBindingRecord | undefined>
  /**
   * Persist one record, replacing any earlier record for the same agent.
   * @param record - Already validated record to store.
   * @returns resolution after the record is durable.
   */
  write(record: AgentBindingRecord): Promise<void>
  /**
   * Read every stored binding, in a stable implementation-defined order.
   * @returns all records; cold recovery rebuilds the registry from this list.
   */
  list(): Promise<readonly AgentBindingRecord[]>
}

/**
 * Minimal persistence seam for project tasks. The same shape contract as
 * {@link BindingStore}: `read` answers `undefined` for a missing record.
 */
export interface TaskStore {
  /**
   * Read one task.
   * @param taskId - Task identity selecting the record.
   * @returns the stored record, or `undefined` when none exists.
   */
  read(taskId: TaskId): Promise<TaskRecord | undefined>
  /**
   * Persist one record, replacing any earlier record for the same task.
   * @param record - Already validated record to store.
   * @returns resolution after the record is durable.
   */
  write(record: TaskRecord): Promise<void>
  /**
   * Read every stored task, in a stable implementation-defined order.
   * @returns all records; consumers filter by state or plugin in memory.
   */
  list(): Promise<readonly TaskRecord[]>
}
