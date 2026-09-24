import { useEffect, useId, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import type {
  McpInventorySnapshot,
  McpServerConfig,
  McpServerEntry,
  PluginInventorySnapshot,
  SkillInstallRequest,
  SkillManagementEntry,
  SkillManagementSnapshot,
  SkillManagementValue,
  SkillSetEnabledRequest,
  SkillEntry,
} from '@deepseek-ai/dsh-api-remotes/client'
import type { PluginEntryId } from '@deepseek-ai/dsh-api-remotes/client'
import {
  IconRefreshOutline16,
  IconSearchOutline16,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import css from './PluginInventorySettingsTab.module.css'

/** Read-only list result used by the current-session Skill Remote. */
export interface SkillConnectorSkillList {
  readonly skills: readonly SkillEntry[]
}

/** Registration-side Remote faces used by the settings tab. */
export interface SkillConnectorSettingsTabInjected {
  /** Read a fresh Host plugin snapshot. */
  readonly listInventory: () => Promise<PluginInventorySnapshot>
  /** Read the active Session's effective Skill catalog, when one is selected. */
  readonly listSkills: () => Promise<SkillConnectorSkillList | undefined>
  /** Read user-owned Skills from the durable DSH home. */
  readonly listManagedSkills: () => Promise<SkillManagementSnapshot>
  /** Install one user-owned Skill. */
  readonly installSkill: (request: SkillInstallRequest) => Promise<SkillManagementValue>
  /** Enable or disable one user-owned Skill. */
  readonly setSkillEnabled: (request: SkillSetEnabledRequest) => Promise<SkillManagementValue>
  /** Remove one user-owned Skill. */
  readonly removeSkill: (name: string) => Promise<void>
  /** Read the live and persisted MCP clients. */
  readonly listMcp: () => Promise<McpInventorySnapshot>
  /** Add one MCP client. */
  readonly createMcp: (config: McpServerConfig) => Promise<void>
  /** Replace one MCP client. */
  readonly updateMcp: (entryId: PluginEntryId, config: McpServerConfig) => Promise<void>
  /** Remove one MCP client. */
  readonly removeMcp: (entryId: PluginEntryId) => Promise<void>
  /** Enable or disable one MCP client. */
  readonly setMcpEnabled: (entryId: PluginEntryId, enabled: boolean) => Promise<void>
  /** Probe one MCP client configuration. */
  readonly testMcpEntry: (entryId: PluginEntryId) => Promise<{ readonly ok: boolean; readonly message: string }>
}

/** Props assembled by the Settings slot renderer. */
export type SkillConnectorSettingsTabProps =
  PropsRuntime<'settings.plugins.tab'>
  & PropsLocale<'settings.pluginInventory'>
  & InjectFace<SkillConnectorSettingsTabInjected>

type Panel = 'skills' | 'connectors'
type Transport = 'stdio' | 'streamable-http'

interface McpFormState {
  readonly serverName: string
  readonly transport: Transport
  readonly command: string
  readonly url: string
}

type ViewState =
  | { readonly status: 'loading' }
  | { readonly status: 'error' }
  | {
    readonly status: 'ready'
    readonly inventory: PluginInventorySnapshot
    readonly skills: SkillConnectorSkillList | undefined
    readonly managedSkills: SkillManagementSnapshot
    readonly mcp: McpInventorySnapshot
  }

const EMPTY_MCP_FORM: McpFormState = { serverName: '', transport: 'stdio', command: '', url: '' }

function skillSearchText(skill: SkillManagementEntry): string {
  return [skill.name, skill.description, skill.whenToUse ?? ''].join(' ').toLocaleLowerCase()
}

function mcpSearchText(server: McpServerEntry): string {
  return [server.serverName, server.entryId, server.transport].join(' ').toLocaleLowerCase()
}

function configForForm(form: McpFormState): McpServerConfig {
  return form.transport === 'stdio'
    ? { serverName: form.serverName.trim(), transport: 'stdio', command: form.command.trim() }
    : { serverName: form.serverName.trim(), transport: 'streamable-http', url: form.url.trim() }
}

/** Browser-safe Skill and MCP management page backed by Host Remotes. */
export function SkillConnectorSettingsTab({
  listInventory,
  listSkills,
  listManagedSkills,
  installSkill,
  setSkillEnabled,
  removeSkill,
  listMcp,
  createMcp,
  updateMcp,
  removeMcp,
  setMcpEnabled,
  testMcpEntry,
  t,
}: SkillConnectorSettingsTabProps): ReactNode {
  const sectionId = useId()
  const [request, setRequest] = useState(0)
  const [panel, setPanel] = useState<Panel>('skills')
  const [query, setQuery] = useState('')
  const [state, setState] = useState<ViewState>({ status: 'loading' })
  const [pending, setPending] = useState<string | undefined>()
  const [operationError, setOperationError] = useState(false)
  const [operationMessage, setOperationMessage] = useState<string | undefined>()
  const [skillForm, setSkillForm] = useState<SkillInstallRequest>({ name: '', description: '', content: '' })
  const [mcpForm, setMcpForm] = useState<McpFormState>(EMPTY_MCP_FORM)
  const [editingMcp, setEditingMcp] = useState<PluginEntryId | undefined>()

  useEffect(() => {
    let current = true
    void Promise.resolve().then(async () => {
      const [inventory, skills, managedSkills, mcp] = await Promise.all([
        listInventory(), listSkills(), listManagedSkills(), listMcp(),
      ])
      if (current) setState({ status: 'ready', inventory, skills, managedSkills, mcp })
    }).catch(() => {
      if (current) setState({ status: 'error' })
    })
    return () => { current = false }
  }, [listInventory, listSkills, listManagedSkills, listMcp, request])

  const refresh = (): void => {
    setState({ status: 'loading' })
    setOperationError(false)
    setOperationMessage(undefined)
    setRequest(value => value + 1)
  }

  const run = async (key: string, operation: () => Promise<void>): Promise<void> => {
    setPending(key)
    setOperationError(false)
    setOperationMessage(undefined)
    try {
      await operation()
      refresh()
    } catch {
      setOperationError(true)
    } finally {
      setPending(current => current === key ? undefined : current)
    }
  }

  const submitSkill = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    void run('skill-install', async () => {
      await installSkill({
        name: skillForm.name.trim(),
        description: skillForm.description.trim(),
        content: skillForm.content,
        ...(skillForm.whenToUse?.trim() === undefined || skillForm.whenToUse.trim() === ''
          ? {} : { whenToUse: skillForm.whenToUse.trim() }),
      })
      setSkillForm({ name: '', description: '', content: '' })
    })
  }

  const submitMcp = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    const config = configForForm(mcpForm)
    void run(editingMcp === undefined ? 'mcp-create' : `mcp-update:${editingMcp}`, async () => {
      if (editingMcp === undefined) await createMcp(config)
      else await updateMcp(editingMcp, config)
      setMcpForm(EMPTY_MCP_FORM)
      setEditingMcp(undefined)
    })
  }

  const snapshot = state.status === 'ready' ? state : undefined
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const managedSkills = useMemo(
    () => (snapshot?.managedSkills.skills ?? []).filter(skill => normalizedQuery === '' || skillSearchText(skill).includes(normalizedQuery)),
    [normalizedQuery, snapshot?.managedSkills.skills],
  )
  const mcpServers = useMemo(
    () => (snapshot?.mcp.servers ?? []).filter(server => normalizedQuery === '' || mcpSearchText(server).includes(normalizedQuery)),
    [normalizedQuery, snapshot?.mcp.servers],
  )
  const sessionSkills = snapshot?.skills?.skills ?? []
  const sessionSkillMissing = snapshot !== undefined && snapshot.skills === undefined

  const beginEditMcp = (server: McpServerEntry): void => {
    const config = server.config
    setEditingMcp(server.entryId)
    setMcpForm({
      serverName: server.serverName,
      transport: server.transport === 'streamable-http' ? 'streamable-http' : 'stdio',
      command: typeof config.command === 'string' ? config.command : '',
      url: typeof config.url === 'string' ? config.url : '',
    })
  }

  return (
    <div className={css.section} aria-busy={state.status === 'loading'}>
      <div className={css.capabilityHeader}>
        <div>
          <h3 className={css.capabilityHeading}>{t('capabilitiesTitle')}</h3>
          <p className={css.capabilityIntro}>{t('capabilitiesIntro')}</p>
        </div>
        <button type="button" className={css.refreshButton} onClick={refresh} disabled={state.status === 'loading' || pending !== undefined}>
          <IconRefreshOutline16 size={14} aria-hidden="true" />
          {t('refresh')}
        </button>
      </div>
      <p className={css.profileOwnedNotice} role="note">{t('profileOwnedNotice')}</p>
      {operationError ? <p className={css.status} role="alert">{t('operationError')}</p> : null}
      {operationMessage === undefined ? null : <p className={css.status} role="status">{operationMessage}</p>}
      {state.status === 'loading' ? <p className={css.status}>{t('loading')}</p> : null}
      {state.status === 'error' ? (
        <div className={css.failure}>
          <p role="alert">{t('error')}</p>
          <button type="button" onClick={refresh}>{t('retry')}</button>
        </div>
      ) : null}
      {snapshot !== undefined ? (
        <div className={css.catalog}>
          <label className={css.search}>
            <IconSearchOutline16 aria-hidden="true" />
            <span className={css.visuallyHidden}>{t('capabilitiesSearch')}</span>
            <input type="search" value={query} placeholder={t('capabilitiesSearch')} aria-label={t('capabilitiesSearch')} onChange={(event) => { setQuery(event.currentTarget.value) }} />
          </label>
          <div className={css.capabilityTabs} role="tablist" aria-label={t('capabilitiesTabs')}>
            <button type="button" role="tab" aria-selected={panel === 'skills'} aria-controls={`${sectionId}-skills`} className={css.capabilityTab} data-active={panel === 'skills' ? 'true' : undefined} onClick={() => { setPanel('skills') }}>
              {t('skillsTab')} <span>{String(managedSkills.length)}</span>
            </button>
            <button type="button" role="tab" aria-selected={panel === 'connectors'} aria-controls={`${sectionId}-connectors`} className={css.capabilityTab} data-active={panel === 'connectors' ? 'true' : undefined} onClick={() => { setPanel('connectors') }}>
              {t('connectorsTab')} <span>{String(mcpServers.length)}</span>
            </button>
          </div>
          {panel === 'skills' ? (
            <section id={`${sectionId}-skills`} role="tabpanel" aria-label={t('skillsTab')}>
              <form className={css.managementForm} onSubmit={submitSkill}>
                <h4>{t('installSkill')}</h4>
                <input aria-label={t('skillName')} placeholder={t('skillName')} value={skillForm.name} onChange={(event) => { const next = event.currentTarget.value; setSkillForm(value => ({ ...value, name: next })) }} />
                <input aria-label={t('skillDescription')} placeholder={t('skillDescription')} value={skillForm.description} onChange={(event) => { const next = event.currentTarget.value; setSkillForm(value => ({ ...value, description: next })) }} />
                <input aria-label={t('skillWhenToUse')} placeholder={t('skillWhenToUse')} value={skillForm.whenToUse ?? ''} onChange={(event) => { const next = event.currentTarget.value; setSkillForm(value => ({ ...value, whenToUse: next })) }} />
                <textarea aria-label={t('skillContent')} placeholder={t('skillContent')} value={skillForm.content} onChange={(event) => { const next = event.currentTarget.value; setSkillForm(value => ({ ...value, content: next })) }} />
                <button type="submit" disabled={pending !== undefined}>{pending === 'skill-install' ? t('working') : t('install')}</button>
              </form>
              <h4 className={css.subheading}>{t('managedSkills')}</h4>
              {managedSkills.length === 0 ? <p className={css.status}>{normalizedQuery === '' ? t('skillsEmpty') : t('emptySearch')}</p> : null}
              {managedSkills.length > 0 ? (
                <ul className={css.cards}>
                  {managedSkills.map(skill => (
                    <li key={skill.name} className={css.card} data-skill-name={skill.name}>
                      <div className={css.capabilityCardContent}>
                        <div className={css.capabilityTitleBlock}>
                          <strong className={css.cardTitle}>{`/${skill.name}`}</strong>
                          <span className={css.capabilityMeta}>{skill.description}</span>
                        </div>
                        <span className={css.configTag} data-kind={skill.enabled ? 'enabled' : undefined}>{skill.enabled ? t('enabledTag') : t('disabledTag')}</span>
                      </div>
                      <div className={css.managementActions}>
                        <button type="button" onClick={() => { void run(`skill-toggle:${skill.name}`, async () => { await setSkillEnabled({ name: skill.name, enabled: !skill.enabled }) }) }} disabled={pending !== undefined}>{skill.enabled ? t('disable') : t('enable')}</button>
                        <button type="button" onClick={() => { void run(`skill-remove:${skill.name}`, async () => { await removeSkill(skill.name) }) }} disabled={pending !== undefined}>{t('uninstall')}</button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
              {sessionSkillMissing ? <p className={css.status}>{t('skillsNoSession')}</p> : null}
              {sessionSkills.length > 0 ? <p className={css.status}>{t('sessionSkills')}: {sessionSkills.map(skill => `/${skill.name}`).join(', ')}</p> : null}
            </section>
          ) : (
            <section id={`${sectionId}-connectors`} role="tabpanel" aria-label={t('connectorsTab')}>
              <form className={css.managementForm} onSubmit={submitMcp}>
                <h4>{editingMcp === undefined ? t('addMcp') : t('editMcp')}</h4>
                <input aria-label={t('mcpServerName')} placeholder={t('mcpServerName')} value={mcpForm.serverName} onChange={(event) => { const next = event.currentTarget.value; setMcpForm(value => ({ ...value, serverName: next })) }} />
                <select aria-label={t('mcpTransport')} value={mcpForm.transport} onChange={(event) => { const next = event.currentTarget.value as Transport; setMcpForm(value => ({ ...value, transport: next })) }}>
                  <option value="stdio">stdio</option>
                  <option value="streamable-http">streamable-http</option>
                </select>
                {mcpForm.transport === 'stdio'
                  ? <input aria-label={t('mcpCommand')} placeholder={t('mcpCommand')} value={mcpForm.command} onChange={(event) => { const next = event.currentTarget.value; setMcpForm(value => ({ ...value, command: next })) }} />
                  : <input aria-label={t('mcpUrl')} placeholder={t('mcpUrl')} value={mcpForm.url} onChange={(event) => { const next = event.currentTarget.value; setMcpForm(value => ({ ...value, url: next })) }} />}
                <div className={css.managementActions}>
                  <button type="submit" disabled={pending !== undefined}>{pending !== undefined && (pending === 'mcp-create' || pending.startsWith('mcp-update:')) ? t('working') : editingMcp === undefined ? t('add') : t('save')}</button>
                  {editingMcp === undefined ? null : <button type="button" onClick={() => { setEditingMcp(undefined); setMcpForm(EMPTY_MCP_FORM) }} disabled={pending !== undefined}>{t('cancel')}</button>}
                </div>
              </form>
              {mcpServers.length === 0 ? <p className={css.status}>{normalizedQuery === '' ? t('connectorsEmpty') : t('emptySearch')}</p> : null}
              {mcpServers.length > 0 ? (
                <ul className={css.cards}>
                  {mcpServers.map(server => (
                    <li key={server.entryId} className={css.card} data-mcp-name={server.serverName}>
                      <div className={css.capabilityCardContent}>
                        <div className={css.capabilityTitleBlock}>
                          <strong className={css.cardTitle}>{server.serverName}</strong>
                          <span className={css.capabilityMeta}>{server.transport} · {server.entryId}</span>
                        </div>
                        <span className={css.configTag} data-kind={server.enabled ? 'enabled' : undefined}>{server.enabled ? t('enabledTag') : t('disabledTag')}</span>
                      </div>
                      <div className={css.managementActions}>
                        <button type="button" onClick={() => { void run(`mcp-toggle:${server.entryId}`, async () => { await setMcpEnabled(server.entryId, !server.enabled) }) }} disabled={pending !== undefined}>{server.enabled ? t('disable') : t('enable')}</button>
                        <button type="button" onClick={() => { void run(`mcp-test:${server.entryId}`, async () => { const result = await testMcpEntry(server.entryId); setOperationMessage(result.message); if (!result.ok) throw new Error(result.message) }) }} disabled={pending !== undefined}>{t('test')}</button>
                        <button type="button" onClick={() => { beginEditMcp(server) }} disabled={pending !== undefined}>{t('edit')}</button>
                        <button type="button" onClick={() => { void run(`mcp-remove:${server.entryId}`, async () => { await removeMcp(server.entryId) }) }} disabled={pending !== undefined}>{t('remove')}</button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          )}
        </div>
      ) : null}
    </div>
  )
}
