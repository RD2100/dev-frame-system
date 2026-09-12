// Web e2e scenario: assistant IconActions belong to the settled answer, so
// they arrive with `turn/end` and not before. The recorded turn narrates in
// plain text before its tool call, which is the event order that would show the
// footer beside mid-turn narration for the seconds a tool runs and then move it
// down. A `hang` sidecar on the SECOND model call parks the turn after the
// narration and the tool result are durable, so the running state is stable by
// construction rather than by timing; stopping from that park writes the
// `turn/end` that hands the footer to the turn's transcript tail.
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import type { Browser, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterEach, describe, expect, it, onTestFailed } from 'vitest'
import type { ReplayOverrideDoc } from '@deepseek-ai/dsh-llm-replay'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import {
  parseSnapshotManifest,
  platformExpectationVariant,
  resolveSessionFixturePath,
  sessionFixtureFileName,
} from '@deepseek-ai/dsh-session-snapshot'
import {
  assertFixtureInventory, captureStableAria, compareOrRefreshGolden, fixtureUserPrompts,
  launchWebScaffold, recordFixture, watchConsole, webSnapshotMode, type WebScaffold,
} from './scaffold.ts'
import { connectFreshWorkspace, newEnglishPage, saveFailureShot } from './support.ts'

const SNAPSHOT_DIR = fileURLToPath(new URL('../../../snapshots/web/turn-tail-actions', import.meta.url))
const MANIFEST_PATH = join(SNAPSHOT_DIR, 'snapshot.yml')
const MANIFEST = parseSnapshotManifest(readFileSync(MANIFEST_PATH, 'utf8'), MANIFEST_PATH)
const MODE = webSnapshotMode()
// Every platform-dependent read resolves through the session-snapshot
// vocabulary: the recording (both replay-script and persisted-comparison
// roles) carries a win32 variant because the standard composition gates the
// persistent shell on the platform seam (bash on POSIX, pwsh on win32).
// In record mode the variant file is this run's write target, so the first
// win32 recording resolves the name without an existence check; every other
// mode keeps the resolver's fail-loud missing-file seam.
const FIXTURE = MODE === 'record'
  ? join(SNAPSHOT_DIR, sessionFixtureFileName(MANIFEST, process.platform))
  : resolveSessionFixturePath({ dir: SNAPSHOT_DIR, manifest: MANIFEST, platform: process.platform })
const WIN32 = platformExpectationVariant(process.platform) === 'win32'
// Three goldens for the same message: parked mid-turn, aborted, and completed.
// Each carries a committed win32 variant: the tool card title embeds the
// shell's tool name and the model-authored command description.
function goldenPath(stem: string): string {
  return join(SNAPSHOT_DIR, WIN32 ? `${stem}.win32.expected.md` : `${stem}.expected.md`)
}
const RUNNING_EXPECTED = goldenPath('running')
const SETTLED_EXPECTED = goldenPath('settled')
const USAGE_EXPANDED_EXPECTED = goldenPath('usage-expanded')
const COMPLETED_EXPECTED = goldenPath('completed')
const FOCUSED_EXPECTED = goldenPath('focused')

// The win32 recording rides the scenario's own approved gateway route (the
// standard composition has no DeepSeek key there); its identity is pinned by
// the manifest-owned fixture itself, not restated here.
const WIN32_ROUTE = 'huoshan-1'
const WIN32_MODEL = 'deepseek-v4-flash-ga-260731'
const WIN32_BASE_URL = 'https://ark.cn-beijing.volces.com/api/coding/v3'
const WIN32_API_KEY_ENV = 'HUOSHAN_1_API_KEY'
// Replay re-serves the route the recording rode through the replay adapter,
// and the same set tells the scaffold that record mode owns its credential
// arrangement (the shipped DEEPSEEK_API_KEY gate applies only to the default
// set). The contextWindow is the request/context value the recording actually
// rode, so the replayed session's request/context matches the fixture.
const WIN32_PROVIDERS = [{
  id: WIN32_ROUTE,
  name: WIN32_ROUTE,
  models: [{ id: WIN32_MODEL, name: 'DeepSeek-V4-Flash-GA', contextWindow: 262_144 }],
}]

// The recording must carry text in the SAME assistant message as the tool
// call; a Think-only step would leave nothing for the footer to attach to and
// the scenario would pass against either implementation. The shell tool named
// here follows the platform seam the composition actually serves.
const NARRATION = 'Reading the workspace now.'
const PROMPT = WIN32
  ? `Begin your reply with the plain sentence "${NARRATION}" as text, and in that same message call the pwsh tool with the command "Write-Output alpha". After the tool result, reply with the single word DONE and stop.`
  : `Begin your reply with the plain sentence "${NARRATION}" as text, and in that same message call the bash tool with the command "echo alpha". After the tool result, reply with the single word DONE and stop.`

// The tool card's collapsed title pairs the shell's tool label with the
// model-authored call description; each platform's recorded turn pins its own.
// The tool card's collapsed title pairs the shell's tool label with the
// model-authored call description; each platform's recorded turn pins its own.
const TOOL_CARD_NAME = WIN32 ? 'Pwsh Output the word alpha' : 'Bash Print alpha to stdout'

// The completed-Turn usage disclosure pins each platform's recorded samples:
// the pill's compact total and the dialog's exact facts. The win32 recording
// rides its own route and carries its own provider-reported usage, pinned
// from that recording — the POSIX figures are never restated as win32 facts.
// The win32 recording's first attempt reported no cache bucket, so the
// aggregate carries none and its dialog has no cache rows (null = absent).
const USAGE = WIN32
  ? {
    pill: /Usage \d+(\.\d+)?[KM]? tok/,
    pillText: 'Usage 17.5K tok',
    route: `${WIN32_ROUTE}/${WIN32_MODEL}`,
    cacheHit: null,
    input: '9,215 tok',
    cacheRead: null,
    output: '73 tok',
    total: '17,480 tok',
  }
  : {
    pill: /Usage 15\.8K tok/,
    pillText: 'Usage 15.8K tok',
    route: 'deepseek-official/deepseek-v4-flash',
    cacheHit: '49.7%' as const,
    input: '7,891 tok',
    cacheRead: '7,808 tok' as const,
    output: '112 tok (42 tok reasoning)',
    total: '15,811 tok',
  }

describe('web e2e: assistant IconActions wait for the turn to end', () => {
  let scaffold: WebScaffold | undefined
  let browser: Browser | undefined
  let page: Page
  let tripwire: ReturnType<typeof watchConsole>
  let sessionEvents: SessionEvent[]
  let sidecarDir: string | undefined

  afterEach(async () => {
    // close() carries the fixture-consumption tripwire, so its failure is the
    // scenario's failure; run every teardown step, then rethrow what failed.
    const failures: unknown[] = []
    await browser?.close().catch((error: unknown) => failures.push(error))
    browser = undefined
    const closing = scaffold
    scaffold = undefined
    await closing?.close().catch((error: unknown) => failures.push(error))
    if (sidecarDir !== undefined) await rm(sidecarDir, { recursive: true, force: true }).catch((error: unknown) => failures.push(error))
    sidecarDir = undefined
    if (failures.length === 1) throw failures[0]
    if (failures.length > 1) throw new AggregateError(failures, 'turn-tail-actions teardown failed')
  })

  /** Boot scaffold + page, materializing the sidecar before the replay row installs. */
  async function launch(
    buildOverride?: (sidecarHome: string) => ReplayOverrideDoc,
    paceMs?: number,
  ): Promise<void> {
    sessionEvents = []
    let overridePath: string | undefined
    if (buildOverride !== undefined) {
      sidecarDir = await mkdtemp(join(tmpdir(), 'dsh-web-e2e-sidecar-'))
      overridePath = join(sidecarDir, 'replay.override.json')
      await writeFile(overridePath, JSON.stringify(buildOverride(sidecarDir)))
    }
    scaffold = await launchWebScaffold(
      MODE === 'record'
        ? {
          // Record mode owns its credential arrangement: WIN32_PROVIDERS
          // tells the scaffold the shipped DEEPSEEK_API_KEY gate does not
          // apply, the real adapter answers, and the fixture is this run's
          // harvest target.
          ...WIN32 ? { replayProviders: WIN32_PROVIDERS } : {},
        }
        : {
          replayFixture: FIXTURE,
          ...WIN32 ? { replayProviders: WIN32_PROVIDERS } : {},
          ...(overridePath === undefined ? {} : { replayOverride: overridePath }),
          compareReplaySession: overridePath === undefined,
          ...(paceMs === undefined ? {} : { paceMs }),
        },
    )
    if (WIN32) {
      if (MODE === 'record') {
        // The win32 recording rides the scenario's approved gateway route: the
        // key comes from the runner's environment, the credential never lands
        // in this file, and the isolated harness home holds the provider profile.
        if (process.env[WIN32_API_KEY_ENV] === undefined || process.env[WIN32_API_KEY_ENV]?.length === 0) {
          throw new Error(`turn-tail-actions win32 record needs ${WIN32_API_KEY_ENV} (env or repo-root .env)`)
        }
        await scaffold.ctx.settings.update('llm-pi-ai', {
          providers: {
            [WIN32_ROUTE]: {
              displayName: 'Huoshan',
              api: 'openai-completions',
              baseURL: WIN32_BASE_URL,
              apiKeyEnv: WIN32_API_KEY_ENV,
              models: [{ id: WIN32_MODEL, name: 'DeepSeek-V4-Flash-GA' }],
            },
          },
        })
      }
      // Both modes ride the same route the recording rode: record through the
      // real adapter, replay through the replay adapter registered above — no
      // pi-ai profile keyless, so no real adapter conflicts.
      await scaffold.ctx.settings.update('agent-default-model', { provider: WIN32_ROUTE, model: WIN32_MODEL })
    }
    scaffold.ctx.on('session/event', (_session, event: SessionEvent) => { sessionEvents.push(event) })
    browser = await chromium.launch()
    page = await newEnglishPage(browser)
    tripwire = watchConsole(page)
    await page.goto(scaffold.authenticatedUrl, { waitUntil: 'load' })
    await page.waitForSelector('[class*="frame"]', { timeout: 30_000 })
    await connectFreshWorkspace(page, scaffold.workspaceCwd)
  }

  /** Send the recorded prompt with the settled barrier pre-armed (returned wrapped so the caller can act mid-turn). */
  async function sendPrompt(timeoutMs?: number): Promise<{ settled: ReturnType<WebScaffold['whenTurnSettled']> }> {
    const input = page.locator('[data-composer-input]').first()
    await input.waitFor({ timeout: 10_000 })
    const settled = scaffold!.whenTurnSettled(timeoutMs)
    await input.fill(PROMPT)
    await input.press('Enter')
    return { settled }
  }

  it.skipIf(MODE !== 'record')('records the narrate-then-call turn live through the composer', async () => {
    await launch()
    onTestFailed(() => saveFailureShot(page, 'web-e2e-turn-tail-actions-record'))
    const { settled } = await sendPrompt(180_000)
    const sessionId = await settled
    await recordFixture(scaffold!, sessionId, FIXTURE)
  }, 200_000)

  it.skipIf(MODE === 'record')('matches the canonical persisted session', async () => {
    await launch()
    const { settled } = await sendPrompt(30_000)
    await settled
  })

  it.skipIf(MODE === 'record')('withholds the footer while the turn runs and grants it at turn/end', async () => {
    expect(fixtureUserPrompts(await readFile(FIXTURE, 'utf8'))).toEqual([PROMPT])
    let marker = ''
    // Patch the SECOND call: the first one delivers the narration and the tool
    // call as recorded, so the park happens with a durable mid-turn message.
    await launch((sidecarHome) => {
      marker = join(sidecarHome, '.hang-ready')
      return { patches: [{ at: 1, entry: { kind: 'hang', readyFile: marker } }] }
    })
    onTestFailed(() => saveFailureShot(page, 'web-e2e-turn-tail-actions'))
    // The barrier is armed before the park and awaited only after the stop
    // click, so its budget must cover the whole parked phase: marker poll,
    // live-state polls, and two captures with their stability windows. The
    // replay default (30s) leaves no headroom on a slow runner.
    const { settled } = await sendPrompt(120_000)
    // The marker IS the synchronization: the second call is provably parked,
    // so the first step's message and tool result are already durable.
    await expect.poll(() => existsSync(marker), { timeout: 20_000 }).toBe(true)
    expect(await page.locator('[data-turn-process]').count()).toBe(0)
    await expect.poll(
      () => page.getByRole('status').filter({ hasText: 'Deep diving...' }).isVisible(),
      { timeout: 10_000 },
    ).toBe(true)
    await page.locator('[data-streaming="true"]')
      .getByText('partial', { exact: true })
      .waitFor({ timeout: 10_000 })
    // Only the user bubble owns a footer (clock + copy; user bubbles carry no
    // branch action): the narration is not the answer yet.
    const copyButtons = page.getByRole('button', { name: 'Copy' })
    await expect.poll(() => copyButtons.count(), { timeout: 10_000 }).toBe(1)
    expect(await page.getByRole('button', { name: 'Branch into a new conversation' }).count()).toBe(0)
    await copyButtons.first().focus()
    const running = await captureStableAria(page, '[class*="centerCol"]', scaffold!.workspaceCwd)
    await compareOrRefreshGolden(RUNNING_EXPECTED, running, MODE)

    // Closing the turn from the park is the state change under test: an
    // aborted turn is durably closed, so its transcript tail (the frozen
    // partial) takes the seat while the mid-turn narration keeps none.
    await page.getByRole('button', { name: 'Stop generating' }).click()
    await settled
    expect(sessionEvents.filter(e => e.type === 'turn/end').map(e => e.data.reason.kind)).toEqual(['aborted'])
    await page.locator('[data-turn-process]').waitFor({ timeout: 10_000 })
    await expect.poll(() => copyButtons.count(), { timeout: 10_000 }).toBe(2)
    await expect.poll(() => page.locator('[data-streaming="true"]').count(), { timeout: 10_000 }).toBe(0)
    await copyButtons.last().focus()
    const settledAria = await captureStableAria(page, '[class*="centerCol"]', scaffold!.workspaceCwd)
    await compareOrRefreshGolden(SETTLED_EXPECTED, settledAria, MODE)
    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 120_000)

  it.skipIf(MODE === 'record')('shows exact completed-Turn usage and expands its available facts', async () => {
    await launch()
    onTestFailed(() => saveFailureShot(page, 'web-e2e-turn-usage-expanded'))
    const { settled } = await sendPrompt(120_000)
    await settled

    const trigger = page.getByRole('button', { name: USAGE.pill })
    await expect.poll(() => trigger.count(), { timeout: 10_000 }).toBe(1)
    expect(await trigger.getAttribute('aria-expanded')).toBe('false')
    // The usage pill carries the icon and the turn total; the time pill beside
    // it carries the run time, and both keep their details dialog-only.
    expect(await trigger.textContent()).toBe(USAGE.pillText)
    const timeTrigger = page.getByRole('button', { name: /^Ran for \S+$/ })
    expect(await timeTrigger.count()).toBe(1)
    expect(await page.locator('[data-turn-tail]').getByText(/tok\/s|TTFT/).count()).toBe(0)
    expect(await page.getByRole('dialog').count()).toBe(0)

    await trigger.click()
    expect(await trigger.getAttribute('aria-expanded')).toBe('true')
    const dialog = page.getByRole('dialog', { name: 'Turn usage' })
    expect(await dialog.count()).toBe(1)
    expect(await dialog.getByText(USAGE.route, { exact: true }).count()).toBe(1)
    if (USAGE.cacheHit !== null) expect(await dialog.getByText(USAGE.cacheHit, { exact: true }).count()).toBe(1)
    expect(await dialog.getByText(USAGE.input, { exact: true }).count()).toBe(1)
    if (USAGE.cacheRead !== null) expect(await dialog.getByText(USAGE.cacheRead, { exact: true }).count()).toBe(1)
    expect(await dialog.getByText(USAGE.output, { exact: true }).count()).toBe(1)
    expect(await dialog.getByText(USAGE.total, { exact: true }).count()).toBe(1)
    await page.keyboard.press('Escape')
    expect(await page.getByRole('dialog').count()).toBe(0)

    await timeTrigger.click()
    const timeDialog = page.getByRole('dialog', { name: 'Turn time and speed' })
    expect(await timeDialog.count()).toBe(1)
    expect(await timeDialog.getByText(/tok\/s/).count()).toBe(1)
    expect(await timeDialog.getByText('Time to first token (TTFT)', { exact: true }).count()).toBe(1)
    await page.keyboard.press('Escape')
    await trigger.click()

    const expanded = await captureStableAria(page, '[class*="centerCol"]', scaffold!.workspaceCwd)
    await compareOrRefreshGolden(USAGE_EXPANDED_EXPECTED, expanded, MODE)
    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 120_000)

  it.skipIf(MODE === 'record')('folds the Turn process after the completed reply becomes the answer', async () => {
    await launch()
    onTestFailed(() => saveFailureShot(page, 'web-e2e-turn-tail-actions-completed'))
    const { settled } = await sendPrompt()
    await settled
    await expect.poll(() => page.getByText('DONE', { exact: true }).count(), { timeout: 10_000 }).toBe(1)
    const process = page.locator('[data-turn-process]')
    await expect.poll(() => process.count(), { timeout: 10_000 }).toBe(1)
    expect(await process.getAttribute('aria-expanded')).toBe('false')
    expect(await process.evaluate(element => getComputedStyle(element).borderBottomWidth)).toBe('1px')
    const processBottom = await process.evaluate(element =>
      element.closest<HTMLElement>('[data-chat-flow-kind="turn-process"]')?.getBoundingClientRect().bottom)
    const answerTop = await page.getByText('DONE', { exact: true }).evaluate(element =>
      element.closest<HTMLElement>('[data-chat-flow-kind="assistant-step"]')?.getBoundingClientRect().top)
    expect(answerTop).toBe((processBottom ?? 0) + 8)
    await process.focus()
    const completed = await captureStableAria(page, '[class*="centerCol"]', scaffold!.workspaceCwd)
    await compareOrRefreshGolden(COMPLETED_EXPECTED, completed, MODE)
    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 60_000)

  it.skipIf(MODE === 'record')('switches a completed Turn between Compact and Normal', async () => {
    await launch()
    onTestFailed(() => saveFailureShot(page, 'web-e2e-turn-process-setting'))
    const { settled } = await sendPrompt()
    await settled
    const process = page.locator('[data-turn-process]')
    const tool = page.getByRole('button', { name: TOOL_CARD_NAME })
    await process.waitFor({ timeout: 10_000 })
    expect(await process.getAttribute('aria-expanded')).toBe('false')
    expect(await tool.isVisible()).toBe(false)

    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Settings' })
    await dialog.getByRole('button', { name: 'Compact', exact: true }).click()
    await page.getByRole('menuitem', { name: 'Normal', exact: true }).click()
    await page.keyboard.press('Escape')

    await expect.poll(() => process.count(), { timeout: 10_000 }).toBe(0)
    await tool.waitFor({ state: 'visible', timeout: 10_000 })
    await expect.poll(async () => readFile(join(scaffold!.harnessHome, 'settings.yaml'), 'utf8'), { timeout: 5_000 })
      .toMatch(/ui-chat:\n\s+transcriptView: normal/)

    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    const restored = page.getByRole('dialog', { name: 'Settings' })
    await restored.getByRole('button', { name: 'Normal', exact: true }).click()
    await page.getByRole('menuitem', { name: 'Compact', exact: true }).click()
    await page.keyboard.press('Escape')
    await process.waitFor({ timeout: 10_000 })
    expect(await process.getAttribute('aria-expanded')).toBe('false')
    expect(await tool.isVisible()).toBe(false)
    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 60_000)

  it.skipIf(MODE === 'record')('keeps a focused process member open when the completed reply arrives', async () => {
    await launch(undefined, 200)
    onTestFailed(() => saveFailureShot(page, 'web-e2e-turn-tail-actions-focused'))
    const { settled } = await sendPrompt()
    const tool = page.getByRole('button', { name: TOOL_CARD_NAME })
    await tool.waitFor({ timeout: 30_000 })
    await tool.focus()
    expect(await tool.evaluate(element => element.ownerDocument.activeElement === element)).toBe(true)
    await settled
    await expect.poll(() => page.getByText('DONE', { exact: true }).count(), { timeout: 10_000 }).toBe(1)
    const process = page.locator('[data-turn-process]')
    await expect.poll(() => process.count(), { timeout: 10_000 }).toBe(1)
    expect(await process.getAttribute('aria-expanded')).toBe('true')
    expect(await tool.evaluate(element => element.ownerDocument.activeElement === element)).toBe(true)
    const focused = await captureStableAria(page, '[class*="centerCol"]', scaffold!.workspaceCwd)
    await compareOrRefreshGolden(FOCUSED_EXPECTED, focused, MODE)
    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 60_000)

  it.skipIf(MODE === 'record')('keeps a closed fixture inventory', async () => {
    await assertFixtureInventory(
      SNAPSHOT_DIR,
      [
        'completed.expected.md', 'completed.win32.expected.md',
        'focused.expected.md', 'focused.win32.expected.md',
        'running.expected.md', 'running.win32.expected.md',
        'session.jsonl',
        'settled.expected.md', 'settled.win32.expected.md',
        'usage-expanded.expected.md', 'usage-expanded.win32.expected.md',
      ],
    )
  })
})
