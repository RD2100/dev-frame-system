/** The `@subagent` mention source: registry-truth candidates, literal pick text, lexicon roll. */
import { describe, expect, it } from 'vitest'
import type { InputTriggerSource } from '@deepseek-ai/dsh-client-ui-input-trigger/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { createSubagentMentionSource, type ReadProviders } from '../src/client/mentions.ts'

const REGISTRY = ['codex', 'claude-code', 'cursor'] as const
const session = { sessionId: 'session-1' as SessionId }

/** A request matching the pipeline's candidate fetch (only query and signal matter here). */
function candidateRequest(query: string, signal: AbortSignal = new AbortController().signal) {
  return { query, signal, position: 'inline' as const, drilled: false }
}

function sourceOver(registry: () => readonly string[]): InputTriggerSource {
  return createSubagentMentionSource(registry as ReadProviders)
}

describe('@subagent mention source', () => {
  it('serves the live registry as candidates, in registry order', async () => {
    const source = sourceOver(() => REGISTRY)
    await expect(source.candidates(session, candidateRequest(''))).resolves.toEqual([
      { name: 'codex' },
      { name: 'claude-code' },
      { name: 'cursor' },
    ])
  })

  it('completes typed queries against the directory', async () => {
    const source = sourceOver(() => REGISTRY)
    await expect(source.candidates(session, candidateRequest('codex'))).resolves.toEqual([{ name: 'codex' }])
    await expect(source.candidates(session, candidateRequest('cl'))).resolves.toEqual([{ name: 'claude-code' }])
    await expect(source.candidates(session, candidateRequest('urs'))).resolves.toEqual([{ name: 'cursor' }])
    await expect(source.candidates(session, candidateRequest('gemini'))).resolves.toEqual([])
  })

  it('picks insert the literal mention text for every provider', async () => {
    const source = sourceOver(() => REGISTRY)
    for (const name of REGISTRY) {
      expect(source.onPick({
        candidate: { name },
        session,
        position: 'inline',
        via: 'menu',
        action: 'pick',
        span: { start: 0, end: 1, draftRev: 0 },
      })).toEqual({ text: `@${name} ` })
    }
  })

  it('keeps the lexicon undefined until a read settles, then tracks registry changes', async () => {
    let registry: readonly string[] = ['codex']
    const source = sourceOver(() => registry)
    const notifications: number[] = []
    const unsubscribe = source.subscribeLexicon?.(session, () => { notifications.push(notifications.length) })
    expect(source.lexicon?.(session)).toBeUndefined()
    await source.candidates(session, candidateRequest(''))
    expect(source.lexicon?.(session)).toEqual(['codex'])
    // The first settled read is itself a change (undefined roll -> names), so
    // the subscriber learns the decoration is live.
    expect(notifications).toEqual([0])
    registry = ['codex', 'cursor']
    await source.candidates(session, candidateRequest(''))
    expect(source.lexicon?.(session)).toEqual(['codex', 'cursor'])
    expect(notifications).toEqual([0, 1])
    await source.candidates(session, candidateRequest(''))
    expect(notifications).toEqual([0, 1])
    unsubscribe?.()
  })

  it('rejects candidates when the directory read fails (group-drop policy)', async () => {
    const source = sourceOver(() => {
      throw new Error('gateway/internal: offline')
    })
    await expect(source.candidates(session, candidateRequest(''))).rejects.toThrow('gateway/internal')
  })

  it('answers an already-aborted candidate request with no rows', async () => {
    const source = sourceOver(() => REGISTRY)
    const controller = new AbortController()
    controller.abort()
    await expect(source.candidates(session, candidateRequest('', controller.signal))).resolves.toEqual([])
  })

  it('keeps the pipeline identity distinct from the existing @ sources', () => {
    const source = sourceOver(() => REGISTRY)
    expect(source.trigger).toBe('@')
    expect(source.name).toBe('subagent')
    expect(source.order).toBe(2)
  })
})
