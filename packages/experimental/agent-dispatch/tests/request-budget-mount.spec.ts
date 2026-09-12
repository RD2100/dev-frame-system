/** Candidate request admission must be active before the dispatch consumer reports ready. */

import { afterEach, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import SessionStore from '@deepseek-ai/dsh-session'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { apply } from '../src/consumer.ts'

const contexts: Context[] = []

afterEach(async () => {
  await Promise.all(contexts.splice(0).map(ctx => ctx.fiber.dispose()))
})

it('waits for the candidate request-budget child before mounting the dispatch face', async () => {
  const ctx = new Context()
  contexts.push(ctx)
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)

  const release = Promise.withResolvers<undefined>()
  let candidateMountSettled = false
  const originalPlugin = ctx.plugin.bind(ctx) as (plugin: unknown, ...args: unknown[]) => ReturnType<Context['plugin']>
  ctx.plugin = (plugin: unknown, ...args: unknown[]) => {
    if (typeof plugin === 'object' && plugin !== null
      && (plugin as { id?: unknown }).id === 'candidate-request-budget') {
      return release.promise.then(() => { candidateMountSettled = true }) as unknown as ReturnType<Context['plugin']>
    }
    return originalPlugin(plugin, ...args)
  }

  let applied = false
  const applying = apply(ctx, { candidateRootSessionId: 'candidate-root' }).then(() => { applied = true })
  await Promise.resolve()
  await Promise.resolve()

  expect(applied).toBe(false)
  expect(candidateMountSettled).toBe(false)
  expect(ctx.tools.get('agent_dispatch')).toBeUndefined()

  release.resolve(undefined)
  await applying

  expect(applied).toBe(true)
  expect(candidateMountSettled).toBe(true)
  expect(ctx.tools.get('agent_dispatch')).toBeDefined()
})
