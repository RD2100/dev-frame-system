/**
 * B6 cleanup check — verifies the cancelled workflow child's real cleanup face
 * from frozen session logs via EXACT EVENT-IDENTITY JOINS (no time windows,
 * no markers, no newest-file heuristics):
 *
 *   job_kill(job_id) ↔ workflow tool call (arguments.meta.name) ↔ its paired
 *   result (toolCallId → jobId receipt) ↔ tool-workflow/run-start (same meta
 *   name → runId) ↔ tool-workflow/agent-start (same runId → childId) ↔ the
 *   child session log (header id = childId).
 *
 * Verified faces:
 *  ① real interruption: the child's own `turn/end` carries reason `parent`;
 *     the parent's agent-end/run-end for the same runId report cancelled.
 *  ② three-way terminal consistency: job settled killed (post-kill read) ↔
 *     agent-end cancelled ↔ child turn/end aborted, all identity-bound; the
 *     child has no completed turn.
 *  ③ resource face (log-provable range): the child artifact persists on disk,
 *     ends at the abort with no later activity, and the parent never reads
 *     the killed job as running afterwards. Process-level resource release is
 *     OUTSIDE this proof range and is reported as such — absent later log
 *     events do not prove every OS/worker resource was reclaimed.
 *
 * Usage:
 *   node --import tsx/esm b6-cleanup-check.ts <projectSessionsDir> <parentSessionId>
 */

import { readdir, readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { scanLog } from '../../../../../packages/session/session-persistence-jsonl/src/format.ts'
import { createZstdFrameDecoder, scanZstdFrames } from '../../../../../packages/session/session-persistence-jsonl/src/zstd.ts'

interface LogEvent {
  type: string
  seq: number
  time: number
  data: Record<string, unknown>
}

interface DecodedLog {
  path: string
  sessionId: string
  events: LogEvent[]
}

const fail = (message: string): never => { throw new Error(`B6 CLEANUP CHECK FAILURE: ${message}`) }
const check = (ok: boolean, message: string): void => { if (!ok) fail(message) }

async function decodeLog(path: string): Promise<DecodedLog> {
  const buffer = await readFile(path)
  let raw = buffer
  if (path.endsWith('.jsonl.zstd')) {
    const decoder = createZstdFrameDecoder()
    try {
      raw = Buffer.concat(Array.from(decoder.decode(buffer, scanZstdFrames(buffer).frames), frame => Buffer.from(frame)))
    } finally {
      decoder.close()
    }
  }
  const scan = scanLog(raw)
  const events: LogEvent[] = scan.events.map(event => ({
    type: event.type, seq: event.seq, time: event.time, data: event.data as Record<string, unknown>,
  }))
  return { path, sessionId: String(scan.meta.id), events }
}

async function loadProjectLogs(projectDir: string): Promise<DecodedLog[]> {
  const entries = await readdir(projectDir, { withFileTypes: true })
  const logs: DecodedLog[] = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    for (const name of ['session.jsonl', 'session.jsonl.zstd']) {
      const path = join(projectDir, entry.name, name)
      try {
        await stat(path)
      } catch {
        continue
      }
      logs.push(await decodeLog(path))
    }
  }
  return logs
}

const argumentsOf = (event: LogEvent): Record<string, unknown> => {
  try { return JSON.parse((event.data as { arguments: string }).arguments) as Record<string, unknown> } catch { return {} }
}

const resultView = (event: LogEvent): { toolCallId: string; text: string; isError: boolean } => {
  const message = (event.data as { message?: { content?: Array<{ type?: string; toolCallId?: string; content?: Array<{ type?: string; text?: string }>; isError?: boolean }> } }).message
  const block = message?.content?.find(candidate => candidate.type === 'tool-result')
  const text = (block?.content ?? []).map(inner => inner.type === 'text' ? inner.text ?? '' : '').join('')
  return { toolCallId: block?.toolCallId ?? '', isError: block?.isError === true, text }
}

const turnEnds = (log: DecodedLog): Array<{ seq: number; time: number; kind: string; reason: unknown }> =>
  log.events.filter(event => event.type === 'turn/end').map(event => ({
    seq: event.seq, time: event.time, kind: (event.data.reason as { kind?: string } | undefined)?.kind ?? 'unknown',
    reason: (event.data.reason as { reason?: unknown } | undefined)?.reason,
  }))

async function main(): Promise<void> {
  const projectDir = process.argv[2]
  const parentSessionId = process.argv[3]
  check(typeof projectDir === 'string' && projectDir.length > 0, 'pass the project sessions directory as argv[2]')
  check(typeof parentSessionId === 'string' && parentSessionId.length > 0, 'pass the workflow parent session id as argv[3]')
  const logs = await loadProjectLogs(projectDir!)
  const parent = logs.find(log => log.sessionId === parentSessionId)
  check(parent !== undefined, `parent session ${parentSessionId} not found under ${projectDir}`)
  const events = parent!.events
  const calls = events.filter(event => event.type === 'tool/call')
  const byType = (type: string): LogEvent[] => events.filter(event => event.type === type)

  // ── identity chain: job → workflow call/meta name → runId → childId ──────
  const resultMap = new Map(events.filter(event => event.type === 'tool/result')
    .map(event => [resultView(event).toolCallId, event]))
  const paired = (call: LogEvent): LogEvent | undefined => resultMap.get((call.data as { callId: string }).callId)
  const starts = calls.filter(event => (event.data as { name: string }).name === 'workflow'
    && argumentsOf(event).run_in_background === true)
    .map(call => {
      const result = paired(call)
      const jobId = result === undefined ? undefined : /started background workflow job (\S+)/u.exec(resultView(result).text)?.[1]
      const metaName = (argumentsOf(call).meta as { name?: string } | undefined)?.name
      return { call, jobId, metaName }
    })
    .filter(start => start.jobId !== undefined && start.metaName !== undefined) as
    Array<{ call: LogEvent; jobId: string; metaName: string }>
  const killCall = calls.find(event => (event.data as { name: string }).name === 'job_kill'
    && starts.some(start => start.jobId === argumentsOf(event).job_id))
  check(killCall !== undefined, `a job_kill against one of the workflow jobIds exists`)
  const killJobId = argumentsOf(killCall!).job_id as string
  const killStart = starts.find(start => start.jobId === killJobId)
  check(killStart !== undefined, `the killed job's workflow start exists (job ${killJobId})`)
  const runStarts = byType('tool-workflow/run-start').filter(event => event.data.name === killStart!.metaName)
  check(runStarts.length === 1, `exactly one run-start matches the killed workflow's meta name (got ${runStarts.length})`)
  const runId = runStarts[0]!.data.runId as string
  const agentStarts = byType('tool-workflow/agent-start').filter(event => event.data.runId === runId)
  check(agentStarts.length === 1, `exactly one agent-start matches run ${runId} (got ${agentStarts.length})`)
  const childId = agentStarts[0]!.data.childId as string

  // ── parent-side terminal faces for the same runId ────────────────────────
  const agentEnds = byType('tool-workflow/agent-end').filter(event => event.data.runId === runId)
  check(agentEnds.length === 1 && agentEnds[0]!.data.outcome === 'cancelled',
    `agent-end for run ${runId} reports cancelled (got ${agentEnds.map(event => String(event.data.outcome)).join(',') || 'none'})`)
  const runEnds = byType('tool-workflow/run-end').filter(event => event.data.runId === runId)
  check(runEnds.length === 1 && runEnds[0]!.data.stopReason === 'cancelled',
    `run-end for run ${runId} reports cancelled (got ${runEnds.map(event => String(event.data.stopReason)).join(',') || 'none'})`)
  const killedRead = calls.find(event => (event.data as { name: string }).name === 'job_output'
    && event.seq > killCall!.seq && argumentsOf(event).job_id === killJobId)
  check(killedRead !== undefined, `a post-kill job_output read for job ${killJobId} exists`)
  const killedReadResult = paired(killedRead!)
  check(killedReadResult !== undefined && resultView(killedReadResult).text.includes('[status: killed'),
    `the post-kill read settled the job killed (got ${killedReadResult === undefined ? 'no result' : resultView(killedReadResult).text.slice(0, 160)})`)

  // ── ① the child's own interruption face (identity-bound by childId) ──────
  const child = logs.find(log => log.sessionId === childId)
  check(child !== undefined, `child session ${childId} not found under ${projectDir}`)
  const childTurnEnds = turnEnds(child!)
  check(childTurnEnds.length >= 1, `the child log carries at least one turn/end`)
  const childLastEnd = childTurnEnds.at(-1)!
  check(childLastEnd.kind === 'aborted', `the child's terminal turn/end is aborted (got ${childLastEnd.kind})`)
  check((childLastEnd.reason as { kind?: string } | undefined)?.kind === 'parent'
    || childLastEnd.reason === 'parent',
    `the child's abort cause is the parent cancellation (got ${JSON.stringify(childLastEnd.reason ?? null)})`)
  console.log(`① child ${childId} (run ${runId}, job ${killJobId}): turn/end aborted reason=parent at seq=${childLastEnd.seq}`)

  // ── ② three-way terminal consistency, all identity-bound ─────────────────
  check(!childTurnEnds.some(end => end.kind === 'completed'), `the child has no completed turn`)
  const orphanRunning = events.filter(event => event.type === 'tool/result' && event.seq > killedReadResult!.seq
    && resultView(event).text.includes(`${killJobId} [workflow] running`))
  check(orphanRunning.length === 0, `no parent read shows the killed job running after its terminal read`)
  console.log(`② consistency closed: job killed (read after seq=${killedRead!.seq}) ↔ agent-end cancelled (seq=${agentEnds[0]!.seq}) `
    + `↔ child turn/end aborted (seq=${childLastEnd.seq}); child has no completed turn`)

  // ── ③ resource face (log-provable range; process-level stated as unproven) ─
  const lastEvent = child!.events.at(-1)!
  check(lastEvent.seq === childTurnEnds.at(-1)!.seq && lastEvent.type === 'turn/end',
    `the child log ends at the aborted turn/end (no post-abort activity)`)
  const artifact = await stat(child!.path)
  check(artifact.isFile() && artifact.size > 0, `the child session artifact is persisted on disk (${child!.path})`)
  console.log(`③ resource face (log-provable range): child artifact ${Math.round(artifact.size / 1024 * 10) / 10}KB ends cleanly at the abort; `
    + `parent log shows no post-terminal running read. Boundary: process-level resource release (worker threads, `
    + `OS handles) is NOT provable from session logs — absent later events are not proof of reclamation.`)

  console.log('B6 CLEANUP CHECK: IDENTITY-BOUND CLEANUP PROVEN WITHIN THE LOG-PROVABLE RANGE')
}

main().then(() => { process.exitCode = 0 }, (error: unknown) => {
  console.error(error)
  process.exitCode = 1
})
