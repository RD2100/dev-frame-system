/**
 * B6 acceptance log check — read-only verifier over a real candidate run's
 * session log. Pairs with b6-acceptance-plan.md in this directory (v2).
 *
 * Evidence policy (V1.2 tightened):
 *  - (c) is proven ONLY by the parent's own intermediate job_list read whose
 *    paired result shows the SAME job still `running` — the mere existence of
 *    intermediate events is not continuation evidence.
 *  - (d) requires the kill job provably `running` in a job_list read BEFORE
 *    job_kill, plus cleanup proven by EXACT EVENT-IDENTITY JOIN (no markers,
 *    no time windows): job → workflow call's meta name → run-start runId →
 *    agent-start childId → the child session log; terminal faces agent-end
 *    `cancelled` ↔ run-end `cancelled` ↔ child `turn/end` aborted
 *    (reason parent); the completed child joins the same way as the positive
 *    control.
 * An honestly early-finishing child makes the run FAIL (rerun); assertions
 * are never loosened to pass.
 *
 * The parent session is selected by EXPLICIT identity (never "newest file" —
 * child logs routinely finish newest), and both physical encodings are read
 * through the repository's own decoder: `session.jsonl` and
 * `session.jsonl.zstd` (zstd frames via session-persistence-jsonl's format
 * helpers).
 *
 * Usage:
 *   node --import tsx/esm b6-acceptance-log-check.ts <DSH_HOME> <parentSessionId>
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

interface ToolResultView {
  toolCallId: string
  isError: boolean
  text: string
}

interface DecodedLog {
  path: string
  sessionId: string
  events: LogEvent[]
}

const fail = (message: string): never => { throw new Error(`B6 LOG CHECK FAILURE: ${message}`) }
const check = (ok: boolean, message: string): void => { if (!ok) fail(message) }

const resultView = (event: { data: unknown }): ToolResultView => {
  const message = (event.data as { message?: { content?: Array<{ type?: string; toolCallId?: string; content?: Array<{ type?: string; text?: string }>; isError?: boolean }> } }).message
  const block = message?.content?.find(candidate => candidate.type === 'tool-result')
  const text = (block?.content ?? []).map(inner => inner.type === 'text' ? inner.text ?? '' : '').join('')
  return { toolCallId: block?.toolCallId ?? '', isError: block?.isError === true, text }
}

const argumentsOf = (event: LogEvent): Record<string, unknown> => {
  try { return JSON.parse((event.data as { arguments: string }).arguments) as Record<string, unknown> } catch { return {} }
}

const turnEndsOf = (log: DecodedLog): Array<{ seq: number; kind: string }> =>
  log.events.filter(event => event.type === 'turn/end').map(event => ({
    seq: event.seq, kind: (event.data.reason as { kind?: string } | undefined)?.kind ?? 'unknown',
  }))

const runningInList = (text: string, jobId: string): boolean => text.includes(`${jobId} [workflow] running`)

async function collectArtifacts(home: string): Promise<string[]> {
  const found: string[] = []
  const walk = async (dir: string, depth: number): Promise<void> => {
    if (depth > 6) return
    let entries
    try { entries = await readdir(dir, { withFileTypes: true }) } catch { return }
    for (const entry of entries) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) await walk(path, depth + 1)
      else if (entry.name === 'session.jsonl' || entry.name === 'session.jsonl.zstd') found.push(path)
    }
  }
  await walk(home, 0)
  check(found.length > 0, `no session artifacts (session.jsonl / session.jsonl.zstd) found under ${home}`)
  const timed = await Promise.all(found.map(async path => ({ path, mtime: (await stat(path)).mtimeMs })))
  timed.sort((left, right) => right.mtime - left.mtime)
  return timed.map(entry => entry.path)
}

async function decodeLog(path: string): Promise<DecodedLog> {
  const buffer = await readFile(path)
  // A session artifact is a concatenated multi-frame zstd container;
  // decompressZstdPrefix only decodes the leading frames, so decode every
  // complete frame through the repository's frame decoder before scanning.
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

interface AssembledToolSchema {
  name?: string
  parameters?: { properties?: Record<string, { type?: string } | undefined> | undefined }
}

interface EpochHeaderView {
  config?: { provider?: string; model?: string }
  tools?: AssembledToolSchema[]
}

async function main(): Promise<void> {
  const home = process.argv[2] ?? process.env.DSH_HOME
  const parentSessionId = process.argv[3]
  check(typeof home === 'string' && home.length > 0, 'pass the candidate home as argv[2]')
  check(typeof parentSessionId === 'string' && parentSessionId.length > 0,
    'pass the parent session id explicitly as argv[3] (newest-file selection is forbidden: child logs routinely finish newest)')

  const artifacts = await collectArtifacts(home!)
  const decoded: DecodedLog[] = []
  const skipped: Array<{ path: string; reason: string }> = []
  for (const path of artifacts) {
    try {
      decoded.push(await decodeLog(path))
    } catch (error) {
      skipped.push({ path, reason: error instanceof Error ? error.message : String(error) })
    }
  }
  const root = decoded.find(log => log.sessionId === parentSessionId)
  check(root !== undefined,
    `no decoded session log matches parent session id ${parentSessionId}; found ids: `
      + `${decoded.map(log => `${log.sessionId} (${log.events.length} events)`).join(', ') || 'none'}`
      + `${skipped.length > 0 ? `; skipped ${skipped.length} unreadable artifact(s)` : ''}`)
  const events = root!.events
  check(events.length > 0, `the parent log ${root!.path} parsed to zero events`)
  const calls = events.filter(event => event.type === 'tool/call')
  const byName = (name: string): LogEvent[] => calls.filter(event => (event.data as { name: string }).name === name)
  // Pairing returns the result event and its parsed view separately: seq/time
  // stay on the event, isError/text live on the view.
  const resultFor = (call: LogEvent): { event: LogEvent; view: ToolResultView } | undefined => {
    const callId = (call.data as { callId: string }).callId
    const event = events.find(candidate => candidate.type === 'tool/result' && candidate.seq > call.seq
      && resultView(candidate).toolCallId === callId)
    return event === undefined ? undefined : { event, view: resultView(event) }
  }
  const listResults = byName('job_list').map(call => ({ call, paired: resultFor(call) }))
    .filter(pair => pair.paired !== undefined) as Array<{ call: LogEvent; paired: { event: LogEvent; view: ToolResultView } }>

  // ── (a) live service tool schemas + the actual provider route ────────────
  const header = events.filter(event => event.type === 'request/header').at(-1)
  check(header !== undefined, 'log carries a request/header event')
  const headerData = header!.data as { header?: EpochHeaderView }
  const tools: AssembledToolSchema[] = headerData.header?.tools ?? []
  const workflowTool = tools.find(tool => tool.name === 'workflow')
  check(workflowTool !== undefined, `assembled tool schemas include workflow (got ${tools.map(tool => tool.name).join(', ')})`)
  const runInBackground = workflowTool!.parameters?.properties?.run_in_background
  check(runInBackground !== undefined && runInBackground.type === 'boolean',
    `workflow.run_in_background is a top-level boolean (got ${runInBackground === undefined ? 'absent' : JSON.stringify(runInBackground)})`)
  for (const name of ['job_output', 'job_list', 'job_kill']) {
    check(tools.some(tool => tool.name === name), `assembled tool schemas include ${name}`)
  }
  const route = headerData.header?.config
  console.log(`[a] seq=${header!.seq}: live schemas carry workflow.run_in_background (boolean, top-level) + job tools; `
    + `actual route provider=${route?.provider ?? '?'} model=${route?.model ?? '?'} (must match the authorized huoshan entry)`)

  // ── (b) background workflow start returns a jobId immediately ────────────
  const workflowStarts = byName('workflow').filter(event => argumentsOf(event).run_in_background === true)
  check(workflowStarts.length >= 1, 'a workflow tool call with run_in_background: true exists')
  const firstStart = workflowStarts[0]!
  const firstResult = resultFor(firstStart)
  check(firstResult !== undefined && firstResult.view.isError === false, 'the background start has a successful paired tool/result')
  const jobIdMatch = /started background workflow job (\S+)/u.exec(firstResult!.view.text)
  check(jobIdMatch !== null, `start result carries the jobId receipt (got ${firstResult!.view.text.slice(0, 200)})`)
  const jobId = jobIdMatch![1]!
  console.log(`[b] seq=${firstStart.seq}->${firstResult!.event.seq}: run_in_background:true returned job ${jobId} at t=${firstResult!.event.time}`)

  // ── (c) HARD: the parent's own job_list read saw the same job running ────
  const collectCall = byName('job_output').find(event => event.seq > firstResult!.event.seq && argumentsOf(event).job_id === jobId)
  check(collectCall !== undefined, `a job_output call for job ${jobId} exists after the start`)
  const collectResult = resultFor(collectCall!)
  check(collectResult !== undefined && collectResult.view.text.includes('[status: completed]'),
    `collecting read reports completed (got ${collectResult === undefined ? 'no result' : collectResult.view.text.slice(0, 200)})`)
  check(collectResult!.view.text.includes('acceptance-child-line'), `job output carries the child result (got ${collectResult!.view.text.slice(0, 300)})`)
  const runningWitness = listResults.find(pair => pair.call.seq > firstStart.seq && pair.call.seq < collectCall!.seq
    && runningInList(pair.paired.view.text, jobId))
  check(runningWitness !== undefined,
    `a job_list read between start and collect shows job ${jobId} still running `
      + `(honest early completion must fail this run and be rerun; got ${listResults.map(pair => pair.paired.view.text.slice(0, 120)).join(' | ') || 'no job_list result'})`)
  const chain = [firstResult!.event, runningWitness!.call, runningWitness!.paired.event, collectCall!, collectResult!.event]
  check(chain.every((event, index) => index === 0 || event.time >= chain[index - 1]!.time), 'event times are monotonic across the protocol')
  console.log(`[c] continuation proven: job_list at seq=${runningWitness!.call.seq} (t=${runningWitness!.call.time}) saw job ${jobId} running; `
    + `collected completed at seq=${collectResult!.event.seq} (t=${collectResult!.event.time})`)

  // ── (d) cancellation of a provably-running job + cleanup on both children ─
  const killStart = workflowStarts[1]
  check(killStart !== undefined, 'a second background workflow call exists')
  const killStartResult = resultFor(killStart!)
  check(killStartResult !== undefined && killStartResult.view.isError === false, 'the second background start succeeds')
  const killJobMatch = /started background workflow job (\S+)/u.exec(killStartResult!.view.text)
  check(killJobMatch !== null, `second start result carries its jobId (got ${killStartResult!.view.text.slice(0, 200)})`)
  const killJobId = killJobMatch![1]!
  const killCall = byName('job_kill').find(event => argumentsOf(event).job_id === killJobId)
  check(killCall !== undefined, `a job_kill call for job ${killJobId} exists`)
  const killRunningWitness = listResults.find(pair => pair.call.seq > killStart!.seq && pair.call.seq < killCall!.seq
    && runningInList(pair.paired.view.text, killJobId))
  check(killRunningWitness !== undefined,
    `a job_list read BEFORE job_kill shows job ${killJobId} running (the cancellation must hit a really-running job)`)
  const killCallResult = resultFor(killCall!)
  check(killCallResult !== undefined && killCallResult.view.text.includes('requested cancellation of job '),
    `job_kill reports the cancellation receipt (got ${killCallResult === undefined ? 'no result' : killCallResult.view.text.slice(0, 200)})`)
  const killedRead = byName('job_output').find(event => event.seq > killCall!.seq && argumentsOf(event).job_id === killJobId)
  check(killedRead !== undefined, `a post-kill job_output read for job ${killJobId} exists`)
  const killedResult = resultFor(killedRead!)
  // The terminal line inlines the cancel reason after a comma
  // (`[status: killed, workflow run was cancelled (…)]`), so match the
  // status prefix; other statuses (`completed`, `running`) differ there.
  check(killedResult !== undefined && killedResult.view.text.includes('[status: killed'),
    `post-kill read reports killed (got ${killedResult === undefined ? 'no result' : killedResult.view.text.slice(0, 200)})`)
  console.log(`[d] job ${killJobId} was seen running (seq=${killRunningWitness!.call.seq}) before job_kill (seq=${killCall!.seq}) `
    + `and settled killed (read seq=${killedRead!.seq})`)

  // ── cleanup by exact event-identity join: job → runId → childId ──────────
  // No markers, no time windows: the parent log's own workflow events carry
  // the identity chain (meta name → run-start runId → agent-start childId),
  // and the terminal faces join across logs by those ids.
  const terminalKind = (event: LogEvent): string =>
    (event.data.reason as { kind?: string } | undefined)?.kind ?? 'unknown'
  const cancelCause = (event: LogEvent): unknown =>
    (event.data.reason as { reason?: unknown } | undefined)?.reason
  const joinChild = (metaName: string): { runId: string; childId: string } => {
    const runStarts = events.filter(event => event.type === 'tool-workflow/run-start' && event.data.name === metaName)
    check(runStarts.length === 1, `exactly one run-start matches the workflow meta name ${metaName} (got ${runStarts.length})`)
    const runId = runStarts[0]!.data.runId as string
    const agentStarts = events.filter(event => event.type === 'tool-workflow/agent-start' && event.data.runId === runId)
    check(agentStarts.length === 1, `exactly one agent-start matches run ${runId} (got ${agentStarts.length})`)
    return { runId, childId: agentStarts[0]!.data.childId as string }
  }
  const killMetaName = (argumentsOf(killStart!).meta as { name?: string } | undefined)?.name
  check(killMetaName !== undefined, `the killed workflow call carries a meta name`)
  const killedJoin = joinChild(killMetaName!)
  const killedAgentEnds = events.filter(event => event.type === 'tool-workflow/agent-end' && event.data.runId === killedJoin.runId)
  check(killedAgentEnds.length === 1 && killedAgentEnds[0]!.data.outcome === 'cancelled',
    `agent-end for run ${killedJoin.runId} reports cancelled (got ${killedAgentEnds.map(event => String(event.data.outcome)).join(',') || 'none'})`)
  const killedRunEnds = events.filter(event => event.type === 'tool-workflow/run-end' && event.data.runId === killedJoin.runId)
  check(killedRunEnds.length === 1 && killedRunEnds[0]!.data.stopReason === 'cancelled',
    `run-end for run ${killedJoin.runId} reports cancelled (got ${killedRunEnds.map(event => String(event.data.stopReason)).join(',') || 'none'})`)
  const killedChild = decoded.find(log => log.sessionId === killedJoin.childId)
  check(killedChild !== undefined, `the cancelled child session ${killedJoin.childId} exists`)
  const killedTurnEnds = killedChild!.events.filter(event => event.type === 'turn/end')
  const killedLastEnd = killedTurnEnds.at(-1)
  check(killedLastEnd !== undefined && terminalKind(killedLastEnd) === 'aborted',
    `the cancelled child's terminal turn/end is aborted (got ${killedLastEnd === undefined ? 'none' : terminalKind(killedLastEnd)})`)
  check((cancelCause(killedLastEnd!) as { kind?: string } | undefined)?.kind === 'parent',
    `the child's abort cause is the parent cancellation (got ${JSON.stringify(cancelCause(killedLastEnd!) ?? null)})`)
  check(!killedTurnEnds.some(event => terminalKind(event) === 'completed'), `the cancelled child has no completed turn`)
  check(killedChild!.events.at(-1)!.seq === killedLastEnd!.seq && killedLastEnd!.type === 'turn/end',
    `the child log ends at the abort (no post-abort activity)`)
  const killedArtifact = await stat(killedChild!.path)
  check(killedArtifact.isFile() && killedArtifact.size > 0, `the cancelled child's session artifact is persisted on disk`)
  const firstMetaName = (argumentsOf(firstStart!).meta as { name?: string } | undefined)?.name
  check(firstMetaName !== undefined, `the first workflow call carries a meta name`)
  const completedJoin = joinChild(firstMetaName!)
  const completedAgentEnds = events.filter(event => event.type === 'tool-workflow/agent-end' && event.data.runId === completedJoin.runId)
  check(completedAgentEnds.length === 1 && completedAgentEnds[0]!.data.outcome === 'completed',
    `agent-end for the first run reports completed (got ${completedAgentEnds.map(event => String(event.data.outcome)).join(',') || 'none'})`)
  const completedChild = decoded.find(log => log.sessionId === completedJoin.childId)
  check(completedChild !== undefined, `the completed child session ${completedJoin.childId} exists`)
  check(turnEndsOf(completedChild!).at(-1)?.kind === 'completed', `the completed child's terminal turn/end is completed`)
  check(completedChild!.events.some(event => event.type === 'assistant/message'
    && JSON.stringify(event.data).includes('acceptance-child-line')),
    `the completed child's own log carries its reply line (positive control)`)
  const orphanRunning = events.filter(event => event.type === 'tool/result' && event.seq > killedResult!.event.seq
    && resultView(event).text.includes(`${killJobId} [workflow] running`))
  check(orphanRunning.length === 0, `no parent read shows the killed job running after its terminal read`)
  console.log(`[d] cleanup (identity join job ${killJobId} → run ${killedJoin.runId} → child ${killedJoin.childId}): `
    + `agent-end/run-end cancelled, child turn/end aborted reason=parent, no completed turn, log ends at the abort; `
    + `positive control child ${completedJoin.childId} completed with its reply line`)
  console.log(`Boundary: process-level resource release (worker threads, OS handles) is NOT provable from session logs — `
    + `absent later events are not proof of reclamation.`)

  console.log('B6 LOG CHECK: ALL FOUR STEPS PROVEN FROM THE REAL SESSION LOG')
}

main().then(() => { process.exitCode = 0 }, (error: unknown) => {
  console.error(error)
  process.exitCode = 1
})
