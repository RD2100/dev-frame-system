// Web e2e scenario (v1.4 C-line C2 browser verification): the composer's
// `@` trigger surfaces the `Subagents` group backed by the REAL
// `subagents/providers` Host directory — the live `ctx.subagents` registry —
// and a picked mention inserts literal `@<provider> ` text. Three providers
// register through the product's own registration seam (registerProvider)
// under the C2 candidate names codex / claude-code / cursor; no model call is
// issued anywhere.
import type { Browser, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it, onTestFailed } from 'vitest'
import type { SubagentProvider } from '@deepseek-ai/dsh-subagent'
import { launchWebScaffold, watchConsole, type WebScaffold } from './scaffold.ts'
import { connectFreshWorkspace, newEnglishPage, saveFailureShot } from './support.ts'

const MENTION_PROVIDERS = ['codex', 'claude-code', 'cursor'] as const

/** A registry-only provider: the directory lists it; nothing ever starts it. */
function stubProvider(name: string): SubagentProvider {
  return {
    name,
    capabilities: {
      agentOptions: false, outputSchema: false, depthLimit: false, toolFilter: false, persona: false,
    },
    inheritsParentContext: false,
    start: () => Promise.reject(new Error('c2 mention stub provider is a directory entry only')),
  }
}

describe('web e2e: @subagent mention candidates and literal pick (C2)', () => {
  let scaffold: WebScaffold
  let browser: Browser
  let page: Page
  let tripwire: ReturnType<typeof watchConsole>

  beforeAll(async () => {
    scaffold = await launchWebScaffold()
    for (const name of MENTION_PROVIDERS) {
      scaffold.ctx.subagents.registerProvider(stubProvider(name))
    }
    browser = await chromium.launch()
    page = await newEnglishPage(browser)
    tripwire = watchConsole(page)
    await page.goto(scaffold.authenticatedUrl, { waitUntil: 'load' })
    await page.waitForSelector('[class*="frame"]', { timeout: 30_000 })
    await connectFreshWorkspace(page, scaffold.workspaceCwd)
  }, 120_000)

  afterAll(async () => {
    await browser?.close()
    await scaffold?.close()
  })

  it('lists the three registry providers and inserts the literal mention on pick', async () => {
    onTestFailed(() => saveFailureShot(page, 'web-e2e-c2-subagent-mentions'))
    const input = page.locator('[data-composer-input]').first()
    const menu = page.getByRole('listbox', { name: 'Trigger suggestions' })

    // A bare `@` opens the shared trigger menu; the subagent source renders
    // its own group with the live registry names as candidates.
    await input.fill('@')
    await menu.getByText('Subagents', { exact: true }).waitFor({ timeout: 15_000 })
    await expect.poll(() => Promise.all(
      MENTION_PROVIDERS.map(async name => menu.getByRole('option', { name, exact: true }).count()),
    ), { timeout: 15_000 }).toEqual([1, 1, 1])

    // Query completion narrows the group to the matching registry name.
    await input.fill('@cl')
    await expect.poll(() => menu.getByRole('option', { name: 'codex', exact: true }).count(), { timeout: 15_000 }).toBe(0)
    await menu.getByRole('option', { name: 'claude-code', exact: true }).click()

    // The pick lands LITERAL text (no chip): `@claude-code ` in the draft.
    await expect.poll(() => input.textContent(), { timeout: 10_000 }).toBe('@claude-code ')
    expect(await input.locator('[data-composer-chip]').count()).toBe(0)

    // Every C2 candidate picks the same literal way, on a fresh draft.
    for (const name of ['cursor', 'codex'] as const) {
      await input.fill(`@${name.slice(0, 2)}`)
      await menu.getByRole('option', { name, exact: true }).click()
      await expect.poll(() => input.textContent(), { timeout: 10_000 }).toBe(`@${name} `)
      expect(await input.locator('[data-composer-chip]').count()).toBe(0)
    }

    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 120_000)
})
