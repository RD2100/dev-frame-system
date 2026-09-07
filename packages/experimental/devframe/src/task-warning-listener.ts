/**
 * Host-assembly listener grading memory-surface degradations into per-task
 * `devframe/task-warning` session events. The grading input is explicit host
 * context declared per session — whether the running task requires memory for
 * acceptance — never a message dispatch mode. An optional-memory failure lands
 * exactly one warning event per task; a required-memory failure stays with the
 * raw `tool/result` error and the host's own fail path. The listener only
 * reads session events: it never writes message dispatch modes, and the memory
 * receipt stays the sole record of a successful save.
 * @module @deepseek-ai/dsh-experimental-devframe/task-warning-listener
 */

import type { Context } from '@deepseek-ai/cordis'
import type { Session, SessionEvent, SessionId } from '@deepseek-ai/dsh-session'
import type { TaskId } from './controller/goal-binding.ts'
import { memoryWarningCode } from './events.ts'

/** The explicit host context one task's memory grading is judged by. */
export interface DevFrameTaskGradingDeclaration {
  /** The task running in the declared session. */
  readonly taskId: TaskId
  /** Whether the task's acceptance requires the memory operation to succeed. */
  readonly memory: 'optional' | 'required'
}

/** Host seam declaring the per-session grading context before memory runs. */
export interface DevFrameTaskGrading {
  /**
   * Declare the grading context for one session's current task.
   * @param sessionId - The session executing the task.
   * @param grading - The task id and the memory requirement.
   */
  declare(sessionId: SessionId, grading: DevFrameTaskGradingDeclaration): void
  /**
   * Drop the declaration when the session ends.
   * @param sessionId - The session whose declaration is dropped.
   */
  clear(sessionId: SessionId): void
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Host seam declaring per-session memory grading context. */
    devframeTaskGrading: DevFrameTaskGrading
  }
}

/** Cordis plugin name. */
export const name = 'devframe-task-warning-listener'
/** The listener consumes session events only. */
export const inject: string[] = []

/**
 * Whether one appended `tool/result` event names a memory tool. The tool name
 * lives on the linked `tool/call` event, cited by the result's call id.
 * @param session - The session whose log holds both events.
 * @param event - The `tool/result` event under classification.
 * @returns The tool name, or `undefined` when the linked call is absent.
 */
function memoryToolName(session: Session, event: SessionEvent<'tool/result'>): string | undefined {
  const callId = event.data.message.callId
  const call = session.snapshotEvents().find(candidate =>
    candidate.type === 'tool/call' && candidate.data.callId === callId)
  return call?.type === 'tool/call' ? call.data.name : undefined
}

/**
 * Plugin entry: provide the grading declaration seam and fold memory tool
 * failures into at most one `devframe/task-warning` per task. The append is
 * deferred to a microtask so the listener never appends while the store is
 * still publishing the `tool/result` event that triggered it.
 * @param ctx - The mounting context.
 * @returns The plugin disposer.
 */
export function apply(ctx: Context): () => void {
  const declared = new Map<string, DevFrameTaskGradingDeclaration>()
  const pending: Array<() => void> = []
  const disposers: Array<() => unknown> = [
    ctx.provide('devframeTaskGrading', {
      declare: (sessionId, grading) => {
        declared.set(String(sessionId), grading)
      },
      clear: (sessionId) => {
        declared.delete(String(sessionId))
      },
    }),
    ctx.on('session/event', (session: Session, event: SessionEvent) => {
      if (event.type !== 'tool/result') return
      const grading = declared.get(String(session.id))
      if (grading === undefined || grading.memory !== 'optional') return
      const warning = memoryWarningCode(event.data.error?.code)
      if (warning === undefined) return
      const tool = memoryToolName(session, event)
      if (tool === undefined || !tool.startsWith('memory_')) return
      if (session.snapshotEvents().some(candidate =>
        candidate.type === 'devframe/task-warning' && String(candidate.data.taskId) === String(grading.taskId))) return
      pending.push(() => {
        session.append('devframe/task-warning', { version: 1, taskId: grading.taskId, warning, tool })
      })
      queueMicrotask(() => {
        for (const append of pending.splice(0)) append()
      })
    }),
    ctx.on('session/disposed', (session: Session) => {
      declared.delete(String(session.id))
    }),
  ]
  return () => {
    for (const dispose of disposers.reverse()) void dispose()
  }
}
