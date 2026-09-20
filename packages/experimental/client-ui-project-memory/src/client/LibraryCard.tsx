/** Library trigger and browse surface for the read-only Obsidian Vault. */

import { useCallback, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import {
  IconCloseOutline16,
  IconDatabaseOutline16,
  IconLinkOutline16,
  IconRefreshOutline16,
  IconSearchOutline16,
  Modal,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { RemoteResult } from '@deepseek-ai/dsh-api-remotes/client'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {
  LibraryFile,
  LibrarySearchResult,
  MemoryLibraryListRequest,
  MemoryLibraryReadRequest,
  MemoryLibraryReadResult,
  MemoryLibrarySearchRequest,
  MemoryLibrarySnapshot,
} from '@deepseek-ai/dsh-experimental-project-memory/client'
import { NS, type LibraryKey } from './locales.ts'
import css from './LibraryCard.module.css'

/** Host library operations injected by the browser mount. */
export interface LibraryCardFace {
  /** Read vault availability and the file listing in one call. */
  load: () => Promise<RemoteResult<MemoryLibrarySnapshot>>
  /** Re-read the file listing with an optional depth cap. */
  list: (request: MemoryLibraryListRequest) => Promise<RemoteResult<readonly LibraryFile[]>>
  /** Read one file for preview, with its real absolute on-disk path. */
  read: (request: MemoryLibraryReadRequest) => Promise<RemoteResult<MemoryLibraryReadResult>>
  /** Search the library by file name and content. */
  search: (request: MemoryLibrarySearchRequest) => Promise<RemoteResult<readonly LibrarySearchResult[]>>
  /** Append one reference line to the current conversation draft. */
  reference: (line: string) => boolean
}

/** Full props composed by the sidebar footer-action slot. */
export type LibraryCardProps = PropsRuntime<'sidebar.footer.action'> & InjectFace<LibraryCardFace> & PropsLocale<typeof NS>

/** Minimal file identity a row resolves to a preview read. */
interface FileRef {
  readonly relativePath: string
}

interface LibraryPaneProps {
  readonly loading: boolean
  readonly snapshot: MemoryLibrarySnapshot | null
  readonly error: string | null
  readonly query: string
  readonly results: readonly LibrarySearchResult[] | null
  readonly searching: boolean
  readonly preview: MemoryLibraryReadResult | null
  readonly previewError: string | null
  readonly copied: boolean
  readonly hint: LibraryKey | null
  readonly onRefresh: () => void
  readonly onQueryChange: (value: string) => void
  readonly onSearch: () => void
  readonly onOpenFile: (file: FileRef) => void
  readonly onClosePreview: () => void
  readonly onCopyPath: (path: string) => void
  readonly onReference: () => void
  readonly onClose: () => void
  readonly t: LibraryCardProps['t']
}

/** Unpack a RemoteResult into the value or null. */
function valueOf<T>(result: RemoteResult<T>): T | null {
  return result.ok ? result.value : null
}

/**
 * Library trigger button in the sidebar foot; opens a modal with the full
 * browse/search/preview surface. The snapshot loads on demand when the
 * trigger is first opened, not on sidebar mount.
 */
export function LibraryCard({ wide, t, load: loadSnapshot, read, search, reference: referenceLine }: LibraryCardProps): ReactNode {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [snapshot, setSnapshot] = useState<MemoryLibrarySnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<readonly LibrarySearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [preview, setPreview] = useState<MemoryLibraryReadResult | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [hint, setHint] = useState<LibraryKey | null>(null)
  const requestSequence = useRef(0)

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError(null)
    const result = await loadSnapshot()
    if (sequence !== requestSequence.current) return
    setLoading(false)
    if (result.ok) {
      setSnapshot(result.value)
      setPreview(null)
      setResults(null)
    } else {
      setError(result.error.message)
    }
  }, [loadSnapshot])

  const openModal = useCallback(() => {
    setOpen(true)
    void load()
  }, [load])

  const closeModal = useCallback(() => {
    setOpen(false)
  }, [])

  const openFile = useCallback(async (file: FileRef) => {
    setPreviewError(null)
    setCopied(false)
    setHint(null)
    const result = await read({ relativePath: file.relativePath })
    if (result.ok) {
      setPreview(result.value)
    } else {
      setPreviewError(result.error.message)
      setPreview(null)
    }
  }, [read])

  const runSearch = useCallback(async () => {
    const text = query.trim()
    setHint(null)
    if (text === '') {
      setResults(null)
      return
    }
    setSearching(true)
    const result = await search({ query: text })
    setSearching(false)
    setResults(valueOf(result))
    if (!result.ok) setError(result.error.message)
  }, [search, query])

  const copyPath = useCallback(async (path: string) => {
    setCopied(false)
    setHint(null)
    try {
      await navigator.clipboard.writeText(path)
      setCopied(true)
    } catch {
      setHint('copyPath.failed')
    }
  }, [])

  const reference = useCallback(() => {
    setHint(null)
    if (preview === null) return
    // A machine-parseable marker the model can resolve with its file tools.
    const line = `@vault:${preview.absolutePath}`
    if (referenceLine(line)) setHint('reference.inserted')
    else setHint('reference.noSession')
  }, [referenceLine, preview])

  const fileCount = snapshot?.status.status === 'AVAILABLE' ? snapshot.status.fileCount : undefined

  return (
    <>
      <div className={css.root} data-library-entry>
        <button
          type="button"
          className={css.trigger}
          aria-expanded={open}
          aria-label={t('trigger.aria')}
          onClick={openModal}
        >
          <IconDatabaseOutline16 size={wide ? 16 : 18} />
          {wide && <span className={css.triggerLabel}>{t('trigger.label')}</span>}
          {wide && fileCount !== undefined && <span className={css.count}>{t('fileCount', { count: fileCount })}</span>}
        </button>
      </div>
      <Modal
        open={open}
        onClose={closeModal}
        title={t('center.title')}
        headless
        className={css.centerModal as string}
      >
        <LibraryPane
          loading={loading}
          snapshot={snapshot}
          error={error}
          query={query}
          results={results}
          searching={searching}
          preview={preview}
          previewError={previewError}
          copied={copied}
          hint={hint}
          onRefresh={() => { void load() }}
          onQueryChange={setQuery}
          onSearch={() => { void runSearch() }}
          onOpenFile={(file) => { void openFile(file) }}
          onClosePreview={() => { setPreview(null) }}
          onCopyPath={(path) => { void copyPath(path) }}
          onReference={reference}
          onClose={closeModal}
          t={t}
        />
      </Modal>
    </>
  )
}

/** Presentational library pane split out so the client spec can exercise every branch. */

/** Extract a display title from a file path: use the basename without extension. */
function displayTitle(relativePath: string, t: LibraryCardProps['t']): string {
  const base = relativePath.split('/').pop() ?? relativePath
  const stem = base.replace(/\.(md|markdown|txt)$/i, '')
  // Hash-only note ids are unreadable; fall back to a short hash prefix.
  if (/^[0-9a-f]{16,}$/i.test(stem)) {
    return `${t('card.untitled')} · ${stem.slice(0, 8)}`
  }
  return stem
}

/** Format a timestamp as a short local date. */
function formatDate(mtimeMs: number): string {
  const d = new Date(mtimeMs)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

/** Type filter tabs. */
type KindFilter = 'all' | 'fact' | 'preference'

export function LibraryPane(props: LibraryPaneProps): ReactNode {
  const {
    loading, snapshot, error, query, results, searching,
    preview, previewError, copied, hint,
    onRefresh, onQueryChange, onSearch, onOpenFile,
    onClosePreview, onCopyPath, onReference, onClose, t,
  } = props

  const status = snapshot?.status.status
  const allFiles = snapshot?.files ?? []
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Filter files by kind
  const files = useMemo(() => {
    if (kindFilter === 'all') return allFiles
    return allFiles.filter(f => f.kind === kindFilter)
  }, [allFiles, kindFilter])

  // Sort by mtimeMs descending
  const sortedFiles = useMemo(() => {
    return [...files].sort((a, b) => b.mtimeMs - a.mtimeMs)
  }, [files])

  const handleCardClick = (file: LibraryFile) => {
    setSelectedPath(file.relativePath)
    onOpenFile({ relativePath: file.relativePath })
  }

  const handleClosePreview = () => {
    setSelectedPath(null)
    onClosePreview()
  }

  return (
    <div className={css.pane}>
      <div className={css.paneHeader}>
        <div className={css.paneTitle}>{t('center.title')}</div>
        <div className={css.paneActions}>
          <button type="button" className={css.iconBtn} onClick={onRefresh} aria-label={t('refresh')}>
            <IconRefreshOutline16 size={16} />
          </button>
          <button type="button" className={css.iconBtn} onClick={onClose} aria-label={t('close')}>
            <IconCloseOutline16 size={16} />
          </button>
        </div>
      </div>

      <div className={css.searchBar} hidden={status === 'UNAVAILABLE'}>
        <IconSearchOutline16 size={16} className={css.searchIcon} />
        <input
          type="text"
          className={css.searchInput}
          aria-label={t('search.label')}
          placeholder={t('search.placeholder')}
          value={query}
          onChange={(e: ChangeEvent<HTMLInputElement>) => { onQueryChange(e.target.value) }}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter') { onSearch() } }}
        />
        {query && (
          <button type="button" className={css.clearBtn} onClick={() => { onQueryChange('') }} aria-label={t('search.clear')}>
            ×
          </button>
        )}
        <button type="button" className={css.searchBtn} onClick={onSearch} disabled={searching}>{searching ? t('loading') : t('search.action')}</button>
      </div>

      <div className={css.filterTabs}>
        <button
          type="button"
          className={`${css.filterTab} ${kindFilter === 'all' ? css.filterTabActive : ''}`}
          onClick={() => { setKindFilter('all') }}
        >
          {t('filter.all')}
        </button>
        <button
          type="button"
          className={`${css.filterTab} ${kindFilter === 'fact' ? css.filterTabActive : ''}`}
          onClick={() => { setKindFilter('fact') }}
        >
          {t('filter.fact')}
        </button>
        <button
          type="button"
          className={`${css.filterTab} ${kindFilter === 'preference' ? css.filterTabActive : ''}`}
          onClick={() => { setKindFilter('preference') }}
        >
          {t('filter.preference')}
        </button>
      </div>

      <div className={css.bodyArea}>
        <div className={css.cardArea}>
          {loading && <div className={css.loadingState}>{t('loading')}</div>}
          {error && <div className={css.errorState} role="alert">{t('status.error')}: {error}</div>}

          {!loading && !error && status === 'UNAVAILABLE' && (
            <div className={css.unavailableState}>
              <div className={css.unavailableTitle}>{t('status.unavailable')}</div>
              <div className={css.unavailableHint}>{t('status.unavailableReason')}</div>
            </div>
          )}

          {!loading && !error && status === 'AVAILABLE' && (
            <>
              {results !== null ? (
                <div className={css.resultsList}>
                  {results.length === 0 ? (
                    <div className={css.emptyState}>
                      <div className={css.emptyTitle}>{t('search.empty')}</div>
                    </div>
                  ) : (
                    results.map(r => (
                      <button
                        key={r.relativePath}
                        type="button"
                        className={css.searchResult}
                        onClick={() => {
                          setSelectedPath(r.relativePath)
                          onOpenFile({ relativePath: r.relativePath })
                        }}
                      >
                        <div className={css.resultPath}>{r.relativePath}</div>
                        <div className={css.resultExcerpt}>{r.excerpt}</div>
                      </button>
                    ))
                  )}
                </div>
              ) : (
                <>
                  {sortedFiles.length === 0 ? (
                    <div className={css.emptyState}>
                      <IconDatabaseOutline16 size={48} className={css.emptyIcon} />
                      <div className={css.emptyTitle}>{t('empty.title')}</div>
                      <div className={css.emptyHint}>{t('empty.hint')}</div>
                    </div>
                  ) : (
                    <div className={css.cardGrid}>
                      {sortedFiles.map(file => (
                        <div
                          key={file.relativePath}
                          className={`${css.noteCard} ${selectedPath === file.relativePath ? css.noteCardSelected : ''}`}
                        >
                          <button
                            type="button"
                            className={css.cardMain}
                            aria-label={file.relativePath}
                            onClick={() => { handleCardClick(file) }}
                          >
                            <div className={css.cardTop}>
                              {file.kind && (
                                <span className={`${css.kindTag} ${file.kind === 'fact' ? css.kindFact : css.kindPreference}`}>
                                  {t(file.kind === 'fact' ? 'card.kind.fact' : 'card.kind.preference')}
                                </span>
                              )}
                              {file.entities && file.entities.length > 0 && (
                                <span className={css.entityTags}>
                                  {file.entities.slice(0, 2).map((e, i) => (
                                    <span key={i} className={css.entityTag}>{e}</span>
                                  ))}
                                </span>
                              )}
                            </div>
                            <div className={css.cardTitle}>{displayTitle(file.relativePath, t)}</div>
                            <div className={css.cardPath}>{file.relativePath}</div>
                            {file.summary && <div className={css.cardExcerpt}>{file.summary}</div>}
                            <div className={css.cardMeta}>
                              <span className={css.cardDate}>{formatDate(file.mtimeMs)}</span>
                            </div>
                          </button>
                          <div className={css.cardActions}>
                            <button
                              type="button"
                              className={css.cardActionBtn}
                              onClick={(e: ReactMouseEvent) => {
                                e.stopPropagation()
                                onReference()
                              }}
                            >
                              {t('card.reference')}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        {(preview || previewError) && (
          <div className={css.previewPanel}>
            <div className={css.previewHeader}>
              <div className={css.previewTitle}>{t('preview.title')}</div>
              <button type="button" className={css.iconBtn} onClick={handleClosePreview} aria-label={t('preview.close')}>
                <IconCloseOutline16 size={16} />
              </button>
            </div>
            {previewError && <div className={css.errorState} role="alert">{previewError}</div>}
            {preview && (
              <>
                <div className={css.previewPathRow}>
                  <span className={css.previewPathLabel}>{t('preview.path')}:</span>
                  <code className={css.previewPath}>{preview.absolutePath}</code>
                </div>
                <pre className={css.previewContent}>{preview.content}</pre>
                <div className={css.previewActions}>
                  <button type="button" className={css.actionBtn} onClick={() => { onCopyPath(preview.absolutePath) }}>
                    <IconLinkOutline16 size={14} />
                    {copied ? t('copyPath.copied') : t('copyPath')}
                  </button>
                  <button type="button" className={css.actionBtn} onClick={onReference}>
                    {t('reference')}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {hint && <div className={css.hintToast} role="status">{t(hint)}</div>}
    </div>
  )
}
