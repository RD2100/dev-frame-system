/**
 * S6 scope-level installation evidence: the host-designated Shadow scope
 * carries exactly the four project tools through the real scoped tools
 * registry, and an unmarked runtime agent's scope carries none of them.
 * @module tests/s6-markshadow-scope
 */

import { describe, expect, it } from 'vitest'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { SHADOW_TOOL_NAMES } from '../src/index.ts'
import { dispatch, failureText, harness } from './helpers.ts'

describe('shadow-router S6 markShadow scope installation', () => {
  it('S6: the marked scope exposes exactly the SHADOW_TOOL_NAMES set and the unmarked scope exposes none of it', async () => {
    const root = await mkdtemp(join(tmpdir(), 'dsh-shadow-router-s6-scope-'))
    const h = await harness(root, { authorizedRoots: [root] })
    try {
      // The harness mounts no global tools, so a scope's visible tool set is
      // exactly its scope-local install — full equality is the whitelist face.
      expect([...SHADOW_TOOL_NAMES]).toEqual(['project_open', 'project_send', 'project_status', 'project_stop'])

      // The harness designates the Shadow internally; marking is idempotent,
      // and the second runtime agent stays unmarked.
      h.router.markShadow(h.shadow)
      expect(h.router.isShadow(h.shadow)).toBe(true)
      expect(h.router.isShadow(h.worker)).toBe(false)

      // Scope-level enumeration through the real tools registry accessor:
      // `schemas(scope)` resolves the visible tool set for one agent scope
      // (the agent itself is its scope key), and `get(name, scope)` resolves
      // one name the same way dispatch does.
      const markedNames = h.ctx.tools.schemas(h.shadow).map(schema => schema.name)
      expect(markedNames).toEqual([...SHADOW_TOOL_NAMES])
      const unmarkedNames = h.ctx.tools.schemas(h.worker).map(schema => schema.name)
      for (const name of SHADOW_TOOL_NAMES) {
        expect(unmarkedNames, `the unmarked scope must not list "${name}"`).not.toContain(name)
        expect(h.ctx.tools.get(name, h.worker), `the unmarked scope must not resolve "${name}"`).toBeUndefined()
        expect(h.ctx.tools.get(name, h.shadow), `the marked scope must resolve "${name}"`).toBeDefined()
      }

      // Behavior cross-check through the real dispatcher: the unmarked agent's
      // call cannot even resolve the name, while the marked agent's call
      // reaches the real tool body and the service behind it.
      const rejected = await dispatch(h.ctx, h.worker, 'project_status', {})
      expect(rejected.isError).toBe(true)
      expect(failureText(rejected)).toContain('unknown tool "project_status"')
      const accepted = await dispatch(h.ctx, h.shadow, 'project_status', {})
      expect(accepted.isError).toBe(false)
    } finally {
      await h.dispose()
    }
  })
})
