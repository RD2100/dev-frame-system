/**
 * Resource-audit experiment — observes the REAL worker-thread termination face
 * on the normal success path, which no existing test asserts:
 *   1. the engine's `dispose()` awaits `worker.terminate()` (host.ts:243,
 *      "the thread never outlives its run"), so the Worker's own `exit` event
 *      is the authoritative in-process observable of thread termination;
 *   2. `process.getActiveResourcesInfo()` corroboration around the run.
 * Read-only over the repo source; evidence only. Exits 0 when the exit face
 * is observed after dispose() resolves.
 *
 * Usage: node --import tsx/esm resource-audit-worker-exit.ts
 */

import { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import SubagentRuntime from '@deepseek-ai/dsh-subagent'
import type { SubagentProvider } from '@deepseek-ai/dsh-subagent'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import WorkerThreadWorkflowEngine from '../../../../../packages/workflow/workflow-worker-thread/src/index.ts'
import { SessionId } from '@deepseek-ai/dsh-session'

const fail = (message: string): never => { throw new Error(`RESOURCE AUDIT FAILURE: ${message}`) }

const ctx = new Context()
await ctx.plugin(SessionProjectionRegistry)
const subagents = await ctx.plugin(SubagentRuntime)
const provider: SubagentProvider = {
  name: 'audit-stub',
  capabilities: { agentOptions: true, outputSchema: true, depthLimit: true, toolFilter: true, persona: false },
  inheritsParentContext: false,
  start: () => Promise.reject(new Error('audit script must not start a child')),
}
ctx.subagents.registerProvider(provider)
const engine = await ctx.plugin(WorkerThreadWorkflowEngine, { provider: 'audit-stub' })
const parent = { id: SessionId('audit-parent'), options: {} } as unknown as Agent

const workerResources = (): number => process.getActiveResourcesInfo().filter(kind => kind === 'Worker').length

const run = ctx.workflowEngine.start({
  script: 'return 6 * 7',
  meta: { name: 'resource-audit', description: 'observe the normal-path worker exit face' },
  parent,
})
const worker = (run as unknown as { worker: import('node:worker_threads') }).worker
checkWorker(worker, 'engine handle exposes the real Worker')
let exitCode: number | undefined
let exitAt = 0
worker.once('exit', (code: number) => { exitCode = code; exitAt = Date.now() })

const beforeDispose = workerResources()
const result = await run.result
if (result.stopReason !== 'completed' || result.value !== 42) fail(`unexpected result ${JSON.stringify(result)}`)
const resultAt = Date.now()
const exitObserved = new Promise<number>(resolve => worker.once('exit', resolve))
await run.dispose()
const disposedAt = Date.now()
const code = await Promise.race([
  exitObserved,
  new Promise<never>((_, reject) => setTimeout(() => reject(new Error('worker exit not observed within 5000ms of dispose()')), 5000).unref()),
])
const afterDispose = workerResources()

console.log(`[evidence] normal path: result completed at t=${resultAt}; dispose() resolved at t=${disposedAt}`)
console.log(`[evidence] worker exit event OBSERVED after dispose(): exit code ${code ?? exitCode} at t=${exitAt || disposedAt} `
  + `(the engine's terminate() took the real thread down)`)
console.log(`[evidence] active resources tagged 'Worker': before dispose=${beforeDispose}, after dispose=${afterDispose} `
  + `(corroboration only: the tag set is Node-version dependent)`)
console.log('RESOURCE AUDIT: NORMAL-PATH WORKER EXIT FACE PROVEN (an assertion no existing test makes)')

function checkWorker(worker: unknown, message: string): void {
  if (worker === undefined || worker === null || typeof (worker as { once?: unknown }).once !== 'function') {
    fail(`${message}: got ${String(worker)}`)
  }
}

await engine.dispose()
await subagents.dispose()
process.exitCode = 0
