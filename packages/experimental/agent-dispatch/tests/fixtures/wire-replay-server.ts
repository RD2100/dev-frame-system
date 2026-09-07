/**
 * Wire-level replay server for the candidate full-chain harness: an
 * OpenAI-compatible chat-completions SSE server whose responses are scripted
 * per session. Each scripted entry is a full turn response — optional text
 * and optional tool calls — so the harness drives exact tool-call ordering
 * through the real provider adapter without credentials. Requests are routed
 * to a session's script by matching a needle in the serialized request body
 * (the harness gives every driven session a distinct briefing text), which
 * keeps concurrent sessions deterministic without shared FIFO scripts.
 * @module tests/fixtures/wire-replay-server
 */

import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'

/** One scripted model turn: optional text and/or tool calls. */
export interface WireReplayTurn {
  /** Assistant text emitted before any tool call. */
  readonly text?: string
  /**
   * Readiness gate evaluated against the captured request body before this
   * turn is served. A false gate holds the cursor in place and answers a
   * bounded standby response instead, so a scripted phase is never consumed
   * before its real precondition (durable registration receipts) holds.
   */
  readonly gate?: (body: string) => boolean
  /** Tool calls the model emits; each carries exact JSON arguments. */
  readonly toolCalls?: readonly {
    readonly id?: string
    readonly name: string
    /**
     * Exact JSON arguments, or a callback evaluated against the captured
     * request body when the turn is served — earlier tool receipts (host
     * bootstrap worktree ids, dispatch briefings) flow back into later
     * scripts without hardcoding per-run identifiers.
     */
    readonly arguments: unknown | ((body: string) => unknown)
  }[]
}

/** One session's scripted turn queue and its routing needle. */
export interface WireReplaySession {
  /** Substring matched against the serialized request body. */
  readonly needle: string
  /** Turns consumed in order; exhaustion fails loud with a 500. */
  readonly turns: readonly WireReplayTurn[]
}

/** A captured wire request with its parsed body. */
export interface WireReplayRequest {
  readonly index: number
  readonly needle: string | null
  readonly body: unknown
}

export interface WireReplayServer {
  /** Base URL to point DEEPSEEK_BASE_URL at. */
  readonly baseURL: string
  /** Captured requests in arrival order. */
  readonly requests: readonly WireReplayRequest[]
  close(): Promise<void>
}

function sseChunks(turn: WireReplayTurn, body: string): readonly unknown[] {
  const chunks: unknown[] = []
  if (turn.text !== undefined && turn.text.length > 0) {
    chunks.push({ choices: [{ index: 0, delta: { role: 'assistant', content: turn.text }, finish_reason: null }] })
  }
  for (const [index, call] of (turn.toolCalls ?? []).entries()) {
    const resolved = typeof call.arguments === 'function'
      ? (call.arguments as (requestBody: string) => unknown)(body)
      : call.arguments
    const args = JSON.stringify(resolved)
    chunks.push({
      choices: [{
        index: 0,
        delta: {
          tool_calls: [{
            index,
            id: call.id ?? `wire-call-${index + 1}`,
            type: 'function',
            function: { name: call.name, arguments: args },
          }],
        },
        finish_reason: null,
      }],
    })
  }
  const finish = (turn.toolCalls?.length ?? 0) > 0 ? 'tool_calls' : 'stop'
  chunks.push({
    choices: [{ index: 0, delta: { content: '' }, finish_reason: finish }],
    usage: { prompt_tokens: 4, completion_tokens: 8 },
  })
  return chunks
}

/**
 * Start the replay server. Closing the handle stops the listener and closes
 * open connections.
 * @param sessions - Session scripts routed by needle.
 */
export async function startWireReplayServer(sessions: readonly WireReplaySession[]): Promise<WireReplayServer> {
  const cursors = new Map<string, number>()
  const requests: WireReplayRequest[] = []
  const timers = new Set<NodeJS.Timeout>()
  const server = createServer((request: IncomingMessage, response: ServerResponse) => {
    let body = ''
    request.setEncoding('utf8')
    request.on('data', (chunk: string) => { body += chunk })
    request.on('end', () => {
      const parsed = JSON.parse(body) as unknown
      let matched: WireReplaySession | undefined
      for (const session of sessions) {
        // Only real agent-loop requests carry a tools array; the web app's
        // session-title generation embeds the user text too and must not
        // consume a scripted turn.
        if (body.includes(session.needle) && body.includes('"tools"')) { matched = session; break }
      }
      const index = requests.length + 1
      requests.push({ index, needle: matched?.needle ?? null, body: parsed })
      if (matched === undefined) {
        response.writeHead(500, { 'content-type': 'application/json' })
        response.end(JSON.stringify({ error: { message: `wire replay: no session script matches this request`, code: 'WIRE_REPLAY_UNROUTED' } }))
        return
      }
      const cursor = cursors.get(matched.needle) ?? 0
      const turn = matched.turns[cursor]
      if (turn === undefined) {
        response.writeHead(500, { 'content-type': 'application/json' })
        response.end(JSON.stringify({ error: { message: `wire replay: script exhausted for "${matched.needle}"`, code: 'WIRE_REPLAY_EXHAUSTED' } }))
        return
      }
      // A gated turn whose precondition has not produced its durable receipt
      // yet holds the response open — the request stays in flight and costs
      // no extra continuation round — and the moment the gate reports ready,
      // the scripted turn streams on the same connection and the cursor
      // advances exactly once, so no phase can repeat. A gate that throws
      // fails the response loudly, the hold has a hard deadline, and
      // close() cancels the poll so nothing hangs on shutdown.
      if (turn.gate !== undefined) {
        let ready = false
        let gateFailed: Error | undefined
        try {
          ready = turn.gate(body)
        } catch (error) {
          gateFailed = error instanceof Error ? error : new Error(String(error))
        }
        if (gateFailed !== undefined) {
          response.writeHead(500, { 'content-type': 'application/json' })
          response.end(JSON.stringify({ error: { message: `wire replay: gate evaluation failed: ${gateFailed.message}`, code: 'WIRE_REPLAY_GATE_FAILED' } }))
          return
        }
        if (!ready) {
          const startedAt = Date.now()
          const serve = (): void => {
            clearInterval(poll)
            timers.delete(poll)
            if (response.destroyed) return
            // Serving from the poll advances the cursor exactly like the
            // immediate path: the phase is consumed once, by the one
            // in-flight request that waited for it.
            cursors.set(matched.needle, cursor + 1)
            response.writeHead(200, { 'content-type': 'text/event-stream' })
            response.end([
              ...sseChunks(turn, body).map(chunk => `data: ${JSON.stringify(chunk)}`),
              'data: [DONE]',
              '',
            ].join('\n\n'))
          }
          const fail = (message: string): void => {
            clearInterval(poll)
            timers.delete(poll)
            if (response.destroyed) return
            response.writeHead(500, { 'content-type': 'application/json' })
            response.end(JSON.stringify({ error: { message, code: 'WIRE_REPLAY_GATE_FAILED' } }))
          }
          const poll = setInterval(() => {
            let ok = false
            try {
              ok = turn.gate!(body)
            } catch (error) {
              fail(`gate evaluation failed: ${error instanceof Error ? error.message : String(error)}`)
              return
            }
            if (ok) {
              serve()
              return
            }
            if (Date.now() - startedAt > 120_000) fail('gate deadline exceeded after 120000ms')
          }, 200)
          timers.add(poll)
          response.on('close', () => {
            clearInterval(poll)
            timers.delete(poll)
          })
          return
        }
      }
      cursors.set(matched.needle, cursor + 1)
      response.writeHead(200, { 'content-type': 'text/event-stream' })
      response.end([
        ...sseChunks(turn, body).map(chunk => `data: ${JSON.stringify(chunk)}`),
        'data: [DONE]',
        '',
      ].join('\n\n'))
    })
  })
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => { server.off('error', reject); resolve() })
  })
  const address = server.address() as AddressInfo
  let closing: Promise<void> | undefined
  return {
    baseURL: `http://127.0.0.1:${String(address.port)}`,
    requests,
    close: () => {
      closing ??= new Promise<void>((resolve) => {
        for (const timer of timers) clearTimeout(timer)
        timers.clear()
        server.close(() => { resolve() })
        server.closeAllConnections()
      })
      return closing
    },
  }
}
