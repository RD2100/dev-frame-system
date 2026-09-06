import { describe, expect, it } from 'vitest'
import type { Session } from '@deepseek-ai/dsh-session'
import { stableSessionFixture } from './scaffold.ts'

const SESSION_ID = '11111111-2222-4333-8444-555555555555'

function harvestedSession(cwd: string): Session {
  return {
    id: SESSION_ID,
    header: {
      version: 0,
      id: SESSION_ID,
      createdAt: 1700000000000,
      cwd,
      isSeeded: false,
      delegationDepth: 0,
    },
    snapshotEvents: () => [],
    inheritedEventCount: 0,
  } as unknown as Session
}

describe('stableSessionFixture', () => {
  it('tokenizes a win32 cwd in its JSON-escaped spelling', () => {
    const fixture = stableSessionFixture(
      harvestedSession('C:\\Users\\alice\\Temp\\dsh-web-e2e-ws-abc123'),
      '',
      'C:\\Users\\alice\\Temp\\dsh-web-e2e-ws-abc123',
    )
    expect(fixture).toContain('"cwd":"{{cwd}}"')
    expect(fixture).not.toContain('dsh-web-e2e-ws-abc123')
  })

  it('keeps tokenizing a POSIX cwd through its raw spelling', () => {
    const fixture = stableSessionFixture(
      harvestedSession('/tmp/dsh-web-e2e-ws-abc123'),
      '',
      '/tmp/dsh-web-e2e-ws-abc123',
    )
    expect(fixture).toContain('"cwd":"{{cwd}}"')
    expect(fixture).not.toContain('dsh-web-e2e-ws-abc123')
  })
})
