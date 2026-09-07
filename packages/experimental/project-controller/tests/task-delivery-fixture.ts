/** Keyless model scripts and a real filesystem/Git workload for delivery composition tests. */
import { execFile } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import { LlmAdapter, ToolCallId } from '@deepseek-ai/dsh-llm'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type {} from '@deepseek-ai/dsh-experimental-session-identity'

/**
 * Execute bounded Git commands without inheriting credential or Git environment overrides.
 * @param cwd - Actual fixture worktree.
 * @param args - Git argument vector.
 * @returns Trimmed Git output after a successful exit.
 */
export async function workloadGit(cwd: string, ...args: string[]): Promise<string> {
  return (await promisify(execFile)('git', ['-C', cwd, ...args], {
    windowsHide: true, timeout: 15_000, maxBuffer: 1024 * 1024,
    env: Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !/KEY|SECRET|TOKEN|PASSWORD/i.test(key) && !/^GIT_/i.test(key))),
  })).stdout.trim()
}

/**
 * Register a test workload tool; it performs real writes and commits in the actual calling Worker's tree.
 * This fixture does not stand in for coverage of the shipped filesystem or shell tools.
 * @param ctx - Real Loader context with tool and binding registries.
 */
export function applyWorkload(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'fixture_commit', description: 'Write and commit the assigned test workload, or rebase it onto target.',
    parameters: { action: { type: 'string', required: true } },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: { head: { type: 'string', required: true } } },
      render: (_args, value) => [{ type: 'text', text: value.head }],
    },
    async execute(args, exec) {
      const worker = exec.agent === undefined ? undefined : ctx.agentBindings.find(exec.agent.id)
      if (worker?.role !== 'worker' || worker.worktreePath !== exec.agent?.session.header.cwd) {
        throw new Error('Workload requires the actual bound Worker')
      }
      const path = worker.worktreePath!
      if (args.action === 'write') {
        const file = String(worker.sessionId) + '.txt'
        await writeFile(join(path, file), 'implemented\n')
        await workloadGit(path, 'add', file)
        await workloadGit(path, 'commit', '-m', 'Implement ' + String(worker.taskId))
      } else if (args.action === 'rebase') await workloadGit(path, 'rebase', 'target')
      else throw new Error('Unknown workload action')
      return { head: await workloadGit(path, 'rev-parse', 'HEAD') }
    },
    presentCall: () => ({ card: 'generic', title: 'Run test workload' }), presentResult: () => ({ card: 'generic' }),
  }))
}

interface Call { name: string; arguments: object }

/** Script only model responses; first Worker requests overlap before either tool executes. */
export class DeliveryAdapter extends LlmAdapter {
  readonly entered: string[] = []
  maxActive = 0
  private active = 0
  private readonly both = Promise.withResolvers<undefined>()
  private readonly calls = new Map<string, (Call | undefined)[]>([
    ['worker-a', [{ name: 'fixture_commit', arguments: { action: 'write' } },
      { name: 'project_deliver', arguments: { taskId: 'task-a' } }, undefined]],
    ['worker-b', [{ name: 'fixture_commit', arguments: { action: 'write' } },
      { name: 'project_deliver', arguments: { taskId: 'task-b' } }, undefined]],
  ])
  private readonly seen = new Set<string>()
  private sequence = 0

  /**
   * Queue another actual Agent turn after the preceding scripted turn is idle.
   * @param sessionId - Actual Agent Session identity.
   * @param calls - Model tool calls for that turn.
   */
  enqueue(sessionId: string, calls: Call[]): void { this.calls.set(sessionId, [...calls, undefined]) }

  override async resolveModel(provider: string, model: string) { return { provider, id: model, name: model } }

  async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const id = String(options.sessionId)
    if (!this.seen.has(id) && id.startsWith('worker-')) {
      this.seen.add(id)
      this.entered.push(id)
      this.maxActive = Math.max(this.maxActive, ++this.active)
      if (this.entered.length === 2) this.both.resolve(undefined)
      const aborted = Promise.withResolvers<never>()
      const abort = () => { aborted.reject(new Error('Delivery model request cancelled')) }
      options.signal?.addEventListener('abort', abort, { once: true })
      try {
        if (options.signal?.aborted) abort()
        await Promise.race([this.both.promise, aborted.promise])
      } finally { options.signal?.removeEventListener('abort', abort); this.active-- }
    }
    const queue = this.calls.get(id)
    if (queue === undefined || queue.length === 0) throw new Error(`Unscripted model request ${id}`)
    const call = queue.shift()
    if (call === undefined) {
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield { type: 'block-end', index: 0, block: { type: 'text', text: 'Turn finished' } }
      yield { type: 'finish', reason: { kind: 'stop' } }
    } else {
      yield { type: 'block-start', index: 0, blockType: 'tool-call' }
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id: ToolCallId(`delivery-${this.sequence++}`),
        name: call.name, arguments: JSON.stringify(call.arguments) } }
      yield { type: 'finish', reason: { kind: 'tool-calls' } }
    }
  }
}
