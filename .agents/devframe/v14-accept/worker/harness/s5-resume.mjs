/**
 * S5 — restart/resume: the same session log loaded cold in a second process
 * (design §2 S5).
 *
 * Mechanism B, two processes over one shared isolated root. `--phase write`
 * boots the /goal-capable composition, creates one real agent
 * (`ctx.agentLoop.create`, provider `mock`), dispatches `/goal <objective>`,
 * flushes, and exits 0, recording the durable facts (id, cwd, event count,
 * last seq, objective). `--phase resume` boots the same composition in a new
 * process, resumes through `ctx.agents.resume({resumeSessionId})` (the
 * AgentLoop factory's JSONL cold load), asserts id/cwd/event-count equality
 * and the goal projection (active + objective equal), then dispatches
 * `/goal pause` and asserts the appended events continue seq-monotonically.
 *
 * CLI: `node --import tsx/esm s5-resume.mjs --tree <worktree> --out <dir> --phase write|resume --root <sharedRoot> --session <id>`
 * @module harness/s5-resume
 */

import { mkdirSync, realpathSync } from 'node:fs'
import { join } from 'node:path'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { SessionId } from '@deepseek-ai/dsh-session'
import * as commandGoal from '@deepseek-ai/dsh-command-goal'
import { bootComposition, parseCliArgs } from './lib/launch.mjs'
import { registerMockAdapter } from './lib/mock-adapter.mjs'
import {
  assembleVerdict,
  check,
  exitCodeForVerdict,
  readJsonIfExists,
  recordHarnessError,
  writeJsonOut,
  writeVerdict,
} from './lib/evidence.mjs'

const USAGE
  = 'usage: node --import tsx/esm s5-resume.mjs --tree <worktree> --out <dir> --phase write|resume --root <sharedRoot> --session <id>'
const OBJECTIVE = 'Accept the v14 resume composition across two processes'

/**
 * Boot the /goal-capable composition over the shared root (both phases use
 * the identical plugin sequence).
 * @param {string} root - shared isolated root.
 * @returns {Promise<import('@deepseek-ai/cordis').Context>} the composition.
 */
async function bootGoalComposition(root) {
  const { ctx } = await bootComposition([
    [mountAgentLoopTestDependencies, {}],
    [SessionProjectionRegistry],
    [AgentLoop, { agents: [] }],
    [JsonlSessionPersistence, { root: join(root, 'session-logs') }],
    [CommandRuntime],
    [GoalService],
    [commandGoal],
  ], root)
  registerMockAdapter(ctx)
  return ctx
}

/**
 * Normalize a path for equality: realpath + lowercase on case-insensitive
 * platforms.
 * @param {string} path - the path to normalize.
 * @returns {string} the normalized absolute path.
 */
function normalizePath(path) {
  const real = realpathSync(path)
  return process.platform === 'win32' ? real.toLowerCase() : real
}

/**
 * Dispatch one command line through the real registry boundary.
 * @param {import('@deepseek-ai/cordis').Context} ctx - the composition.
 * @param {import('@deepseek-ai/dsh-agent').Agent} agent - the receiving agent.
 * @param {string} line - the slash-command line.
 * @returns {Promise<{commandId: string, kind: string, text: string|undefined}>}
 *   the settled result, verbatim.
 */
async function dispatch(ctx, agent, line) {
  const execution = await ctx.commands.execute(agent, line, [], new AbortController().signal)
  if (execution === undefined) throw new Error(`command "${line}" was not registered in the composition`)
  return { commandId: execution.commandId, kind: execution.result.kind, text: execution.result.text }
}

/**
 * Write phase: create the agent, set the goal, flush, exit 0.
 * @param {string} root - shared isolated root.
 * @param {string} outDir - the `--out` evidence directory.
 * @param {string} session - the shared session id.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function runWrite(root, outDir, session) {
  const worktree = join(root, 'worktree')
  mkdirSync(worktree, { recursive: true })
  const ctx = await bootGoalComposition(root)
  const agent = ctx.agentLoop.create(SessionId(session), { provider: 'mock', model: 'mock' }, { cwd: worktree })
  const dispatched = await dispatch(ctx, agent, `/goal ${OBJECTIVE}`)
  const events = agent.session.snapshotEvents()
  const facts = {
    sessionId: agent.session.header.id,
    cwd: agent.session.header.cwd,
    eventCount: events.length,
    lastSeq: events[events.length - 1]?.seq ?? null,
    objective: ctx.goals.get(agent)?.objective ?? null,
    goalPhase: ctx.goals.get(agent)?.phase ?? null,
  }
  await ctx.sessions.flush(agent.session)
  await ctx.fiber.dispose()

  const verdict = assembleVerdict({
    scenario: 's5-resume (write phase)',
    checks: [
      check({
        id: 's5-write-dispatch',
        expectation: '/goal <objective> dispatches successfully and the goal is active',
        pass: dispatched.kind === 'success' && facts.goalPhase === 'active' && facts.objective === OBJECTIVE,
        observed: { dispatch: dispatched, facts },
        evidence: 's5/write.json',
      }),
    ],
    notes: ['write 进程事实（id/cwd/事件数/lastSeq/objective）由 resume 进程核对 —— design §2 S5'],
  })
  // The verdict rides inside write.json so the resume phase can combine both.
  await writeJsonOut(outDir, 's5/write.json', {
    exitcode: 0,
    verdict: verdict.verdict,
    dispatch: dispatched,
    facts,
    events: events.map(event => ({ seq: event.seq, type: event.type })),
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

/**
 * Resume phase: cold-load the persisted session, verify restoration, then
 * continue the log seq-monotonically.
 * @param {string} root - shared isolated root.
 * @param {string} outDir - the `--out` evidence directory.
 * @param {string} session - the shared session id.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function runResume(root, outDir, session) {
  const write = await readJsonIfExists(join(outDir, 's5', 'write.json'))
  if (write === undefined) {
    const verdict = assembleVerdict({
      scenario: 's5-resume',
      checks: [],
      blocked: { reason: '缺少 write 阶段产物 s5/write.json：先运行 --phase write，再运行 --phase resume' },
    })
    await writeVerdict(outDir, verdict)
    return exitCodeForVerdict(verdict)
  }
  const writeFacts = write.facts
  const ctx = await bootGoalComposition(root)
  const handle = await ctx.agents.resume({
    resumeSessionId: SessionId(session),
    agentOptions: { provider: 'mock', model: 'mock' },
  })
  const agent = handle.agent
  const events = agent.session.snapshotEvents()
  const lastSeq = events[events.length - 1]?.seq ?? null
  const headerCwd = agent.session.header.cwd
  const goal = ctx.goals.get(agent)
  const continued = await dispatch(ctx, agent, '/goal pause')
  const afterEvents = agent.session.snapshotEvents()
  const newEvents = afterEvents.slice(events.length)
  const newSeqs = newEvents.map(event => event.seq)
  const seqMonotonic = newSeqs.length > 0
    && newSeqs.every(seq => seq > writeFacts.lastSeq)
    && newSeqs[0] === writeFacts.lastSeq + 1
    && newSeqs.every((seq, index) => index === 0 || seq > newSeqs[index - 1])
  await ctx.sessions.flush(agent.session)
  await handle.dispose()
  await ctx.fiber.dispose()

  await writeJsonOut(outDir, 's5/resume.json', {
    exitcode: 0,
    resumed: {
      sessionId: agent.session.header.id,
      cwd: headerCwd,
      eventCount: events.length,
      lastSeq,
      goalPhase: goal?.phase ?? null,
      objective: goal?.objective ?? null,
    },
    writeFacts,
    pauseDispatch: continued,
    newEvents: newEvents.map(event => ({ seq: event.seq, type: event.type })),
  })
  const verdict = assembleVerdict({
    scenario: 's5-resume',
    checks: [
      ...(write.verdict === 'PASS' ? [] : [{
        id: 's5-write-phase',
        expectation: 'the write phase reproduced its checks',
        pass: false,
        observed: { writeVerdict: write.verdict },
        evidence: 's5/write.json',
      }]),
      check({
        id: 's5-resume-identity',
        expectation: 'resumed session id, cwd, and event count equal the write process facts',
        pass: agent.session.header.id === session
          && normalizePath(headerCwd) === normalizePath(writeFacts.cwd)
          && events.length === writeFacts.eventCount,
        observed: {
          sessionId: agent.session.header.id,
          expectedSessionId: session,
          headerCwd,
          writeCwd: writeFacts.cwd,
          eventCount: events.length,
          writeEventCount: writeFacts.eventCount,
          lastSeq,
          writeLastSeq: writeFacts.lastSeq,
        },
        evidence: 's5/resume.json',
      }),
      check({
        id: 's5-resume-goal-projection',
        expectation: 'the goal projection restores as active with the write-time objective',
        pass: goal?.phase === 'active' && goal?.objective === writeFacts.objective,
        observed: { goalPhase: goal?.phase ?? null, objective: goal?.objective ?? null, writeObjective: writeFacts.objective },
        evidence: 's5/resume.json',
      }),
      check({
        id: 's5-resume-pause-and-seq',
        expectation: '/goal pause succeeds after cold load and every new event continues the log seq monotonically',
        pass: continued.kind === 'success' && seqMonotonic,
        observed: { pause: continued, newSeqs, seqMonotonic },
        evidence: 's5/resume.json',
      }),
    ],
    notes: [
      'ctx.agents.resume 传入与 write 相同的 agentOptions（provider/model 路由一致）—— 已登记偏差（design 文本仅列 resumeSessionId）',
      '生产 /devframe-resume 宿主入口未落地（findings §4 现状失败），本场景钉住的是 JSONL 冷加载面本身',
    ],
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(
  process.argv.slice(2),
  { tree: { required: true }, out: { required: true }, phase: { required: true }, root: { required: true }, session: { required: true } },
  USAGE,
)
const runner = parsed.phase === 'write'
  ? runWrite(parsed.root, parsed.out, parsed.session)
  : parsed.phase === 'resume'
    ? runResume(parsed.root, parsed.out, parsed.session)
    : Promise.reject(new Error(`--phase must be write|resume, got "${parsed.phase}". ${USAGE}`))
process.exit(await runner.catch(error => recordHarnessError(parsed.out, 's5-resume', error)))
