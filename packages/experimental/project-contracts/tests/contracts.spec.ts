/** Contract tests: guards, exhaustiveness, branded id factories, and record shapes. */

import { expect, describe, it } from 'vitest'
import { ProjectContractsError } from '../src/errors.ts'
import { AGENT_ROLES, isAgentRole, isTaskState, TASK_STATES } from '../src/guards.ts'
import { PluginId, TaskId } from '../src/ids.ts'
import type {
  AgentBindingRecord,
  AgentRole,
  CreationIntent,
  TaskRecord,
  TaskState,
} from '../src/types.ts'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type { WorktreeId } from '@deepseek-ai/dsh-worktree-registry'

/** Require a compile-time closed union branch to be handled. */
function assertNever(value: never): never {
  throw new Error(`unhandled union member ${String(value)}`)
}

/** Exhaustive over AgentRole: adding a role without a branch fails to compile. */
function roleBranch(role: AgentRole): AgentRole {
  switch (role) {
    case 'controller': return 'controller'
    case 'lead': return 'lead'
    case 'worker': return 'worker'
    default: return assertNever(role)
  }
}

/** Exhaustive over TaskState: adding a state without a branch fails to compile. */
function stateBranch(state: TaskState): TaskState {
  switch (state) {
    case 'planned': return 'planned'
    case 'assigned': return 'assigned'
    case 'developing': return 'developing'
    case 'reviewing': return 'reviewing'
    case 'submitted': return 'submitted'
    case 'integrated': return 'integrated'
    case 'completed': return 'completed'
    case 'blocked': return 'blocked'
    case 'failed': return 'failed'
    default: return assertNever(state)
  }
}

describe('agent roles', () => {
  it('freeze exactly the three hierarchy roles', () => {
    expect(Object.isFrozen(AGENT_ROLES)).toBe(true)
    expect([...AGENT_ROLES]).toEqual(['controller', 'lead', 'worker'])
  })

  it('guard accepts every member and rejects retired or malformed values', () => {
    for (const role of AGENT_ROLES) expect(isAgentRole(role)).toBe(true)
    expect(isAgentRole('reviewer')).toBe(false)
    expect(isAgentRole('idle')).toBe(false)
    expect(isAgentRole('')).toBe(false)
    expect(isAgentRole('controller ')).toBe(false)
    expect(isAgentRole(undefined)).toBe(false)
    expect(isAgentRole(null)).toBe(false)
    expect(isAgentRole(0)).toBe(false)
    expect(isAgentRole({})).toBe(false)
  })

  it('every tuple member passes its exhaustive switch', () => {
    for (const role of AGENT_ROLES) expect(roleBranch(role)).toBe(role)
  })
})

describe('task states', () => {
  it('freeze exactly the nine dispatch states without an idle placeholder', () => {
    expect(Object.isFrozen(TASK_STATES)).toBe(true)
    expect([...TASK_STATES]).toEqual([
      'planned',
      'assigned',
      'developing',
      'reviewing',
      'submitted',
      'integrated',
      'completed',
      'blocked',
      'failed',
    ])
    expect(TASK_STATES).not.toContain('idle')
  })

  it('guard accepts every member and rejects malformed values', () => {
    for (const state of TASK_STATES) expect(isTaskState(state)).toBe(true)
    expect(isTaskState('idle')).toBe(false)
    expect(isTaskState('open')).toBe(false)
    expect(isTaskState('')).toBe(false)
    expect(isTaskState('blocked ')).toBe(false)
    expect(isTaskState(undefined)).toBe(false)
    expect(isTaskState(null)).toBe(false)
    expect(isTaskState(42)).toBe(false)
    expect(isTaskState([])).toBe(false)
  })

  it('every tuple member passes its exhaustive switch', () => {
    for (const state of TASK_STATES) expect(stateBranch(state)).toBe(state)
  })
})

describe('branded id factories', () => {
  it('brand validated identifiers', () => {
    const pluginId = PluginId('agent-reliability')
    const taskId = TaskId('task-7')
    expect(pluginId).toBe('agent-reliability')
    expect(taskId).toBe('task-7')
  })

  it('reject empty, whitespace-only, and padded values', () => {
    for (const factory of [PluginId, TaskId]) {
      for (const invalid of ['', '   ', ' padded', 'padded ', ' ']) {
        expect(() => factory(invalid)).toThrow(ProjectContractsError)
        expect(() => factory(invalid)).toThrow(/non-empty trimmed string/)
      }
    }
  })

  it('carry the stable error code', () => {
    try {
      PluginId('  ')
      expect.unreachable('factory must reject whitespace-only ids')
    } catch (error: unknown) {
      expect(error).toBeInstanceOf(ProjectContractsError)
      expect((error as ProjectContractsError).code).toBe('CONTRACTS_INVALID_ID')
      expect((error as ProjectContractsError).name).toBe('ProjectContractsError')
    }
  })
})

describe('stable error type', () => {
  it('preserves message, code, and cause', () => {
    const cause = new Error('backend down')
    const error = new ProjectContractsError('store unusable', 'CONTRACTS_STORE_UNAVAILABLE', { cause })
    expect(error).toBeInstanceOf(Error)
    expect(error.message).toBe('store unusable')
    expect(error.code).toBe('CONTRACTS_STORE_UNAVAILABLE')
    expect(error.cause).toBe(cause)
  })
})

describe('record shapes', () => {
  it('round-trip a fully populated agent binding record', () => {
    const record: AgentBindingRecord = {
      agentId: 'session-1' as SessionId,
      sessionId: 'session-1' as SessionId,
      parentSessionId: 'parent-1' as SessionId,
      role: 'lead',
      pluginId: PluginId('agent-reliability'),
      taskId: TaskId('task-7'),
      worktreeId: 'wt-1' as WorktreeId,
      worktreePath: 'D:/repo/.worktrees/wt-1',
      branch: 'p/task-7',
      createdAt: '2026-09-06T00:00:00.000Z',
    }
    expect(record.role).toBe('lead')
    expect(record.agentId).toBe(record.sessionId)
    expect(record.worktreePath).toContain('wt-1')
  })

  it('allow the optional binding fields to be absent', () => {
    const record: AgentBindingRecord = {
      agentId: 'agent-2' as SessionId,
      sessionId: 'session-2' as SessionId,
      role: 'worker',
      createdAt: '2026-09-06T00:00:00.000Z',
    }
    expect(record.parentSessionId).toBeUndefined()
    expect(record.worktreeId).toBeUndefined()
  })

  it('round-trip a blocked task record with its recovery triple', () => {
    const record: TaskRecord = {
      taskId: TaskId('task-7'),
      pluginId: PluginId('agent-reliability'),
      title: 'Wire admission cut-off',
      state: 'blocked',
      blockedReason: 'worktree registry unavailable',
      nextAction: 'retry after storage domain remounts',
      wakeCondition: 'ctx.worktreeRegistry is reachable again',
      assigneeSessionId: 'session-3' as SessionId,
      worktreeId: 'wt-1' as WorktreeId,
      createdAt: '2026-09-06T00:00:00.000Z',
      updatedAt: '2026-09-06T00:01:00.000Z',
    }
    expect(record.state).toBe('blocked')
    expect(record.blockedReason).toBeTruthy()
    expect(record.nextAction).toBeTruthy()
    expect(record.wakeCondition).toBeTruthy()
  })

  it('round-trip a creation intent', () => {
    const intent: CreationIntent = {
      parentSessionId: 'parent-1' as SessionId,
      requestedRole: 'worker',
      pluginScope: PluginId('agent-reliability'),
    }
    expect(isAgentRole(intent.requestedRole)).toBe(true)
    expect(intent.pluginScope).toBe('agent-reliability')
  })
})
