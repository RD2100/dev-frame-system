/**
 * Cross-file wire-protocol consistency: the Desktop main-process encoder in
 * `apps/desktop/src/host-protocol.ts` must stay byte-for-byte aligned with the
 * Host decoder in `apps/desktop-host/src/wire.ts`. The Host source is read-only
 * from this test (the parallel Host team owns it); we regex-pin its literals
 * and compare them against the Desktop side's exported constants.
 *
 * `DESKTOP_CONTROL_IPC_FD` is Desktop-only (Node's lifecycle IPC descriptor) and
 * is deliberately NOT part of this cross-file contract.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  DESKTOP_HOST_PROTOCOL_VERSION,
  DESKTOP_PIPE_CHUNK_BYTES,
  DESKTOP_REQUEST_PIPE_FD,
  DESKTOP_RESPONSE_PIPE_FD,
  DESKTOP_WIRE_FORMAT,
} from '../src/host-protocol.ts'

const HOST_WIRE_SOURCE = readFileSync(
  fileURLToPath(new URL('../../desktop-host/src/wire.ts', import.meta.url)),
  'utf8',
)

function hostLiteral(regex: RegExp): string {
  const match = HOST_WIRE_SOURCE.match(regex)
  expect(match, `host wire.ts literal missing for ${regex.source}`).not.toBeNull()
  return match?.[0] ?? ''
}

describe('desktop/host wire-protocol constants stay aligned', () => {
  it('pins the exported Host shared literals', () => {
    hostLiteral(/DESKTOP_HOST_PROTOCOL_VERSION = 3 as const/u)
    hostLiteral(/DESKTOP_REQUEST_PIPE_FD = 3/u)
    hostLiteral(/DESKTOP_RESPONSE_PIPE_FD = 4/u)
    hostLiteral(/DESKTOP_PIPE_CHUNK_BYTES = 64 \* 1024/u)
    hostLiteral(/FRAME_MAGIC = 0x44534833/u)
    hostLiteral(/FRAME_HEADER_BYTES = 13/u)
    hostLiteral(/MAX_CONTROL_PAYLOAD_BYTES = 1024 \* 1024/u)
  })

  it('matches the Desktop exported constants against the Host literals', () => {
    expect(DESKTOP_HOST_PROTOCOL_VERSION).toBe(3)
    expect(DESKTOP_REQUEST_PIPE_FD).toBe(3)
    expect(DESKTOP_RESPONSE_PIPE_FD).toBe(4)
    expect(DESKTOP_PIPE_CHUNK_BYTES).toBe(64 * 1024)
    expect(DESKTOP_WIRE_FORMAT.frameMagic).toBe(0x44534833)
    expect(DESKTOP_WIRE_FORMAT.frameHeaderBytes).toBe(13)
    expect(DESKTOP_WIRE_FORMAT.maxControlPayloadBytes).toBe(1024 * 1024)
  })

  it('does not treat the Desktop-only control IPC fd as part of the wire contract', () => {
    expect(HOST_WIRE_SOURCE).not.toMatch(/DESKTOP_CONTROL_IPC_FD/u)
  })
})
