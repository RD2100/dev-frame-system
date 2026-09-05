/**
 * L-Integration cold-recovery probe over the real integration composition:
 * boots the `integration` profile tree (dsh-base + the integration plugin
 * layer; the headless app surface is filtered out because the probe is not a
 * one-shot task run), drives the five experimental services, and — across two
 * separate process launches — proves durable domain rows cold-restore.
 *
 * Phase `write`: boot → createBoundSession → startProject/createTask/assign →
 * recordTaskGoalBinding → recordVerification → openAdmission/assertAdmitted →
 * print state → persist probe-state.json → dispose (flush).
 * Phase `verify`: fresh boot → read the same rows back from the restored
 * domains → compare against probe-state.json → print RESTORE OK or exit 1.
 *
 * Run from the p/integration work tree root with the isolated home:
 *   $env:DSH_HOME='C:\Users\25313\.dsh-integration'
 *   pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write
 *   pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase verify
 *
 * @module probe-cold-recovery
 */

import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  boot,
  DSH_PROFILE_IDENTITY_KEY,
  ensureProfileIdentity,
  healProfilesModuleFallback,
  loadLayeredEnv,
  loadOptionalPatches,
  loadOverlayPatches,
} from '@deepseek-ai/dsh-app-boot'
import { DSH_LAUNCH_ENVIRONMENT_KEY } from '@deepseek-ai/dsh-launch-environment'
import { provideCmdline } from '@deepseek-ai/dsh-cmdline'
import { INSTALL_ANCHOR, homePatchPath, prepareProfile } from '../../../apps/cli/src/profile-boot.ts'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { Context } from '@deepseek-ai/cordis'

const ARCHIVE = resolve(fileURLToPath(new URL('./cordis.patch.yml', import.meta.url)))
const STATE = resolve(fileURLToPath(new URL('./probe-state.json', import.meta.url)))
const NAME = 'dsh'

const phaseIndex = process.argv.indexOf('--phase')
const phase = phaseIndex >= 0 ? process.argv[phaseIndex + 1] : undefined
if (phase !== 'write' && phase !== 'verify') {
  console.error('probe: pass --phase write or --phase verify')
  process.exit(2)
}

const profile = prepareProfile('integration')
await healProfilesModuleFallback({ installAnchor: INSTALL_ANCHOR, profile })
const bundlePatches = profile.layers
  .filter(layer => layer.packageName === '@deepseek-ai/dsh-base')
  .flatMap(layer => layer.patches)
const homePatches = loadOptionalPatches(NAME, homePatchPath()) ?? []
const overlays = loadOverlayPatches(NAME, ARCHIVE)
const patches = structuredClone([...bundlePatches, ...profile.patches, ...homePatches, ...overlays])

const identity = await ensureProfileIdentity(NAME, 'integration')
const environment = loadLayeredEnv('dsh')

const ctx = await boot(NAME, join(profile.dir, 'cordis.yml'), patches, (hostCtx) => {
  hostCtx.provide(DSH_LAUNCH_ENVIRONMENT_KEY, environment)
  hostCtx.provide(DSH_PROFILE_IDENTITY_KEY, identity)
  provideCmdline(hostCtx, {
    args: [],
    exit: () => {},
    ready: { onReady: () => () => {} },
  })
})

const goalId = 'goal-probe-1' as GoalId

try {
  if (phase === 'write') {
    const workspace = mkdtempSync(join(tmpdir(), 'dsh-integration-probe-'))
    const { session, record } = await ctx.agentBindings.createBoundSession({
      cwd: workspace,
      role: 'controller',
    })
    const lifecycle = ctx.projectController.startProject()
    const task = await ctx.projectController.createTask({
      taskId: TaskId('task-probe-1'),
      pluginId: PluginId('integration-probe'),
      title: 'L-Integration cold-recovery probe task',
    })
    const assigned = await ctx.projectController.assign(TaskId('task-probe-1'), session.id)
    await ctx.agentEvidence.recordTaskGoalBinding({
      taskId: TaskId('task-probe-1'),
      controllerSessionId: session.id as never,
      goalId,
      goalRevision: 1,
      workspaceId: 'integration-probe',
      acceptanceHash: 'probe-acceptance',
      sourceFingerprint: 'probe-source',
    })
    await ctx.agentEvidence.recordVerification({
      taskId: TaskId('task-probe-1'),
      command: 'tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write',
      exitCode: 0,
      artifactPaths: [STATE],
    })
    ctx.agentReliability.openAdmission({ controllerSessionId: session.id as never, goalId })
    ctx.agentReliability.assertAdmitted({ controllerSessionId: session.id as never, goalId })
    const state = {
      sessionId: session.id,
      bindingRole: record.role,
      lifecycleState: lifecycle,
      taskState: assigned.state,
      sessionLogExists: existsSync(join(process.env.DSH_HOME ?? '', 'sessions')),
    }
    writeFileSync(STATE, JSON.stringify(state, undefined, 2) + '\n')
    console.log('WRITE PHASE OK', JSON.stringify(state))
  } else {
    const state = JSON.parse(readFileSync(STATE, 'utf8')) as {
      sessionId: string
      bindingRole: string
      lifecycleState: string
      taskState: string
    }
    const binding = ctx.agentBindings.find(state.sessionId as never)
    if (binding === undefined || binding.role !== state.bindingRole) {
      throw new Error(`binding for ${state.sessionId} did not cold-restore: ${JSON.stringify(binding)}`)
    }
    const tasks = ctx.projectController.list().filter(task => task.taskId === ('task-probe-1' as never))
    if (tasks.length !== 1 || tasks[0].state !== state.taskState) {
      throw new Error(`task task-probe-1 did not cold-restore: ${JSON.stringify(tasks)}`)
    }
    const evidence = ctx.agentEvidence.byTask('task-probe-1' as never)
    if (evidence.bindings.length !== 1 || evidence.verifications.length !== 1) {
      throw new Error(`evidence did not cold-restore: ${JSON.stringify(evidence)}`)
    }
    console.log('RESTORE OK', JSON.stringify({
      sessionId: state.sessionId,
      role: binding.role,
      taskState: tasks[0].state,
      bindings: evidence.bindings.length,
      verifications: evidence.verifications.length,
    }))
  }
} finally {
  await ctx.fiber.dispose()
}
