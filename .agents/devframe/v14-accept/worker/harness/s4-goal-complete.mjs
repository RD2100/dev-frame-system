/**
 * S4 — goal command flow + the real `/goal-complete` output, pinning the
 * no-verification stable error (design §2 S4).
 *
 * Mechanism B, single process: agent-loop testkit dependencies +
 * SessionProjectionRegistry + AgentLoop + JsonlSessionPersistence (isolated
 * root) + CommandRuntime + GoalService + the command-goal `/goal` family +
 * the command-goal-binding plugin (workspaceId `ws-v14-accept`,
 * workspaceRoot `<isolated root>/worktree`); one real agent via
 * `ctx.agentLoop.create` (provider `mock`); every command dispatched through
 * `ctx.commands.execute`. The stable refusal texts are imported from the
 * product src export surface (`packages/experimental/command-goal-binding/src`
 * `command.ts`) and compared verbatim — never a private copy.
 *
 * The goal-binding start lane (`startBinding`) is the composition's
 * test-visible entry (README-marked); the production host start surface is
 * not delivered (v14-compos in flight) and is annotated as such.
 *
 * CLI: `node --import tsx/esm s4-goal-complete.mjs --tree <worktree> --out <dir>`
 * @module harness/s4-goal-complete
 */

import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import CommandRuntime from '@deepseek-ai/dsh-commands'
import GoalService from '@deepseek-ai/dsh-goal'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { SessionId } from '@deepseek-ai/dsh-session'
import * as commandGoal from '@deepseek-ai/dsh-command-goal'
// Stable refusal texts: the product src export surface (no private copies).
import {
  NO_BINDING_TEXT,
  NO_CURRENT_GOAL_TEXT,
  NO_VERIFICATION_TEXT,
} from '../../../../../packages/experimental/command-goal-binding/src/command.ts'
// The plugin itself is not on the generated tsconfig paths; import its src directly.
import * as commandGoalBinding from '../../../../../packages/experimental/command-goal-binding/src/index.ts'
import { AcceptanceHash, DevFrameSnapshotId, SourceFingerprint } from '../../../../../packages/experimental/devframe/src/shared/types.ts'
import { TaskId } from '../../../../../packages/experimental/devframe/src/controller/goal-binding.ts'
import { bootComposition, isolatedRoot, parseCliArgs } from './helpers/launch.mjs'
import { findSessionLogs, readSessionLog } from './helpers/logread.mjs'
import { registerMockAdapter } from './helpers/mock-adapter.mjs'
import {
  assembleVerdict,
  check,
  evidencePath,
  exitCodeForVerdict,
  recordHarnessError,
  writeJsonOut,
  writeVerdict,
} from './helpers/evidence.mjs'

const USAGE = 'usage: node --import tsx/esm s4-goal-complete.mjs --tree <worktree> --out <dir>'
const SESSION_ID = 'accept-s4-goal-complete'
const OBJECTIVE = 'Accept the v14 goal-complete composition end to end'

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
 * The goal/change events of a session, in log order.
 * @param {import('@deepseek-ai/dsh-session').Session} session - live session.
 * @returns {object[]} the parsed `goal/change` event records.
 */
function goalChanges(session) {
  return session.snapshotEvents().filter(event => event.type === 'goal/change')
}

/**
 * Run the S4 scenario.
 * @param {string} _tree - the launched worktree (unused by mechanism B).
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function run(_tree, outDir) {
  const root = isolatedRoot('s4')
  const persistenceRoot = join(root, 'session-logs')
  const worktree = join(root, 'worktree')
  mkdirSync(worktree, { recursive: true })

  const { ctx } = await bootComposition([
    [mountAgentLoopTestDependencies, {}],
    [SessionProjectionRegistry],
    [AgentLoop, { agents: [] }],
    [JsonlSessionPersistence, { root: persistenceRoot }],
    [CommandRuntime],
    [GoalService],
    [commandGoal],
    [commandGoalBinding, { workspaceId: 'ws-v14-accept', workspaceRoot: worktree }],
  ], root)
  registerMockAdapter(ctx)
  const agent = ctx.agentLoop.create(SessionId(SESSION_ID), { provider: 'mock', model: 'mock' })
  const composition = Reflect.get(ctx, 'commandGoalBinding')

  // --- dispatches, in design §2 S4 order ---------------------------------
  const results = []
  const record = async (lane, line) => {
    const before = ctx.goals.get(agent)
    const dispatched = await dispatch(ctx, agent, line)
    const after = ctx.goals.get(agent)
    const entry = {
      lane,
      line,
      commandId: dispatched.commandId,
      kind: dispatched.kind,
      text: dispatched.text,
      goalPhaseBefore: before?.phase ?? null,
      goalPhaseAfter: after?.phase ?? null,
    }
    results.push(entry)
    return entry
  }

  // 1. /goal-complete with no goal → NO_CURRENT_GOAL_TEXT.
  const r1 = await record('command', '/goal-complete')
  // 2. /goal <objective> → success; goal/change pins the goal active.
  const r2 = await record('command', `/goal ${OBJECTIVE}`)
  const createEvents = goalChanges(agent.session).filter(event => event.data?.operation === 'create')
  // 3. pause → paused; resume → active (each with its own goal/change).
  const r3 = await record('command', '/goal pause')
  const pauseEvents = goalChanges(agent.session).filter(event => event.data?.operation === 'pause')
  const r4 = await record('command', '/goal resume')
  const resumeEvents = goalChanges(agent.session).filter(event => event.data?.operation === 'resume')
  // 4. /goal-complete with an unbound goal → NO_BINDING_TEXT.
  const r5 = await record('command', '/goal-complete')
  // The start lane requires no current non-complete goal; the design sequence
  // creates the goal in step 2, so an intermediate clear is required here.
  const rClearForStart = await record('command', '/goal clear')
  // 5. startBinding (composition start lane) succeeds, then /goal-complete →
  //    NO_VERIFICATION_TEXT (pinned).
  const binding = await composition.startBinding(agent, {
    objective: 'complete the bound work',
    taskIds: [TaskId('task-v14-accept')],
    acceptanceHash: AcceptanceHash('acceptance-v14-accept'),
    sourceFingerprint: SourceFingerprint('dsh-source-fp-v1-accept-pin'),
    snapshotId: DevFrameSnapshotId('snapshot-v14-accept'),
    budget: { maxAttempts: 3 },
    confirmationId: 'confirm-v14-accept',
  })
  results.push({
    lane: 'startBinding',
    line: 'composition.startBinding(agent, {...})',
    goalId: binding.goalId,
    goalRevision: binding.goalRevision,
    lifecycle: binding.lifecycle,
    workspaceId: binding.workspaceId,
  })
  const r6 = await record('command', '/goal-complete')
  // 7. /goal clear → cleared.
  const r7 = await record('command', '/goal clear')
  const clearEvents = goalChanges(agent.session).filter(event => event.data?.operation === 'clear')

  // 6. command/run + command/done pairing, and phase unchanged after refusals.
  const sessionEvents = agent.session.snapshotEvents()
  const pairing = results
    .filter(entry => entry.lane === 'command')
    .map((entry) => {
      const runs = sessionEvents.filter(event => event.type === 'command/run' && event.data.commandId === entry.commandId)
      const dones = sessionEvents.filter(event => event.type === 'command/done' && event.data.commandId === entry.commandId)
      return { commandId: entry.commandId, line: entry.line, runCount: runs.length, doneCount: dones.length, doneKinds: dones.map(event => event.data.kind) }
    })
  const refusalPhaseStable = r1.goalPhaseBefore === null && r1.goalPhaseAfter === null
    && r5.goalPhaseBefore === 'active' && r5.goalPhaseAfter === 'active'
    && r6.goalPhaseBefore === 'active' && r6.goalPhaseAfter === 'active'

  // Flush so the persisted log carries every event, then dispose.
  await ctx.sessions.flush(agent.session)
  await ctx.fiber.dispose()

  // Real persisted log as the durable evidence surface.
  const logs = findSessionLogs(persistenceRoot)
  let logEvents = []
  let logReadError = undefined
  if (logs.length === 1) {
    try {
      logEvents = readSessionLog(logs[0].logPath).events
    } catch (error) {
      logReadError = error instanceof Error ? error.message : String(error)
    }
  }
  const resultsPath = await writeJsonOut(outDir, 's4/command-results.json', { dispatches: results, pairing })
  const logEventsPath = await writeJsonOut(outDir, 's4/log-events.json', {
    sessionLogs: logs.map(log => log.logPath),
    ...(logReadError !== undefined ? { logReadError } : {}),
    events: logEvents,
  })

  const persistedPairing = pairing.map((entry) => ({
    commandId: entry.commandId,
    runCount: logEvents.filter(event => event.type === 'command/run' && event.data.commandId === entry.commandId).length,
    doneCount: logEvents.filter(event => event.type === 'command/done' && event.data.commandId === entry.commandId).length,
  }))
  const hasActiveCreate = logEvents.some(event =>
    event.type === 'goal/change' && event.data?.operation === 'create' && event.data?.goal?.phase === 'active')

  const checks = [
    check({
      id: 's4-1-no-current-goal-text',
      expectation: `/goal-complete with no goal answers the error text NO_CURRENT_GOAL_TEXT verbatim`,
      pass: r1.kind === 'error' && r1.text === NO_CURRENT_GOAL_TEXT,
      observed: { kind: r1.kind, text: r1.text, expectedText: NO_CURRENT_GOAL_TEXT },
      evidence: evidencePath(outDir, resultsPath),
    }),
    check({
      id: 's4-2-goal-create-active',
      expectation: '/goal <objective> succeeds and the log holds a goal/change with phase active',
      pass: r2.kind === 'success' && createEvents.length === 1 && createEvents[0]?.data?.goal?.phase === 'active' && hasActiveCreate,
      observed: { kind: r2.kind, createEvents: createEvents.map(event => event.data), persistedHasActiveCreate: hasActiveCreate },
      evidence: evidencePath(outDir, logEventsPath),
    }),
    check({
      id: 's4-3-pause-resume',
      expectation: '/goal pause → paused and /goal resume → active, each with its own goal/change',
      pass: r3.kind === 'success' && r3.goalPhaseAfter === 'paused' && pauseEvents.length === 1
        && pauseEvents[0]?.data?.goal?.phase === 'paused'
        && r4.kind === 'success' && r4.goalPhaseAfter === 'active' && resumeEvents.length === 1
        && resumeEvents[0]?.data?.goal?.phase === 'active',
      observed: {
        pause: { kind: r3.kind, phase: r3.goalPhaseAfter, events: pauseEvents.map(event => event.data) },
        resume: { kind: r4.kind, phase: r4.goalPhaseAfter, events: resumeEvents.map(event => event.data) },
      },
      evidence: evidencePath(outDir, resultsPath),
    }),
    check({
      id: 's4-4-no-binding-text',
      expectation: '/goal-complete with an unbound goal answers the error text NO_BINDING_TEXT verbatim',
      pass: r5.kind === 'error' && r5.text === NO_BINDING_TEXT,
      observed: { kind: r5.kind, text: r5.text, expectedText: NO_BINDING_TEXT },
      evidence: evidencePath(outDir, resultsPath),
    }),
    check({
      id: 's4-5-no-verification-text-pinned',
      expectation: 'after startBinding succeeds, /goal-complete answers the error text NO_VERIFICATION_TEXT verbatim (pinned: production composition has no producer wiring; v14-compos in flight)',
      pass: rClearForStart.kind === 'success' && binding !== undefined && r6.kind === 'error' && r6.text === NO_VERIFICATION_TEXT,
      observed: {
        intermediateClear: { kind: rClearForStart.kind, text: rClearForStart.text },
        startBinding: { goalId: binding?.goalId, goalRevision: binding?.goalRevision, lifecycle: binding?.lifecycle },
        kind: r6.kind,
        text: r6.text,
        expectedText: NO_VERIFICATION_TEXT,
      },
      evidence: evidencePath(outDir, resultsPath),
    }),
    check({
      id: 's4-6-command-pairing-and-phase-stability',
      expectation: 'every dispatch logs a paired command/run + command/done (live and persisted), and goal phase is unchanged after each refusal',
      pass: pairing.every(entry => entry.runCount === 1 && entry.doneCount === 1)
        && persistedPairing.every(entry => entry.runCount === 1 && entry.doneCount === 1)
        && refusalPhaseStable,
      observed: { pairing, persistedPairing, refusalPhaseStable },
      evidence: evidencePath(outDir, logEventsPath),
    }),
    check({
      id: 's4-7-goal-clear',
      expectation: '/goal clear succeeds and the log holds a goal/change clear tombstone',
      pass: r7.kind === 'success' && r7.text === 'Goal cleared.' && clearEvents.length >= 1 && clearEvents[clearEvents.length - 1]?.data?.cleared !== undefined,
      observed: {
        kind: r7.kind,
        text: r7.text,
        clearEvents: clearEvents.map(event => ({ cleared: event.data?.cleared, clearedAt: event.data?.clearedAt })),
      },
      evidence: evidencePath(outDir, resultsPath),
    }),
  ]

  const verdict = assembleVerdict({
    scenario: 's4-goal-complete',
    checks,
    notes: [
      'startBinding 为组合 test-visible start lane（README 标注）；生产宿主 start 面未交付（v14-compos 在飞），如实标注',
      '稳定拒绝文本逐字导入自产品 src 导出面 packages/experimental/command-goal-binding/src/command.ts，无比对副本',
      '检查 5 前插入一次 /goal clear（中间步）：start lane 要求当前无未完成 goal（GOAL_BINDING_ALREADY_RUNNING），design §2 S4 检查序未含此步 —— 已登记偏差',
      '完成链走通（admitted 路径）在本基线不可达，记为现状失败清单条目（非场景 FAIL）—— design §2 S4 判定',
    ],
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(process.argv.slice(2), { tree: { required: true }, out: { required: true } }, USAGE)
process.exit(await run(parsed.tree, parsed.out).catch(error => recordHarnessError(parsed.out, 's4-goal-complete', error)))
