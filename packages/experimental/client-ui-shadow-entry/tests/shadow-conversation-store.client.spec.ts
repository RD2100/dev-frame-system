// @vitest-environment jsdom
/** The conversation store: tail load, incremental poll, failure surface, and latest-read ownership. */

import { describe, expect, it } from 'vitest'
import { RemoteError, type RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ShadowConversationPage, ShadowConversationReadInput } from '@deepseek-ai/dsh-experimental-shadow-controller'
import { ShadowConversationController } from '../src/client/shadow-conversation-store.ts'
import type { ShadowConversationPort } from '../src/client/shadow-conversation-store.ts'

const USER_ROW = { seq: 4, role: 'user' as const, text: 'hello', at: '2026-09-10T12:00:00.000Z' }
const REPLY_ROW = { seq: 5, role: 'shadow' as const, text: 'hi there', at: '2026-09-10T12:00:05.000Z' }

const OK = (messages: ShadowConversationPage['messages'], cursor: number): RemoteResult<ShadowConversationPage> =>
  ({ ok: true, value: { messages, cursor } })

const FAIL: RemoteResult<ShadowConversationPage> =
  { ok: false, error: new RemoteError('gateway/internal', 'read failed', {}) }

/** A port from one answer per call; running past the script fails loud. */
function scripted(answers: Array<RemoteResult<ShadowConversationPage> | Promise<RemoteResult<ShadowConversationPage>>>): {
  port: ShadowConversationPort
  calls: ShadowConversationReadInput[]
} {
  const calls: ShadowConversationReadInput[] = []
  let index = 0
  const port: ShadowConversationPort = (request) => {
    calls.push(request)
    const answer = answers[index]
    // The transport face always settles with a RemoteResult; a scripted port
    // asked for more answers than it holds is a test bug, never an absence.
    if (answer === undefined) throw new Error('scripted conversation port ran past its answers')
    index += 1
    return Promise.resolve(answer)
  }
  return { port, calls }
}

describe('the Shadow conversation store', () => {
  it('loads the tail and publishes the rows plus the cursor', async () => {
    const { port, calls } = scripted([OK([USER_ROW], 5)])
    const controller = new ShadowConversationController(port)
    await controller.loadTail()
    expect(calls).toEqual([{}])
    expect(controller.store.getSnapshot()).toEqual({ messages: [USER_ROW], cursor: 5, error: undefined })
  })

  it('appends only the new rows on an incremental poll', async () => {
    const { port, calls } = scripted([OK([USER_ROW], 4), OK([REPLY_ROW], 9)])
    const controller = new ShadowConversationController(port)
    await controller.loadTail()
    await controller.poll()
    expect(calls).toEqual([{}, { after: 4 }])
    expect(controller.store.getSnapshot()).toEqual({ messages: [USER_ROW, REPLY_ROW], cursor: 9, error: undefined })
  })

  it('falls back to a tail load when no cursor has settled yet', async () => {
    const { port, calls } = scripted([OK([USER_ROW], 2)])
    const controller = new ShadowConversationController(port)
    await controller.poll()
    expect(calls).toEqual([{}])
    expect(controller.store.getSnapshot()).toEqual({ messages: [USER_ROW], cursor: 2, error: undefined })
  })

  it('keeps the rows and publishes the failure when a read fails', async () => {
    const { port } = scripted([OK([USER_ROW], 4), FAIL])
    const controller = new ShadowConversationController(port)
    await controller.loadTail()
    await controller.poll()
    expect(controller.store.getSnapshot()).toEqual({ messages: [USER_ROW], cursor: 4, error: 'read failed' })
    // The next poll retries the same cursor.
    const { port: retryPort } = scripted([OK([USER_ROW], 4), OK([REPLY_ROW], 9)])
    const retried = new ShadowConversationController(retryPort)
    await retried.loadTail()
    await retried.poll()
    expect(retried.store.getSnapshot().messages).toEqual([USER_ROW, REPLY_ROW])
  })

  it('lets the latest issued read own the store', async () => {
    let releaseFirst: (value: RemoteResult<ShadowConversationPage>) => void = () => {}
    const first = new Promise<RemoteResult<ShadowConversationPage>>((resolve) => { releaseFirst = resolve })
    const calls: ShadowConversationReadInput[] = []
    const port: ShadowConversationPort = (request) => {
      calls.push(request)
      return calls.length === 1 ? first : Promise.resolve(OK([REPLY_ROW], 9))
    }
    const controller = new ShadowConversationController(port)
    const pending = controller.loadTail()
    await controller.loadTail()
    releaseFirst(OK([USER_ROW], 4))
    await pending
    expect(controller.store.getSnapshot()).toEqual({ messages: [REPLY_ROW], cursor: 9, error: undefined })
  })

  it('lets a later read own a superseded poll', async () => {
    let releasePoll: (value: RemoteResult<ShadowConversationPage>) => void = () => {}
    const hanging = new Promise<RemoteResult<ShadowConversationPage>>((resolve) => { releasePoll = resolve })
    const calls: ShadowConversationReadInput[] = []
    const port: ShadowConversationPort = (request) => {
      calls.push(request)
      if (calls.length === 1) return Promise.resolve(OK([USER_ROW], 4))
      return calls.length === 2 ? hanging : Promise.resolve(OK([REPLY_ROW], 9))
    }
    const controller = new ShadowConversationController(port)
    await controller.loadTail()
    const polled = controller.poll()
    // A tail load issued after the poll wins; the late poll must not append.
    await controller.loadTail()
    releasePoll(OK([USER_ROW], 4))
    await polled
    expect(calls).toEqual([{}, { after: 4 }, {}])
    expect(controller.store.getSnapshot()).toEqual({ messages: [REPLY_ROW], cursor: 9, error: undefined })
  })

  it('the failed poll before any tail leaves the empty state with the failure', async () => {
    const { port } = scripted([FAIL])
    const controller = new ShadowConversationController(port)
    await controller.poll()
    expect(controller.store.getSnapshot()).toEqual({ messages: [], cursor: undefined, error: 'read failed' })
  })

  it('polls an empty tail again with the same cursor and stays empty', async () => {
    const { port, calls } = scripted([OK([], 0), OK([], 0)])
    const controller = new ShadowConversationController(port)
    await controller.loadTail()
    await controller.poll()
    expect(calls).toEqual([{}, { after: 0 }])
    expect(controller.store.getSnapshot()).toEqual({ messages: [], cursor: 0, error: undefined })
  })
})
