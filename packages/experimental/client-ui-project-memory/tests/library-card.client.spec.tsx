// @vitest-environment jsdom
/** The Library tab loads on mount and browses/searches files, previews content,
 * copies paths, and references files in conversation. An unconfigured vault
 * stays an honest empty state. */

import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RemoteResult } from '@deepseek-ai/dsh-api-remotes/client'
import type {
  LibraryFile,
  LibrarySearchResult,
  MemoryLibraryReadRequest,
  MemoryLibraryReadResult,
  MemoryLibrarySnapshot,
} from '@deepseek-ai/dsh-experimental-project-memory/client'
import { RemoteError } from '@deepseek-ai/dsh-client-test-runtime'
import type { LibraryCardFace, LibraryCardProps } from '../src/client/LibraryCard.tsx'
import { LibraryCard } from '../src/client/LibraryCard.tsx'
import { zh, type LibraryKey } from '../src/client/locales.ts'

const t = ((key: LibraryKey, params?: Record<string, unknown>) => {
  const text = zh[key]
  return params === undefined
    ? text
    : Object.entries(params).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, String(value)), text)
}) as LibraryCardProps['t']

const unusedHook = (() => { throw new Error('unused by the library page') }) as never

const FILES: readonly LibraryFile[] = [
  { relativePath: 'welcome.md', size: 42, mtimeMs: 1 },
  { relativePath: 'projects/devframe.md', size: 128, mtimeMs: 2 },
]

const SNAPSHOT: MemoryLibrarySnapshot = {
  status: {
    status: 'AVAILABLE',
    vaultRoot: 'D:\\vault',
    realPath: 'D:\\vault',
    fileCount: 2,
    totalSizeBytes: 170,
  },
  files: FILES,
}

const UNAVAILABLE: MemoryLibrarySnapshot = {
  status: { status: 'UNAVAILABLE', reason: 'vaultRoot is not configured' },
  files: [],
}

const PREVIEW: MemoryLibraryReadResult = {
  relativePath: 'projects/devframe.md',
  absolutePath: 'D:\\vault\\projects\\devframe.md',
  content: '# DevFrame\nKeyword: alpha-omega.',
}

const HITS: readonly LibrarySearchResult[] = [
  { relativePath: 'projects/devframe.md', matchType: 'content', excerpt: '…alpha-omega…', line: 2 },
]

const ok = <T,>(value: T): RemoteResult<T> => ({ ok: true, value })

function face(overrides: Partial<LibraryCardFace> = {}): LibraryCardFace {
  return {
    load: vi.fn(async (): Promise<RemoteResult<MemoryLibrarySnapshot>> => ok(SNAPSHOT)),
    list: vi.fn(async (): Promise<RemoteResult<readonly LibraryFile[]>> => ok(FILES)),
    read: vi.fn(async ({ relativePath }: MemoryLibraryReadRequest): Promise<RemoteResult<MemoryLibraryReadResult>> => ok({
      ...PREVIEW,
      relativePath,
      absolutePath: relativePath === PREVIEW.relativePath ? PREVIEW.absolutePath : 'D:\\vault\\welcome.md',
    })),
    search: vi.fn(async (): Promise<RemoteResult<readonly LibrarySearchResult[]>> => ok(HITS)),
    reference: vi.fn(() => true),
    ...overrides,
  }
}

function props(actions: LibraryCardFace): LibraryCardProps {
  return {
    t,
    useSessions: unusedHook,
    useSessionPendingInteraction: unusedHook,
    useWorkspaces: unusedHook,
    ...actions,
  }
}

async function settle(): Promise<void> {
  await act(async () => { await Promise.resolve() })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise })
  return { promise, resolve }
}

/** Wait for the mount-time snapshot read to settle. */
async function openLibrary(): Promise<void> {
  await settle()
}

afterEach(cleanup)

describe('the library capability-center page', () => {
  it('loads and renders the page directly when mounted', async () => {
    const actions = face()
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    expect(actions.load).toHaveBeenCalledOnce()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('textbox', { name: '搜索记忆库' })).not.toBeNull()
    expect(screen.getByText('记忆库管理')).not.toBeNull()
    expect(screen.getByText('2 个文件')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'welcome.md' })).not.toBeNull()
    expect(screen.getByRole('button', { name: 'projects/devframe.md' })).not.toBeNull()
  })

  it('does not expose a page-level close action', async () => {
    const actions = face()
    render(<LibraryCard {...props(actions)} />)

    await openLibrary()
    expect(screen.queryByRole('button', { name: /关闭/ })).toBeNull()
  })
})

describe('the library page', () => {
  it('stays an honest empty state when the vault is not configured', async () => {
    const actions = face({ load: vi.fn(async () => ok(UNAVAILABLE)) })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    expect(screen.getByText('当前部署未配置 Vault 目录，记忆库不可用。')).not.toBeNull()
    expect(screen.queryByRole('textbox', { name: '搜索记忆库' })).toBeNull()
    expect(screen.queryByRole('button', { name: '全部' })).toBeNull()
  })

  it('reports a Remote load failure', async () => {
    const actions = face({
      load: vi.fn(async (): Promise<RemoteResult<MemoryLibrarySnapshot>> => ({
        ok: false,
        error: new RemoteError('gateway/internal', 'vault offline', {}),
      })),
    })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    expect(screen.getByRole('alert').textContent).toContain('vault offline')
  })

  it('shows the empty-library state when the vault has no files', async () => {
    const actions = face({ load: vi.fn(async () => ok({ ...SNAPSHOT, files: [], status: { ...SNAPSHOT.status, fileCount: 0 } })) })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    expect(screen.getByText('还没有记忆笔记')).not.toBeNull()
    expect(screen.getByText('与助手对话产生的重要事实会自动记录在这里。')).not.toBeNull()
  })

  it('searches the library and renders the hits with excerpts', async () => {
    const actions = face()
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.change(screen.getByRole('textbox', { name: '搜索记忆库' }), { target: { value: 'alpha-omega' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await settle()

    expect(actions.search).toHaveBeenCalledWith({ query: 'alpha-omega' })
    expect(screen.getByRole('button', { name: /projects\/devframe\.md/ })).not.toBeNull()
    expect(screen.getByText('…alpha-omega…')).not.toBeNull()
  })

  it('reports an empty search result', async () => {
    const actions = face({ search: vi.fn(async () => ok([])) })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.change(screen.getByRole('textbox', { name: '搜索记忆库' }), { target: { value: 'zzz' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await settle()

    expect(screen.getByText('没有匹配的文件。')).not.toBeNull()
  })

  it('keeps the latest search result when an earlier request finishes last', async () => {
    const first = deferred<RemoteResult<readonly LibrarySearchResult[]>>()
    const second = deferred<RemoteResult<readonly LibrarySearchResult[]>>()
    const search = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const actions = face({ search })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    const textbox = screen.getByRole('textbox', { name: '搜索记忆库' })
    fireEvent.change(textbox, { target: { value: 'first' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    fireEvent.change(textbox, { target: { value: 'second' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    expect(search).toHaveBeenNthCalledWith(1, { query: 'first' })
    expect(search).toHaveBeenNthCalledWith(2, { query: 'second' })

    await act(async () => {
      second.resolve(ok([{ ...HITS[0]!, excerpt: 'second response' }]))
    })
    await act(async () => {
      first.resolve(ok([{ ...HITS[0]!, excerpt: 'stale first response' }]))
    })

    expect(screen.getByText('second response')).not.toBeNull()
    expect(screen.queryByText('stale first response')).toBeNull()
  })

  it('previews a file with its content and real absolute path', async () => {
    const actions = face()
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: 'projects/devframe.md' }))
    await settle()

    expect(actions.read).toHaveBeenCalledWith({ relativePath: 'projects/devframe.md' })
    expect(screen.getByText('D:\\vault\\projects\\devframe.md')).not.toBeNull()
    expect(screen.getByText(/Keyword: alpha-omega/)).not.toBeNull()
  })

  it('reports a preview read failure', async () => {
    const actions = face({
      read: vi.fn(async (): Promise<RemoteResult<MemoryLibraryReadResult>> => ({
        ok: false,
        // Host ProjectMemoryError crosses the wire as gateway/internal (rpcFailure).
        error: new RemoteError('gateway/internal', 'path rejected', {}),
      })),
    })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: 'welcome.md' }))
    await settle()

    expect(screen.getByRole('alert').textContent).toContain('path rejected')
  })

  it('copies the absolute path and shows the copied feedback', async () => {
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const actions = face()
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: 'projects/devframe.md' }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '复制路径' }))
    await settle()

    expect(writeText).toHaveBeenCalledWith('D:\\vault\\projects\\devframe.md')
    expect(screen.getByRole('button', { name: '已复制' })).not.toBeNull()
  })

  it('shows a hint when the clipboard write fails', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn(async () => { throw new Error('denied') }) },
      configurable: true,
    })
    const actions = face()
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: 'projects/devframe.md' }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '复制路径' }))
    await settle()

    expect(screen.getByRole('status').textContent).toContain('复制失败')
  })

  it('references the file in conversation and reports the inserted state', async () => {
    const reference = vi.fn(() => true)
    const actions = face({ reference })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: 'projects/devframe.md' }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '引用到对话' }))
    await settle()

    expect(reference).toHaveBeenCalledWith('@vault:D:\\vault\\projects\\devframe.md')
    expect(screen.getByRole('status').textContent).toContain('已引用')
  })

  it('references the file on the selected card without using a previous preview', async () => {
    const reference = vi.fn(() => true)
    const actions = face({
      load: vi.fn(async () => ok({ ...SNAPSHOT, files: [FILES[0]!], status: { ...SNAPSHOT.status, fileCount: 1 } })),
      reference,
    })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    const card = screen.getByRole('button', { name: 'welcome.md' }).parentElement
    if (card === null) throw new Error('file card was not rendered')
    fireEvent.click(within(card).getByRole('button', { name: '引用' }))
    await settle()

    expect(actions.read).toHaveBeenCalledWith({ relativePath: 'welcome.md' })
    expect(reference).toHaveBeenCalledWith('@vault:D:\\vault\\welcome.md')
    expect(screen.getByRole('status').textContent).toContain('已引用')
  })

  it('reports when a file cannot be read for direct reference', async () => {
    const actions = face({
      load: vi.fn(async () => ok({ ...SNAPSHOT, files: [FILES[0]!], status: { ...SNAPSHOT.status, fileCount: 1 } })),
      read: vi.fn(async (): Promise<RemoteResult<MemoryLibraryReadResult>> => ({
        ok: false,
        error: new RemoteError('gateway/internal', 'path rejected', {}),
      })),
    })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    const card = screen.getByRole('button', { name: 'welcome.md' }).parentElement
    if (card === null) throw new Error('file card was not rendered')
    fireEvent.click(within(card).getByRole('button', { name: '引用' }))
    await settle()

    expect(screen.getByRole('status').textContent).toContain('无法引用')
  })

  it('reports when no conversation can receive the reference', async () => {
    const actions = face({ reference: vi.fn(() => false) })
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: 'projects/devframe.md' }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: '引用到对话' }))
    await settle()

    expect(screen.getByRole('status').textContent).toContain('没有可引用的会话')
  })

  it('refreshes the snapshot from the host', async () => {
    const actions = face()
    render(<LibraryCard {...props(actions)} />)
    await openLibrary()

    fireEvent.click(screen.getByRole('button', { name: '刷新记忆库' }))
    await settle()

    expect(actions.load).toHaveBeenCalledTimes(2)
  })
})
