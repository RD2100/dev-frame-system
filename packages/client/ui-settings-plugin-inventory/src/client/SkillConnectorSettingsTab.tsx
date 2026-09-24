import { useEffect, useId, useMemo, useState, type ReactNode } from 'react'
import type { PluginInventorySnapshot, SkillEntry } from '@deepseek-ai/dsh-api-remotes/client'
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
}

/** Props assembled by the Settings slot renderer. */
export type SkillConnectorSettingsTabProps =
  PropsRuntime<'settings.plugins.tab'>
  & PropsLocale<'settings.pluginInventory'>
  & InjectFace<SkillConnectorSettingsTabInjected>

type Translate = SkillConnectorSettingsTabProps['t']
type FiberPhase = PluginInventorySnapshot['entries'][number]['fiberPhase']

type ConnectorRow = {
  readonly key: string
  readonly moduleName: string
  readonly entryId: string | null
  readonly enabled: boolean | 'conditional'
  readonly fiberPhase: FiberPhase
  readonly scope: 'global' | 'preset'
  readonly presetName?: string
}

type ViewState =
  | { readonly status: 'loading' }
  | { readonly status: 'error' }
  | {
    readonly status: 'ready'
    readonly inventory: PluginInventorySnapshot
    readonly skills: SkillConnectorSkillList | undefined
  }

type Panel = 'skills' | 'connectors'

const CONNECTOR_MODULE = /(?:^|[-_/])(?:mcp|connector)(?:[-_/]|$)/iu

/** Keep the module identity visible without hiding the package scope. */
function moduleShortName(moduleName: string): string {
  const unscoped = moduleName.startsWith('@') ? moduleName.slice(moduleName.indexOf('/') + 1) : moduleName
  return unscoped.replace(/^cordis:/u, '').replace(/^dsh-(?:host-|client-)?/u, '')
}

/** Localized phase text for an entry's root Fiber. */
function phaseLabel(phase: FiberPhase, t: Translate): string {
  if (phase === null) return t('unobserved')
  switch (phase) {
    case 'pending': return t('pending')
    case 'loading': return t('loadingPhase')
    case 'active': return t('active')
    case 'failed': return t('failed')
    case 'unloading': return t('unloading')
  }
}

/** Whether a Loader module is an MCP or connector contribution. */
function isConnector(moduleName: string): boolean {
  return CONNECTOR_MODULE.test(moduleName)
}

/** Return the search text for one connector row. */
function connectorSearchText(row: ConnectorRow): string {
  return [row.moduleName, row.entryId ?? '', row.presetName ?? ''].join(' ').toLocaleLowerCase()
}

/** Build connector rows from the authoritative Loader and preset projections. */
function connectorRows(snapshot: PluginInventorySnapshot, presetName: (id: string) => string): ConnectorRow[] {
  const rows: ConnectorRow[] = []
  for (const entry of snapshot.entries) {
    if (!isConnector(entry.moduleName)) continue
    rows.push({
      key: `global:${entry.entryId}`,
      moduleName: entry.moduleName,
      entryId: entry.entryId,
      enabled: entry.enabled,
      fiberPhase: entry.fiberPhase,
      scope: 'global',
    })
  }
  for (const preset of snapshot.agentPresets ?? []) {
    for (const [index, row] of preset.rows.entries()) {
      if (!isConnector(row.moduleName)) continue
      rows.push({
        key: `preset:${preset.id}:${String(index)}`,
        moduleName: row.moduleName,
        entryId: row.entryId,
        enabled: row.enabled,
        fiberPhase: row.fiberPhase,
        scope: 'preset',
        presetName: presetName(preset.id),
      })
    }
  }
  return rows
}

/** Format one enablement tag without exposing configuration values. */
function enablementLabel(enabled: ConnectorRow['enabled'], t: Translate): string {
  if (enabled === 'conditional') return t('conditionalTag')
  return enabled ? t('enabledTag') : t('disabledTag')
}

/** A compact read-only status card for one connector. */
function ConnectorCard({ row, t }: { readonly row: ConnectorRow; readonly t: Translate }): ReactNode {
  const status = row.fiberPhase === 'failed' ? t('failedTag') : enablementLabel(row.enabled, t)
  return (
    <li className={css.card} data-connector-row={row.key} data-failed={row.fiberPhase === 'failed' ? 'true' : undefined}>
      <div className={css.capabilityCardContent}>
        <div className={css.capabilityTitleBlock}>
          <strong className={css.cardTitle} title={row.moduleName}>{moduleShortName(row.moduleName)}</strong>
          <span className={css.capabilityMeta}>{row.scope === 'global' ? t('globalTitle') : row.presetName}</span>
        </div>
        <span className={css.cardTrailing}>
          <span className={css.configTag} data-kind={row.fiberPhase === 'failed' ? 'failed' : row.enabled === 'conditional' ? 'conditional' : row.enabled ? 'enabled' : undefined}>
            {status}
          </span>
          <span className={css.capabilityPhase}>{phaseLabel(row.fiberPhase, t)}</span>
        </span>
      </div>
      <dl className={css.capabilityDetails}>
        <div><dt>{t('moduleLabel')}</dt><dd>{row.moduleName}</dd></div>
        {row.entryId === null ? null : <div><dt>{t('entryLabel')}</dt><dd><code>{row.entryId}</code></dd></div>}
        <div><dt>{t('configuration')}</dt><dd>{row.scope === 'global' ? t('globalProfileOwned') : t('presetProfileOwned')}</dd></div>
      </dl>
    </li>
  )
}

/** A compact read-only card for one current-session Skill. */
function SkillCard({ skill, t }: { readonly skill: SkillEntry; readonly t: Translate }): ReactNode {
  const modelLabel = skill.modelInvocable ? t('modelInvocable') : t('modelHidden')
  return (
    <li className={css.card} data-skill-name={skill.name}>
      <div className={css.capabilityCardContent}>
        <div className={css.capabilityTitleBlock}>
          <strong className={css.cardTitle}>{`/${skill.name}`}</strong>
          <span className={css.capabilityMeta}>{skill.description}</span>
        </div>
        <span className={css.cardTrailing}>
          <span className={css.configTag} data-kind={skill.modelInvocable ? 'enabled' : undefined}>{modelLabel}</span>
        </span>
      </div>
      <dl className={css.capabilityDetails}>
        <div><dt>{t('configuration')}</dt><dd>{t('sessionProfileOwned')}</dd></div>
        <div><dt>{t('userInvocation')}</dt><dd>{skill.modelInvocable ? t('modelAndUser') : t('userOnly')}</dd></div>
        {skill.whenToUse === undefined ? null : <div><dt>{t('whenToUse')}</dt><dd>{skill.whenToUse}</dd></div>}
      </dl>
    </li>
  )
}

/** Read-only Skill and MCP connector settings page backed by official Remotes. */
export function SkillConnectorSettingsTab({ listInventory, listSkills, t }: SkillConnectorSettingsTabProps): ReactNode {
  const sectionId = useId()
  const [request, setRequest] = useState(0)
  const [panel, setPanel] = useState<Panel>('skills')
  const [query, setQuery] = useState('')
  const [state, setState] = useState<ViewState>({ status: 'loading' })

  useEffect(() => {
    let current = true
    void Promise.resolve().then(async () => {
      const [inventory, skills] = await Promise.all([listInventory(), listSkills()])
      if (current) setState({ status: 'ready', inventory, skills })
    }).catch(() => {
      if (current) setState({ status: 'error' })
    })
    return () => { current = false }
  }, [listInventory, listSkills, request])

  const refresh = (): void => {
    setState({ status: 'loading' })
    setRequest(value => value + 1)
  }
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const snapshot = state.status === 'ready' ? state.inventory : undefined
  const skills = state.status === 'ready' ? state.skills?.skills ?? [] : []
  const rows = useMemo(
    () => snapshot === undefined ? [] : connectorRows(snapshot, (id) => {
      const preset = snapshot.agentPresets?.find(item => item.id === id)
      return preset?.name ?? id
    }),
    [snapshot],
  )
  const filteredSkills = skills.filter(skill => normalizedQuery.length === 0
    || `${skill.name} ${skill.description} ${skill.whenToUse ?? ''}`.toLocaleLowerCase().includes(normalizedQuery))
  const filteredConnectors = rows.filter(row => normalizedQuery.length === 0 || connectorSearchText(row).includes(normalizedQuery))
  const activeCount = panel === 'skills' ? filteredSkills.length : filteredConnectors.length
  const skillSessionMissing = state.status === 'ready' && state.skills === undefined

  return (
    <div className={css.section} aria-busy={state.status === 'loading'}>
      <div className={css.capabilityHeader}>
        <div>
          <h3 className={css.capabilityHeading}>{t('capabilitiesTitle')}</h3>
          <p className={css.capabilityIntro}>{t('capabilitiesIntro')}</p>
        </div>
        <button type="button" className={css.refreshButton} onClick={refresh} disabled={state.status === 'loading'}>
          <IconRefreshOutline16 size={14} aria-hidden="true" />
          {t('refresh')}
        </button>
      </div>
      <p className={css.profileOwnedNotice} role="note">{t('profileOwnedNotice')}</p>
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
            <input
              type="search"
              value={query}
              placeholder={t('capabilitiesSearch')}
              aria-label={t('capabilitiesSearch')}
              onChange={(event) => { setQuery(event.currentTarget.value) }}
            />
          </label>
          <div className={css.capabilityTabs} role="tablist" aria-label={t('capabilitiesTabs')}>
            <button
              type="button"
              role="tab"
              aria-selected={panel === 'skills'}
              aria-controls={`${sectionId}-skills`}
              className={css.capabilityTab}
              data-active={panel === 'skills' ? 'true' : undefined}
              onClick={() => { setPanel('skills') }}
            >
              {t('skillsTab')} <span>{String(skills.length)}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={panel === 'connectors'}
              aria-controls={`${sectionId}-connectors`}
              className={css.capabilityTab}
              data-active={panel === 'connectors' ? 'true' : undefined}
              onClick={() => { setPanel('connectors') }}
            >
              {t('connectorsTab')} <span>{String(rows.length)}</span>
            </button>
          </div>
          {panel === 'skills' ? (
            <section id={`${sectionId}-skills`} role="tabpanel" aria-label={t('skillsTab')}>
              {skillSessionMissing ? <p className={css.status}>{t('skillsNoSession')}</p> : null}
              {!skillSessionMissing && filteredSkills.length === 0 ? <p className={css.status}>{normalizedQuery === '' ? t('skillsEmpty') : t('emptySearch')}</p> : null}
              {filteredSkills.length > 0 ? (
                <ul className={css.cards}>
                  {filteredSkills.map(skill => <SkillCard key={skill.name} skill={skill} t={t} />)}
                </ul>
              ) : null}
            </section>
          ) : (
            <section id={`${sectionId}-connectors`} role="tabpanel" aria-label={t('connectorsTab')}>
              {filteredConnectors.length === 0 ? <p className={css.status}>{normalizedQuery === '' ? t('connectorsEmpty') : t('emptySearch')}</p> : null}
              {filteredConnectors.length > 0 ? (
                <ul className={css.cards}>
                  {filteredConnectors.map(row => <ConnectorCard key={row.key} row={row} t={t} />)}
                </ul>
              ) : null}
            </section>
          )}
          <p className={css.capabilityCount}>{String(activeCount)} {t('countUnit')}</p>
        </div>
      ) : null}
    </div>
  )
}
