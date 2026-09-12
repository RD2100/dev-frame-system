/**
 * ⚠️ NOT B6 ACCEPTANCE EVIDENCE — auxiliary in-process component check only.
 * The authorized B6 acceptance is the real dsh profile candidate with the real
 * provider and real session logs (see b6-acceptance-plan.md in this directory).
 * This script boots its own composition with a scripted subagent transport, so
 * it proves the tool/engine/jobs wiring in isolation and nothing more; do not
 * cite it as the B6 four-step evidence.
 *
 * Auxiliary component check — four-step protocol shape over the REAL tool,
 * engine, jobs registry, and tool-jobs tools, with the only scripted pieces
 * being the external model/subagent transports (nondeterministic inputs).
 *
 * Steps proven (each hard-asserts; any failure throws and exits 1):
 *   a) the LIVE registered tool definitions carry the top-level
 *      `run_in_background` parameter on `workflow`, plus the `job_output` /
 *      `job_list` / `job_kill` model tools (read from the service registry
 *      after boot, not from source);
 *   b) `workflow` with `run_in_background: true` returns `{ jobId }`
 *      immediately (the tool call settles before the child settles);
 *   c) the caller continues while the job is provably non-terminal: the child
 *      transport records `enteredAt` when the engine's `agent()` call reaches
 *      it, the protocol waits for that readiness event, reads the job as
 *      `running`, and only then releases the child — so
 *      returnedAt < enteredAt <= runningCheckedAt < releasedAt < completedAt
 *      is a deterministic overlap proof, not a timing race;
 *   d) `job_output(wait: true)` collects the completed result text, and
 *      `job_kill` on a second background workflow settles it terminal (`killed`)
 *      with no lingering job.
 *
 * Ownership: runs in-process on the current main source — no webserver row is
 * mounted (nothing listens; the 3080 deployment is untouched), the home and
 * session/storage roots live in a private `mkdtemp` directory removed on
 * exit, and no build or install step runs (tsx resolves workspace sources
 * through tsconfig paths; the workflow worker forwards `TSX_TSCONFIG_PATH`).
 *
 * Run (PowerShell, from D:\dsh-devframe):
 *   $env:TSX_TSCONFIG_PATH='D:\dsh-devframe\tsconfig.base.json'
 *   node --import tsx/esm .agents/devframe/v14/remaining/consumer-draft/b6-background-workflow-acceptance.ts
 */

import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import type { ToolDefinition } from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import LlmRuntime, { LlmAdapter, ToolCallId } from '@deepseek-ai/dsh-llm'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import LocalJobRegistry from '@deepseek-ai/dsh-jobs-local'
import SubagentRuntime from '@deepseek-ai/dsh-subagent'
import type { ResolvedSubagentStartRequest, SubagentProvider, SubagentResult, SubagentRun } from '@deepseek-ai/dsh-subagent'
import WorkerThreadWorkflowEngine from '@deepseek-ai/dsh-workflow-worker-thread'
import * as ToolWorkflow from '@deepseek-ai/dsh-tool-workflow'
import * as ToolJobs from '@deepseek-ai/dsh-tool-jobs'

/** Any model request during this acceptance is a defect: the transports are scripted. */
class SilentAdapter extends LlmAdapter {
  override async resolveModel(provider: string, model: string) { return { provider, id: model, name: model } }

  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    throw new Error(`Unexpected model request ${String(options.sessionId)}`)
  }
}

interface ChildGate {
  readonly promise: Promise<SubagentResult>
  readonly complete: () => void
  readonly abort: () => void
  entered: boolean
  enteredAt: string | undefined
}

const makeGate = (): ChildGate => {
  let settle!: (result: SubagentResult) => void
  const gate: ChildGate = {
    promise: new Promise<SubagentResult>((resolve) => { settle = resolve }),
    complete: () => undefined,
    abort: () => undefined,
    entered: false,
    enteredAt: undefined,
  }
  const childLine: SubagentResult = {
    output: [{ type: 'text', text: 'acceptance-child-line' }],
    stopReason: 'completed',
  }
  gate.complete = () => settle(childLine)
  gate.abort = () => settle({ output: [], stopReason: 'aborted' })
  return gate
}

const check = (ok: boolean, message: string): void => {
  if (!ok) throw new Error(`ACCEPTANCE FAILURE: ${message}`)
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => { setTimeout(resolve, ms) })

const WORKFLOW_SCRIPT = 'const line = await agent(\'produce the acceptance line\')\nreturn { child: line }'

async function main(): Promise<void> {
  const root = await mkdtemp(join(tmpdir(), 'b6-workflow-acceptance-'))
  const ctx = new Context()
  try {
    const modules = new Map<string, unknown>([
      ['@deepseek-ai/dsh-llm', LlmRuntime],
      ['@deepseek-ai/dsh-session', SessionStore],
      ['@deepseek-ai/dsh-session-persistence-jsonl', JsonlSessionPersistence],
      ['@deepseek-ai/dsh-system-prompt', SystemPrompt],
      ['@deepseek-ai/dsh-tools', ToolRuntime],
      ['@deepseek-ai/dsh-agent', AgentRegistry],
      ['@deepseek-ai/dsh-agent-loop', AgentLoop],
      ['@deepseek-ai/dsh-storage', Storage],
      ['@deepseek-ai/dsh-storage-json', StorageJson],
      ['@deepseek-ai/dsh-storage-domain', StorageDomain],
      ['@deepseek-ai/dsh-jobs-local', LocalJobRegistry],
      ['@deepseek-ai/dsh-subagent', SubagentRuntime],
      ['@deepseek-ai/dsh-workflow-worker-thread', WorkerThreadWorkflowEngine],
      ['@deepseek-ai/dsh-tool-workflow', ToolWorkflow],
      ['@deepseek-ai/dsh-tool-jobs', ToolJobs],
    ])
    const settings: Record<string, unknown> = {
      '@deepseek-ai/dsh-agent-loop': { agents: [] },
      '@deepseek-ai/dsh-session-persistence-jsonl': { root: join(root, 'sessions'), compression: 'none', writeBatchMaxDelayMs: 1 },
      '@deepseek-ai/dsh-storage-json': { root: join(root, 'storage') },
      '@deepseek-ai/dsh-storage-domain': { backend: 'json' },
      '@deepseek-ai/dsh-workflow-worker-thread': { provider: 'acceptance' },
    }
    const configPath = join(root, 'cordis.yml')
    await writeFile(configPath, JSON.stringify([...modules.keys()].map(name => ({ name, config: settings[name] }))))
    ctx.baseUrl = pathToFileURL(root).href + '/'
    await ctx.plugin(Loader)
    ctx.loader.builtins.include = Include
    ctx.loader.internal = {
      version: 'v2',
      async import(specifier: string) {
        if (!modules.has(specifier)) throw new Error(`Unexpected Loader import ${specifier}`)
        return modules.get(specifier)
      },
    } as unknown as NonNullable<typeof ctx.loader.internal>
    await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
    await ctx.loader.await()
    check([...ctx.loader.entries()].filter(entry => entry.fiber === undefined && !entry.disabled).length === 0,
      'every mounted row resolved (no unresolved fiber)')

    // One job controller at the root scope serves every owner, so the
    // background start below is accepted without a per-agent controller.
    ctx.jobs.attachController('b6-acceptance')

    // Scripted child transport: the workflow engine's agent() calls land here.
    // Each background workflow consumes exactly one gate, held by this protocol
    // until step (c)/(d) releases or aborts it.
    const gates: ChildGate[] = []
    let childSeq = 0
    const provider: SubagentProvider = {
      name: 'acceptance',
      capabilities: { agentOptions: false, outputSchema: false, depthLimit: false, toolFilter: false, persona: false },
      inheritsParentContext: false,
      async start(request: ResolvedSubagentStartRequest): Promise<SubagentRun> {
        const gate = gates.shift()
        if (gate === undefined) throw new Error('no staged child gate for the acceptance run')
        gate.entered = true
        gate.enteredAt = new Date().toISOString()
        void request
        const id = SessionId(`acceptance-child-${++childSeq}`)
        return {
          id,
          localAgent: undefined,
          result: gate.promise,
          dispose: async () => { gate.abort() },
        }
      },
    }
    ctx.subagents.registerProvider(provider)

    ctx.llm.registerAdapter(['acceptance-silent'], new SilentAdapter())
    const parent = (await ctx.agents.create({
      sessionId: SessionId('b6-parent'),
      meta: { cwd: root },
    })).agent

    const runTool = async (name: string, args: object) => await ctx.tools.execute({
      signal: new AbortController().signal, callId: ToolCallId(`b6-${name}-${Math.random().toString(36).slice(2)}`),
      name, arguments: args, agent: parent,
    })

    const liveDefinition = (name: string): ToolDefinition => {
      const definition = ctx.tools.get(name)
      check(definition !== undefined, `live tool registry carries ${name}`)
      return definition!
    }

    // ── Step (a): the live service tool list, not source inference ──────────
    const workflow = liveDefinition('workflow')
    const runInBackground = (workflow.parameters as { properties?: Record<string, { type?: string }> }).properties
      ?.run_in_background
    check(runInBackground !== undefined && runInBackground.type === 'boolean',
      `workflow's live schema carries a top-level boolean run_in_background (got ${JSON.stringify(runBackgroundReport(runInBackground))})`)
    for (const name of ['job_output', 'job_list', 'job_kill']) {
      const jobTool = liveDefinition(name)
      check(jobTool.parameters !== undefined, `${name} is registered as a model-facing tool`)
    }
    console.log('[a] live tool schemas: workflow.run_in_background (boolean, top-level) + job_output/job_list/job_kill present')

    // ── Step (b): background start returns a jobId immediately ──────────────
    const gate = makeGate()
    gates.push(gate)
    const started = await runTool('workflow', {
      meta: { name: 'b6-acceptance', description: 'Acceptance workflow: one child, released by the protocol.' },
      script: WORKFLOW_SCRIPT,
      run_in_background: true,
    })
    const returnedAt = new Date().toISOString()
    check(started.isError !== true, `background workflow start succeeds: ${JSON.stringify(started).slice(0, 400)}`)
    const rawJobId = (started.value as { jobId?: unknown } | undefined)?.jobId
    check(typeof rawJobId === 'string' && rawJobId.length > 0, `start returns a non-empty string jobId (got ${JSON.stringify(started.value)})`)
    const jobId = rawJobId as string
    console.log(`[b] run_in_background: true returned jobId ${jobId} at ${returnedAt}`)

    // ── Step (c): the parent continues while the job is provably non-terminal ─
    // The provider shifted this same gate object when the engine's agent()
    // call reached it; the local reference stays authoritative.
    const waitStart = Date.now()
    while (!gate.entered && Date.now() - waitStart < 20_000) await sleep(100)
    if (!gate.entered) {
      const diagnostic = await runTool('job_output', { job_id: jobId })
      throw new Error(`ACCEPTANCE FAILURE: the child never reached the transport; job diagnostic: ${JSON.stringify(diagnostic).slice(0, 600)}`)
    }
    const enteredAt = staged.enteredAt!
    const runningRead = await runTool('job_output', { job_id: jobId })
    check(runningRead.isError !== true, `non-blocking job_output reads the live job: ${JSON.stringify(runningRead).slice(0, 400)}`)
    const runningStatus = (runningRead.value as { job: { status: string } }).job.status
    check(runningStatus === 'running', `job is non-terminal while the child gate is held (got ${runningStatus})`)
    const runningCheckedAt = new Date().toISOString()
    // The overlap is now pinned: the tool call returned, and the job is still
    // running with the child held mid-flight. Only then does the protocol
    // release the child.
    staged.complete()
    const releasedAt = new Date().toISOString()
    const collected = await runTool('job_output', { job_id: jobId, wait: true, timeout_ms: 30_000 })
    check(collected.isError !== true, `blocking job_output collects the settled job: ${JSON.stringify(collected).slice(0, 400)}`)
    const settled = collected.value as { text: string; job: { status: string } }
    check(settled.job.status === 'completed', `job settles completed (got ${settled.job.status})`)
    check(settled.text.includes('acceptance-child-line'), `job output carries the child result: ${settled.text.slice(0, 300)}`)
    const completedAt = new Date().toISOString()
    check(returnedAt < enteredAt && enteredAt <= runningCheckedAt && runningCheckedAt < releasedAt
      && releasedAt <= completedAt,
      `timestamps prove parent continuation before the child settled: returned=${returnedAt} entered=${enteredAt} `
        + `runningChecked=${runningCheckedAt} released=${releasedAt} completed=${completedAt}`)
    console.log(`[c] parent continued: returned=${returnedAt} < childEntered=${enteredAt} <= runningChecked=${runningCheckedAt} `
      + `< released=${releasedAt} <= completed=${completedAt}; output carried the child result`)

    // ── Step (d): job_kill cancels a second background workflow ─────────────
    const killGate = makeGate()
    gates.push(killGate)
    const killStarted = await runTool('workflow', {
      meta: { name: 'b6-acceptance-kill', description: 'Acceptance workflow cancelled by job_kill.' },
      script: WORKFLOW_SCRIPT,
      run_in_background: true,
    })
    check(killStarted.isError !== true, `second background start succeeds: ${JSON.stringify(killStarted).slice(0, 400)}`)
    const rawKillJobId = (killStarted.value as { jobId?: unknown } | undefined)?.jobId
    check(typeof rawKillJobId === 'string' && rawKillJobId.length > 0, `second start returns a non-empty string jobId (got ${JSON.stringify(killStarted.value)})`)
    const killJobId = rawKillJobId as string
    const killWaitStart = Date.now()
    while (!killGate.entered && Date.now() - killWaitStart < 20_000) await sleep(100)
    check(killGate.entered, `kill-path child reached the transport before job_kill`)
    const killed = await runTool('job_kill', { job_id: killJobId, reason: 'acceptance cleanup' })
    check(killed.isError !== true, `job_kill requests cancellation: ${JSON.stringify(killed).slice(0, 400)}`)
    check((killed.value as { outcome: string }).outcome === 'cancellation-requested', 'job_kill reports cancellation-requested')
    const killedRead = await runTool('job_output', { job_id: killJobId, wait: true, timeout_ms: 30_000 })
    check(killedRead.isError !== true, `blocked read collects the killed job: ${JSON.stringify(killedRead).slice(0, 400)}`)
    const killedStatus = (killedRead.value as { job: { status: string } }).job.status
    check(killedStatus === 'killed', `killed job settles terminal as killed (got ${killedStatus})`)
    const listed = await runTool('job_list', {})
    const statuses = (listed.value as Array<{ id: string; status: string }>)
    check(statuses.length === 2, `job_list shows both jobs (got ${statuses.length})`)
    check(statuses.every(job => job.status === 'completed' || job.status === 'killed'),
      `no lingering non-terminal job after cleanup: ${JSON.stringify(statuses)}`)
    console.log(`[d] job_kill settled ${killJobId} as killed; job_list shows both jobs terminal`)

    console.log('B6 BACKGROUND-WORKFLOW ACCEPTANCE: ALL FOUR STEPS PASSED')
  } finally {
    await ctx.fiber.dispose()
    await rm(root, { recursive: true, force: true, maxRetries: 20, retryDelay: 25 })
  }
}

function runBackgroundReport(spec: { type?: string } | undefined): string {
  return spec === undefined ? 'absent' : JSON.stringify(spec)
}

main().then(() => { process.exitCode = 0 }, (error: unknown) => {
  console.error(error)
  process.exitCode = 1
})
