/**
 * S6 — shadow routing across two real project roots (design §2 S6).
 *
 * Mechanism B: the full real shadow composition (agent-loop testkit +
 * SessionProjectionRegistry + AgentLoop + Storage + StorageJson + StorageDomain
 * + JsonlSessionPersistence + WorkspaceRegistry + session-identity
 * AgentBindingRegistry + ShadowRouter with `authorizedRoots` =
 * `<isolated root>/projects`), one real marked-Shadow agent created through
 * `ctx.agentLoop.create` (provider `mock`), and projects A/B as real
 * directories under the authorized root. Checks 1–5 are the required pass
 * set; check 6 (row-level cold restore in a second process over the same
 * root) is a bonus record — a failure there is recorded honestly but does not
 * fail the verdict (design §2 S6).
 *
 * The default run keeps the isolated root on disk; run `--phase cold --root
 * <the printed root>` afterwards to boot the fresh process over it.
 *
 * CLI: `node --import tsx/esm s6-shadow-routing.mjs --tree <worktree> --out <dir> [--phase cold --root <root>]`
 * @module harness/s6-shadow-routing
 */

import { mkdirSync, realpathSync } from 'node:fs'
import { join } from 'node:path'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { SessionId } from '@deepseek-ai/dsh-session'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import AgentBindingRegistry from '@deepseek-ai/dsh-experimental-session-identity'
import ShadowRouter, { ShadowRouterError } from '@deepseek-ai/dsh-experimental-shadow-router'
import { bootComposition, isolatedRoot, parseCliArgs } from './lib/launch.mjs'
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
  = 'usage: node --import tsx/esm s6-shadow-routing.mjs --tree <worktree> --out <dir> [--phase cold --root <root>]'

/**
 * Boot the real shadow composition over a root.
 * @param {string} root - storage/persistence root (warm: fresh; cold: reused).
 * @param {string} projectsRoot - the authorized-roots directory.
 * @returns {Promise<{ctx: import('@deepseek-ai/cordis').Context, router: import('@deepseek-ai/dsh-experimental-shadow-router').ShadowRouter}>}
 *   the booted composition and its router service.
 */
async function bootShadowComposition(root, projectsRoot) {
  const { ctx } = await bootComposition([
    [mountAgentLoopTestDependencies, {}],
    [SessionProjectionRegistry],
    [AgentLoop, { agents: [] }],
    [Storage],
    [StorageJson, { root }],
    [StorageDomain, { backend: 'json' }],
    [JsonlSessionPersistence, { root: join(root, 'session-logs') }],
    [WorkspaceRegistry],
    [AgentBindingRegistry],
    [ShadowRouter, { authorizedRoots: [projectsRoot] }],
  ], root)
  registerMockAdapter(ctx)
  return { ctx, router: ctx.shadowRouter }
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
 * Warm phase: provision two projects, route one delivery each, stop A, and
 * probe the request-conflict surface. The root stays on disk for `--phase cold`.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function runWarm(outDir) {
  const root = isolatedRoot('s6')
  const projectsRoot = join(root, 'projects')
  const dirA = join(projectsRoot, 'project-a')
  const dirB = join(projectsRoot, 'project-b')
  mkdirSync(dirA, { recursive: true })
  mkdirSync(dirB, { recursive: true })

  const { ctx, router } = await bootShadowComposition(root, projectsRoot)
  const shadow = ctx.agentLoop.create(SessionId('accept-s6-shadow'), { provider: 'mock', model: 'mock' })
  router.markShadow(shadow)

  const steps = []
  const record = (name, value) => {
    steps.push({ name, value })
    return value
  }
  const recordError = (name, error) => {
    steps.push({
      name,
      error: {
        message: error instanceof Error ? error.message : String(error),
        ...(error instanceof ShadowRouterError ? { code: error.code } : {}),
      },
    })
    return error
  }

  // 1. openProject A/B → ready, distinct identities, profile devframe, exact cwd.
  const openA = record('openProject A', await router.openProject(shadow, { path: dirA, requestId: 'accept-s6-open-a' }))
  const openB = record('openProject B', await router.openProject(shadow, { path: dirB, requestId: 'accept-s6-open-b' }))
  const bindingAAfterOpen = router.findBinding(openA.workspaceId)
  const bindingBAfterOpen = router.findBinding(openB.workspaceId)

  // 2/3. per-project active goals, then one delivery into each project.
  const goalA = record('setActiveGoal A', await router.setActiveGoal(openA.workspaceId, 'accept-s6-goal-a', 'accept-s6-hash-a'))
  const goalB = record('setActiveGoal B', await router.setActiveGoal(openB.workspaceId, 'accept-s6-goal-b', 'accept-s6-hash-b'))
  const sendA = record('sendToProject A', await router.sendToProject(shadow, {
    workspaceId: openA.workspaceId,
    bindingRevision: router.findBinding(openA.workspaceId).bindingRevision,
    goalId: 'accept-s6-goal-a',
    acceptanceHash: 'accept-s6-hash-a',
    requestId: 'accept-s6-send-a',
    mode: 'work',
    text: 'S6 acceptance delivery for project A',
  }))
  const sendB = record('sendToProject B', await router.sendToProject(shadow, {
    workspaceId: openB.workspaceId,
    bindingRevision: router.findBinding(openB.workspaceId).bindingRevision,
    goalId: 'accept-s6-goal-b',
    acceptanceHash: 'accept-s6-hash-b',
    requestId: 'accept-s6-send-b',
    mode: 'work',
    text: 'S6 acceptance delivery for project B',
  }))
  const deliveriesABeforeStop = router.listDeliveries(openA.workspaceId)
  const deliveriesBBeforeStop = router.listDeliveries(openB.workspaceId)

  // 4. stop A and confirm; B stays ready with its queue intact.
  const stopA = record('stopProject A', await router.stopProject(shadow, {
    workspaceId: openA.workspaceId,
    expectedRevision: router.findBinding(openA.workspaceId).bindingRevision,
    requestId: 'accept-s6-stop-a',
  }))
  const confirmedA = record('confirmProjectStopped A', await router.confirmProjectStopped(openA.workspaceId))
  const bindingAAfterStop = router.findBinding(openA.workspaceId)
  const bindingBAfterStop = router.findBinding(openB.workspaceId)
  const deliveriesAAfterStop = router.listDeliveries(openA.workspaceId)
  const deliveriesBAfterStop = router.listDeliveries(openB.workspaceId)

  // 5. same requestId replay with different input → SHADOW_REQUEST_CONFLICT.
  let conflictCode = undefined
  let conflictMessage = undefined
  try {
    await router.openProject(shadow, { path: dirB, requestId: 'accept-s6-open-a' })
  } catch (error) {
    if (error instanceof ShadowRouterError) {
      conflictCode = error.code
      conflictMessage = error.message
      recordError('openProject replay conflict', error)
    } else {
      throw error
    }
  }

  // Rows for the cold phase's field-by-field comparison.
  const coldSeed = {
    root,
    projectsRoot,
    bindings: {
      a: bindingAAfterStop === undefined ? undefined : { ...bindingAAfterStop },
      b: bindingBAfterStop === undefined ? undefined : { ...bindingBAfterStop },
    },
    deliveries: { a: deliveriesAAfterStop, b: deliveriesBAfterStop },
  }

  const checks = [
    check({
      id: 's6-1-open-two-projects',
      expectation: 'openProject A/B → ready, distinct workspaceId + controllerSessionId, profileKey devframe, canonical path equal to each project dir',
      pass: openA.state === 'ready' && openB.state === 'ready'
        && openA.workspaceId !== openB.workspaceId
        && openA.controllerSessionId !== openB.controllerSessionId
        && bindingAAfterOpen?.profileKey === 'devframe' && bindingBAfterOpen?.profileKey === 'devframe'
        && normalizePath(bindingAAfterOpen?.canonicalPath ?? '') === normalizePath(dirA)
        && normalizePath(bindingBAfterOpen?.canonicalPath ?? '') === normalizePath(dirB),
      observed: { openA, openB, bindingsAfterOpen: { a: bindingAAfterOpen, b: bindingBAfterOpen } },
      evidence: 's6/routing-log.json',
    }),
    check({
      id: 's6-2-delivery-received-and-isolated',
      expectation: 'sendToProject A → received and present in A deliveries only; B deliveries never contain A message',
      pass: sendA.status === 'received'
        && deliveriesABeforeStop.some(row => row.messageId === sendA.messageId && row.state === 'received')
        && !deliveriesBBeforeStop.some(row => row.messageId === sendA.messageId),
      observed: { sendA, sendB, deliveriesABeforeStop, deliveriesBBeforeStop },
      evidence: 's6/routing-log.json',
    }),
    check({
      id: 's6-3-active-goal-per-project',
      expectation: 'setActiveGoal A/B each take effect and neither overwrites the other',
      pass: goalA.activeGoalId === 'accept-s6-goal-a' && goalB.activeGoalId === 'accept-s6-goal-b'
        && goalA.activeGoalId !== goalB.activeGoalId,
      observed: { a: { activeGoalId: goalA.activeGoalId }, b: { activeGoalId: goalB.activeGoalId } },
      evidence: 's6/routing-log.json',
    }),
    check({
      id: 's6-4-stop-isolation',
      expectation: 'stopProject A → stopping, confirmProjectStopped A → stopped, while B stays ready with its queue unchanged',
      pass: stopA.status === 'stopping' && confirmedA.state === 'stopped'
        && bindingBAfterStop?.state === 'ready'
        && JSON.stringify(deliveriesBAfterStop) === JSON.stringify(deliveriesBBeforeStop),
      observed: {
        stopA,
        confirmedA: { workspaceId: confirmedA.workspaceId, state: confirmedA.state },
        bindingAAfterStop: { state: bindingAAfterStop?.state, bindingRevision: bindingAAfterStop?.bindingRevision },
        bindingBAfterStop: { state: bindingBAfterStop?.state },
        deliveriesUnchangedB: JSON.stringify(deliveriesBAfterStop) === JSON.stringify(deliveriesBBeforeStop),
      },
      evidence: 's6/routing-log.json',
    }),
    check({
      id: 's6-5-request-conflict',
      expectation: 'the same requestId replayed with different input fails loud with SHADOW_REQUEST_CONFLICT',
      pass: conflictCode === 'SHADOW_REQUEST_CONFLICT',
      observed: { conflictCode, conflictMessage },
      evidence: 's6/routing-log.json',
    }),
  ]

  const verdict = assembleVerdict({
    scenario: 's6-shadow-routing',
    checks,
    notes: [
      '冷恢复检查（design §2 S6 第 6 项）为加分记录：以 --phase cold --root <root> 复跑本脚本，root 已随本次运行保留',
      'markShadow 施加于真实 agent（ctx.agentLoop.create，provider mock）',
    ],
  })
  await writeJsonOut(outDir, 's6/routing-log.json', {
    root,
    steps,
    bindingsAfterOpen: { a: bindingAAfterOpen, b: bindingBAfterOpen },
    goalsSetActive: { a: { revision: goalA.bindingRevision, activeGoalId: goalA.activeGoalId }, b: { revision: goalB.bindingRevision, activeGoalId: goalB.activeGoalId } },
    stop: { stopA, confirmedA },
    checks,
    coldSeed,
  })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

/**
 * Cold phase (bonus): boot a fresh composition over the reused root and
 * assert row-level restore of the bindings and the received deliveries.
 * Failures here are recorded but do not fail the verdict (design §2 S6).
 * @param {string} root - the warm run's isolated root.
 * @param {string} outDir - the `--out` evidence directory.
 * @returns {Promise<number>} the process exit code (design contract).
 */
async function runCold(root, outDir) {
  const routingLog = await readJsonIfExists(join(outDir, 's6', 'routing-log.json'))
  if (routingLog === undefined) {
    const verdict = assembleVerdict({
      scenario: 's6-shadow-routing (cold)',
      checks: [],
      blocked: { reason: '缺少 warm 阶段产物 s6/routing-log.json：先运行默认（warm）阶段，再运行 --phase cold --root <其 root>' },
    })
    await writeVerdict(outDir, verdict)
    return exitCodeForVerdict(verdict)
  }
  const seed = routingLog.coldSeed
  const { ctx, router } = await bootShadowComposition(root, seed.projectsRoot)
  const bindingA = router.findBinding(seed.bindings.a.workspaceId)
  const bindingB = router.findBinding(seed.bindings.b.workspaceId)
  const deliveriesA = router.listDeliveries(seed.bindings.a.workspaceId)
  const deliveriesB = router.listDeliveries(seed.bindings.b.workspaceId)
  await ctx.fiber.dispose()

  const compareBinding = (expected, restored) => restored !== undefined && expected !== undefined && (
    restored.state === expected.state
    && restored.bindingRevision === expected.bindingRevision
    && restored.canonicalPath === expected.canonicalPath
    && restored.controllerSessionId === expected.controllerSessionId
    && restored.profileKey === expected.profileKey
    && restored.activeGoalId === expected.activeGoalId
  )
  const coldPath = await writeJsonOut(outDir, 's6/cold.json', {
    root,
    restored: {
      a: bindingA === undefined ? undefined : { ...bindingA },
      b: bindingB === undefined ? undefined : { ...bindingB },
      deliveries: { a: deliveriesA, b: deliveriesB },
    },
    expected: seed,
  })
  const bindingRestored = compareBinding(seed.bindings.a, bindingA) && compareBinding(seed.bindings.b, bindingB)
  const deliveriesRestored = JSON.stringify(deliveriesA) === JSON.stringify(seed.deliveries.a)
    && JSON.stringify(deliveriesB) === JSON.stringify(seed.deliveries.b)

  // Bonus record: check 6 never flips the verdict (design §2 S6).
  const verdict = assembleVerdict({
    scenario: 's6-shadow-routing (cold)',
    checks: routingLog.checks ?? [],
    notes: [
      `加分检查 6（行级冷恢复）${bindingRestored && deliveriesRestored ? '复现' : '未复现'}：绑定行级恢复 ${String(bindingRestored)}，投递行级恢复 ${String(deliveriesRestored)} —— 如实记录，失败不判 FAIL（design §2 S6）`,
      `warm 阶段 root: ${seed.root}`,
    ],
  })
  await writeJsonOut(outDir, 's6/verdict-copy-cold.json', { bonusCheck6: { bindingRestored, deliveriesRestored }, coldSeedFile: coldPath })
  await writeVerdict(outDir, verdict)
  return exitCodeForVerdict(verdict)
}

const parsed = parseCliArgs(
  process.argv.slice(2),
  { tree: { required: true }, out: { required: true }, phase: {}, root: {} },
  USAGE,
)
const runner = parsed.phase === undefined
  ? runWarm(parsed.out)
  : parsed.phase === 'cold'
    ? (parsed.root === undefined
        ? Promise.reject(new Error(`--phase cold requires --root. ${USAGE}`))
        : runCold(parsed.root, parsed.out))
    : Promise.reject(new Error(`--phase must be cold or omitted, got "${parsed.phase}". ${USAGE}`))
process.exit(await runner.catch(error => recordHarnessError(parsed.out, 's6-shadow-routing', error)))
