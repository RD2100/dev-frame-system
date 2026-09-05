/**
 * L-Integration cold-recovery probe over the real integration composition:
 * boots the `integration` profile tree (dsh-base + the integration plugin
 * layer; the headless app surface is filtered out because the probe is not a
 * one-shot task run), drives the six experimental plugins, and — across two
 * separate process launches — proves durable domain rows cold-restore.
 *
 * Phase `write`: boot → createBoundSession → startProject/createTask/assign →
 * recordTaskGoalBinding → recordVerification → openAdmission/assertAdmitted →
 * memory tool registration + real read path + write-deny face → shadow
 * scope-isolation + caller fail-closed + domain file → print state →
 * persist probe-state.json → dispose (flush).
 * Phase `verify`: fresh boot → read the same rows back from the restored
 * domains → re-assert the memory and shadow faces → compare against
 * probe-state.json → print RESTORE OK or exit 1.
 *
 * Run from the p/integration work tree root with the isolated home:
 *   $env:DSH_HOME='C:\Users\25313\.dsh-integration'
 *   pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase write
 *   pnpm exec tsx .agents/devframe/integration/probe-cold-recovery.ts --phase verify
 *
 * @module probe-cold-recovery
 */

import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
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
import { dshHomePath } from '@deepseek-ai/dsh-home-paths'
import { PluginId, TaskId } from '@deepseek-ai/dsh-experimental-project-contracts'
import { NoteId, ProjectMemoryError } from '@deepseek-ai/dsh-experimental-project-memory'
import { SHADOW_TOOL_NAMES, ShadowRouterError } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { Context } from '@deepseek-ai/cordis'

const ARCHIVE = resolve(fileURLToPath(new URL('./cordis.patch.yml', import.meta.url)))
const STATE = resolve(fileURLToPath(new URL('./probe-state.json', import.meta.url)))
const NAME = 'dsh'
/** A well-formed but never-issued note id: read must answer `memory_missing`. */
const ABSENT_NOTE_ID = 'a'.repeat(64)
const MEMORY_TOOL_NAMES = ['memory_search', 'memory_read', 'memory_append'] as const
/** The probe-owned workspace root the shadow-router row authorizes; must exist at load. */
const SHADOW_ROOT = dshHomePath('integration-shadow-roots')

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

// The shadow-router row's authorizedRoots entries must exist at load
// (fail-closed validation fails the activation otherwise).
mkdirSync(SHADOW_ROOT, { recursive: true })

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

/**
 * The project-memory read-only face over the real mounted plugin: the three
 * tools are registered on the global registry, the search/read path touches
 * the probe Vault for real, and the append path is refused by consent.
 */
async function probeMemoryFace(): Promise<{
  toolsRegistered: boolean
  searchCoverageComplete: boolean
  readAbsent: boolean
  appendDenied: boolean
}> {
  const missing = MEMORY_TOOL_NAMES.filter(toolName => ctx.tools.get(toolName) === undefined)
  if (missing.length > 0) throw new Error(`memory tools not registered: ${missing.join(', ')}`)
  const vaultRoot = dshHomePath('integration-vault')
  mkdirSync(vaultRoot, { recursive: true })
  const search = await ctx.projectMemory.search({ scope: 'project', query: 'probe' })
  if (search.hits.length !== 0) {
    throw new Error(`unexpected memory search hits over the probe vault: ${JSON.stringify(search)}`)
  }
  const read = await ctx.projectMemory.read({ scope: 'project', noteId: NoteId(ABSENT_NOTE_ID) })
  const readAbsent = read.status === 'memory_missing'
  let appendDenied = false
  try {
    await ctx.projectMemory.append({
      scope: 'project',
      sourceRef: 'probe://write-deny',
      kind: 'fact',
      body: 'the read-only assembly must refuse this body',
      assertionStatus: 'observed',
    })
  } catch (error: unknown) {
    appendDenied = error instanceof ProjectMemoryError && error.code === 'MEMORY_APPEND_DISABLED'
  }
  return {
    toolsRegistered: true,
    searchCoverageComplete: search.coverageComplete,
    readAbsent,
    appendDenied,
  }
}

/**
 * The shadow-router read-only face over the real mounted service: the four
 * project tools stay out of the global registry (they install only into a
 * host-marked Shadow agent's scope) and every service call fails closed
 * against an unmarked caller. The `shadow_router` domain opens at init with
 * zero rows in this assembly — the storage backend publishes the medium file
 * on the first write-through, so its absence is the expected empty-domain
 * observation, not an assert.
 */
async function probeShadowFace(): Promise<{
  toolsScopeIsolated: boolean
  callerForbidden: boolean
  domainFileOnDisk: boolean
}> {
  const leaked = SHADOW_TOOL_NAMES.filter(toolName => ctx.tools.get(toolName) !== undefined)
  if (leaked.length > 0) {
    throw new Error(`shadow tools leaked into the global registry: ${leaked.join(', ')}`)
  }
  let callerForbidden = false
  try {
    await ctx.shadowRouter.openProject(undefined, { path: SHADOW_ROOT, requestId: 'probe-shadow-deny-1' })
  } catch (error: unknown) {
    callerForbidden = error instanceof ShadowRouterError && error.code === 'SHADOW_CALLER_FORBIDDEN'
  }
  if (!callerForbidden) {
    throw new Error('shadow openProject did not fail closed against an unmarked caller')
  }
  return {
    toolsScopeIsolated: true,
    callerForbidden,
    domainFileOnDisk: existsSync(join(process.env.DSH_HOME ?? '', 'storages', 'shadow_router.json')),
  }
}

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
    const memory = await probeMemoryFace()
    const shadow = await probeShadowFace()
    const state = {
      sessionId: session.id,
      bindingRole: record.role,
      lifecycleState: lifecycle,
      taskState: assigned.state,
      sessionLogExists: existsSync(join(process.env.DSH_HOME ?? '', 'sessions')),
      memoryToolsRegistered: memory.toolsRegistered,
      memorySearchCoverageComplete: memory.searchCoverageComplete,
      memoryReadAbsent: memory.readAbsent,
      memoryAppendDenied: memory.appendDenied,
      shadowToolsScopeIsolated: shadow.toolsScopeIsolated,
      shadowCallerForbidden: shadow.callerForbidden,
      shadowDomainFileOnDisk: shadow.domainFileOnDisk,
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
    const memory = await probeMemoryFace()
    if (!memory.toolsRegistered || !memory.readAbsent) {
      throw new Error(`memory face did not survive the cold boot: ${JSON.stringify(memory)}`)
    }
    const shadow = await probeShadowFace()
    if (!shadow.toolsScopeIsolated || !shadow.callerForbidden) {
      throw new Error(`shadow face did not survive the cold boot: ${JSON.stringify(shadow)}`)
    }    console.log('RESTORE OK', JSON.stringify({
      sessionId: state.sessionId,
      role: binding.role,
      taskState: tasks[0].state,
      bindings: evidence.bindings.length,
      verifications: evidence.verifications.length,
      memoryToolsRegistered: memory.toolsRegistered,
      memorySearchCoverageComplete: memory.searchCoverageComplete,
      memoryReadAbsent: memory.readAbsent,
      memoryAppendDenied: memory.appendDenied,
      shadowToolsScopeIsolated: shadow.toolsScopeIsolated,
      shadowCallerForbidden: shadow.callerForbidden,
      shadowDomainFileOnDisk: shadow.domainFileOnDisk,
    }))
  }
} finally {
  await ctx.fiber.dispose()
}
