/**
 * Keyless snapshot coverage for the TypeScript SDK path: each scenario spawns
 * the real `dsh --profile sdk` runtime through
 * `@deepseek-ai/dsh-sdk-client`, drives one turn over stdio JSON-RPC,
 * and pins the SDK `RunResult`, the complete notification stream, and the
 * persisted session logs. Replay serves recorded model
 * responses via `llm-replay` (`cordis.snapshot.yml`); `DSH_SNAPSHOT=record`
 * re-records against the live API; `DSH_SNAPSHOT=refresh` replays committed
 * fixtures and rewrites expected outputs.
 */

import { existsSync } from 'node:fs'
import { cp, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, delimiter, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  captureExpectedWorkspaceSnapshot,
  captureWorkspaceSnapshot,
  childExpectationFileName,
  childSessionFixtureFileName,
  declaredExpectationVariantFiles,
  expectationFileName,
  normalizeSessionLog,
  normalizeSessionSnapshots,
  normalizeStdout,
  normalizedHeaders,
  normalizedSystemPrompts,
  normalizedToolSchemas,
  parseSnapshotManifest,
  parseToolSchemasSnapshot,
  platformExpectationVariant,
  redactSessionSnapshotIds,
  refreshFixtureReplacements,
  resolveChildExpectationPath,
  resolveChildSessionFixturePath,
  resolveExpectationPath,
  resolveSessionFixturePath,
  restorePinnedToolSchemas,
  scrubRequestHeaders,
  scrubSessionSnapshot,
  scrubSystemPrompts,
  sessionFixtureFileName,
  sessionFixtureNames,
  stabilizeFixtureMessageIds,
  stabilizeRefreshLog,
  tokenizeSessionFixtureCwd,
  materializeProfilePatch,
  formatSystemPromptSnapshot,
  formatToolSchemasSnapshot,
  type HarvestedLog,
  type NormalizeContext,
  type SnapshotManifest,
  type WorkspaceSnapshotEntry,
} from '@deepseek-ai/dsh-session-snapshot'
import {
  DeepSeekHarness,
  type HarnessNotification,
  type NotificationSubscription,
  type RunResult,
  type SdkPromptContentBlock,
} from '@deepseek-ai/dsh-sdk-client'
import { prepareProjectIntegration, verifyProjectIntegration } from './project-integration-setup.ts'

const corpusRoot = fileURLToPath(new URL('../', import.meta.url))

const MINIMAL_SYSTEM_PROMPT = 'You are the environment-selected minimal software engineer.'
// The native win32 worktree tools append their guidance section to the
// assembled system prompt; the POSIX composition never registers them. The
// text mirrors the product's private GUIDANCE constant in
// packages/workflow/tool-worktree/src/index.ts.
const WORKTREE_GUIDANCE = `The worktree_* tools manage second checkouts (git worktrees) of the calling session's own workspace: they authorize against the session's working directory and cannot touch another workspace's registrations. Get ids with worktree_list before worktree_status or worktree_remove; create with worktree_create for clean builds, experiments, or parallel tasks. A worktree whose directory was deleted outside the product is recovered with worktree_prune (pruneDangling: true), and outside-created checkouts become manageable after worktree_prune (adoptUnregistered: true).`
const MINIMAL_BASH_DESCRIPTION = `Run commands in a bash shell
* When invoking this tool, the contents of the "command" parameter does NOT need to be XML-escaped.
* You don't have access to the internet via this tool.
* You do have access to a mirror of common linux and python packages via apt and pip.
* State is persistent across command calls and discussions with the user.
* To inspect a particular line range of a file, e.g. lines 10-25, try 'sed -n 10,25p /path/to/the/file'.
* Please avoid commands that may produce a very large amount of output.
* Please run long lived commands in the background, e.g. 'sleep 10 &' or start a server in the background.`

const mode = process.env.DSH_SNAPSHOT ?? 'replay'
const recording = mode === 'record'
const refreshing = mode === 'refresh'
const RUNTIME_WORKSPACE_ENTRIES = [
  '.agents',
  '.child-dsh',
  '.dsh',
  '.dsh-sdk-background-release',
  '.replay-fixtures',
  '.snapshot-patches',
] as const
const dshSdkDiagnosticChildPatch = fileURLToPath(new URL(
  './subagent-dsh-sdk-diagnostic/child.cordis.yml',
  import.meta.url,
))
const dshSdkChildConfig = fileURLToPath(new URL(
  '../../packages/subagent/subagent-dsh-sdk/tests/fixtures/loader/child.patch.yml',
  import.meta.url,
))

function dirOf(url: string): string {
  return fileURLToPath(new URL('.', url))
}

interface SdkAssertions {
  /** Session worktree below the isolated run root. */
  sessionCwd?: string
  /** Inspect external effects after the runtime has closed and flushed storage. */
  verifyWorkspace?: (cwd: string) => Promise<void>
  /** Child sessions contain seeded evidence without an Agent model run. */
  boundSessionsOnly?: boolean
  /** Environment overrides passed to the runtime subprocess. */
  environment?: Readonly<Record<string, string>>
  /** A separate DSH SDK child whose persisted session joins the evidence. */
  dshSdkChild?: {
    /** Profile patch materialized for the child runtime. */
    config: string
    /** Exact request configuration committed by the child runtime. */
    agentConfig: Readonly<Record<string, unknown>>
  }
  /** Assembled model-facing tool names and required argument keys. */
  expectedTools?: Readonly<Record<string, readonly string[]>>
  /** Exact assembled system prompt for the root request. */
  expectedSystem?: string
  /** Exact model-facing descriptions for selected tools. */
  expectedToolDescriptions?: Readonly<Record<string, string>>
  /** Expected runtime-context state in the real assembled request. */
  runtimeContext?: false | { includes: readonly string[]; excludes: readonly string[] }
}

const SDK_ASSERTIONS: Readonly<Record<string, SdkAssertions>> = {
  'project-repair-integrate': {
    sessionCwd: '.dsh/integration/target',
    verifyWorkspace: cwd => verifyProjectIntegration(cwd, 'repaired\n'),
    boundSessionsOnly: true,
  },
  'project-integrate-success': {
    sessionCwd: '.dsh/integration/target',
    verifyWorkspace: verifyProjectIntegration,
    boundSessionsOnly: true,
  },
  // Hierarchy-created children use native sessions rather than the subagent seam.
  'dispatch-settlement-followup': {
    sessionCwd: '.dsh/dispatch/repo',
    boundSessionsOnly: true,
  },
  'subagent-dsh-sdk-diagnostic': {
    environment: { DSH_TEST_CHILD_PATCH: dshSdkDiagnosticChildPatch },
  },
  'persistent-tools': {
    environment: { DSH_SYSTEM_PROMPT: MINIMAL_SYSTEM_PROMPT },
    // The scenario-owned composition registers the same persistent bash tool
    // on every platform (win32 bash calls fail with deterministic spawn
    // errors); the win32 runtime additionally registers the native worktree
    // tools, which the POSIX composition never sees.
    expectedTools: process.platform === 'win32'
      ? {
        bash: ['command'],
        str_replace_editor: ['command', 'path'],
        worktree_create: ['path'],
        worktree_list: [],
        worktree_prune: [],
        worktree_remove: ['id'],
        worktree_status: ['id'],
      }
      : { bash: ['command'], str_replace_editor: ['command', 'path'] },
    expectedSystem: process.platform === 'win32'
      ? `${MINIMAL_SYSTEM_PROMPT}\n\n${WORKTREE_GUIDANCE}`
      : MINIMAL_SYSTEM_PROMPT,
    expectedToolDescriptions: { bash: MINIMAL_BASH_DESCRIPTION },
    runtimeContext: {
      includes: ['Current DSH file policy: danger-full-access', 'Approval prompts are disabled in this session'],
      excludes: ['workspace-write'],
    },
  },
  'subagent-dsh-sdk-dynamic-route': {
    environment: { DSH_TEST_PARENT_PROVIDER: 'deepseek-official' },
    dshSdkChild: {
      config: dshSdkChildConfig,
      agentConfig: {
        provider: 'mock',
        model: 'mock-routed',
        reasoningEffort: 'max',
        maxTokens: 777,
      },
    },
  },
}

interface CorpusScenario {
  readonly key: string
  readonly name: string
  readonly dir: string
  readonly manifest: SnapshotManifest & {
    composition: string
    recording: 'live' | 'authored'
    header: NonNullable<SnapshotManifest['header']>
  }
}

async function collectCorpus(): Promise<CorpusScenario[]> {
  const scenarios: CorpusScenario[] = []
  for (const profile of ['session', 'sdk']) {
    const root = join(corpusRoot, profile)
    for (const entry of await readdir(root, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      const dir = join(root, entry.name)
      const manifestPath = join(dir, 'snapshot.yml')
      if (!existsSync(manifestPath)) continue
      const manifest = parseSnapshotManifest(await readFile(manifestPath, 'utf8'), manifestPath)
      if (manifest.composition === undefined || manifest.recording === undefined || manifest.header === undefined) continue
      scenarios.push({
        key: `${profile}/${entry.name}`,
        name: entry.name,
        dir,
        manifest: { ...manifest, composition: manifest.composition, recording: manifest.recording, header: manifest.header },
      })
    }
  }
  return scenarios
}

const corpus = await collectCorpus()
const scenarioByKey = new Map(corpus.map(scenario => [scenario.key, scenario]))
const sdkScenarios = corpus
  .filter(scenario => scenario.manifest.profile === 'sdk')
  .sort((left, right) => left.name.localeCompare(right.name))
const compositionOwners = new Map<string, CorpusScenario>()
const headerPins = new Map<string, CorpusScenario>()
for (const scenario of corpus) {
  const { composition, header } = scenario.manifest
  if (existsSync(join(scenario.dir, 'cordis.yml'))) {
    if (compositionOwners.has(composition)) throw new Error(`snapshot composition ${composition} has multiple patch owners`)
    compositionOwners.set(composition, scenario)
  }
  if (header.pin === true) {
    const key = `${composition}/${header.class}`
    if (headerPins.has(key)) throw new Error(`snapshot header class ${key} has multiple pins`)
    headerPins.set(key, scenario)
  }
}

function compositionOwner(scenario: CorpusScenario): CorpusScenario {
  const owner = compositionOwners.get(scenario.manifest.composition)
  if (owner === undefined) throw new Error(`${scenario.key}: composition has no cordis.yml owner`)
  return owner
}

function headerPin(scenario: CorpusScenario): CorpusScenario {
  const pin = headerPins.get(`${scenario.manifest.composition}/${scenario.manifest.header.class}`)
  if (pin === undefined) throw new Error(`${scenario.key}: composition/header class has no pin`)
  return pin
}

function sourceScenario(owner: CorpusScenario, source: string | undefined): CorpusScenario {
  const key = source === undefined
    ? owner.key
    : source.includes('/') ? source : `${owner.key.split('/')[0]}/${source}`
  const scenario = scenarioByKey.get(key)
  if (scenario === undefined) throw new Error(`${owner.key}: unknown sidecar source ${key}`)
  return scenario
}

interface PersistedLog {
  readonly path: string
  readonly content: string
  readonly header: Record<string, unknown>
}

async function jsonlFiles(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { recursive: true })
  return entries.filter(entry => entry.endsWith('.jsonl')).map(entry => join(dir, entry)).sort()
}

async function persistedLogs(sessionsRoot: string): Promise<PersistedLog[]> {
  const files = await jsonlFiles(sessionsRoot)
  return Promise.all(files.map(async (path) => {
    const content = await readFile(path, 'utf8')
    const header = JSON.parse(content.slice(0, content.indexOf('\n'))) as Record<string, unknown>
    return { path, content, header }
  }))
}

interface LoggedRequestHeader {
  type?: string
  data?: { header?: { system?: unknown; tools?: LoggedTool[] } }
}

interface LoggedTool {
  readonly name: string
  readonly description?: unknown
  readonly parameters: { readonly required?: string[] }
}

function assembledTools(log: PersistedLog): LoggedTool[] {
  const event = log.content.trimEnd().split('\n')
    .map(line => JSON.parse(line) as LoggedRequestHeader)
    .find(candidate => candidate.type === 'request/header')
  const tools = event?.data?.header?.tools
  if (tools === undefined) throw new Error('session log has no request/header tools')
  return tools
}

function assembledToolRequirements(log: PersistedLog): Record<string, string[]> {
  return Object.fromEntries(assembledTools(log).map(tool => [tool.name, tool.parameters.required ?? []]))
}

function assembledToolDescriptions(log: PersistedLog): Record<string, string> {
  return Object.fromEntries(assembledTools(log).map((tool) => {
    if (typeof tool.description !== 'string') throw new Error(`tool ${tool.name} has no description`)
    return [tool.name, tool.description]
  }))
}

function assembledSystem(log: PersistedLog): string {
  const event = log.content.trimEnd().split('\n')
    .map(line => JSON.parse(line) as LoggedRequestHeader)
    .find(candidate => candidate.type === 'request/header')
  const system = event?.data?.header?.system
  if (typeof system !== 'string') throw new Error('session log has no request/header system')
  return system
}

function assembledRuntimeContexts(log: PersistedLog): string[] {
  return log.content.trimEnd().split('\n').flatMap((line) => {
    const event = JSON.parse(line) as {
      type?: string
      data?: { source?: { kind?: string; plugin?: string }; content?: Array<{ type?: string; text?: unknown }> }
    }
    if (event.type !== 'user/message'
      || event.data?.source?.kind !== 'plugin'
      || event.data.source.plugin !== '@deepseek-ai/dsh-system-prompt') return []
    return event.data.content?.flatMap(block => block.type === 'text' && typeof block.text === 'string' ? [block.text] : []) ?? []
  })
}

function contextOf(logs: readonly { content: string; header: Record<string, unknown> }[], cwd: string): NormalizeContext {
  return {
    sessionIds: logs.flatMap(log => typeof log.header.id === 'string' ? [log.header.id] : []),
    cwd,
  }
}

function contextOfContents(contents: readonly string[]): NormalizeContext {
  const headers = contents.map(content => JSON.parse(content.slice(0, content.indexOf('\n'))) as Record<string, unknown>)
  return {
    sessionIds: headers.flatMap(header => typeof header.id === 'string' ? [header.id] : []),
    cwd: typeof headers[0]?.cwd === 'string' ? headers[0].cwd : '\0no-cwd\0',
  }
}

async function fixtureFiles(scenario: CorpusScenario): Promise<string[]> {
  const variants = new Set(declaredExpectationVariantFiles(scenario.manifest))
  const names = sessionFixtureNames((await readdir(scenario.dir)).filter(name => !variants.has(name)))
  return [
    resolveSessionFixturePath({ dir: scenario.dir, manifest: scenario.manifest, platform: process.platform }),
    ...names.slice(1).map((_, position) => resolveChildSessionFixturePath({
      dir: scenario.dir,
      manifest: scenario.manifest,
      index: position + 1,
      platform: process.platform,
    })),
  ]
}

/**
 * Replace every `{{cwd}}` token in one session fixture with the run's real
 * cwd, honoring the JSON encoding depth of each occurrence. The token sits
 * directly in a JSON string for header fields and result texts, but one
 * encoding deeper inside model-issued tool-call arguments (a JSON payload
 * carried as a string value): a raw win32 path inserted at the wrong depth
 * would survive the outer parse with single backslashes and fail the runtime's
 * arguments parse (`\t` becomes a tab, `\s` is invalid).
 */
function hydrateCwdToken(value: unknown, cwd: string): unknown {
  if (typeof value === 'string') {
    if (!value.includes('{{cwd}}')) return value
    if (value.trimStart().startsWith('{') || value.trimStart().startsWith('[')) {
      try {
        return JSON.stringify(hydrateCwdToken(JSON.parse(value) as unknown, cwd))
      } catch {
        // Not a JSON payload after all: the token sits in plain text and the
        // direct replacement below is the correct depth.
      }
    }
    return value.split('{{cwd}}').join(cwd)
  }
  if (Array.isArray(value)) return value.map(item => hydrateCwdToken(item, cwd))
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, hydrateCwdToken(item, cwd)]))
  }
  return value
}

/** Hydrate one complete fixture text line-by-line so each line's JSON depth stays exact. */
function hydrateCwdFixtureText(text: string, cwd: string): string {
  if (!text.includes('{{cwd}}')) return text
  const lines = text.split('\n')
  for (const [index, line] of lines.entries()) {
    if (!line.includes('{{cwd}}')) continue
    lines[index] = JSON.stringify(hydrateCwdToken(JSON.parse(line) as unknown, cwd))
  }
  return lines.join('\n')
}

async function hydrateReplayFixtures(scenario: CorpusScenario, cwd: string): Promise<string[]> {
  const root = join(cwd, '.replay-fixtures')
  await mkdir(root, { recursive: true })
  return Promise.all((await fixtureFiles(scenario)).map(async (source, index) => {
    // Hydrated names stay canonical regardless of which committed variant the
    // source resolved to, so the runtime-facing fixture contract is constant.
    const destination = join(root, index === 0 ? 'session.jsonl' : `session.${index}.jsonl`)
    const sourceText = await readFile(source, 'utf8')
    await writeFile(destination, hydrateCwdFixtureText(sourceText, cwd))
    return destination
  }))
}

/**
 * Normalize the SDK-visible notification stream: embedded `session.event`
 * envelopes get the session-log treatment (times zeroed, headers tokenized),
 * then every record is scrubbed like a wire frame.
 */
function normalizeNotifications(notifications: readonly HarnessNotification[], ctx: NormalizeContext): string {
  const events = notifications
    .filter(n => n.method === 'session.event')
    .map(n => n.params.event as Record<string, unknown>)
  const normalizedEvents = events.length === 0
    ? []
    : scrubRequestHeaders(normalizeSessionLog(
      `${events.map(event => JSON.stringify(event)).join('\n')}\n`,
      ctx,
    )).trimEnd().split('\n').map(line => JSON.parse(line) as Record<string, unknown>)
  let eventIndex = 0
  const records = notifications.map((notification) => {
    if (notification.method !== 'session.event') return { method: notification.method, params: notification.params }
    const event = normalizedEvents[eventIndex++]
    return { method: notification.method, params: { ...notification.params, event } }
  })
  return normalizeStdout(`${records.map(record => JSON.stringify(record)).join('\n')}\n`, ctx)
}

/** Normalize the owned-run projection. */
function normalizeResult(result: RunResult, ctx: NormalizeContext): string {
  return normalizeStdout(`${JSON.stringify({
    sessionId: result.sessionId,
    finalResponse: result.finalResponse,
  })}\n`, ctx)
}

interface JsonObject {
  [key: string]: unknown
}

interface TurnAction {
  readonly turn: number
  readonly content?: JsonObject[]
}

function records(log: string): JsonObject[] {
  return log.split(/\r?\n/)
    .filter(line => line.trim() !== '')
    .map(line => JSON.parse(line) as JsonObject)
}

function modelFromSession(log: string): { provider: string; model: string } {
  for (const record of records(log)) {
    if (record.type !== 'request/header') continue
    const data = record.data as JsonObject | undefined
    const header = data?.header as JsonObject | undefined
    const config = header?.config as JsonObject | undefined
    if (typeof config?.provider === 'string' && typeof config.model === 'string') {
      return { provider: config.provider, model: config.model }
    }
  }
  throw new Error('SDK snapshot session has no request model')
}

function turnActions(log: string): TurnAction[] {
  const actions: TurnAction[] = []
  let current: TurnAction | undefined
  for (const record of records(log)) {
    if (record.type === 'turn/start') {
      const data = record.data as JsonObject | undefined
      if (typeof data?.turn !== 'number') throw new Error('SDK snapshot turn/start has no turn')
      current = { turn: data.turn }
      continue
    }
    if (record.type === 'user/message' && current !== undefined && current.content === undefined) {
      const data = record.data as JsonObject | undefined
      const source = data?.source as JsonObject | undefined
      if (source?.kind === 'user' && Array.isArray(data?.content)) {
        current = { turn: current.turn, content: data.content as JsonObject[] }
      }
      continue
    }
    if (record.type === 'turn/end' && current !== undefined) {
      actions.push(current)
      current = undefined
    }
  }
  return actions
}

function postTurnEventTypes(log: string): string[] {
  const values = records(log)
  const finalTurnEnd = values.findLastIndex(record => record.type === 'turn/end')
  return values.slice(finalTurnEnd + 1).flatMap(record => typeof record.type === 'string' ? [record.type] : [])
}

function materializeInput(
  content: readonly JsonObject[],
  scenario: CorpusScenario,
  cwd: string,
  liveSessions: readonly (string | undefined)[],
): SdkPromptContentBlock[] {
  const attachments = new Map(scenario.manifest.input?.attachments?.map(attachment => [attachment.id, attachment]))
  const replace = (value: unknown): unknown => {
    if (typeof value === 'string') {
      let output = value.replaceAll('{{cwd}}', cwd)
      output = output.replace(/\{\{session:([1-9]\d*)\}\}/g, (_token, ordinal: string) => {
        const live = liveSessions[Number(ordinal) - 1]
        if (live === undefined) throw new Error(`${scenario.name}: session token ${ordinal} has not bound`)
        return live
      })
      return output
    }
    if (Array.isArray(value)) return value.map(replace)
    if (value !== null && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, replace(item)]))
    }
    return value
  }
  return content.map((block) => {
    if (block.type !== 'image') return replace(block) as SdkPromptContentBlock
    const attachment = block.attachment as JsonObject | undefined
    const id = attachment?.attachmentId
    const input = typeof id === 'string' ? attachments.get(id) : undefined
    if (input === undefined) throw new Error(`${scenario.name}: no input bytes for image attachment ${String(id)}`)
    return { type: 'image', data: input.data, mimeType: input.mediaType } as SdkPromptContentBlock
  })
}

function notificationEvent(notification: HarnessNotification): JsonObject | undefined {
  return notification.method === 'session.event' && notification.params.event !== null
    && typeof notification.params.event === 'object'
    ? notification.params.event as JsonObject
    : undefined
}

async function waitForRootEvent(
  subscription: NotificationSubscription,
  sessionId: string,
  match: (event: JsonObject) => boolean,
  observe: (notification: HarnessNotification) => void,
): Promise<void> {
  while (true) {
    const notification = await subscription.next()
    observe(notification)
    const event = notification.params.sessionId === sessionId ? notificationEvent(notification) : undefined
    if (event !== undefined && match(event)) return
  }
}

function authoredPatches(scenario: CorpusScenario, replaying: boolean): string[] {
  const owner = compositionOwner(scenario)
  if (scenario.manifest.composition.startsWith('sdk-')) {
    return [join(owner.dir, 'cordis.yml'), ...(replaying ? [join(owner.dir, 'cordis.snapshot.yml')] : [])]
  }
  const base = compositionOwners.get('default')
  if (base === undefined) throw new Error('SDK corpus has no default transport-neutral composition')
  return [
    join(base.dir, 'cordis.yml'),
    ...owner === base && !replaying ? [] : [join(owner.dir, replaying ? 'cordis.snapshot.yml' : 'cordis.yml')],
    join(base.dir, 'model.cordis.yml'),
  ]
}

/** One SDK-controlled recorded scenario against a fresh `dsh --profile sdk` subprocess. */
async function runScenario(scenario: CorpusScenario): Promise<{
  results: RunResult[]
  notifications: HarnessNotification[]
  observedMethods: ReadonlySet<string>
  logs: PersistedLog[]
  initialWorkspace: WorkspaceSnapshotEntry[]
  finalWorkspace: WorkspaceSnapshotEntry[]
  cwd: string
}> {
  const cwd = await mkdtemp(join(tmpdir(), `sdk-snapshot-${scenario.name}-`))
  const dshHome = join(cwd, '.dsh')
  const sessionsRoot = join(dshHome, 'sessions')
  const replayFixtures = recording ? [] : await hydrateReplayFixtures(scenario, cwd)
  const fixtureContents = await Promise.all((await fixtureFiles(scenario)).map(file => readFile(file, 'utf8')))
  const primaryFixture = fixtureContents[0]
  if (primaryFixture === undefined) throw new Error(`${scenario.name}: no primary session fixture`)
  const route = modelFromSession(primaryFixture)
  const patchRoot = join(cwd, '.snapshot-patches')
  await mkdir(patchRoot, { recursive: true })
  const patches = authoredPatches(scenario, !recording)
    .map((patch, index) => materializeProfilePatch(patch, cwd, patchRoot, index))
  const assertions = SDK_ASSERTIONS[scenario.name] ?? {}
  let childSessionsRoot: string | undefined
  let childEnvironment: Record<string, string> = {}
  if (assertions.dshSdkChild !== undefined) {
    const childHome = join(cwd, '.child-dsh')
    const childPatch = materializeProfilePatch(assertions.dshSdkChild.config, cwd, patchRoot, patches.length)
    await mkdir(childHome, { recursive: true })
    childSessionsRoot = join(childHome, 'sessions')
    childEnvironment = {
      DSH_TEST_CHILD_PATCHES: JSON.stringify([childPatch]),
      DSH_TEST_CHILD_HOME: childHome,
    }
  }
  const workspaceDir = join(scenario.dir, 'workspace')
  if (existsSync(workspaceDir)) {
    for (const entry of await readdir(workspaceDir)) {
      await cp(join(workspaceDir, entry), join(cwd, entry), { recursive: true, verbatimSymlinks: true })
    }
  }
  const workspaceSetup = scenario.manifest.workspace?.setup
  if (workspaceSetup !== undefined) {
    const setups: Readonly<Record<string, (root: string) => Promise<void>>> = {
      'project-integration': prepareProjectIntegration,
    }
    const prepare = setups[workspaceSetup]
    if (prepare === undefined) throw new Error(`${scenario.name}: unknown SDK workspace setup ${workspaceSetup}`)
    try {
      await prepare(cwd)
    } catch (error) {
      await rm(cwd, { recursive: true, force: true })
      throw error
    }
  }
  const initialWorkspace = await captureWorkspaceSnapshot(cwd, {
    ignoredRootEntries: RUNTIME_WORKSPACE_ENTRIES,
  })
  const [parentFixture, ...childFixtures] = replayFixtures
  const env: Record<string, string> = {
    ...Object.fromEntries(Object.entries(process.env).filter(([, value]) => value !== undefined)) as Record<string, string>,
    DSH_SNAPSHOT: mode,
    DSH_SNAPSHOT_PROVIDER: route.provider,
    DSH_SNAPSHOT_MODEL: route.model,
    DSH_TELEMETRY_DISABLED: '1',
    DSH_AGENTS_HOME: join(cwd, '.agents'),
    NODE_OPTIONS: [process.env.NODE_OPTIONS, '--disable-warning=ExperimentalWarning'].filter(Boolean).join(' '),
    ...parentFixture === undefined ? {} : {
      DSH_SNAPSHOT_FILE: parentFixture,
      ...childFixtures.length > 0 ? { DSH_SNAPSHOT_CHILD_FILES: childFixtures.join(delimiter) } : {},
    },
    ...!recording && scenario.manifest.replay?.override === true
      ? { DSH_SNAPSHOT_OVERRIDE: join(scenario.dir, 'replay.override.json') }
      : {},
    ...scenario.manifest.environment,
    ...assertions.environment,
    ...childEnvironment,
  }

  const harness = new DeepSeekHarness({
    profile: 'sdk',
    patches,
    dshHome,
    processCwd: cwd,
    env,
    requestTimeoutMs: 110_000,
    cwd: assertions.sessionCwd === undefined ? cwd : join(cwd, assertions.sessionCwd),
    provider: route.provider,
    model: route.model,
  })
  try {
    const notifications: HarnessNotification[] = []
    const observedMethods = new Set<string>()
    const results: RunResult[] = []
    const sessionId = 'fixture-root-session'
    const liveSessions: (string | undefined)[] = [sessionId]
    await harness.start()
    const subscription = harness.client.subscribeSessionTree(sessionId)
    const observe = (notification: HarnessNotification): void => {
      observedMethods.add(notification.method)
      if (notification.method !== 'subagent.started') return
      const child = notification.params.childSessionId
      if (typeof child !== 'string' || liveSessions.includes(child)) return
      liveSessions.push(child)
    }
    try {
      const session = harness.session(sessionId)
      for (const action of turnActions(primaryFixture)) {
        if (action.content === undefined) {
          await waitForRootEvent(
            subscription,
            sessionId,
            event => event.type === 'turn/end' && (event.data as JsonObject | undefined)?.turn === action.turn,
            observe,
          )
          continue
        }
        const result = await session.run(materializeInput(action.content, scenario, cwd, liveSessions), {
          onNotification: (notification) => {
            notifications.push(notification)
            observe(notification)
          },
        })
        results.push(result)
        await waitForRootEvent(
          subscription,
          sessionId,
          event => event.type === 'turn/end' && (event.data as JsonObject | undefined)?.turn === action.turn,
          observe,
        )
      }
      for (const type of postTurnEventTypes(primaryFixture)) {
        await waitForRootEvent(subscription, sessionId, event => event.type === type, observe)
      }
    } finally {
      subscription.close()
    }
    await harness.close()
    await assertions.verifyWorkspace?.(cwd)
    const logs = (await Promise.all([
      persistedLogs(sessionsRoot),
      ...(childSessionsRoot === undefined ? [] : [persistedLogs(childSessionsRoot)]),
    ])).flat()
    const finalWorkspace = await captureWorkspaceSnapshot(cwd, {
      ignoredRootEntries: RUNTIME_WORKSPACE_ENTRIES,
    })
    return { results, notifications, observedMethods, logs, initialWorkspace, finalWorkspace, cwd }
  } finally {
    await harness.close()
    await rm(cwd, { recursive: true, force: true })
  }
}

/** Order logs parent-first, children by creation time (fixture layout order). */
function orderLogs(logs: PersistedLog[], expectedCount: number, separateDshSdkChild: boolean): PersistedLog[] {
  if (separateDshSdkChild) {
    expect(logs).toHaveLength(expectedCount)
    return logs
  }
  const parents = logs.filter(log => typeof log.header.parentSession !== 'string')
  const children = logs.filter(log => typeof log.header.parentSession === 'string')
    .sort((left, right) => Number(left.header.createdAt) - Number(right.header.createdAt))
  expect(parents).toHaveLength(1)
  expect(children).toHaveLength(expectedCount - 1)
  return [...parents, ...children]
}

/**
 * The committed file name of one sidecar write target: the declared platform
 * variant name on a variant-declaring host platform, the base name otherwise.
 * Never consults the filesystem, so refresh write-backs can name a variant
 * target that does not exist yet.
 */
function sidecarTarget(
  scenario: CorpusScenario,
  kind: 'system-prompt' | 'tool-schemas',
  index?: number,
): string {
  const variant = platformExpectationVariant(process.platform)
  const declared = index === undefined
    ? scenario.manifest.expectations?.variants[variant]?.includes(kind) === true
    : scenario.manifest.childExpectations?.variants[variant]?.includes(kind) === true
  if (!declared) {
    return index === undefined ? expectationFileName(kind) : childExpectationFileName(kind, index)
  }
  return index === undefined ? expectationFileName(kind, variant) : childExpectationFileName(kind, index, variant)
}

/** The wire-golden pair the host platform must compare against, plus whether the platform declares a variant. */
function wireGoldenPaths(scenario: CorpusScenario): { declared: boolean; notifications: string; result: string } {
  const variant = platformExpectationVariant(process.platform)
  const declared = scenario.manifest.wireVariants?.[variant] === true
  const suffix = declared ? `.${variant}` : ''
  return {
    declared,
    notifications: join(scenario.dir, `notifications${suffix}.expected.jsonl`),
    result: join(scenario.dir, `result${suffix}.expected.json`),
  }
}

async function writeHeaderSidecars(
  scenario: CorpusScenario,
  ordered: readonly PersistedLog[],
  ctx: NormalizeContext,
): Promise<void> {
  if (scenario.manifest.header.pin === true) {
    const primary = ordered[0]
    if (primary === undefined) throw new Error(`${scenario.name}: no primary header to snapshot`)
    const prompts = normalizedSystemPrompts(primary.content, ctx)
    const schemas = normalizedToolSchemas(primary.content, ctx)
    if (scenario.manifest.header.systemPromptSource === undefined) {
      await writeFile(
        join(scenario.dir, sidecarTarget(scenario, 'system-prompt')),
        formatSystemPromptSnapshot(prompts[0] as string, prompts.slice(1)),
      )
    }
    if (scenario.manifest.header.toolSchemasSource === undefined) {
      await writeFile(
        join(scenario.dir, sidecarTarget(scenario, 'tool-schemas')),
        formatToolSchemasSnapshot(schemas[0] as unknown[], schemas.slice(1)),
      )
    }
  }
  for (const index of scenario.manifest.header.childSystemPrompts ?? []) {
    const child = ordered[index]
    if (child === undefined) throw new Error(`${scenario.name}: no child ${index} prompt to snapshot`)
    const prompts = normalizedSystemPrompts(child.content, ctx)
    await writeFile(join(scenario.dir, sidecarTarget(scenario, 'system-prompt', index)), formatSystemPromptSnapshot(
      prompts[0] as string,
      prompts.slice(1),
    ))
  }
  for (const index of scenario.manifest.header.childToolSchemas ?? []) {
    const child = ordered[index]
    if (child === undefined) throw new Error(`${scenario.name}: no child ${index} schemas to snapshot`)
    const schemas = normalizedToolSchemas(child.content, ctx)
    await writeFile(join(scenario.dir, sidecarTarget(scenario, 'tool-schemas', index)), formatToolSchemasSnapshot(
      schemas[0] as unknown[],
      schemas.slice(1),
    ))
  }
}

async function verifyHeaders(
  scenario: CorpusScenario,
  ordered: readonly PersistedLog[],
  ctx: NormalizeContext,
  dshSdkChildConfig?: Readonly<Record<string, unknown>>,
): Promise<void> {
  const pin = headerPin(scenario)
  const pinFixture = await readFile(
    resolveSessionFixturePath({ dir: pin.dir, manifest: pin.manifest, platform: process.platform }),
    'utf8',
  )
  const firstLine = pinFixture.split('\n').find(line => line.trim() !== '') ?? '{}'
  const pinHeader = JSON.parse(firstLine) as JsonObject
  const pinned = normalizedHeaders(pinFixture, {
    sessionIds: [],
    cwd: typeof pinHeader.cwd === 'string' ? pinHeader.cwd : '\0no-cwd\0',
  })
  const promptOwner = sourceScenario(pin, pin.manifest.header.systemPromptSource)
  const schemaOwner = sourceScenario(pin, pin.manifest.header.toolSchemasSource)
  const prompt = await readFile(
    resolveExpectationPath({ dir: promptOwner.dir, kind: 'system-prompt', manifest: promptOwner.manifest, platform: process.platform }),
    'utf8',
  )
  const schemas = parseToolSchemasSnapshot(await readFile(
    resolveExpectationPath({ dir: schemaOwner.dir, kind: 'tool-schemas', manifest: schemaOwner.manifest, platform: process.platform }),
    'utf8',
  ))
  const schemaSets = [schemas.initial, ...schemas.changes]
  const reconstructed = pinned.map((header, index) => restorePinnedToolSchemas(
    header,
    schemaSets[index] as unknown[],
  ))

  const childPrompts = new Map<number, string>()
  const childSchemas = new Map<number, unknown[][]>()
  for (const index of scenario.manifest.header.childSystemPrompts ?? []) {
    childPrompts.set(index, await readFile(
      resolveChildExpectationPath({ dir: scenario.dir, kind: 'system-prompt', index, manifest: scenario.manifest, platform: process.platform }),
      'utf8',
    ))
  }
  for (const index of scenario.manifest.header.childToolSchemas ?? []) {
    const child = parseToolSchemasSnapshot(await readFile(
      resolveChildExpectationPath({ dir: scenario.dir, kind: 'tool-schemas', index, manifest: scenario.manifest, platform: process.platform }),
      'utf8',
    ))
    childSchemas.set(index, [child.initial, ...child.changes])
  }

  for (const [logIndex, log] of ordered.entries()) {
    const headers = normalizedHeaders(scrubSystemPrompts(log.content), ctx)
    const prompts = normalizedSystemPrompts(log.content, ctx)
    expect(formatSystemPromptSnapshot(prompts[0] as string, prompts.slice(1)),
      `${scenario.name}: session ${logIndex} system prompts`).toBe(childPrompts.get(logIndex) ?? prompt)
    for (const [index, header] of headers.entries()) {
      const selectedSchemas = childSchemas.get(logIndex)?.[index]
      const base = reconstructed[index] ?? reconstructed[0]
      const configured = logIndex === 1 && dshSdkChildConfig !== undefined
        ? { ...base as JsonObject, config: dshSdkChildConfig }
        : base
      const expected = selectedSchemas === undefined
        ? configured
        : { ...configured as JsonObject, tools: selectedSchemas }
      expect(header, `${scenario.name}: session ${logIndex} header ${index + 1}`).toEqual(expected)
    }
  }
}

describe('TypeScript SDK snapshots over the jsonrpc runtime', () => {
  for (const scenario of sdkScenarios) {
    const scenarioTest = recording && scenario.manifest.recording === 'authored' ? it.skip : it
    scenarioTest(`${mode}s ${scenario.name} through dsh --profile sdk`, async () => {
      const scenarioDir = scenario.dir
      const wire = wireGoldenPaths(scenario)
      if (wire.declared && (!existsSync(wire.notifications) || !existsSync(wire.result))) {
        throw new Error(`${scenario.name}: declared platform wire variant files are missing: ${basename(wire.notifications)}, ${basename(wire.result)}`)
      }
      const hasWireGoldens = existsSync(wire.notifications) || existsSync(wire.result)
      const assertions = SDK_ASSERTIONS[scenario.name] ?? {}

      const files = await fixtureFiles(scenario)
      const { results, notifications, observedMethods, logs, initialWorkspace, finalWorkspace, cwd } = await runScenario(scenario)
      const ordered = orderLogs(
        logs,
        recording ? logs.length : files.length,
        assertions.dshSdkChild !== undefined,
      )
      const actualContext = contextOf(ordered, cwd)
      // Embedded JSON-quoted paths must be replaced before the shared normalizer
      // converts Windows separators; all three workspace relationships stay visible.
      const nestedCwd = (log: string): string => {
        if (assertions.sessionCwd === undefined) return log
        const paths = ordered.map(({ header }) => String(header.cwd))
        const canonicalize = (value: unknown): unknown => {
          if (typeof value === 'string') {
            let text = value
            for (const path of paths) {
              const replacement = '{{cwd}}' + path.slice(cwd.length).replaceAll('\\', '/')
              text = text.split(JSON.stringify(path).slice(1, -1)).join(replacement)
              text = text.split(path).join(replacement)
            }
            return text
          }
          if (Array.isArray(value)) return value.map(canonicalize)
          if (value !== null && typeof value === 'object') {
            return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, canonicalize(item)]))
          }
          return value
        }
        return log.split('\n').map(line => line.length === 0 ? line : JSON.stringify(canonicalize(JSON.parse(line)))).join('\n')
      }
      const fixtureCwd = (log: string) => assertions.sessionCwd === undefined
        ? tokenizeSessionFixtureCwd(log)
        : normalizeSessionLog(nestedCwd(log), actualContext, { identityMode: 'preserve' })

      let expectedContents = await Promise.all(files.map(file => readFile(file, 'utf8')))

      if (recording) {
        expectedContents = redactSessionSnapshotIds(stabilizeFixtureMessageIds(
          ordered.map(log => scrubSessionSnapshot(fixtureCwd(log.content))),
          expectedContents,
        ))
      }

      if (refreshing) {
        const harvested = ordered.map((log): HarvestedLog => ({
          id: String(log.header.id),
          createdAt: Number(log.header.createdAt),
          ...typeof log.header.parentSession === 'string' ? { parentSession: log.header.parentSession } : {},
          content: log.content,
        }))
        const replacements = refreshFixtureReplacements(harvested, expectedContents)
        const refreshed = ordered.map((log, index) => {
          const existing = expectedContents[index]
          if (existing === undefined) throw new Error(`no fixture for persisted log ${index}`)
          return scrubSessionSnapshot(fixtureCwd(
            stabilizeRefreshLog(nestedCwd(log.content), existing, replacements, actualContext),
          ))
        })
        expectedContents = redactSessionSnapshotIds(stabilizeFixtureMessageIds(refreshed, expectedContents))
      }

      if (recording || refreshing) {
        const outputFiles = [
          join(scenarioDir, sessionFixtureFileName(scenario.manifest, process.platform)),
          ...Array.from({ length: expectedContents.length - 1 }, (_, index) =>
            join(scenarioDir, childSessionFixtureFileName(scenario.manifest, index + 1, process.platform))),
        ]
        await Promise.all(expectedContents.map((stable, index) => writeFile(outputFiles[index] as string, stable)))
        if (recording) {
          const retained = new Set(outputFiles.map(file => basename(file)))
          for (const entry of await readdir(scenarioDir, { withFileTypes: true })) {
            if (entry.isFile() && /^session\.[1-9]\d*\.jsonl$/u.test(entry.name) && !retained.has(entry.name)) {
              await rm(join(scenarioDir, entry.name))
            }
          }
        }
        await writeHeaderSidecars(scenario, ordered, actualContext)
      }

      for (const [index, expected] of expectedContents.entries()) {
        expect(scrubRequestHeaders(expected), `${scenario.name} session fixture ${index} carries request-header bulk`)
          .toBe(expected)
      }
      expect(redactSessionSnapshotIds(expectedContents), `${scenario.name}: identity redaction fixed point`)
        .toEqual(expectedContents)

      // Persisted transcripts match the committed fixtures.
      const expectedContext = contextOfContents(expectedContents)
      if (assertions.sessionCwd !== undefined) expectedContext.cwd = '{{cwd}}'
      const actualLogs = ordered.map(log => nestedCwd(log.content))
      const actualSnapshots = normalizeSessionSnapshots(actualLogs, actualContext)
      const expectedSnapshots = normalizeSessionSnapshots(expectedContents, expectedContext)
      if (scenario.name === 'dispatch-settlement-followup') {
        expect(ordered).toHaveLength(2)
        const [parent, child] = ordered as [PersistedLog, PersistedLog]
        const parentEvents = records(parent.content)
        const childEvents = records(child.content)
        const parentEnds = parentEvents.filter(event => event.type === 'turn/end')
        const childEnds = childEvents.filter(event => event.type === 'turn/end')
        expect(parentEnds.map(event => event.data)).toEqual([1, 2, 3, 4].map(turn => ({ turn, reason: { kind: 'completed' } })))
        expect(childEnds.map(event => event.data)).toEqual([1, 2].map(turn => ({ turn, reason: { kind: 'completed' } })))
        expect(child.header.parentSession).toBe(parent.header.id)
        const messages = (events: JsonObject[]) => events.filter(event => event.type === 'user/message')
          .map(event => event.data as JsonObject)
        const source = (message: JsonObject) => message.source as JsonObject
        const notices = messages(parentEvents).filter(message => source(message).kind === 'dispatch-settled')
        expect(notices.map(source)).toEqual(childEnds.map(event => ({
          kind: 'dispatch-settled', form: 'notice', senderSessionId: child.header.id, taskId: 'review-1',
          turnIdentity: String(event.seq) + ':' + String((event.data as JsonObject).turn),
          summary: 'Dispatch task review-1: child ' + String(child.header.id) + ' settled turn '
            + String((event.data as JsonObject).turn) + '.',
        })))
        expect(messages(parentEvents).filter(message => source(message).kind === 'user')).toHaveLength(2)
        const childInputs = messages(childEvents).filter(message => source(message).plugin === 'agent-dispatch')
        expect(childInputs.map(message => message.content)).toEqual([
          [{ type: 'text', text: 'Acknowledge this briefing.' }],
          [{ type: 'text', text: 'Confirm that this is a followup to the same task.' }],
        ])
        const calls = parentEvents.filter(event => event.type === 'tool/call').map(event => event.data as JsonObject)
        expect(calls.map(call => [call.turn, call.name, JSON.parse(String(call.arguments)).followup]))
          .toEqual([[1, 'agent_dispatch', undefined], [3, 'agent_dispatch', true]])
      }
      if (scenario.name === 'project-repair-integrate') {
        const evidence = records(ordered[0]!.content)
        const repair = evidence.filter(event => event.type === 'devframe/repair-admission')
        const reviews = evidence.filter(event => event.type === 'devframe/review').map(event => event.data as JsonObject)
        const deliveries = evidence.filter(event => event.type === 'devframe/task-delivery').map(event => event.data as JsonObject)
        expect(repair).toHaveLength(1)
        const goal = evidence.find(event => event.type === 'devframe/goal-binding')!.data as JsonObject
        expect(repair[0]!.data).toEqual({
          version: 1, identity: { controllerSessionId: goal.controllerSessionId, goalId: goal.goalId },
          cause: { kind: 'review', reviewId: 'review-before-repair' }, repairRound: 1, repairLimit: 2,
        })
        expect(reviews.map(review => review.decision)).toEqual(['changes_required', 'pass'])
        expect(deliveries).toHaveLength(2)
        expect(deliveries[0]!.taskId).toBe(deliveries[1]!.taskId)
        expect(deliveries[0]!.sourceCommit).not.toBe(deliveries[1]!.sourceCommit)
        expect(deliveries[0]!.sourceFingerprint).not.toBe(deliveries[1]!.sourceFingerprint)
        expect(notifications.map(notificationEvent).filter(event => event?.type === 'devframe/repair-admission')
          .map(event => event!.data)).toEqual(repair.map(event => event.data))
      }
      for (const [index, actual] of actualSnapshots.entries()) {
        expect(actual, `${scenario.name}: session ${index}`).toBe(expectedSnapshots[index])
      }
      if (scenario.name === 'project-integrate-success') {
        const headers = actualSnapshots.map(log => JSON.parse(log.slice(0, log.indexOf('\n'))) as { cwd: string })
        expect(headers.map(header => header.cwd)).toEqual([
          '{{cwd}}/.dsh/integration/target', '{{cwd}}/.dsh/integration/lead', '{{cwd}}/.dsh/integration/worker',
        ])
        expect(normalizeSessionSnapshots(actualSnapshots, { cwd: '{{cwd}}', sessionIds: [] }))
          .toEqual(actualSnapshots)
        expect(actualSnapshots.some(log => log.includes(cwd) || log.includes(cwd.replaceAll('\\', '/')))).toBe(false)
      }
      await verifyHeaders(scenario, ordered, actualContext, assertions.dshSdkChild?.agentConfig)

      // Genuine SDK protocol cases retain their secondary wire projections.
      const finalResult = results.at(-1)
      if (hasWireGoldens) {
        if (finalResult === undefined) throw new Error(`${scenario.name}: SDK wire golden has no run result`)
        const normalizedNotifications = normalizeNotifications(notifications, actualContext)
        const normalizedResult = normalizeResult(finalResult, actualContext)
        if (recording || refreshing) {
          await writeFile(wire.notifications, normalizedNotifications)
          await writeFile(wire.result, normalizedResult)
        }
        // The committed projection predates or postdates the file-policy
        // tokenization (a host-environment attribute, not tested semantics),
        // so read it through the same final-stage normalizer: a literal
        // policy row aligns with the tokenized received side, an already
        // tokenized row is the identity.
        expect(normalizedNotifications)
          .toBe(normalizeStdout(await readFile(wire.notifications, 'utf8'), actualContext))
        expect(normalizedResult).toBe(await readFile(wire.result, 'utf8'))
      }

      // Wire-shape invariants that must hold in every mode.
      if (scenario.manifest.workspace?.final === true) {
        const expectedWorkspace = await captureExpectedWorkspaceSnapshot(join(scenario.dir, 'workspace.expected'))
        expect(finalWorkspace, `${scenario.name}: complete final workspace`).toEqual(expectedWorkspace)
      } else {
        expect(finalWorkspace, `${scenario.name}: a changed workspace requires workspace.final`).toEqual(initialWorkspace)
      }
      if (assertions.expectedTools !== undefined) {
        const parent = ordered[0]
        if (parent === undefined) throw new Error(`${scenario.name} has no parent session log`)
        expect(assembledToolRequirements(parent)).toEqual(assertions.expectedTools)
      }
      if (assertions.expectedSystem !== undefined) {
        const parent = ordered[0]
        if (parent === undefined) throw new Error(`${scenario.name} has no parent session log`)
        expect(assembledSystem(parent)).toBe(assertions.expectedSystem)
      }
      if (assertions.expectedToolDescriptions !== undefined) {
        const parent = ordered[0]
        if (parent === undefined) throw new Error(`${scenario.name} has no parent session log`)
        expect(assembledToolDescriptions(parent)).toMatchObject(assertions.expectedToolDescriptions)
      }
      if (assertions.runtimeContext !== undefined) {
        const parent = ordered[0]
        if (parent === undefined) throw new Error(`${scenario.name} has no parent session log`)
        const contexts = assembledRuntimeContexts(parent)
        if (assertions.runtimeContext === false) {
          expect(contexts).toEqual([])
        } else {
          expect(contexts).toHaveLength(1)
          const context = contexts[0] as string
          for (const clause of assertions.runtimeContext.includes) expect(context).toContain(clause)
          for (const clause of assertions.runtimeContext.excludes) expect(context).not.toContain(clause)
          const system = assembledSystem(parent)
          for (const clause of assertions.runtimeContext.includes) expect(system).not.toContain(clause)
        }
      }
      if (ordered.length > 1 && assertions.dshSdkChild === undefined) {
        expect(observedMethods.has('subagent.started')).toBe(true)
        expect(observedMethods.has('subagent.finished')).toBe(assertions.boundSessionsOnly !== true)
      }
    })
  }
})
