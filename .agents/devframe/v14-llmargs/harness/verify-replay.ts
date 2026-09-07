/**
 * C2b ③ real-call probe: one huoshan-1 boot whose single task demands TWO
 * parallel cordis_inspect_query calls in the same turn, one carrying a nested
 * object input — the exact task shape whose streamed fragments chain3
 * corrupted. After task-idle the session log holds the a-d evidence
 * (arguments JSON, rejection absence, turn/end, request/header provider).
 * Modeled on harness/streamargs-replay.ts; logging appends (never truncates)
 * and the boot exits itself through appExit when the probe settles.
 * @module harness/verify-replay
 */
import { appendFileSync } from 'node:fs'

/** Loader plugin name. */
export const name = 'v14-llmargs-verify-replay'

/** Services the replay driver needs. */
export const inject = [
  'agents',
  'sessions',
  'sessionController',
]

/** Replay evidence path and single-shot task text. */
export interface VerifyConfig {
  /** JSONL evidence file (absolute). */
  evidencePath: string
}

/** Append one evidence line. */
function log(path: string, entry: Record<string, unknown>): void {
  appendFileSync(path, `${JSON.stringify({ at: new Date().toISOString(), ...entry })}\n`, 'utf8')
}

/** The single-shot task: two parallel inspect queries, one with nested object input. */
const TASK_TEXT = `你的唯一任务：在同一个回合内同时（并行）发起两次 cordis_inspect_query 工具调用，两次调用都要发，然后停止。
1) 第一次调用参数必须是：platform="host"，provider="Service"，method="listService"，input={"service":"workflowEngine"}（input 必须是 JSON 对象本身，绝不允许把它序列化成字符串）。
2) 第二次调用参数必须是：platform="host"，provider="Builtin"，method="listBuiltins"（不带 input）。
两次工具调用都返回后，最终答复只写两行：每行一个调用的 method 与其结果条目数。不要调用任何其他工具，不要使用 pwsh、read、memory 等工具。`

/** Activate: create one session under the standard preset, deliver the parallel
 * multi-tool task, await idle, flush, then exit the boot with the probe verdict. */
export function apply(ctx: any, config: VerifyConfig): void {
  void (async () => {
    const exit = ctx.get('appExit') as ((code: number) => void) | undefined
    try {
      await ctx.get('loader')?.await()
      const controller = ctx.get('sessionController') as import('@deepseek-ai/dsh-api-session-controller').SessionController | undefined
      if (controller === undefined) throw new Error('verify-replay: sessionController unavailable')
      const created = await controller.create({ cwd: process.cwd(), agentPreset: 'standard' })
      const agent = ctx.agents.get(created.sessionId)
      if (agent === undefined) throw new Error('verify-replay: agent not live')
      log(config.evidencePath, { event: 'agent-created', sessionId: agent.session.id.toString(), agentPreset: created.agentPreset })
      const { createUserMessage } = await import('@deepseek-ai/dsh-llm')
      agent.followup(createUserMessage({
        content: [{ type: 'text', text: TASK_TEXT }],
        source: { kind: 'user' },
      }))
      await agent.whenIdle()
      await (ctx.get('sessions') as { flush(s: unknown): Promise<void> }).flush(agent.session)
      log(config.evidencePath, { event: 'task-idle', sessionId: agent.session.id.toString() })
      exit?.(0)
    } catch (error) {
      log(config.evidencePath, { event: 'verify-error', error: String(error instanceof Error ? error.stack : error) })
      exit?.(1)
    }
  })()
}
