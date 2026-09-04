// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, screen } from '@testing-library/react'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import { en as commonEn } from '@deepseek-ai/dsh-client-locale/src/locales/en.ts'
import { zh as commonZh } from '@deepseek-ai/dsh-client-locale/src/locales/zh.ts'
import type { SlotTestRuntime } from '@deepseek-ai/dsh-client-test-runtime'
import { TestRemote, usePinnedBrowserLanguages } from '@deepseek-ai/dsh-client-test-runtime'
import { apply, inject } from '@deepseek-ai/dsh-client-ui-workspace/client'
import { en, zh } from '@deepseek-ai/dsh-client-ui-workspace/src/client/locales.ts'
import { mountComposition } from '../src/index.ts'

// The service reads its initial locale from the browser; these specs assert
// the shipped Chinese copy, so they state the browser they assume.
usePinnedBrowserLanguages('zh-CN')

let bench: SlotTestRuntime | undefined
let locale: LocaleRuntime | undefined

/**
 * Assemble the full ui-workspace composition: the production client stack
 * over the bench doubles, the locale registry (face installed, pinned to the
 * shipped Chinese copy), a scripted directory-picker Remote namespace, and
 * the real client plugin mounted on a live fiber.
 */
async function mountedWorkspace(): Promise<SlotTestRuntime> {
  bench = await mountComposition({ inject: [...inject], apply }, {
    provide: (runtime) => {
      const directoryPicker = {}
      Object.assign(new TestRemote(runtime.ctx), { directoryPicker })
      runtime.ctx.provide('remote.directoryPicker', directoryPicker as never)
      locale = new LocaleRuntime(runtime.ctx)
      runtime.ctx.provide('locale', locale)
      runtime.slots.installLocale(locale)
      runtime.releaseWorkspaceSource()
    },
  })
  return bench
}

beforeEach(() => { localStorage.clear() })
afterEach(async () => {
  cleanup()
  await bench?.dispose()
  bench = undefined
  locale = undefined
})

describe('workspace composition smoke', () => {
  it('reaches the Session-ID dialog from the assembled sidebar session list through the row actions menu', async () => {
    const runtime = await mountedWorkspace()
    await runtime.sessions.add({ id: 'session-alpha', summary: { title: 'Alpha', displayTitle: 'Alpha' } })
    await runtime.declare({ 'sidebar.workspaces': { kind: 'single', scope: 'root' } })
    const view = runtime.renderSlot('sidebar.workspaces', { wide: true, expandSidebar: () => {} })
    // The current session's group auto-expands; open the row's action menu.
    const rowActions = await view.view.findByRole('button', { name: zh['actions.session.aria'].replace('{name}', 'Alpha') })
    // Opening the row menu is presentation-only: no session opens behind it.
    fireEvent.click(rowActions)
    expect(runtime.sessions.calls.filter(call => call.method === 'open')).toHaveLength(0)
    fireEvent.click(screen.getByRole('menuitem', { name: zh['menu.sessionId'], hidden: true }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-label')).toBe(zh['sessionId.title'])
    // The complete id survives the composed assembly verbatim.
    expect(dialog.textContent).toContain('session-alpha')
  })

  it('registers the browser on the slot ledger with its locale namespace and directory-flow child hole', async () => {
    const runtime = await mountedWorkspace()
    await runtime.declare({ 'sidebar.workspaces': { kind: 'single', scope: 'root' } })
    const entries = runtime.slots.entries('sidebar.workspaces')
    expect(entries).toHaveLength(1)
    expect(entries[0]!.locale).toBe('workspace')
    expect(runtime.slots.spec('sidebar.workspaces.directoryFlow')).toMatchObject({ kind: 'single' })
  })

  it('binds the workspace namespace through the production locale registry', async () => {
    await mountedWorkspace()
    expect(locale!.bind('workspace')('menu.sessionId')).toBe(zh['menu.sessionId'])
  })

  it('keeps the composed dictionaries key-identical across both shipped languages', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zh).sort())
    expect(Object.keys(commonEn).sort()).toEqual(Object.keys(commonZh).sort())
  })

  it('unregisters the composed entry when the bench disposes', async () => {
    const runtime = await mountedWorkspace()
    await runtime.declare({ 'sidebar.workspaces': { kind: 'single', scope: 'root' } })
    expect(runtime.slots.entries('sidebar.workspaces')).toHaveLength(1)
    await runtime.dispose()
    expect(runtime.slots.entries('sidebar.workspaces')).toHaveLength(0)
  })
})
