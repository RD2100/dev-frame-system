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
  /** Tool calls the model emits; each carries exact JSON arguments. */
  readonly toolCalls?: readonly {
    readonly id?: string
    readonly name: string
    readonly arguments: unknown
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

function sseChunks(turn: WireReplayTurn): readonly unknown[] {
  const chunks: unknown[] = []
  if (turn.text !== undefined && turn.text.length > 0) {
    chunks.push({ choices: [{ index: 0, delta: { role: 'assistant', content: turn.text }, finish_reason: null }] })
  }
  for (const [index, call] of (turn.toolCalls ?? []).entries()) {
    const args = JSON.stringify(call.arguments)
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
  const server = createServer((request: IncomingMessage, response: ServerResponse) => {
    let body = ''
    request.setEncoding('utf8')
    request.on('data', (chunk: string) => { body += chunk })
    request.on('end', () => {
      const parsed = JSON.parse(body) as unknown
      let matched: WireReplaySession | undefined
      for (const session of sessions) {
        if (body.includes(session.needle)) { matched = session; break }
      }
      const index = requests.length + 1
      requests.push({ index, needle: matched?.needle ?? null, body: parsed })
      if (matched === undefined) {
        response.writeHead(500, { 'content-type': 'application/json' })
        response.end(JSON.stringify({ error: { message: `wire replay: no session script matches this request`, code: 'WIRE_REPLAY_UNROUTED' } }))
        return
      }
      const cursor = cursors.get(matched.needle) ?? 0
      cursors.set(matched.needle, cursor + 1)
      const turn = matched.turns[cursor]
      if (turn === undefined) {
        response.writeHead(500, { 'content-type': 'application/json' })
        response.end(JSON.stringify({ error: { message: `wire replay: script exhausted for "${matched.needle}"`, code: 'WIRE_REPLAY_EXHAUSTED' } }))
        return
      }
      response.writeHead(200, { 'content-type': 'text/event-stream' })
      response.end([
        ...sseChunks(turn).map(chunk => `data: ${JSON.stringify(chunk)}`),
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
        server.close(() => { resolve() })
        server.closeAllConnections()
      })
      return closing
    },
  }
}
