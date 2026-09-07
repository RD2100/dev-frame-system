/**
 * Host-assembly listener grading memory-surface degradations into per-task
 * `devframe/task-warning` session events. The grading input is explicit host
 * context declared per session — whether the running task requires memory for
 * acceptance — never a message dispatch mode. Every graded failure lands
 * exactly one event per task carrying its grade: `complete-with-warning` for
 * a task whose acceptance tolerates the degradation, `fail` for a task whose
 * acceptance required the memory operation — the durable record the goal
 * judgment consumes to refuse completion. The listener only reads session
 * events: it never writes message dispatch modes, and the memory receipt
 * stays the sole record of a successful save.
 * @module @deepseek-ai/dsh-experimental-devframe/task-warning-listener
 */

import type { Context } from '@deepseek-ai/cordis'
import type { Session, SessionEvent, SessionId } from '@deepseek-ai/dsh-session'
import type { TaskId } from './controller/goal-binding.ts'
import { gradeMemoryFailure, memoryWarningCode } from './events.ts'
import type { DevFrameMemoryGrading, DevFrameTaskWarningCode } from './events.ts'

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
/** The listener consumes session events and reads store liveness at drain. */
export const inject: string[] = ['sessions']

/** One queued append for a task whose warning is not in the log yet. */
interface PendingWrite {
  readonly taskId: TaskId
  readonly warning: DevFrameTaskWarningCode
  readonly tool: string
  readonly grade: DevFrameMemoryGrading
}

/** The deferred appends of one session, cancellable until their drain runs. */
interface PendingBatch {
  readonly session: Session
  readonly writes: PendingWrite[]
  cancelled: boolean
}

/**
 * Whether one appended `tool/result` event names a memory tool. The call id
 * lives on the tool-result message's source (`ToolMessageSource.callId` — the
 * real message has no top-level callId), and the tool name on the linked
 * `tool/call` event.
 * @param session - The session whose log holds both events.
 * @param event - The `tool/result` event under classification.
 * @returns The tool name, or `undefined` when the linked call is absent.
 */
function memoryToolName(session: Session, event: SessionEvent<'tool/result'>): string | undefined {
  const callId = event.data.message.source.callId
  const call = session.snapshotEvents().find(candidate =>
    candidate.type === 'tool/call' && candidate.data.callId === callId)
  return call?.type === 'tool/call' ? call.data.name : undefined
}

/**
 * Plugin entry: provide the grading declaration seam and fold memory tool
 * failures into at most one graded `devframe/task-warning` per task — the
 * grade (`complete-with-warning` for optional memory, `fail` for required)
 * rides the event so the goal judgment can refuse a required task's completion
 * without re-deriving the runtime declaration. Appends are
 * deferred past the current macrotask so the listener never appends while the
 * store is still publishing the `tool/result` event that triggered it. Dedup
 * reserves the task key at enqueue time — two failures drained together still
 * land one event — and re-checks the log at drain. Liveness is re-verified
 * before EVERY append: a synchronous listener of one warning may detach the
 * session mid-batch, and a teardown whose `session/disposed` dispatch has not
 * run yet still removed the session from the store; terminated writes release
 * their reservations. The disposer cancels the remaining timers and batches
 * outright, so a captured session is never appended after either teardown.
 * @param ctx - The mounting context.
 * @returns The plugin disposer.
 */
export function apply(ctx: Context): () => void {
  const declared = new Map<string, DevFrameTaskGradingDeclaration>()
  const pending = new Map<string, PendingBatch>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const reserved = new Set<string>()
  let disposed = false

  const warnKey = (sessionId: string, taskId: TaskId): string => `${sessionId}::${String(taskId)}`

  /** Whether the task's warning is already in the session log. */
  const inLog = (session: Session, taskId: TaskId): boolean =>
    session.snapshotEvents().some(candidate =>
      candidate.type === 'devframe/task-warning' && String(candidate.data.taskId) === String(taskId))

  /** Release the enqueue reservations of a batch that will not drain fully. */
  const releaseBatch = (sessionId: string, batch: PendingBatch): void => {
    for (const write of batch.writes) reserved.delete(warnKey(sessionId, write.taskId))
  }

  /**
   * Whether the batch may still append: the plugin must be mounted, the batch
   * must not be cancelled, and the session must be the live store entry. A
   * teardown that has not dispatched its disposal notification yet still
   * removed the session from the store; the live lookup is authoritative. The
   * mounting context may itself already be inactive when a late timer fires
   * during teardown — that is not live either.
   */
  const mayAppend = (batch: PendingBatch): boolean => {
    if (batch.cancelled || disposed) return false
    try {
      return ctx.sessions.get(batch.session.id) === batch.session
    } catch {
      return false // the context is disposed; no service lookup can succeed
    }
  }

  const drainSession = (sessionId: string): void => {
    timers.delete(sessionId)
    const batch = pending.get(sessionId)
    if (batch === undefined) return
    pending.delete(sessionId)
    if (!mayAppend(batch)) {
      releaseBatch(sessionId, batch)
      return
    }
    for (const write of batch.writes) {
      // The log may have grown between enqueue and drain through another
      // writer; the enqueue reservation is this listener's own and is not
      // consulted here — the log alone decides.
      if (inLog(batch.session, write.taskId)) {
        reserved.delete(warnKey(sessionId, write.taskId))
        continue
      }
      // Re-verify before EVERY append: a synchronous listener of the previous
      // warning may have detached the session mid-batch.
      if (!mayAppend(batch)) {
        releaseBatch(sessionId, batch)
        return
      }
      batch.session.append('devframe/task-warning', { version: 1, taskId: write.taskId, warning: write.warning, tool: write.tool, grade: write.grade })
      reserved.delete(warnKey(sessionId, write.taskId))
    }
  }

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
      const sessionId = String(session.id)
      const grading = declared.get(sessionId)
      if (grading === undefined) return
      const grade = gradeMemoryFailure({ memory: grading.memory, code: event.data.error?.code })
      if (grade === undefined) return
      const warning = memoryWarningCode(event.data.error?.code)
      if (warning === undefined) return
      const tool = memoryToolName(session, event)
      if (tool === undefined || !tool.startsWith('memory_')) return
      // The enqueue guard consults both the log and this listener's own
      // reservation, so two failures drained together reserve one write.
      if (inLog(session, grading.taskId) || reserved.has(warnKey(sessionId, grading.taskId))) return
      reserved.add(warnKey(sessionId, grading.taskId))
      let batch = pending.get(sessionId)
      if (batch === undefined) {
        batch = { session, writes: [], cancelled: false }
        pending.set(sessionId, batch)
        // A macrotask drain lets a teardown that starts before it cancel the
        // write; a microtask would outrun the disposal notification.
        timers.set(sessionId, setTimeout(() => {
          drainSession(sessionId)
        }, 0))
      }
      batch.writes.push({ taskId: grading.taskId, warning, tool, grade })
    }),
    ctx.on('session/disposed', (session: Session) => {
      const sessionId = String(session.id)
      declared.delete(sessionId)
      const timer = timers.get(sessionId)
      if (timer !== undefined) {
        clearTimeout(timer)
        timers.delete(sessionId)
      }
      const batch = pending.get(sessionId)
      if (batch !== undefined) batch.cancelled = true
      pending.delete(sessionId)
      for (const key of [...reserved]) {
        if (key.startsWith(`${sessionId}::`)) reserved.delete(key)
      }
    }),
  ]
  return () => {
    disposed = true
    declared.clear()
    for (const timer of timers.values()) clearTimeout(timer)
    timers.clear()
    for (const batch of pending.values()) batch.cancelled = true
    pending.clear()
    reserved.clear()
    for (const dispose of disposers.reverse()) void dispose()
  }
}
