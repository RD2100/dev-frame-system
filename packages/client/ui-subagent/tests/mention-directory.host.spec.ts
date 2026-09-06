/** The `subagents/providers` directory face: registry-truth roster over the wire. */
import { Context } from '@deepseek-ai/cordis'
import SubagentRuntime, {
  NO_START_CAPABILITIES,
  type SubagentProvider,
} from '@deepseek-ai/dsh-subagent'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import { describe, expect, it } from 'vitest'

function provider(name: string): SubagentProvider {
  return {
    name,
    capabilities: NO_START_CAPABILITIES,
    inheritsParentContext: false,
    start: () => {
      throw new Error('not started by this test')
    },
  }
}

async function runtimeWith(names: readonly string[]): Promise<{ runtime: SubagentRuntime; disposeLast: () => void }> {
  const ctx = new Context()
  const runtime = new SubagentRuntime(ctx)
  const disposers = names.map(name => runtime.registerProvider(provider(name)))
  return {
    runtime,
    disposeLast: () => disposers.at(-1)?.(),
  }
}

describe('subagent provider directory face', () => {
  it('serves the live registry in insertion order, not an alphabetical roster', async () => {
    const { runtime } = await runtimeWith(['claude-code', 'codex'])
    expect(runtime.list()).toEqual(['claude-code', 'codex'])
  })

  it('tracks registry reality: later registrations appear and disposals withdraw', async () => {
    const { runtime, disposeLast } = await runtimeWith(['codex'])
    expect(runtime.list()).toEqual(['codex'])
    const disposeCursor = runtime.registerProvider(provider('cursor'))
    expect(runtime.list()).toEqual(['codex', 'cursor'])
    disposeCursor()
    disposeLast()
    expect(runtime.list()).toEqual([])
  })

  it('exposes the read as the subagents/providers Remote endpoint', async () => {
    const { runtime } = await runtimeWith(['codex'])
    expect(remoteMethods(runtime)).toContainEqual({
      method: 'list',
      exportName: 'providers',
      invocation: { kind: 'direct' },
    })
  })
})
