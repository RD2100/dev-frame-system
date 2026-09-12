import { describe, expect, it } from 'vitest'
import { AcceptanceHash, ShadowMessageId, ShadowRequestId, ShadowRouterError } from '../src/index.ts'

describe('shadow routing brand factories', () => {
  it('ShadowRequestId brands a bounded URL-safe token (identity at runtime)', () => {
    expect(ShadowRequestId('req-1')).toBe('req-1')
    expect(ShadowRequestId('A'.repeat(128))).toBe('A'.repeat(128))
  })

  it('ShadowRequestId rejects non-strings and ids outside the token shape', () => {
    expect(() => ShadowRequestId(undefined as unknown as string)).toThrow(ShadowRouterError)
    expect(() => ShadowRequestId('-leading-punct')).toThrow(ShadowRouterError)
    expect(() => ShadowRequestId('-leading-punct')).toThrow(/requestId must be 1-128 chars/)
  })

  it('ShadowMessageId brands a bounded token and rejects the rest', () => {
    expect(ShadowMessageId('msg-req-1')).toBe('msg-req-1')
    expect(() => ShadowMessageId('has space')).toThrow(/messageId must be 1-128 chars/)
    expect(() => ShadowMessageId(7 as unknown as string)).toThrow(ShadowRouterError)
  })

  it('AcceptanceHash brands bounded printable ASCII and rejects short, long, and spaced values', () => {
    expect(AcceptanceHash('a'.repeat(8))).toBe('a'.repeat(8))
    expect(AcceptanceHash('~'.repeat(256))).toBe('~'.repeat(256))
    expect(() => AcceptanceHash('a'.repeat(7))).toThrow(/acceptanceHash must be 8-256/)
    expect(() => AcceptanceHash('a'.repeat(257))).toThrow(ShadowRouterError)
    expect(() => AcceptanceHash('a a')).toThrow(ShadowRouterError)
    expect(() => AcceptanceHash(null as unknown as string)).toThrow(ShadowRouterError)
  })

  it('ShadowRouterError carries the stable class name and a machine-routable code', () => {
    const error = new ShadowRouterError('bad input', 'SHADOW_INVALID_REQUEST')
    expect(error.name).toBe('ShadowRouterError')
    expect(error.code).toBe('SHADOW_INVALID_REQUEST')
    expect(error).toBeInstanceOf(Error)
  })
})
