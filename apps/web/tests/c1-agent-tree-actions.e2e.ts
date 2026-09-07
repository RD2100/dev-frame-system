// Web e2e scenario (v1.4 C-line C1 browser verification): the workspace
// browser's project agent tree under REAL browser actions. A real continuable
// subagent child hangs below its owner row; the scenario drives the collapse
// default, the chevron's one-level toggle, and the row-menu direct Session ID
// copy, asserting DOM state (aria-expanded, child row visibility, clipboard
// contents, toast) after every action. No golden: the assertions below ARE the
// evidence contract for this lane.
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { Browser, Locator, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it, onTestFailed } from 'vitest'
import { createUserMessage, LlmAdapter } from '@deepseek-ai/dsh-llm'
import type { GenerateOptions, StreamChunk } from '@deepseek-ai/dsh-llm'
import { SessionId, type SessionId as SessionIdValue } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-subagent'
import type {} from '@deepseek-ai/dsh-workspace'
import { launchWebScaffold, watchConsole, type WebScaffold } from './scaffold.ts'
import { connectFreshWorkspace, newEnglishPage, saveFailureShot } from './support.ts'

const OWNER_PROMPT = 'C1TREEOWNER prompt'
const CHILD_PROMPT = 'Hold the C1 agent-tree child turn open-free.'
const PROVIDER = 'c1-tree-provider'
const MODEL = 'c1-tree-model'

/** Model stub that settles every turn immediately: rows must be idle, not held. */
class SettleAdapter extends LlmAdapter {
  override async *stream(_options: GenerateOptions): AsyncIterable<StreamChunk> {
    const text = 'C1 settled reply.'
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text }
    yield { type: 'block-end', index: 0, block: { type: 'text', text } }
    yield { type: 'usage', usage: { inputTokens: 16, outputTokens: 8 } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

describe('web e2e: agent tree collapse, chevron, and Session ID copy (C1)', () => {
  let scaffold: WebScaffold
  let browser: Browser
  let page: Page
  let tripwire: ReturnType<typeof watchConsole>
  let parentId: SessionIdValue
  let childId: SessionIdValue

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
    scaffold = await launchWebScaffold()
    scaffold.ctx.effect(
      () => scaffold.ctx.llm.registerAdapter([PROVIDER], new SettleAdapter()),
      'c1 agent tree settle adapter',
    )
    const cwd = join(scaffold.workspaceCwd, 'workspace')
    await mkdir(cwd)
    const parent = await scaffold.ctx.agents.create({
      sessionId: SessionId('c1-tree-owner'),
      meta: { cwd },
      agentOptions: { provider: PROVIDER, model: MODEL },
    })
    parentId = parent.agent.session.id
    parent.agent.followup(createUserMessage({
      content: [{ type: 'text', text: OWNER_PROMPT }],
      source: { kind: 'user' },
    }))
    await parent.agent.whenIdle()
    const child = await scaffold.ctx.subagents.startContinuable({
      provider: 'spawn',
      label: 'C1 tree child',
      signal: new AbortController().signal,
      request: {
        prompt: [{ type: 'text', text: CHILD_PROMPT }],
        parent: parent.agent,
      },
    })
    childId = child.childId
    // A settled spawn child is released from the live registry (the lane's
    // settle idiom, cf. subagent-conversation's waitForAgentToSettle): wait
    // for idle-or-absence, not idle alone.
    const childDeadline = Date.now() + 30_000
    for (;;) {
      const handle = scaffold.ctx.agents.get(childId)
      if (handle === undefined || handle.status === 'idle') break
      if (Date.now() >= childDeadline) throw new Error('c1 agent-tree child did not settle idle')
      await new Promise<void>(resolve => setTimeout(resolve, 20))
    }

    browser = await chromium.launch()
    page = await newEnglishPage(browser)
    tripwire = watchConsole(page)
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.goto(scaffold.authenticatedUrl, { waitUntil: 'load' })
    await page.waitForSelector('[class*="frame"]', { timeout: 30_000 })
    await connectFreshWorkspace(page, scaffold.workspaceCwd)
    const workspace = await scaffold.ctx.workspaceRegistry.resolveByPath(cwd)
    if (workspace === undefined) throw new Error('connected Web workspace was not registered')
    await workspace.attachSession(parentId)
  }, 120_000)

  afterAll(async () => {
    const failures: unknown[] = []
    const child = childId === undefined ? undefined : scaffold?.ctx.agents.get(childId)
    await child?.whenIdle().catch((error: unknown) => failures.push(error))
    await browser?.close().catch((error: unknown) => failures.push(error))
    await scaffold?.close().catch((error: unknown) => failures.push(error))
    if (failures.length === 1) throw failures[0]
    if (failures.length > 1) throw new AggregateError(failures, 'c1 agent tree teardown failed')
  })

  it('drives collapse default, one-level chevron toggle, and Session ID copy', async () => {
    onTestFailed(() => saveFailureShot(page, 'web-e2e-c1-agent-tree-actions'))
    const tree = page.getByRole('tree', { name: 'Sessions' })
    const ownerRow = tree.getByRole('treeitem').filter({ hasText: OWNER_PROMPT })
    await ownerRow.waitFor({ timeout: 30_000 })

    // Default collapsed: the owner row renders its expand chevron (folded) and
    // the subagent child row is absent from the DOM.
    expect(await ownerRow.getAttribute('aria-expanded')).toBe('false')
    const chevron = ownerRow.locator('button[aria-label^="Toggle the direct children of"]')
    expect(await chevron.count()).toBe(1)
    expect(await chevron.getAttribute('aria-expanded')).toBe('false')
    const childRow = tree.getByRole('treeitem').filter({ hasText: childId })
    expect(await childRow.count()).toBe(0)
    // The owner meta line carries the durable Session ID in plain text.
    expect(await ownerRow.innerText()).toContain(parentId)

    // Chevron click expands exactly one level: the child row appears, the
    // chevron flips, and the owner's aria-expanded agrees.
    await chevron.click()
    await childRow.waitFor({ timeout: 10_000 })
    expect(await chevron.getAttribute('aria-expanded')).toBe('true')
    expect(await ownerRow.getAttribute('aria-expanded')).toBe('true')
    expect(await childRow.innerText()).toContain(childId)
    // A leaf child renders no expand chevron of its own.
    expect(await childRow.locator('button[aria-label^="Toggle the direct children of"]').count()).toBe(0)

    // Second click collapses: the child row leaves the DOM again.
    await chevron.click()
    await expect.poll(() => childRow.count(), { timeout: 10_000 }).toBe(0)
    expect(await chevron.getAttribute('aria-expanded')).toBe('false')

    // Re-expand for the copy action, then copy the Session ID from the row
    // menu: clipboard receives the full durable id and a Copied toast shows.
    await chevron.click()
    await childRow.waitFor({ timeout: 10_000 })
    await clickRowAction(ownerRow, 'Session actions for')
    await page.getByRole('menuitem', { name: 'Copy session ID' }).click()
    // The row-level result toast renders through the Toast primitive (role=alert).
    const toast = page.getByRole('alert')
    await toast.waitFor({ timeout: 5_000 })
    expect(await toast.innerText()).toBe('Copied')
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(String(parentId))

    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 120_000)
})
