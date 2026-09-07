/**
 * C2b HuoshanStreamArgs minimal real replay: one request + one parallel-free
 * tool call through the real huoshan-1 provider, verifying streamed tool-call
 * arguments assemble into valid JSON after the fix. Run from a worktree with
 * the fix installed. Not a chain run; a provider-contract probe.
 * @module harness/streamargs-replay
 */
import { writeFileSync } from 'node:fs'

/** Loader plugin name. */
export const name = 'v14-llmargs-replay'

/** Services the replay driver needs. */
export const inject = [
  'agents',
  'sessions',
  'sessionController',
]

/** Replay evidence path and single-shot task text. */
export interface ReplayConfig {
  /** JSONL evidence file (absolute). */
  evidencePath: string
}

/** Append one evidence line. */
function log(path: string, entry: Record<string, unknown>): void {
  writeFileSync(path, `${JSON.stringify({ at: new Date().toISOString(), ...entry })}\n`, 'utf8')
}

/** Activate: create one session under the standard preset and deliver a task
 * whose only sensible action is one small tool call, then await idle. */
export function apply(ctx: any, config: ReplayConfig): void {
  void (async () => {
    try {
      await ctx.get('loader')?.await()
      const controller = ctx.get('sessionController') as import('@deepseek-ai/dsh-api-session-controller').SessionController | undefined
      if (controller === undefined) throw new Error('replay: sessionController unavailable')
      const created = await controller.create({ cwd: process.cwd(), agentPreset: 'standard' })
      const agent = ctx.agents.get(created.sessionId)
      if (agent === undefined) throw new Error('replay: agent not live')
      log(config.evidencePath, { event: 'agent-created', sessionId: agent.session.id.toString() })
      const { createUserMessage } = await import('@deepseek-ai/dsh-llm')
      agent.followup(createUserMessage({
        content: [{ type: 'text', text: 'Call the cordis_inspect_list tool once with empty arguments, report the provider count, then stop. Do not call any other tool.' }],
        source: { kind: 'user' },
      }))
      await agent.whenIdle()
      await (ctx.get('sessions') as { flush(s: unknown): Promise<void> }).flush(agent.session)
      log(config.evidencePath, { event: 'replay-idle' })
    } catch (error) {
      log(config.evidencePath, { event: 'replay-error', error: String(error instanceof Error ? error.stack : error) })
    }
  })()
}
