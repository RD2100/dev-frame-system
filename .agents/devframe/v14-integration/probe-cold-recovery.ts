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
 * scope-isolation + caller fail-closed + domain file → hierarchy guard allow
 * (controller read) and deny (lead plugin scope, unbound controlled) through
 * the real dispatcher → print state → persist probe-state.json → dispose
 * (flush).
 * Phase `verify`: fresh boot → read the same rows back from the restored
 * domains → re-assert the memory, shadow, and hierarchy faces → compare
 * against probe-state.json → print RESTORE OK or exit 1.
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
import { SHADOW_TOOL_NAMES, ShadowMessageId, ShadowRouterError } from '@deepseek-ai/dsh-experimental-shadow-router'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import { WorkspaceId } from '@deepseek-ai/dsh-workspace'
import type { GoalId } from '@deepseek-ai/dsh-goal/types'
import type { Context } from '@deepseek-ai/cordis'

const ARCHIVE = resolve(fileURLToPath(new URL('./cordis.patch.yml', import.meta.url)))
const STATE = resolve(fileURLToPath(new URL('./probe-state.json', import.meta.url)))
const NAME = 'dsh'
/** A well-formed but never-issued note id: read must answer `memory_missing`. */
const ABSENT_NOTE_ID = 'a'.repeat(64)
const MEMORY_TOOL_NAMES = ['memory_search', 'memory_read', 'memory_append'] as const
/** The stable source reference of the probe's real append; the verify phase retries the same reference. */
const PROBE_MEMORY_SOURCE_REF = 'probe://integration-local-write/1'
/** The body of the probe's real append; both phases share the exact bytes. */
const PROBE_MEMORY_BODY = 'L-Integration local write-enabled instance: the append path must create this note.'
/** A lowercase substring of the probe body, used as the search query in both phases. */
const PROBE_MEMORY_QUERY = 'write-enabled instance'
/** The appending agent's session id; the verify phase resumes it to replay the receipt log. */
const PROBE_MEMORY_WRITER_SESSION = 'session-memory-write-w'
/** The probe-owned workspace root the shadow-router row authorizes; must exist at load. */
const SHADOW_ROOT = dshHomePath('integration-shadow-roots')
/** Execution signal for the probe's real tool executions; the probe never aborts them. */
const probeSignal = new AbortController().signal
let hierarchyProbeCounter = 0

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => {
    setTimeout(resolve, ms)
  })
}

const phaseIndex = process.argv.indexOf('--phase')
const phase = phaseIndex >= 0 ? process.argv[phaseIndex + 1] : undefined
if (phase !== 'write' && phase !== 'verify') {
  console.error('probe: pass --phase write or --phase verify')
  process.exit(2)
}

const profile = prepareProfile('integration')
await healProfilesModuleFallback({ installAnchor: INSTALL_ANCHOR, profile })
// Base bundle layers only: the probe is not a one-shot task run, so the
// headless app surface (which pends on `headlessStartup` without a task)
// stays out. The base tree's tool-worktree row hard-injects
// workspaceRegistry/worktreeRegistry, and the headless bundle — which
// normally provides them (p/bundlefix) — is absent here, so the probe
// carries the two provider rows itself, after the archive.
const bundlePatches = profile.layers
  .filter(layer => layer.packageName === '@deepseek-ai/dsh-base')
  .flatMap(layer => layer.patches)
const homePatches = loadOptionalPatches(NAME, homePatchPath()) ?? []
const overlays = loadOverlayPatches(NAME, ARCHIVE)
// The probe-stack replacement for the headless bundle's provider rows
// (p/bundlefix): same ids and names, scoped to this base-only composition.
const probeProviderEntries = [
  {
    insert: [
      { id: 'workspace', name: '@deepseek-ai/dsh-workspace' },
      { id: 'worktree-registry', name: '@deepseek-ai/dsh-worktree-registry' },
    ],
  },
]
const patches = structuredClone([...bundlePatches, ...profile.patches, ...homePatches, ...overlays, ...probeProviderEntries])

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

/** The write-phase memory facts one phase hands to the next. */
interface ProbeMemoryState {
  readonly noteId: string
  readonly relativePath: string
  readonly sourceRef: string
  readonly appendingSessionId: string
}

/**
 * The project-memory face over the real mounted plugin in the write phase:
 * the three tools are registered on the global registry, the fresh probe
 * Vault answers an empty search and a `memory_missing` read, and the real
 * write path — `memory_append` through the real dispatcher as a
 * controller-bound agent, admitted by the role allow table and the enabled
 * local instance — creates the note file under the isolated Vault root with
 * its receipt in the calling session's log. The lead and worker roles resolve
 * their allowed memory tools through the same dispatcher, and user scope
 * stays fail-closed.
 */
async function probeMemoryWriteFace(): Promise<ProbeMemoryState & {
  toolsRegistered: boolean
  searchEmpty: boolean
  readAbsent: boolean
  appendCreated: boolean
  noteFileOnDisk: boolean
  controllerReadVerified: boolean
  controllerSearchHits: boolean
  leadReadAllowed: boolean
  workerSearchAllowed: boolean
  userScopeForbidden: boolean
}> {
  const missing = MEMORY_TOOL_NAMES.filter(toolName => ctx.tools.get(toolName) === undefined)
  if (missing.length > 0) throw new Error(`memory tools not registered: ${missing.join(', ')}`)
  const vaultRoot = dshHomePath('integration-vault')
  mkdirSync(vaultRoot, { recursive: true })
  const search = await ctx.projectMemory.search({ scope: 'project', query: PROBE_MEMORY_QUERY })
  if (search.hits.length !== 0) {
    throw new Error(`unexpected memory search hits over the fresh probe vault: ${JSON.stringify(search)}`)
  }
  const read = await ctx.projectMemory.read({ scope: 'project', noteId: NoteId(ABSENT_NOTE_ID) })
  const readAbsent = read.status === 'memory_missing'

  const writer = (await ctx.agents.create({ sessionId: SessionId(PROBE_MEMORY_WRITER_SESSION) })).agent
  await ctx.agentBindings.bind({ agentId: writer.id, role: 'controller' })
  const appended = await executeAsAgent(writer, 'memory_append', {
    scope: 'project',
    source_ref: PROBE_MEMORY_SOURCE_REF,
    kind: 'fact',
    body: PROBE_MEMORY_BODY,
  })
  if (appended.isError !== false || fieldValue(appended.value, 'status') !== 'created') {
    throw new Error(`memory_append through the real dispatcher did not create the note: ${JSON.stringify(appended)}`)
  }
  const noteId = textOf(fieldValue(appended.value, 'noteId'), 'append noteId')
  const relativePath = textOf(fieldValue(appended.value, 'relativePath'), 'append relativePath')
  if (!existsSync(join(vaultRoot, relativePath))) {
    throw new Error(`the created note file is not on disk under the vault root: ${join(vaultRoot, relativePath)}`)
  }
  const readBack = await executeAsAgent(writer, 'memory_read', { scope: 'project', note_id: noteId })
  if (readBack.isError !== false || fieldValue(readBack.value, 'status') !== 'found' || fieldValue(readBack.value, 'verified') !== true) {
    throw new Error(`memory_read did not verify the fresh note in-process: ${JSON.stringify(readBack.value)}`)
  }
  const searched = await executeAsAgent(writer, 'memory_search', { scope: 'project', query: PROBE_MEMORY_QUERY })
  const hitIds = Array.isArray(fieldValue(searched.value, 'hits'))
    ? (fieldValue(searched.value, 'hits') as unknown[]).map(hit => textOf(fieldValue(hit, 'noteId'), 'hit noteId'))
    : []
  if (searched.isError !== false || !hitIds.includes(noteId)) {
    throw new Error(`memory_search did not surface the fresh note: ${JSON.stringify(searched.value)}`)
  }

  const lead = (await ctx.agents.create({ sessionId: SessionId('session-memory-lead-w') })).agent
  await ctx.agentBindings.bind({ agentId: lead.id, role: 'lead' })
  const leadRead = await executeAsAgent(lead, 'memory_read', { scope: 'project', note_id: noteId })
  if (leadRead.isError !== false || fieldValue(leadRead.value, 'status') !== 'found') {
    throw new Error(`the lead role could not read through the real dispatcher: ${JSON.stringify(leadRead.value)}`)
  }
  const worker = (await ctx.agents.create({ sessionId: SessionId('session-memory-worker-w') })).agent
  await ctx.agentBindings.bind({ agentId: worker.id, role: 'worker' })
  const workerSearch = await executeAsAgent(worker, 'memory_search', { scope: 'project', query: PROBE_MEMORY_QUERY })
  if (workerSearch.isError !== false) {
    throw new Error(`the worker role could not search through the real dispatcher: ${JSON.stringify(workerSearch.value)}`)
  }

  let userScopeForbidden = false
  try {
    await ctx.projectMemory.append({
      scope: 'user',
      sourceRef: 'probe://user-scope-deny',
      kind: 'fact',
      body: 'user scope must stay disabled in the local instance',
      assertionStatus: 'observed',
    })
  } catch (error: unknown) {
    userScopeForbidden = error instanceof ProjectMemoryError && error.code === 'MEMORY_SCOPE_FORBIDDEN'
  }
  if (!userScopeForbidden) throw new Error('the user-scope append did not fail closed')
  if (!readAbsent) throw new Error('the absent-note read did not answer memory_missing')

  return {
    noteId,
    relativePath,
    sourceRef: PROBE_MEMORY_SOURCE_REF,
    appendingSessionId: PROBE_MEMORY_WRITER_SESSION,
    toolsRegistered: true,
    searchEmpty: true,
    readAbsent: true,
    appendCreated: true,
    noteFileOnDisk: true,
    controllerReadVerified: true,
    controllerSearchHits: true,
    leadReadAllowed: true,
    workerSearchAllowed: true,
    userScopeForbidden: true,
  }
}

/**
 * The project-memory face over the cold-restored composition: the note from
 * the write phase is read back from the Vault, the resumed appending session
 * replays its log and rehydrates the receipt (the `agent/created` hook is
 * fire-and-forget, so the rehydration is awaited on the observable outcome
 * instead of a clock), the re-read verifies the file against the replayed
 * receipt, a fresh controller agent resolves the tools through the real
 * dispatcher again, and the same-source retry reports already_exists. User
 * scope stays fail-closed.
 */
async function probeMemoryVerifyFace(recorded: ProbeMemoryState): Promise<{
  toolsRegistered: boolean
  coldReadFound: boolean
  receiptRehydrated: boolean
  dispatcherReadVerified: boolean
  searchHitRestored: boolean
  retryAlreadyExists: boolean
  readAbsent: boolean
  userScopeForbidden: boolean
}> {
  const missing = MEMORY_TOOL_NAMES.filter(toolName => ctx.tools.get(toolName) === undefined)
  if (missing.length > 0) throw new Error(`memory tools not registered: ${missing.join(', ')}`)
  const noteId = NoteId(recorded.noteId)
  const absent = await ctx.projectMemory.read({ scope: 'project', noteId: NoteId(ABSENT_NOTE_ID) })
  const readAbsent = absent.status === 'memory_missing'

  await ctx.agents.resume({ resumeSessionId: SessionId(recorded.appendingSessionId) })
  let cold = await ctx.projectMemory.read({ scope: 'project', noteId })
  let rehydrateAttempts = 0
  while (!(cold.status === 'found' && cold.verified === true) && rehydrateAttempts < 100) {
    await sleep(50)
    rehydrateAttempts += 1
    cold = await ctx.projectMemory.read({ scope: 'project', noteId })
  }
  if (cold.status !== 'found' || cold.verified !== true) {
    throw new Error(`the cold read did not re-verify against the replayed receipt: ${JSON.stringify(cold)}`)
  }

  const reader = (await ctx.agents.create({ sessionId: SessionId('session-memory-verify-v') })).agent
  await ctx.agentBindings.bind({ agentId: reader.id, role: 'controller' })
  const readBack = await executeAsAgent(reader, 'memory_read', { scope: 'project', note_id: recorded.noteId })
  if (readBack.isError !== false || fieldValue(readBack.value, 'status') !== 'found' || fieldValue(readBack.value, 'verified') !== true) {
    throw new Error(`memory_read through the real dispatcher did not survive the cold boot: ${JSON.stringify(readBack.value)}`)
  }

  const search = await ctx.projectMemory.search({ scope: 'project', query: PROBE_MEMORY_QUERY })
  if (search.hits.length !== 1 || search.hits[0]!.noteId !== recorded.noteId) {
    throw new Error(`the cold search did not surface exactly the written note: ${JSON.stringify(search)}`)
  }

  const retry = await ctx.projectMemory.append({
    scope: 'project',
    sourceRef: recorded.sourceRef,
    kind: 'fact',
    body: PROBE_MEMORY_BODY,
    assertionStatus: 'observed',
  })
  if (retry.status !== 'already_exists') {
    throw new Error(`the same-source cold retry did not report already_exists: ${JSON.stringify(retry)}`)
  }

  let userScopeForbidden = false
  try {
    await ctx.projectMemory.append({
      scope: 'user',
      sourceRef: 'probe://user-scope-deny-verify',
      kind: 'fact',
      body: 'user scope must stay disabled in the local instance',
      assertionStatus: 'observed',
    })
  } catch (error: unknown) {
    userScopeForbidden = error instanceof ProjectMemoryError && error.code === 'MEMORY_SCOPE_FORBIDDEN'
  }
  if (!userScopeForbidden) throw new Error('the user-scope append did not fail closed after the cold boot')
  if (!readAbsent) throw new Error('the absent-note read did not answer memory_missing after the cold boot')

  return {
    toolsRegistered: true,
    coldReadFound: true,
    receiptRehydrated: true,
    dispatcherReadVerified: true,
    searchHitRestored: true,
    retryAlreadyExists: true,
    readAbsent: true,
    userScopeForbidden: true,
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

/** The part of a canonical tool result the probe faces read. */
interface ProbeToolResult {
  readonly isError?: boolean
  readonly error?: { readonly message?: string }
  readonly value?: unknown
}

/** Read one key off a rendered JSON object value. */
function fieldValue(record: unknown, key: string): unknown {
  if (typeof record !== 'object' || record === null) {
    throw new Error(`expected a JSON object while reading "${key}": ${JSON.stringify(record)}`)
  }
  const value = (record as Record<string, unknown>)[key]
  if (value === undefined) throw new Error(`the rendered value carries no "${key}"`)
  return value
}

function textOf(value: unknown, label: string): string {
  if (typeof value !== 'string') throw new Error(`${label} is not a string: ${JSON.stringify(value)}`)
  return value
}

function numberOf(value: unknown, label: string): number {
  if (typeof value !== 'number') throw new Error(`${label} is not a number: ${JSON.stringify(value)}`)
  return value
}

/** Execute one real tool through the real dispatcher as a live agent. */
async function executeAsAgent(agent: Agent, name: string, args: Record<string, unknown>): Promise<ProbeToolResult> {
  hierarchyProbeCounter += 1
  return await ctx.tools.execute({
    callId: ToolCallId(`probe-tool-${hierarchyProbeCounter}`),
    name,
    arguments: args,
    agent,
    signal: probeSignal,
  })
}

/**
 * The agent-hierarchy read-only face over the real guard path: live agents
 * (real registry identities), real bindings, real `ctx.tools.execute`
 * dispatch. `subagent` is controlled (delegation seam) and resolvable for
 * every face agent, so each denial comes from the hierarchy guard itself and
 * the tool body never runs; the allow assertion runs the real `read` body.
 * The suffix separates write- and verify-phase identities so cold-restored
 * session records never collide.
 */
async function probeHierarchyFace(suffix: string): Promise<{
  controllerReadAllowed: boolean
  leadDelegationDenied: boolean
  unboundControlledDenied: boolean
}> {
  const controller = (await ctx.agents.create({ sessionId: SessionId(`session-hier-controller-${suffix}`) })).agent
  await ctx.agentBindings.bind({ agentId: controller.id, role: 'controller' })
  const allowed = await executeAsAgent(controller, 'read', { file_path: ARCHIVE })
  if (allowed.isError !== false) {
    throw new Error(`controller read through the real guard path did not succeed: ${JSON.stringify(allowed)}`)
  }

  const lead = (await ctx.agents.create({ sessionId: SessionId(`session-hier-lead-${suffix}`) })).agent
  await ctx.agentBindings.bind({ agentId: lead.id, role: 'lead' })
  const leadDenial = await executeAsAgent(lead, 'subagent', {})
  if (leadDenial.isError !== true || !/no plugin scope binding/.test(leadDenial.error?.message ?? '')) {
    throw new Error(`lead delegation was not denied by the plugin-scope face: ${JSON.stringify(leadDenial)}`)
  }

  const unbound = (await ctx.agents.create({ sessionId: SessionId(`session-hier-unbound-${suffix}`) })).agent
  const unboundDenial = await executeAsAgent(unbound, 'subagent', {})
  if (unboundDenial.isError !== true || !/no role binding/.test(unboundDenial.error?.message ?? '')) {
    throw new Error(`unbound controlled execution was not denied by the missing-role face: ${JSON.stringify(unboundDenial)}`)
  }

  return { controllerReadAllowed: true, leadDelegationDenied: true, unboundControlledDenied: true }
}

/**
 * The shadow-router composition face over a real agent session: the host
 * designates one live composition agent as its Shadow through the public
 * `markShadow` seam (the S6 in-package marking pattern, at composition
 * level), the four project tools become visible in that agent's scope while
 * an unmarked composition agent's scope stays clean, and the marked agent's
 * real binding row persists through the write-through binding registry.
 * Marking is a runtime host seam — cordis.yml carries no declarative
 * marking face — so the assembly is probe-driven by design, not fabricated
 * into the archive layer.
 */
async function probeShadowCompositionFace(suffix: string): Promise<{
  markedScopeSeesTools: boolean
  unmarkedScopeClean: boolean
  bindingRowPersisted: boolean
}> {
  const marked = (await ctx.agents.create({ sessionId: SessionId(`session-shadow-marked-${suffix}`) })).agent
  ctx.shadowRouter.markShadow(marked)
  if (!ctx.shadowRouter.isShadow(marked)) {
    throw new Error('the host-designated agent is not marked as Shadow')
  }
  for (const toolName of SHADOW_TOOL_NAMES) {
    if (ctx.tools.get(toolName, marked) === undefined) {
      throw new Error(`the marked scope does not resolve "${toolName}"`)
    }
  }
  if (!ctx.tools.schemas(marked).some(schema => schema.name === 'project_open')) {
    throw new Error('the marked scope enumeration does not list the project tools')
  }

  const unmarked = (await ctx.agents.create({ sessionId: SessionId(`session-shadow-unmarked-${suffix}`) })).agent
  for (const toolName of SHADOW_TOOL_NAMES) {
    if (ctx.tools.get(toolName, unmarked) !== undefined) {
      throw new Error(`the unmarked scope resolves "${toolName}"`)
    }
  }
  if (ctx.tools.schemas(unmarked).some(schema => SHADOW_TOOL_NAMES.includes(schema.name as never))) {
    throw new Error('the unmarked scope enumeration lists a project tool')
  }

  await ctx.agentBindings.bind({ agentId: marked.id, role: 'controller' })
  const persisted = ctx.agentBindings.find(marked.id)
  if (persisted === undefined || persisted.role !== 'controller') {
    throw new Error(`the marked agent's binding row did not persist: ${JSON.stringify(persisted)}`)
  }
  for (const toolName of SHADOW_TOOL_NAMES) {
    if (ctx.tools.get(toolName, marked) === undefined) {
      throw new Error(`the role restriction hid the scope-local "${toolName}"`)
    }
  }

  return {
    markedScopeSeesTools: true,
    unmarkedScopeClean: true,
    bindingRowPersisted: existsSync(join(process.env.DSH_HOME ?? '', 'storages', 'session_identity.json')),
  }
}

/** The recorded delivery-journey facts one phase hands to the next. */
interface ShadowDeliveryState {
  workspaceId: string
  controllerSessionId: string
  messageId: string
  receivedAt: string
  completedAt: string
  goalId: string
  acceptanceHash: string
}

function successValue(outcome: ProbeToolResult, label: string): unknown {
  if (outcome.isError !== false) throw new Error(`${label} failed: ${JSON.stringify(outcome)}`)
  return outcome.value
}

/**
 * The shadow-router delivery-journey face at composition level, closing the
 * S6 production gap: the marked Shadow agent drives project_open and
 * project_send through the real dispatcher (queued → received two-write
 * history), the host drives the settlement seam (completeDelivery →
 * completed) and the stop contrast (project_stop → stopping, then
 * confirmProjectStopped → stopped), and the cold phase re-reads every
 * durable field from the restored router. `recorded` switches the face into
 * its verify mode: no new rows, only field-by-field restoration checks plus
 * one model-face status read-back through a freshly marked agent.
 */
async function probeShadowDeliveryFace(suffix: string, recorded?: ShadowDeliveryState): Promise<ShadowDeliveryState> {
  const marked = (await ctx.agents.create({ sessionId: SessionId(`session-shadow-flow-${suffix}`) })).agent
  ctx.shadowRouter.markShadow(marked)

  if (recorded !== undefined) {
    const workspaceId = WorkspaceId(recorded.workspaceId)
    const binding = ctx.shadowRouter.findBinding(workspaceId)
    if (binding === undefined || binding.state !== 'stopped' || binding.activeGoalId !== recorded.goalId || binding.activeAcceptanceHash !== recorded.acceptanceHash) {
      throw new Error(`the shadow binding did not cold-restore field-by-field: ${JSON.stringify(binding)}`)
    }
    const row = ctx.shadowRouter.listDeliveries(workspaceId).find(candidate => candidate.messageId === ShadowMessageId(recorded.messageId))
    if (row === undefined || row.state !== 'completed' || row.receivedAt !== recorded.receivedAt || row.completedAt !== recorded.completedAt) {
      throw new Error(`the delivery row did not cold-restore field-by-field: ${JSON.stringify(row)}`)
    }
    if (ctx.agentBindings.find(SessionId(recorded.controllerSessionId))?.role !== 'controller') {
      throw new Error(`the project controller binding for "${recorded.controllerSessionId}" did not cold-restore`)
    }
    const status = await executeAsAgent(marked, 'project_status', { workspace_id: recorded.workspaceId })
    const projects = fieldValue(successValue(status, 'project_status'), 'projects')
    if (!Array.isArray(projects)) throw new Error('project_status rendered no projects array')
    const entry = projects.find(candidate => textOf(fieldValue(candidate, 'workspaceId'), 'status workspaceId') === recorded.workspaceId)
    if (entry === undefined) throw new Error('project_status did not render the recorded workspace')
    const deliveries = fieldValue(entry, 'deliveries')
    if (!Array.isArray(deliveries)) throw new Error('the rendered entry carries no deliveries array')
    const rendered = deliveries.find(candidate => textOf(fieldValue(candidate, 'messageId'), 'status messageId') === recorded.messageId)
    if (rendered === undefined || textOf(fieldValue(rendered, 'state'), 'status delivery state') !== 'completed') {
      throw new Error(`the rendered delivery did not read completed after the cold boot: ${JSON.stringify(rendered)}`)
    }
    return recorded
  }

  const projectDir = join(SHADOW_ROOT, `delivery-project-${suffix}`)
  mkdirSync(projectDir, { recursive: true })
  const opened = successValue(await executeAsAgent(marked, 'project_open', { path: projectDir, request_id: `probe-open-${suffix}-1` }), 'project_open')
  if (textOf(fieldValue(opened, 'state'), 'open state') !== 'ready') {
    throw new Error(`project_open did not report a ready association: ${JSON.stringify(opened)}`)
  }
  const workspaceIdText = textOf(fieldValue(opened, 'workspaceId'), 'workspaceId')
  const controllerSessionId = textOf(fieldValue(opened, 'controllerSessionId'), 'controllerSessionId')
  const workspaceId = WorkspaceId(workspaceIdText)
  const controller = ctx.sessions.get(SessionId(controllerSessionId))
  if (controller === undefined || controller.header.cwd !== textOf(fieldValue(opened, 'canonicalPath'), 'canonicalPath')) {
    throw new Error(`the opened controller session is not real/rooted: ${JSON.stringify(controller?.header)}`)
  }
  if (ctx.agentBindings.find(SessionId(controllerSessionId))?.role !== 'controller') {
    throw new Error(`the opened controller session "${controllerSessionId}" is not durably bound as controller`)
  }

  const goalId = `probe-goal-${suffix}`
  const acceptanceHash = `probe-hash-${suffix}`
  await ctx.shadowRouter.setActiveGoal(workspaceId, goalId, acceptanceHash)
  const authorized = ctx.shadowRouter.findBinding(workspaceId)
  if (authorized?.activeGoalId !== goalId || authorized?.activeAcceptanceHash !== acceptanceHash) {
    throw new Error(`the host goal authorization was not recorded: ${JSON.stringify(authorized)}`)
  }

  const sent = successValue(await executeAsAgent(marked, 'project_send', {
    workspace_id: workspaceIdText,
    // The open receipt's revision can already be stale (provisioning
    // convergence bumps it); the send must observe the current one.
    binding_revision: ctx.shadowRouter.findBinding(workspaceId)!.bindingRevision,
    goal_id: goalId,
    acceptance_hash: acceptanceHash,
    request_id: `probe-send-${suffix}-1`,
    mode: 'work',
    text: 'L-Integration composition delivery journey',
  }), 'project_send')
  if (textOf(fieldValue(sent, 'status'), 'send status') !== 'received') {
    throw new Error(`project_send did not report received: ${JSON.stringify(sent)}`)
  }
  const messageId = textOf(fieldValue(sent, 'messageId'), 'messageId')
  const deliveries = ctx.shadowRouter.listDeliveries(workspaceId)
  if (deliveries.length !== 1 || deliveries[0]!.state !== 'received' || deliveries[0]!.receivedAt === undefined || deliveries[0]!.completedAt !== undefined) {
    throw new Error(`the delivery row after the send is not a received two-write state: ${JSON.stringify(deliveries)}`)
  }
  const receivedAt = deliveries[0]!.receivedAt!

  const settled = await ctx.shadowRouter.completeDelivery(workspaceId, ShadowMessageId(messageId))
  if (settled.state !== 'completed' || settled.completedAt === undefined || settled.receivedAt !== receivedAt) {
    throw new Error(`the host settlement did not complete the delivery: ${JSON.stringify(settled)}`)
  }

  const stop = successValue(await executeAsAgent(marked, 'project_stop', {
    workspace_id: workspaceIdText,
    expected_revision: ctx.shadowRouter.findBinding(workspaceId)!.bindingRevision,
    request_id: `probe-stop-${suffix}-1`,
  }), 'project_stop')
  if (textOf(fieldValue(stop, 'status'), 'stop status') !== 'stopping') {
    throw new Error(`project_stop did not report stopping: ${JSON.stringify(stop)}`)
  }
  await ctx.shadowRouter.confirmProjectStopped(workspaceId)
  if (ctx.shadowRouter.findBinding(workspaceId)?.state !== 'stopped') {
    throw new Error('the host quiescence confirmation did not stop the binding')
  }
  return {
    workspaceId: workspaceIdText,
    controllerSessionId,
    messageId,
    receivedAt,
    completedAt: settled.completedAt!,
    goalId,
    acceptanceHash,
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
    const memory = await probeMemoryWriteFace()
    const shadow = await probeShadowFace()
    const hierarchy = await probeHierarchyFace('w')
    const shadowComposition = await probeShadowCompositionFace('w')
    const shadowDelivery = await probeShadowDeliveryFace('w')
    const state = {
      sessionId: session.id,
      bindingRole: record.role,
      lifecycleState: lifecycle,
      taskState: assigned.state,
      sessionLogExists: existsSync(join(process.env.DSH_HOME ?? '', 'sessions')),
      memoryWrite: {
        noteId: memory.noteId,
        relativePath: memory.relativePath,
        sourceRef: memory.sourceRef,
        appendingSessionId: memory.appendingSessionId,
        toolsRegistered: memory.toolsRegistered,
        searchEmpty: memory.searchEmpty,
        readAbsent: memory.readAbsent,
        appendCreated: memory.appendCreated,
        noteFileOnDisk: memory.noteFileOnDisk,
        controllerReadVerified: memory.controllerReadVerified,
        controllerSearchHits: memory.controllerSearchHits,
        leadReadAllowed: memory.leadReadAllowed,
        workerSearchAllowed: memory.workerSearchAllowed,
        userScopeForbidden: memory.userScopeForbidden,
      },
      shadowToolsScopeIsolated: shadow.toolsScopeIsolated,
      shadowCallerForbidden: shadow.callerForbidden,
      shadowDomainFileOnDisk: shadow.domainFileOnDisk,
      hierarchyControllerReadAllowed: hierarchy.controllerReadAllowed,
      hierarchyLeadDelegationDenied: hierarchy.leadDelegationDenied,
      hierarchyUnboundControlledDenied: hierarchy.unboundControlledDenied,
      shadowCompMarkedScopeSeesTools: shadowComposition.markedScopeSeesTools,
      shadowCompUnmarkedScopeClean: shadowComposition.unmarkedScopeClean,
      shadowCompBindingRowPersisted: shadowComposition.bindingRowPersisted,
      shadowDelivery: {
        workspaceId: shadowDelivery.workspaceId,
        controllerSessionId: shadowDelivery.controllerSessionId,
        messageId: shadowDelivery.messageId,
        receivedAt: shadowDelivery.receivedAt,
        completedAt: shadowDelivery.completedAt,
        goalId: shadowDelivery.goalId,
        acceptanceHash: shadowDelivery.acceptanceHash,
      },
    }
    writeFileSync(STATE, JSON.stringify(state, undefined, 2) + '\n')
    console.log('WRITE PHASE OK', JSON.stringify(state))
  } else {
    const state = JSON.parse(readFileSync(STATE, 'utf8')) as {
      sessionId: string
      bindingRole: string
      lifecycleState: string
      taskState: string
      memoryWrite?: ProbeMemoryState
      shadowDelivery?: ShadowDeliveryState
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
    if (state.memoryWrite === undefined) {
      throw new Error('probe-state.json carries no memoryWrite record from the write phase')
    }
    const memory = await probeMemoryVerifyFace(state.memoryWrite)
    const shadow = await probeShadowFace()
    if (!shadow.toolsScopeIsolated || !shadow.callerForbidden) {
      throw new Error(`shadow face did not survive the cold boot: ${JSON.stringify(shadow)}`)
    }
    for (const [agentId, expectedRole] of [
      ['session-hier-controller-w', 'controller'],
      ['session-hier-lead-w', 'lead'],
      ['session-shadow-marked-w', 'controller'],
    ] as const) {
      const restored = ctx.agentBindings.find(SessionId(agentId))
      if (restored === undefined || restored.role !== expectedRole) {
        throw new Error(`binding for "${agentId}" did not cold-restore: ${JSON.stringify(restored)}`)
      }
    }
    const hierarchy = await probeHierarchyFace('v')
    if (!hierarchy.controllerReadAllowed || !hierarchy.leadDelegationDenied || !hierarchy.unboundControlledDenied) {
      throw new Error(`hierarchy face did not survive the cold boot: ${JSON.stringify(hierarchy)}`)
    }
    const shadowComposition = await probeShadowCompositionFace('v')
    if (!shadowComposition.markedScopeSeesTools || !shadowComposition.unmarkedScopeClean) {
      throw new Error(`shadow composition face did not survive the cold boot: ${JSON.stringify(shadowComposition)}`)
    }
    if (state.shadowDelivery === undefined) {
      throw new Error('probe-state.json carries no shadowDelivery record from the write phase')
    }
    await probeShadowDeliveryFace('v', state.shadowDelivery)
    console.log('RESTORE OK', JSON.stringify({
      sessionId: state.sessionId,
      role: binding.role,
      taskState: tasks[0].state,
      bindings: evidence.bindings.length,
      verifications: evidence.verifications.length,
      memoryWriteRestored: {
        toolsRegistered: memory.toolsRegistered,
        coldReadFound: memory.coldReadFound,
        receiptRehydrated: memory.receiptRehydrated,
        dispatcherReadVerified: memory.dispatcherReadVerified,
        searchHitRestored: memory.searchHitRestored,
        retryAlreadyExists: memory.retryAlreadyExists,
        readAbsent: memory.readAbsent,
        userScopeForbidden: memory.userScopeForbidden,
      },
      shadowToolsScopeIsolated: shadow.toolsScopeIsolated,
      shadowCallerForbidden: shadow.callerForbidden,
      shadowDomainFileOnDisk: shadow.domainFileOnDisk,
      hierarchyControllerReadAllowed: hierarchy.controllerReadAllowed,
      hierarchyLeadDelegationDenied: hierarchy.leadDelegationDenied,
      hierarchyUnboundControlledDenied: hierarchy.unboundControlledDenied,
      shadowCompMarkedScopeSeesTools: shadowComposition.markedScopeSeesTools,
      shadowCompUnmarkedScopeClean: shadowComposition.unmarkedScopeClean,
      shadowCompBindingRowPersisted: shadowComposition.bindingRowPersisted,
      shadowDeliveryRestored: true,
    }))
  }
} finally {
  await ctx.fiber.dispose()
}
