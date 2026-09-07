/**
 * AT3-07 host-assembly grading: the real memory tool failure (unavailable
 * Vault through the real tool registry) folds into exactly one
 * `devframe/task-warning` per task, the grading rides the explicit host
 * requirement context — never a message dispatch mode — and a failed save
 * never gains a success receipt. The `tool/call`/`tool/result` log rows are
 * appended in the exact shape the agent loop appends them, with the error
 * info taken from the real dispatch outcome.
 * @module tests/task-warning-listener
 */

import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import SessionStore from '@deepseek-ai/dsh-session'
import type { Session } from '@deepseek-ai/dsh-session'
import type { SessionSeq } from '@deepseek-ai/dsh-session'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import * as projectMemory from '@deepseek-ai/dsh-experimental-project-memory'
import {
  gradeMemoryFailure,
  memoryWarningCode,
  taskWarningListener,
} from '../src/index.ts'
import { decodeDevFramePayload } from '../src/events.ts'
import { TaskId } from '../src/controller/goal-binding.ts'

const ROOTS: string[] = []
const CONTEXTS: Context[] = []

afterEach(async () => {
  for (const ctx of CONTEXTS.splice(0).reverse()) await ctx.fiber.dispose()
  while (ROOTS.length > 0) {
    const root = ROOTS.pop()
    if (root !== undefined) await rm(root, { recursive: true, force: true })
  }
})

/**
 * Boot the real composition: session store, tool runtime, project-memory over
 * an absent Vault root (the unconfigured face — every append reports
 * `MEMORY_UNAVAILABLE`), and the task-warning listener.
 */
async function boot(): Promise<{ ctx: Context; session: Session }> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-devframe-task-warning-'))
  ROOTS.push(root)
  const ctx = new Context()
  CONTEXTS.push(ctx)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(projectMemory, { workspaceId: 'ws-warn', vaultRoot: join(root, 'absent-vault'), writeEnabled: true })
  await ctx.plugin(taskWarningListener)
  const session = ctx.sessions.create(undefined, { meta: { cwd: root } })
  return { ctx, session }
}

/** The agent face the memory tools dispatch through: the live session only. */
function agentOn(session: Session): Agent {
  return { session } as unknown as Agent
}

/** Append the `tool/call` row exactly as the agent loop appends it. */
function appendToolCall(session: Session, turn: number, callId: string, name: string): SessionSeq {
  return session.append('tool/call', { turn, step: 1, callId, name, arguments: {} }).seq
}

/**
 * Append the `tool/result` row exactly as the agent loop appends it, carrying
 * the error info of the real dispatch outcome and citing its call row.
 */
function appendToolResult(session: Session, turn: number, callId: string, callSeq: SessionSeq, outcome: {
  readonly isError: boolean
  readonly error?: { readonly info?: { readonly name?: string; readonly code?: string } }
}): void {
  session.append('tool/result', {
    turn,
    step: 1,
    message: {
      callId,
      content: [{ type: 'text', text: outcome.isError ? `failed: ${outcome.error?.message ?? ''}` : 'ok' }],
      isError: outcome.isError,
    },
    ...outcome.error?.info ? { error: outcome.error.info } : {},
  }, { surfaceOp: 'append', sourceEventSeqs: [callSeq] })
}

/** Dispatch one real memory append against the unavailable Vault. */
function dispatchMemoryAppend(ctx: Context, session: Session, callId: string, sourceRef: string) {
  return ctx.tools.execute({
    callId: ToolCallId(callId),
    name: 'memory_append',
    arguments: { scope: 'project', source_ref: sourceRef, kind: 'fact', body: 'AT3-07 grading probe: the vault is absent.' },
    signal: new AbortController().signal,
    agent: agentOn(session),
  })
}

/** Drain the listener's deferred appends. */
async function drain(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

function taskWarnings(session: Session) {
  return session.snapshotEvents().filter(event => event.type === 'devframe/task-warning')
}

describe('AT3-07 explicit-context grading', () => {
  it('A1+A2: an optional-memory task folds one real failure into exactly one warning with no success receipt', async () => {
    const { ctx, session } = await boot()
    ctx.devframeTaskGrading.declare(session.id, { taskId: TaskId('task-a'), memory: 'optional' })
    const callSeqA1 = appendToolCall(session, 1, 'call-a1', 'memory_append')
    const outcome = await dispatchMemoryAppend(ctx, session, 'call-a1', 'session-a#event-1')
    expect(outcome.isError, 'the absent vault fails the append for real').toBe(true)
    expect(outcome.error?.info).toMatchObject({ name: 'ProjectMemoryError', code: 'MEMORY_UNAVAILABLE' })
    appendToolResult(session, 1, 'call-a1', callSeqA1, outcome)
    await drain()

    const warnings = taskWarnings(session)
    expect(warnings, 'exactly one graded event per task').toHaveLength(1)
    expect(warnings[0]!.data).toMatchObject({
      version: 1,
      taskId: 'task-a',
      warning: 'MEMORY_UNAVAILABLE',
      tool: 'memory_append',
    })
    expect(gradeMemoryFailure({ memory: 'optional', code: 'MEMORY_UNAVAILABLE' })).toBe('complete-with-warning')
    expect(session.snapshotEvents().some(event => event.type === 'memory/receipt'), 'A2: a failed save never commits a receipt').toBe(false)

    // A retried failure under the same task stays at exactly one event.
    const callSeqA2 = appendToolCall(session, 2, 'call-a2', 'memory_append')
    const retry = await dispatchMemoryAppend(ctx, session, 'call-a2', 'session-a#event-2')
    expect(retry.isError).toBe(true)
    appendToolResult(session, 2, 'call-a2', callSeqA2, retry)
    await drain()
    expect(taskWarnings(session)).toHaveLength(1)
  })

  it('A3+counter-example: a required-memory task in the SAME dispatch shape warns nothing and fails', async () => {
    const { ctx, session } = await boot()
    // Identical message dispatch shape as A1 — only the explicit host
    // requirement context differs; the mode face is never consulted.
    ctx.devframeTaskGrading.declare(session.id, { taskId: TaskId('task-b'), memory: 'required' })
    const callSeqB1 = appendToolCall(session, 1, 'call-b1', 'memory_append')
    const outcome = await dispatchMemoryAppend(ctx, session, 'call-b1', 'session-b#event-1')
    expect(outcome.isError).toBe(true)
    expect(outcome.error?.info).toMatchObject({ code: 'MEMORY_UNAVAILABLE' })
    appendToolResult(session, 1, 'call-b1', callSeqB1, outcome)
    await drain()

    expect(taskWarnings(session), 'no warning vocabulary for a required-memory failure').toHaveLength(0)
    expect(gradeMemoryFailure({ memory: 'required', code: 'MEMORY_UNAVAILABLE' })).toBe('fail')
    expect(session.snapshotEvents().some(event => event.type === 'memory/receipt')).toBe(false)

    // An undeclared session grades nothing either — the conservative default.
    const undeclared = ctx.sessions.create(undefined, { meta: { cwd: ROOTS[0] } })
    const callSeqC1 = appendToolCall(undeclared, 1, 'call-c1', 'memory_append')
    const other = await dispatchMemoryAppend(ctx, undeclared, 'call-c1', 'session-c#event-1')
    expect(other.isError).toBe(true)
    appendToolResult(undeclared, 1, 'call-c1', callSeqC1, other)
    await drain()
    expect(taskWarnings(undeclared)).toHaveLength(0)
  })

  it('grades only memory-save degradations and decodes the durable payload with brands', () => {
    expect(memoryWarningCode('MEMORY_UNAVAILABLE')).toBe('MEMORY_UNAVAILABLE')
    expect(memoryWarningCode('MEMORY_APPEND_DISABLED')).toBe('MEMORY_APPEND_DISABLED')
    expect(memoryWarningCode('MEMORY_CONTENT_REJECTED')).toBeUndefined()
    expect(memoryWarningCode('MEMORY_INVALID_NOTE')).toBeUndefined()
    expect(memoryWarningCode(undefined)).toBeUndefined()
    expect(gradeMemoryFailure({ memory: 'optional', code: 'MEMORY_CONTENT_REJECTED' })).toBeUndefined()

    const decoded = decodeDevFramePayload('devframe/task-warning', {
      version: 1,
      taskId: 'task-a',
      warning: 'MEMORY_UNAVAILABLE',
      tool: 'memory_append',
    })
    expect(String(decoded.taskId)).toBe('task-a')
    expect(() => decodeDevFramePayload('devframe/task-warning', {
      version: 1,
      taskId: 'task-a',
      // A hostile log row cannot widen the vocabulary past the closed union.
      warning: 'MEMORY_INVALID_REQUEST',
      tool: 'memory_append',
    })).toThrow()
  })
})
