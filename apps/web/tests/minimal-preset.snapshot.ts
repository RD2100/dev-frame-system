import { readFileSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Browser, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it, onTestFailed } from 'vitest'
import type { AgentHandle } from '@deepseek-ai/dsh-agent'
import {
  parseSnapshotManifest,
  platformExpectationVariant,
  resolveExpectationPath,
  resolveSessionFixturePath,
} from '@deepseek-ai/dsh-session-snapshot'
import { ToolCallId, createUserMessage } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-agent-presets'
import type {} from '@deepseek-ai/dsh-system-prompt'
import {
  assertFixtureInventory,
  captureStableAria,
  compareOrRefreshGolden,
  launchWebScaffold,
  watchConsole,
  webSnapshotMode,
  type WebScaffold,
} from './scaffold.ts'
import { newEnglishPage, saveFailureShot } from './support.ts'

const SNAPSHOT_DIR = fileURLToPath(new URL('../../../snapshots/web/minimal-preset', import.meta.url))
const MANIFEST_PATH = join(SNAPSHOT_DIR, 'snapshot.yml')
const MANIFEST = parseSnapshotManifest(readFileSync(MANIFEST_PATH, 'utf8'), MANIFEST_PATH)
// Every platform-dependent read resolves through the session-snapshot
// vocabulary instead of scattered process.platform conditionals: the
// persisted-replay fixture (both its replay-script and comparison roles), the
// pinned sidecars (scaffold-side), and this file's UI golden.
const FIXTURE = resolveSessionFixturePath({ dir: SNAPSHOT_DIR, manifest: MANIFEST, platform: process.platform })
const UI_EXPECTED = resolveExpectationPath({ dir: SNAPSHOT_DIR, kind: 'ui', manifest: MANIFEST, platform: process.platform })
const MODE = webSnapshotMode()
// Authored-corpus constant, byte-identical on every platform (the system-prompt
// two-platform exemption precedent): the recorded model output is scripted, so
// the wording drives no platform-conditional behavior — the scripted tool call
// is what varies, inside the session fixture variant.
const PROMPT = "Use the bash tool to run exactly: printf 'MINIMAL_BASH_CARD_OK\\n'. Then reply exactly MINIMAL_PRESET_REQUEST_OK and stop."

/**
 * The minimal preset's persistent shell per the platform seam — the preset
 * gates `bash` on POSIX and `pwsh` on win32 (agent.cordis.yml), so the direct
 * tool calls, the Web card selector, and the replayed-command probe all hang
 * off this one seam. Expectation texts normalize to the shared canonical form
 * in `text()`; the exact per-platform tool name stays pinned by the
 * tool-schemas variant file and the tools assertion in the first test.
 */
const SHELL = platformExpectationVariant(process.platform) === 'win32'
  ? {
    name: 'pwsh',
    cardRow: '[data-tool="pwsh"] [data-disclosure-row]',
    setState: (stateDir: string): string => `Set-Location -LiteralPath ${JSON.stringify(stateDir)}; $env:DSH_MINIMAL_STATE = 'PERSISTED'`,
    readState: 'Write-Output "${env:DSH_MINIMAL_STATE}:$PWD"',
    commandProbe: /"command": "Write-Output 'MINIMAL_BASH_CARD_OK/,
  }
  : {
    name: 'bash',
    cardRow: '[data-sample="bash"]',
    setState: (stateDir: string): string => `cd ${JSON.stringify(stateDir)} && export DSH_MINIMAL_STATE=PERSISTED`,
    readState: 'printf \'%s:%s\n\' "$DSH_MINIMAL_STATE" "$PWD"',
    commandProbe: /"command": "printf 'MINIMAL_BASH_CARD_OK/,
  }

describe('minimal agent preset', () => {
  let scaffold: WebScaffold
  let agentHandle: AgentHandle
  let disposeInjectedPrompt: () => void
  let browser: Browser | undefined
  let page: Page | undefined
  let tripwire: ReturnType<typeof watchConsole> | undefined

  beforeAll(async () => {
    scaffold = await launchWebScaffold({ replayFixture: FIXTURE, compareReplaySession: true, paceMs: 10 })
    disposeInjectedPrompt = scaffold.ctx.systemPrompt.section({
      name: 'test:injected-prompt',
      order: 999,
      text: 'THIS TEXT MUST NOT REACH THE MODEL.',
    })
    agentHandle = await scaffold.ctx.agents.create({
      sessionId: SessionId('minimal-preset-smoke'),
      meta: { cwd: scaffold.workspaceCwd, agentPreset: 'minimal' },
      agentOptions: { provider: 'deepseek-official', model: 'deepseek-v4-flash' },
      setup: agentCtx => scaffold.ctx.agentPresets.mount(agentCtx, 'minimal').then(() => undefined),
    })
    agentHandle.agent.followup(createUserMessage({
      content: [{ type: 'text', text: PROMPT }],
      source: { kind: 'user' },
    }))
    await agentHandle.agent.whenIdle()
  })

  afterAll(async () => {
    const failures: unknown[] = []
    await page?.close().catch((error: unknown) => failures.push(error))
    await browser?.close().catch((error: unknown) => failures.push(error))
    await agentHandle?.dispose().catch((error: unknown) => failures.push(error))
    try {
      disposeInjectedPrompt?.()
    } catch (error: unknown) {
      failures.push(error)
    }
    await scaffold?.close().catch((error: unknown) => failures.push(error))
    if (failures.length === 1) throw failures[0]
    if (failures.length > 1) throw new AggregateError(failures, 'minimal preset smoke teardown failed')
  })

  it('sends the exact RL prompt and schemas, then executes the persistent shell and editor', async () => {
    const requestHeader = agentHandle.agent.session.requestHeader()
    if (requestHeader === undefined) throw new Error('the minimal agent issued no model request')
    expect(agentHandle.agent.session.snapshotEvents().some(event => event.type === 'user/message'
      && event.data.source.kind === 'plugin'
      && event.data.source.plugin === '@deepseek-ai/dsh-system-prompt')).toBe(false)
    const presetFileSystem = scaffold.ctx.agentPresets.serviceFor(agentHandle.agent, 'fs')
    expect(presetFileSystem).toBeDefined()
    expect(presetFileSystem?.sandboxMode).toBeUndefined()
    expect(scaffold.ctx.agentPresets.serviceFor(agentHandle.agent, 'compaction')).toBeUndefined()

    const stateDir = join(scaffold.workspaceCwd, 'persistent-state')
    await mkdir(stateDir)
    const signal = new AbortController().signal
    await scaffold.ctx.tools.execute({
      signal,
      callId: ToolCallId('minimal-bash-state-setup'),
      name: SHELL.name,
      arguments: { command: SHELL.setState(stateDir) },
      agent: agentHandle.agent,
    })
    const shell = await scaffold.ctx.tools.execute({
      signal,
      callId: ToolCallId('minimal-bash-state-read'),
      name: SHELL.name,
      arguments: { command: SHELL.readState },
      agent: agentHandle.agent,
    })
    const seedPath = join(scaffold.workspaceCwd, 'preset-smoke.txt')
    await writeFile(seedPath, 'MINIMAL_EDITOR_OK\n')
    const editor = await scaffold.ctx.tools.execute({
      signal,
      callId: ToolCallId('minimal-editor-smoke'),
      name: 'str_replace_editor',
      arguments: { command: 'view', path: seedPath },
      agent: agentHandle.agent,
    })

    const text = (result: typeof shell): string => result.content
      .filter(block => block.type === 'text')
      .map(block => block.text)
      .join('')
      // Win32 conpty pads the START nonce's visual line with trailing spaces,
      // leaving one whitespace-only line above the tool output; the persistent
      // shell capture already strips a bare leading newline
      // (tool-pwsh-persistent/src/index.ts), and this padded form is platform
      // rendering, not behavior — like the path-separator normalization below —
      // so strip at most one such leading line for the shared inline snapshot.
      .replace(/^[ \t]*\r?\n/, '')
      .replaceAll(scaffold.workspaceCwd, '{{cwd}}')
      // Canonical POSIX separator spelling: path separators in tool output are
      // platform rendering, not behavior, so the shared inline snapshot reads
      // the same on every host.
      .replaceAll('\\', '/')
      .trimEnd()

    expect({
      prompt: requestHeader.system,
      goalCommand: scaffold.ctx.commands.find(agentHandle.agent, 'goal') !== undefined,
      shell: text(shell),
      editor: text(editor),
    }).toMatchInlineSnapshot(`
      {
        "editor": "Here's the content of {{cwd}}/preset-smoke.txt with line numbers (which has a total of 2 lines):
           1  MINIMAL_EDITOR_OK
           2",
        "goalCommand": false,
        "prompt": "You are a helpful software engineer assistant.",
        "shell": "PERSISTED:{{cwd}}/persistent-state",
      }
    `)
    expect(requestHeader.tools?.map(tool => tool.name)).toEqual([SHELL.name, 'str_replace_editor'])
    expect(requestHeader.tools?.toSorted((left, right) => left.name.localeCompare(right.name)))
      .toEqual(scaffold.ctx.tools.schemas(agentHandle.agent).toSorted((left, right) => left.name.localeCompare(right.name)))
  })

  it.skipIf(MODE === 'record')('expands the completed persistent shell call in the Web conversation', async () => {
    onTestFailed(() => { if (page !== undefined) void saveFailureShot(page, 'web-minimal-persistent-bash-card') })
    browser = await chromium.launch()
    page = await newEnglishPage(browser)
    tripwire = watchConsole(page)
    await page.goto(scaffold.authenticatedUrl, { waitUntil: 'load' })
    await page.waitForSelector('[class*="frame"]', { timeout: 30_000 })

    const groupRow = page.locator('[role="treeitem"]').first()
    await groupRow.waitFor({ timeout: 15_000 })
    await groupRow.click()
    const sessionRow = page.locator('[role="treeitem"]').nth(1)
    await sessionRow.waitFor({ timeout: 10_000 })
    await sessionRow.click()
    await page.getByText('MINIMAL_PRESET_REQUEST_OK', { exact: true }).waitFor({ timeout: 15_000 })

    const process = page.locator('[data-turn-process]')
    await process.waitFor({ timeout: 15_000 })
    await expect.poll(() => process.getAttribute('aria-expanded')).toBe('false')
    await process.click()
    await expect.poll(() => process.getAttribute('aria-expanded')).toBe('true')

    const row = page.locator(SHELL.cardRow).first()
    await row.waitFor({ timeout: 15_000 })
    await expect.poll(() => row.getAttribute('aria-expanded')).toBe('false')
    await row.click()

    await expect.poll(() => row.getAttribute('aria-expanded')).toBe('true')
    const call = row.locator('xpath=..')
    await call.getByText('IN', { exact: true }).waitFor()
    await call.getByText('OUT', { exact: true }).waitFor()
    await call.getByText('MINIMAL_BASH_CARD_OK', { exact: true }).waitFor()
    await call.getByText(SHELL.commandProbe).waitFor()

    const snapshot = await captureStableAria(page, '[class*="centerCol"]', scaffold.workspaceCwd)
    await compareOrRefreshGolden(UI_EXPECTED, snapshot, MODE)
    expect(tripwire.pageErrors).toEqual([])
    expect(tripwire.warnings).toEqual([])
  }, 60_000)

  it('keeps its snapshot inventory closed', async () => {
    await assertFixtureInventory(SNAPSHOT_DIR, [
      'session.jsonl',
      'system-prompt.expected.md',
      'tool-schemas.expected.json',
      'ui.expected.md',
    ])
  })
})
