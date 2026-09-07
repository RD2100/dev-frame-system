// Web e2e scenario (v1.4 C-line C3 browser verification): the sidebar under
// REAL browser actions — session management (durable Session ID on the row
// meta, rename round trip, archive round trip), the composer model switch
// (seat menu → radio pick → host-durable agent-default-model settings), turn
// usage (a live replayed turn renders the usage pill and its details dialog),
// and the sidebar collapse/expand toggle. The usage turn rides the shipped
// deepseek-official route through a replay override; the switch target is a
// settings-declared pi-ai route that is never called.
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Browser, Locator, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it, onTestFailed } from 'vitest'
import type { ReplayEntry, ReplayOverrideDoc } from '@deepseek-ai/dsh-llm-replay'
import { launchWebScaffold, watchConsole, type WebScaffold } from './scaffold.ts'
import { connectFreshWorkspace, newEnglishPage, saveFailureShot } from './support.ts'

const PROMPT = 'C3USAGE turn'
const RENAMED = 'C3 renamed session'
const SWITCH_ROUTE = 'acme-gateway'
const SWITCH_MODEL = 'acme-large'
const INPUT_TOKENS = 700
const OUTPUT_TOKENS = 500

/** One settled text turn with explicit usage buckets, replayed on demand. */
function usageScript(): ReplayOverrideDoc {
  const text = 'C3 usage turn settled reply.'
  const chunks: ReplayEntry[] = [{
    kind: 'chunks',
    chunks: [
      { type: 'block-start', index: 0, blockType: 'text' },
      { type: 'text-delta', index: 0, text },
      { type: 'block-end', index: 0, block: { type: 'text', text } },
      { type: 'usage', usage: { inputTokens: INPUT_TOKENS, outputTokens: OUTPUT_TOKENS } },
      { type: 'finish', reason: { kind: 'stop' } },
    ],
  }]
  return chunks
}

describe('web e2e: sidebar session management, model switch, and usage (C3)', () => {
  let scaffold: WebScaffold
  let browser: Browser
  let page: Page
  let tripwire: ReturnType<typeof watchConsole>
  let replayDir: string

  /** Reveal and click a row action, re-hovering until the hover-only button shows. */
  async function clickRowAction(row: Locator, name: string): Promise<void> {
    const button = row.getByRole('button', { name })
    await expect.poll(async () => {
      await row.hover()
      return await button.isVisible()
    }, { timeout: 10_000 }).toBe(true)
    await button.click()
  }

  beforeAll(async () => {
    replayDir = await mkdtemp(join(tmpdir(), 'dsh-c3-usage-replay-'))
    const replayOverride = join(replayDir, 'replay.override.json')
    await writeFile(replayOverride, JSON.stringify(usageScript()))
    scaffold = await launchWebScaffold({
      replayFixture: join(replayDir, 'override-only.jsonl'),
      replayOverride,
      replayContextWindow: 10_000_000,
    })
    // The switch target: a settings-declared pi-ai route (never called here).
    await scaffold.ctx.settings.update('llm-pi-ai', {
      providers: {
        [SWITCH_ROUTE]: {
          displayName: 'Acme Gateway',
          api: 'openai-completions',
          baseURL: 'https://gateway.acme.example/v1',
          models: [{ id: SWITCH_MODEL, name: 'Acme Large' }],
        },
      },
    })
    browser = await chromium.launch()
    page = await newEnglishPage(browser)
    tripwire = watchConsole(page)
    await page.goto(scaffold.authenticatedUrl, { waitUntil: 'load' })
    await page.waitForSelector('[class*="frame"]', { timeout: 30_000 })
    await connectFreshWorkspace(page, scaffold.workspaceCwd)
  }, 120_000)

  afterAll(async () => {
    const failures: unknown[] = []
    await browser?.close().catch((error: unknown) => failures.push(error))
    await scaffold?.close().catch((error: unknown) => failures.push(error))
    if (replayDir !== undefined) {
      await rm(replayDir, { recursive: true, force: true }).catch((error: unknown) => failures.push(error))
    }
    if (failures.length === 1) throw failures[0]
    if (failures.length > 1) throw new AggregateError(failures, 'c3 sidebar teardown failed')
  })

  it('drives session management, model switch, usage panel, and the sidebar toggle', async () => {
    onTestFailed(() => saveFailureShot(page, 'web-e2e-c3-sidebar-actions'))
    const tree = page.getByRole('tree', { name: 'Sessions' })
    const composer = page.locator('[data-composer-input][contenteditable="true"]').last()
    await composer.waitFor({ timeout: 15_000 })

    // --- Live turn through the composer on the shipped route.
    const settled = scaffold.whenTurnSettled(60_000)
    await composer.fill(PROMPT)
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const sessionId = await settled
    await expect.poll(() => page.locator('[data-streaming="true"]').count(), { timeout: 15_000 }).toBe(0)

    const sessionRow = tree.getByRole('treeitem').filter({ hasText: PROMPT })
    await sessionRow.waitFor({ timeout: 15_000 })
    // The row's meta line carries the durable Session ID in plain text, and it
    // is the id of the session that actually ran the turn.
    expect(await sessionRow.innerText()).toContain(String(sessionId))
    expect(scaffold.ctx.workspaceRegistry.list().some(workspace => (
      workspace.sessionIds.includes(sessionId)
    ))).toBe(true)

    // --- Session rename over the row menu.
    await clickRowAction(sessionRow, 'Session actions for')
    await page.getByRole('menuitem', { name: 'Rename' }).click()
    const renameDialog = page.getByRole('dialog', { name: 'Rename session' })
    await renameDialog.waitFor({ timeout: 10_000 })
    await renameDialog.getByLabel('Session name').fill(RENAMED)
    await renameDialog.getByRole('button', { name: 'Rename' }).click()
    await expect.poll(() => renameDialog.count(), { timeout: 10_000 }).toBe(0)
    await expect.poll(() => tree.getByRole('treeitem').filter({ hasText: RENAMED }).count(), { timeout: 10_000 })
      .toBe(1)
    expect(await tree.getByRole('treeitem').filter({ hasText: RENAMED }).innerText())
      .toContain(String(sessionId))

    // --- Model switch through the composer seat; durable as the Agent default.
    const seat = page.getByRole('button', { name: /^Select model/ })
    await seat.waitFor({ timeout: 15_000 })
    await seat.click()
    // The root cell's accessible name concatenates the label and the current
    // model value, so match by prefix.
    await page.getByRole('menuitem', { name: /^Model/ }).click()
    await page.getByRole('menuitemradio', { name: 'Acme Large' }).click()
    await expect.poll(
      async () => readFile(join(scaffold.harnessHome, 'settings.yaml'), 'utf8'),
      { timeout: 10_000 },
    ).toContain('agent-default-model:')
    const settings = await readFile(join(scaffold.harnessHome, 'settings.yaml'), 'utf8')
    expect(settings).toContain(`provider: ${SWITCH_ROUTE}`)
    expect(settings).toContain(`model: ${SWITCH_MODEL}`)
    await expect.poll(
      () => page.getByRole('button', { name: 'Select model, current Acme Large' }).count(),
      { timeout: 10_000 },
    ).toBe(1)

    // --- Completed-turn usage: pill label plus the details dialog facts.
    // Temporary diagnostic: dump the tail-area buttons so a label mismatch is
    // attributable from the log alone.
    await page.waitForTimeout(3_000)
    const tailTexts = await page.locator('[data-turn-tail]').allInnerTexts()
    const buttonNames = await page.locator('button').evaluateAll(els => els
      .map(el => el.getAttribute('aria-label') ?? el.textContent ?? '')
      .filter(name => /tok|Usage|usage/i.test(name)))
    console.log('C3-DIAG tail:', JSON.stringify(tailTexts))
    console.log('C3-DIAG buttons:', JSON.stringify(buttonNames))
    const usageTrigger = page.getByRole('button', { name: 'Usage 1.2K tok' })
    await expect.poll(() => usageTrigger.count(), { timeout: 10_000 }).toBe(1)
    expect(await usageTrigger.getAttribute('aria-expanded')).toBe('false')
    await usageTrigger.click()
    expect(await usageTrigger.getAttribute('aria-expanded')).toBe('true')
    const dialog = page.getByRole('dialog', { name: 'Turn usage' })
    expect(await dialog.count()).toBe(1)
    expect(await dialog.getByText('deepseek-official/deepseek-v4-flash', { exact: true }).count()).toBe(1)
    expect(await dialog.getByText(`${String(INPUT_TOKENS)} tok`, { exact: true }).count()).toBe(1)
    expect(await dialog.getByText(`${String(OUTPUT_TOKENS)} tok`, { exact: true }).count()).toBe(1)
    expect(await dialog.getByText('1,200 tok', { exact: true }).count()).toBe(1)
    await page.keyboard.press('Escape')
    expect(await page.getByRole('dialog').count()).toBe(0)

    // --- Archive from the row menu: the row disappears and the id is durable.
    const renamedRow = tree.getByRole('treeitem').filter({ hasText: RENAMED })
    await clickRowAction(renamedRow, 'Session actions for')
    await page.getByRole('menuitem', { name: 'Archive session' }).click()
    await expect.poll(() => renamedRow.count(), { timeout: 10_000 }).toBe(0)
    expect([...scaffold.ctx.workspaceRegistry.archivedSessionIds]).toContain(sessionId)

    // --- Sidebar collapse/expand toggle round trip.
    const toggle = page.getByRole('button', { name: 'Collapse sidebar' })
    await toggle.waitFor({ timeout: 10_000 })
    await toggle.click()
    const expand = page.getByRole('button', { name: 'Open sidebar' })
    await expand.waitFor({ timeout: 10_000 })
    await expect.poll(() => tree.count(), { timeout: 10_000 }).toBe(0)
    await expand.click()
    await expect.poll(() => tree.count(), { timeout: 10_000 }).toBe(1)

    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 180_000)
})
