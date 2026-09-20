/**
 * Unit behavior of the load-time singleton peer guard. The guard must pass a
 * satisfied plugin, throw the exact fail-loud template when the host is missing
 * a required singleton or cannot satisfy its range, and short-circuit
 * workspace:* ranges (the in-repo single-instance form).
 * @module tests/desktop-host-peer-satisfaction
 */

import { describe, expect, it } from 'vitest'
import { assertHostPeerSatisfaction, type PluginPeerRow } from '../src/peer-satisfaction.ts'

function plugin(requires: Record<string, string>, name = 'test-plugin', version = '0.1.6-alpha.1'): PluginPeerRow {
  return { pluginName: name, pluginVersion: version, requires }
}

describe('assertHostPeerSatisfaction', () => {
  it('passes when the host provides the singleton at a compatible range', () => {
    const rows = [plugin({ '@deepseek-ai/cordis': '^3.20.0' })]
    expect(() => { assertHostPeerSatisfaction(rows, { '@deepseek-ai/cordis': '3.20.5' }) }).not.toThrow()
  })

  it('short-circuits workspace:* ranges without requiring the host version', () => {
    const rows = [plugin({ '@deepseek-ai/cordis': 'workspace:^' })]
    expect(() => { assertHostPeerSatisfaction(rows, {}) }).not.toThrow()
  })

  it('throws the fail-loud template when the singleton is not installed', () => {
    const rows = [plugin({ '@deepseek-ai/schemastery': '^3.0.0' }, 'expert-team', '0.1.6-alpha.1')]
    expect(() => { assertHostPeerSatisfaction(rows, {}) }).toThrow(/peer dependency not satisfied/)
    try {
      assertHostPeerSatisfaction(rows, {})
    } catch (error) {
      const message = (error as Error).message
      expect(message).toContain('plugin: expert-team@0.1.6-alpha.1')
      expect(message).toContain('requires: @deepseek-ai/schemastery@^3.0.0')
      expect(message).toContain('NOT INSTALLED')
    }
  })

  it('throws when the host version does not satisfy the plugin range', () => {
    const rows = [plugin({ '@deepseek-ai/dsh-brand': '^2.0.0' })]
    expect(() => { assertHostPeerSatisfaction(rows, { '@deepseek-ai/dsh-brand': '1.9.3' }) }).toThrow(/host provides: @deepseek-ai\/dsh-brand@1\.9\.3/)
  })

  it('ignores peers that are not tracked framework singletons', () => {
    const rows = [plugin({ 'some-other-lib': '^9.9.9', '@deepseek-ai/cordis': '^3.0.0' })]
    expect(() => { assertHostPeerSatisfaction(rows, { '@deepseek-ai/cordis': '3.1.0' }) }).not.toThrow()
  })
})
