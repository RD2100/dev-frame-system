import { Context } from '@deepseek-ai/cordis'
import { internals as cmdlineInternals, provideCmdline } from '@deepseek-ai/dsh-cmdline'
import { afterEach, describe, expect, it } from 'vitest'
import {
  apply as applyStartup,
  DEVFRAME_TASK_STARTUP_SERVICE,
  DEVFRAME_EXPERIMENTAL_TASKS_ENV,
  type DevFrameTaskStartupValues,
} from '../src/task-startup.ts'
import {
  apply as applyRunner,
  internals as runnerInternals,
  resolveProject,
  runTask,
} from '../src/task-runner.ts'

const PROJECT_ID = 'project-alpha'
const PROJECT_ROOT = 'C:\\work\\project-alpha'

function withExperimentalTasks<T>(callback: () => T): T {
  const previous = process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV]
  process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] = '1'
  try {
    return callback()
  } finally {
    process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] = previous ?? ''
  }
}

async function withExperimentalTasksAsync<T>(callback: () => Promise<T>): Promise<T> {
  const previous = process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV]
  process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] = '1'
  try {
    return await callback()
  } finally {
    process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] = previous ?? ''
  }
}

function workspace(id = PROJECT_ID, path = PROJECT_ROOT): { id: string; path: string } {
  return { id, path }
}

afterEach(() => {
  cmdlineInternals.stdout = process.stdout
  cmdlineInternals.stderr = process.stderr
  runnerInternals.stdout = process.stdout
  runnerInternals.stderr = process.stderr
})

describe('DevFrame task command provider', () => {
  it('keeps the normal profile invocation unclaimed when no task command is present', () => {
    const ctx = new Context()
    provideCmdline(ctx, { args: [], exit: () => {} })
    applyStartup(ctx)
    expect(ctx.get(DEVFRAME_TASK_STARTUP_SERVICE)).toBeUndefined()
  })

  it.each([
    ['--port', '0'],
    ['--host', '127.0.0.1'],
  ])('leaves ordinary Web argv %j unclaimed', (...args: string[]) => {
    const output: string[] = []
    const exits: number[] = []
    const ctx = new Context()
    cmdlineInternals.stdout = { write: (chunk) => { output.push(chunk); return true } }
    cmdlineInternals.stderr = cmdlineInternals.stdout
    provideCmdline(ctx, {
      args,
      exit: (code) => { exits.push(code) },
    })
    applyStartup(ctx)
    expect(output).toEqual([])
    expect(exits).toEqual([])
    expect(ctx.get(DEVFRAME_TASK_STARTUP_SERVICE)).toBeUndefined()
  })

  it('fails closed for task invocations unless the experimental switch is enabled', () => {
    const output: string[] = []
    const ctx = new Context()
    const previous = process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV]
    process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] = ''
    cmdlineInternals.stdout = { write: (chunk) => { output.push(chunk); return true } }
    cmdlineInternals.stderr = cmdlineInternals.stdout
    const exits: number[] = []
    try {
      provideCmdline(ctx, {
        args: ['task', '--project', PROJECT_ID, '--objective', 'inspect'],
        exit: (code) => { exits.push(code) },
      })
      applyStartup(ctx)
    } finally {
      process.env[DEVFRAME_EXPERIMENTAL_TASKS_ENV] = previous ?? ''
    }
    expect(output.join('')).toContain(`${DEVFRAME_EXPERIMENTAL_TASKS_ENV}=1`)
    expect(exits).toEqual([1])
    expect(ctx.get(DEVFRAME_TASK_STARTUP_SERVICE)).toBeUndefined()
  })

  it('publishes a trimmed project objective and bounded round budget', () => {
    withExperimentalTasks(() => {
      const ctx = new Context()
      provideCmdline(ctx, {
        args: ['task', '--project', PROJECT_ID, '--objective', '  inspect the repo  ', '--rounds', '2'],
        exit: () => {},
      })
      applyStartup(ctx)
      expect(ctx.get(DEVFRAME_TASK_STARTUP_SERVICE)).toEqual({
        project: PROJECT_ID,
        objective: 'inspect the repo',
        rounds: 2,
      })
    })
  })

  it('rejects an unsupported round budget before publishing the runner service', () => {
    withExperimentalTasks(() => {
      const output: string[] = []
      const ctx = new Context()
      cmdlineInternals.stdout = { write: (chunk) => { output.push(chunk); return true } }
      cmdlineInternals.stderr = cmdlineInternals.stdout
      const exits: number[] = []
      provideCmdline(ctx, {
        args: ['task', '--project', PROJECT_ID, '--objective', 'inspect', '--rounds', '3'],
        exit: (code) => { exits.push(code) },
      })
      applyStartup(ctx)
      expect(output.join('')).toContain('--rounds must be 1 or 2')
      expect(exits).toEqual([1])
      expect(ctx.get(DEVFRAME_TASK_STARTUP_SERVICE)).toBeUndefined()
    })
  })
})

describe('DevFrame task runner', () => {
  it('stays inert in the ordinary Web profile when no task request was published', () => {
    const ctx = new Context()
    expect(() => {
      applyRunner(ctx, {})
    }).not.toThrow()
    expect(ctx.get('appExit')).toBeUndefined()
  })

  it('resolves an existing non-UUID workspace id before treating the selector as a path', async () => {
    const selected = workspace()
    const registry = {
      get: () => selected,
      resolveByPath: async () => undefined,
      create: async () => { throw new Error('path fallback must not run') },
    }
    await expect(resolveProject(registry as never, PROJECT_ID)).resolves.toBe(selected)
  })

  it('does not turn a registry/storage failure into a create-by-path attempt', async () => {
    const failure = Object.assign(new Error('permission denied'), { code: 'EACCES' })
    const registry = {
      get: () => undefined,
      resolveByPath: async () => { throw failure },
      create: async () => { throw new Error('create must not run') },
    }
    await expect(resolveProject(registry as never, 'project-selector')).rejects.toBe(failure)
  })

  it('composes parser and runner and emits a pathless successful result', async () => {
    await withExperimentalTasksAsync(async () => {
      const output: string[] = []
      runnerInternals.stdout = { write: (chunk) => { output.push(chunk); return true } }
      const exits: number[] = []
      const selected = workspace()
      const ctx = new Context()
      provideCmdline(ctx, {
        args: ['task', '--project', PROJECT_ID, '--objective', 'run focused checks'],
        exit: (code) => { exits.push(code) },
      })
      ctx.provide('profileIdentity', { id: 'profile-1', name: 'devframe' })
      ctx.provide('workspaceRegistry', {
        get: () => selected,
        resolveByPath: async () => undefined,
        create: async () => selected,
      })
      ctx.provide('devframeControlSessions', {
        dispatchProjectGoal: async (options: Record<string, unknown>) => ({
          projectId: String(options.projectId),
          goalId: 'goal-1',
          revision: 1,
          round: 1,
          sessionId: 'session-1',
          provider: 'test',
          model: 'test-model',
          outcome: 'completed',
        }),
      })
      applyStartup(ctx)
      const request = ctx.get(DEVFRAME_TASK_STARTUP_SERVICE) as DevFrameTaskStartupValues
      applyRunner(ctx, { request })
      await new Promise(resolve => setTimeout(resolve, 0))
      expect(exits).toEqual([0])
      expect(JSON.parse(output.join(''))).toEqual({
        ok: true,
        projectId: PROJECT_ID,
        goalId: 'goal-1',
        sessionId: 'session-1',
        outcome: 'completed',
      })
      expect(output.join('')).not.toContain(PROJECT_ROOT)
    })
  })

  it('maps native path/storage failures to a stable code without leaking the path', async () => {
    const output: string[] = []
    const errors: string[] = []
    runnerInternals.stdout = { write: (chunk) => { output.push(chunk); return true } }
    runnerInternals.stderr = { write: (chunk) => { errors.push(chunk); return true } }
    const exits: number[] = []
    const ctx = new Context()
    const request: DevFrameTaskStartupValues = {
      project: 'C:\\private\\not-for-output',
      objective: 'inspect',
      rounds: 1,
    }
    provideCmdline(ctx, { args: [], exit: (code) => { exits.push(code) } })
    ctx.provide('profileIdentity', { id: 'profile-1', name: 'devframe' })
    ctx.provide('workspaceRegistry', {
      get: () => undefined,
      resolveByPath: async () => undefined,
      create: async () => { throw new Error('cannot create C:\\private\\not-for-output') },
    })
    ctx.provide('devframeControlSessions', {
      dispatchProjectGoal: async () => { throw new Error('must not dispatch') },
    })
    applyRunner(ctx, { request })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(exits).toEqual([1])
    expect(JSON.parse(output.join(''))).toEqual({ ok: false, error: 'TASK_FAILED' })
    expect(output.join('')).not.toContain('private')
    expect(errors.join('')).not.toContain('private')
  })

  it('passes the selected workspace root only to the Host service', async () => {
    const selected = workspace()
    let call: Record<string, unknown> | undefined
    const registry = {
      get: () => undefined,
      resolveByPath: async () => selected,
      create: async () => selected,
    }
    const sessions = {
      dispatchProjectGoal: async (options: Record<string, unknown>) => {
        call = options
        return {
          projectId: PROJECT_ID,
          goalId: 'goal-1',
          revision: 1,
          round: 1,
          sessionId: 'session-1',
          provider: 'test',
          model: 'test-model',
          outcome: 'completed' as const,
        }
      },
    }
    const ctx = new Context()
    ctx.provide('profileIdentity', { id: 'profile-1', name: 'devframe' })
    ctx.provide('workspaceRegistry', registry)
    ctx.provide('devframeControlSessions', sessions)
    const trace = await runTask(ctx, { project: PROJECT_ID, objective: 'inspect', rounds: 1 })
    expect(trace.projectId).toBe(PROJECT_ID)
    expect(call).toMatchObject({
      profileId: 'profile-1',
      projectId: PROJECT_ID,
      projectRoot: PROJECT_ROOT,
      objective: 'inspect',
      maxGoalRounds: 1,
    })
  })

  it.each([
    { outcome: 'failed' as const, exit: 1 },
    { outcome: 'aborted' as const, exit: 1 },
  ])('marks a non-completed trace as unsuccessful ($outcome)', async ({ outcome, exit }) => {
    const output: string[] = []
    runnerInternals.stdout = { write: (chunk) => { output.push(chunk); return true } }
    const exits: number[] = []
    const ctx = new Context()
    ctx.provide('appExit', (code: number) => { exits.push(code) })
    ctx.provide('profileIdentity', { id: 'profile-1', name: 'devframe' })
    ctx.provide('workspaceRegistry', {
      get: () => workspace(),
      resolveByPath: async () => undefined,
      create: async () => workspace(),
    })
    ctx.provide('devframeControlSessions', {
      dispatchProjectGoal: async () => ({
        projectId: PROJECT_ID,
        goalId: 'goal-1',
        revision: 1,
        round: 1,
        sessionId: 'session-1',
        provider: 'test',
        model: 'test-model',
        outcome,
      }),
    })
    applyRunner(ctx, {
      request: { project: PROJECT_ID, objective: 'inspect', rounds: 1 },
    })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(exits).toEqual([exit])
    expect(JSON.parse(output.join(''))).toMatchObject({ ok: false, outcome })
  })
})
