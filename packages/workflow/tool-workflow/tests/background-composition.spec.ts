import { describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import AgentRegistry, { type Agent } from '@deepseek-ai/dsh-agent'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import * as ToolJobs from '@deepseek-ai/dsh-tool-jobs'
import LocalJobRegistry from '@deepseek-ai/dsh-jobs-local'
import { JobId } from '@deepseek-ai/dsh-jobs'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import { Session, SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SubagentRuntime, { type SubagentResult } from '@deepseek-ai/dsh-subagent'
import WorkerThreadWorkflowEngine from '@deepseek-ai/dsh-workflow-worker-thread'
import * as ToolWorkflow from '../src/index.ts'

describe('background workflow through Loader and a real worker', () => {
  it.each(['complete', 'cancel'] as const)('allows parent work before %s and waits for child disposal', async (outcome) => {
    const ctx = new Context()
    const childResult = Promise.withResolvers<SubagentResult>()
    const childStarted = Promise.withResolvers<undefined>()
    const disposeStarted = Promise.withResolvers<undefined>()
    const disposeAllowed = Promise.withResolvers<undefined>()
    let childDisposed = false
    try {
      await ctx.plugin(Loader)
      Object.assign(ctx.loader.builtins, {
        'test-agents': AgentRegistry,
        'test-prompt': SystemPrompt,
        'test-tools': ToolRuntime,
        'test-projections': SessionProjectionRegistry,
        'test-subagents': SubagentRuntime,
        'test-jobs': LocalJobRegistry,
        'test-job-tools': ToolJobs,
        'test-workflow-engine': WorkerThreadWorkflowEngine,
        'test-workflow-tool': ToolWorkflow,
      })
      for (const name of ['agents', 'prompt', 'tools', 'projections', 'subagents', 'jobs']) {
        await ctx.loader.create({ name: `cordis:test-${name}` })
      }
      ctx.subagents.registerProvider({
        name: 'spawn',
        inheritsParentContext: false,
        capabilities: { agentOptions: true, outputSchema: true, depthLimit: true, toolFilter: true, persona: true },
        async start(request) {
          request.signal.addEventListener('abort', () => {
            childResult.resolve({ output: [], stopReason: 'aborted' })
          }, { once: true })
          childStarted.resolve(undefined)
          return {
            id: SessionId('background-composition-child'),
            result: childResult.promise,
            localAgent: undefined,
            async dispose() {
              disposeStarted.resolve(undefined)
              await disposeAllowed.promise
              childDisposed = true
            },
          }
        },
      })
      await ctx.loader.create({ name: 'cordis:test-job-tools', config: { completionDelivery: 'quiet' } })
      await ctx.loader.create({ name: 'cordis:test-workflow-engine' })
      await ctx.loader.create({ name: 'cordis:test-workflow-tool' })
      await ctx.loader.await()
      const ownerFiber = ctx.plugin(() => {})
      const session = Session.create(SessionId('background-composition-owner'))
      const parent = { id: session.id, session, options: {}, ctx: ownerFiber.ctx, status: 'idle', inject: vi.fn() } as unknown as Agent
      ctx.agents.register(parent)
      let call = 0
      const execute = (name: string, args: unknown) => ctx.tools.execute({
        name, arguments: args, callId: ToolCallId(`composition-${++call}`),
        signal: new AbortController().signal, agent: parent,
      })
      const started = await execute('workflow', {
        meta: { name: 'background-composition', description: 'controlled child' },
        script: "return await agent('controlled')", run_in_background: true,
      })
      expect(started.isError).toBe(false)
      if (started.isError) throw new Error(JSON.stringify(started.error))
      expect(started.value).toEqual({ jobId: 'workflow-1' })
      await childStarted.promise
      const listing = await execute('job_list', {})
      expect(listing.isError).toBe(false)
      expect(ctx.jobs.list(parent)[0]?.status).toBe('running')
      if (outcome === 'cancel') {
        expect((await execute('job_kill', { job_id: 'workflow-1', reason: 'stop requested by owner' })).isError).toBe(false)
      } else {
        childResult.resolve({ output: [{ type: 'text', text: 'child-result' }], stopReason: 'completed' })
      }
      await disposeStarted.promise
      expect(childDisposed).toBe(false)
      expect(['running', 'stopping']).toContain(ctx.jobs.list(parent)[0]?.status)
      expect(session.snapshotEvents().some(event => event.type === 'tool-workflow/run-end')).toBe(false)
      disposeAllowed.resolve(undefined)
      const output = await execute('job_output', { job_id: 'workflow-1', wait: true, timeout_ms: 10_000 })
      expect(output.isError).toBe(false)
      expect(childDisposed).toBe(true)
      expect(ctx.jobs.read(JobId('workflow-1'), parent).snapshot.status).toBe(outcome === 'complete' ? 'completed' : 'killed')
      if (outcome === 'complete') expect(JSON.stringify(output.content)).toContain('child-result')
      else expect(JSON.stringify(output.content)).toContain('stop requested by owner')
      expect(session.snapshotEvents().map(event => event.type)).toEqual([
        'tool-workflow/run-start', 'tool-workflow/agent-start', 'tool-workflow/agent-end', 'tool-workflow/run-end',
      ])
    } finally {
      childResult.resolve({ output: [], stopReason: 'aborted' })
      disposeAllowed.resolve(undefined)
      await ctx.fiber.dispose()
    }
  })
})
