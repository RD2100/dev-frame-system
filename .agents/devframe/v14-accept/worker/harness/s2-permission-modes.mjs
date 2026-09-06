/**
 * S2 — permission preset / sandbox mode / approval policy really take effect
 * (design §2 S2).
 *
 * Mechanism A × 3 sub-runs differing only in `DSH_PERMISSION_MODE`
 * (`<unset>`, `read-only`, `danger-full-access`), each with its own isolated
 * `DSH_HOME` and its own cwd, running the same task string. Each sub-run's
 * real session log is parsed: the three initial events pinned at
 * `session/created` (`permission/preset`, `sandbox/mode`, `approval/policy`)
 * must each appear exactly once with the env-determined value.
 *
 * CLI: `node --import tsx/esm s2-permission-modes.mjs --tree <worktree> --out <dir>`
 * @module harness/s2-permission-modes
 */

import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { isolatedRoot, launchHeadless, parseCliArgs } from './helpers/launch.mjs'
import { findSessionLogs, readSessionLog } from './helpers/logread.mjs'
import {
  assembleVerdict,
  check,
  evidencePath,
  exitCodeForVerdict,
  recordHarnessError,
  writeJsonOut,
  writeTextOut,
  writeVerdict,
} from './helpers/evidence.mjs'

const USAGE = 'usage: node --import tsx/esm s2-permission-modes.mjs --tree <worktree> --out <dir>'
const TASK = 'reply with the single word ok'

/** The three sub-runs and their expected event values (design §2 S2). */
const SUBRUNS = [
  { id: 'unset', env: {}, expected: { preset: 'workspace-write', mode: 'workspace-write', policy: 'ask' } },
  { id: 'read-only', env: { DSH_PERMISSION_MODE: 'read-only' }, expected: { preset: 'read-only', mode: 'read-only', policy: 'ask' } },
  {
    id: 'danger-full-access',
    env: { DSH_PERMISSION_MODE: 'danger-full-access' },
    expected: { preset: 'danger-full-access', mode: 'danger-full-access', policy: 'never' },
  },
]

/**
 * The three initial permission events of one run's session log.
 * @param {object[]} events - parsed log events in order.
 * @returns {{preset: object[], mode: object[], policy: object[]}} the events
 *   of each type, in log order.
 */
function permissionEvents(events) {
  return {
    preset: events.filter(event => event.type === 'permission/preset'),
    mode: events.filter(event => event.type === 'sandbox/mode'),
    policy: events.filter(event => event.type === 'approval/policy'),
  }
}

/**
 * Run one sub-run and collect its checks and artifacts.
 * @param {string} tree - the launched worktree.
 * @param {string} outDir - the `--out` evidence directory.
 * @param {{id: string, env: object, expected: object}} subrun - sub-run spec.
 * @returns {Promise<object[]>} the sub-run's check records.
 */
async function runSubrun(tree, outDir, subrun) {
  const root = isolatedRoot(`s2-${subrun.id}`)
  const dshHome = join(root, 'dsh-home')
  const cwd = join(root, 'cwd')
  mkdirSync(cwd, { recursive: true })

  const runRecord = await launchHeadless({ tree, task: TASK, dshHome, cwd, timeoutMs: 120_000, env: subrun.env })
  const stderrPath = await writeTextOut(outDir, `s2/${subrun.id}/stderr.txt`, runRecord.stderr)
  const stdoutPath = await writeTextOut(outDir, `s2/${subrun.id}/stdout.txt`, runRecord.stdout)
  await writeTextOut(outDir, `s2/${subrun.id}/exitcode.txt`, `${String(runRecord.exitCode)}\n`)

  const logs = findSessionLogs(join(dshHome, 'sessions'))
  let events = []
  let logReadError = undefined
  if (logs.length === 1) {
    try {
      events = readSessionLog(logs[0].logPath).events
    } catch (error) {
      logReadError = error instanceof Error ? error.message : String(error)
    }
  }
  await writeJsonOut(outDir, `s2/${subrun.id}/launch.json`, {
    env: subrun.env,
    run: {
      exitCode: runRecord.exitCode,
      timedOut: runRecord.timedOut,
      durationMs: runRecord.durationMs,
      cwd: runRecord.cwd,
      dshHome: runRecord.dshHome,
      isolationEnv: runRecord.isolationEnv,
    },
    sessionLogs: logs.map(log => log.logPath),
    ...(logReadError !== undefined ? { logReadError } : {}),
  })

  if (logs.length !== 1 || logReadError !== undefined) {
    return [
      check({
        id: `s2-${subrun.id}-session-log`,
        expectation: 'the sub-run leaves exactly one readable session log',
        pass: false,
        observed: { sessionLogCount: logs.length, ...(logReadError !== undefined ? { logReadError } : {}) },
        evidence: evidencePath(outDir, stderrPath),
      }),
    ]
  }

  const found = permissionEvents(events)
  const eventsPath = await writeJsonOut(outDir, `s2/${subrun.id}/events.json`, {
    permissionPreset: found.preset,
    sandboxMode: found.mode,
    approvalPolicy: found.policy,
  })
  return [
    check({
      id: `s2-${subrun.id}-preset`,
      expectation: `permission/preset appears exactly once with value "${subrun.expected.preset}"`,
      pass: found.preset.length === 1 && found.preset[0]?.data?.preset === subrun.expected.preset,
      observed: found.preset.map(event => event.data),
      evidence: evidencePath(outDir, eventsPath),
    }),
    check({
      id: `s2-${subrun.id}-sandbox-mode`,
      expectation: `sandbox/mode appears exactly once with value "${subrun.expected.mode}"`,
      pass: found.mode.length === 1 && found.mode[0]?.data?.mode === subrun.expected.mode,
      observed: found.mode.map(event => event.data),
      evidence: evidencePath(outDir, eventsPath),
    }),
    check({
      id: `s2-${subrun.id}-approval-policy`,
      expectation: `approval/policy appears exactly once with value "${subrun.expected.policy}"`,
      pass: found.policy.length === 1 && found.policy[0]?.data?.policy === subrun.expected.policy,
      observed: found.policy.map(event => event.data),
      evidence: evidencePath(outDir, eventsPath),
    }),
  ]
}

/**
 * Run the S2 scenario (three sub-runs, sequential).
 * @param {string} tree - the launched worktree.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function run(tree, outDir) {
  const checks = []
  for (const subrun of SUBRUNS) {
    checks.push(...await runSubrun(tree, outDir, subrun))
  }
  const verdict = assembleVerdict({
    scenario: 's2-permission-modes',
    checks,
    notes: [
      '每次子运行各隔离 DSH_HOME + 独立 cwd，同一任务串；三事件由 session/created 钩子钉入，env → 事件值的真实因果即"真实生效"（findings §4）',
      '每次子运行的 stdout.txt / exitcode.txt 为附加证据（design 产物行之外）',
    ],
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(process.argv.slice(2), { tree: { required: true }, out: { required: true } }, USAGE)
process.exit(await run(parsed.tree, parsed.out).catch(error => recordHarnessError(parsed.out, 's2-permission-modes', error)))
