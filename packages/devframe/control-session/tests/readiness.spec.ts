import { describe, expect, it } from 'vitest'
import { DevFrameReadinessState } from '../src/readiness.ts'

describe('DevFrame readiness state', () => {
  it('fences stale generation completions and keeps revisions monotonic', () => {
    const state = new DevFrameReadinessState()
    const first = state.begin()
    const second = state.begin()

    expect(first.signal.aborted).toBe(true)
    expect(state.ready(first.generation, 'devframe-global:stale')).toBe(false)
    expect(state.blocked(first.generation, 'CONTROLLER_UNAVAILABLE')).toBe(false)
    expect(state.ready(second.generation, 'devframe-global:current')).toBe(true)
    expect(state.snapshot()).toEqual({
      status: 'ready',
      generation: 2,
      revision: 3,
      sessionId: 'devframe-global:current',
    })
  })

  it('long-polls until a new revision and returns only the bounded snapshot', async () => {
    const state = new DevFrameReadinessState()
    const generation = state.begin()
    const current = state.snapshot()
    const waiting = state.wait(current.revision, new AbortController().signal)

    state.blocked(generation.generation, 'PROFILE_IDENTITY_UNAVAILABLE')

    await expect(waiting).resolves.toEqual({
      status: 'blocked',
      generation: generation.generation,
      revision: current.revision + 1,
      code: 'PROFILE_IDENTITY_UNAVAILABLE',
    })
  })

  it('cancels an in-flight long poll without exposing the abort reason', async () => {
    const state = new DevFrameReadinessState()
    state.begin()
    const abort = new AbortController()
    const waiting = state.wait(state.snapshot().revision, abort.signal)

    abort.abort(new Error('__SECRET__ D:/private/controller'))

    await expect(waiting).rejects.toThrow('DevFrame readiness wait aborted')
    await expect(waiting).rejects.not.toThrow('__SECRET__')
  })

  it('publishes stopping before aborting the generation signal', () => {
    const state = new DevFrameReadinessState()
    const generation = state.begin()

    expect(state.stopping(generation.generation)).toBe(true)
    expect(generation.signal.aborted).toBe(true)
    expect(state.snapshot()).toEqual({
      status: 'stopping',
      generation: generation.generation,
      revision: 2,
    })
    expect(state.ready(generation.generation, 'devframe-global:late')).toBe(false)
  })
})
