/**
 * 「数据与诊断」设置 section：宿主插件统计 + 浏览器模块加载结果。
 *
 * 计数全部来自运行时快照；拿不到的就写"读不到"，不补估算值。
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import type { ClientEntryState } from '@deepseek-ai/dsh-client-modules/client'
import type { ObservableSnapshot } from '@deepseek-ai/dsh-client-store'
import type { PluginInventorySnapshot } from '@deepseek-ai/dsh-api-remotes/client'
import { Button, StateDot } from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { en } from './locales.ts'
import styles from './DiagnosticsSection.module.css'

/** Injected dependencies of {@link DiagnosticsSection} (slot `inject`). */
export interface DiagnosticsSectionInjected {
  /** Page-local module synchronization state. */
  hooks: { clientSync: ObservableSnapshot<ClientEntryState> }
  /** Read a current Host inventory snapshot. */
  list: () => Promise<PluginInventorySnapshot>
  /** Retry the latest client graph without changing the Host composition. */
  retryClient: () => void
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** Props delivered by the slot outlet. */
export type DiagnosticsSectionProps = Partial<InjectFace<DiagnosticsSectionInjected>> & PropsRenderSlots<never>

type Translate = (key: keyof typeof en) => string

/** Section-local view state. */
type ViewState =
  | { readonly status: 'loading' }
  | { readonly status: 'error'; readonly message: string }
  | { readonly status: 'ready'; readonly snapshot: PluginInventorySnapshot }

/** `useClientSync` 选择器 hook 的类型。 */
type ClientSyncHook = <S>(sel: (s: ClientEntryState) => S) => S

/** Render the diagnostics section. */
export function DiagnosticsSection(props: DiagnosticsSectionProps): ReactNode {
  const { useClientSync, list, retryClient, t } = props
  if (useClientSync === undefined || list === undefined || retryClient === undefined || t === undefined) return null
  return <Loaded useClientSync={useClientSync} list={list} retryClient={retryClient} t={t} />
}

/** Loaded render: subscriptions and reads are live here. */
function Loaded({ useClientSync, list, retryClient, t }: {
  useClientSync: ClientSyncHook
  list: () => Promise<PluginInventorySnapshot>
  retryClient: () => void
  t: Translate
}): ReactNode {
  const [view, setView] = useState<ViewState>({ status: 'loading' })
  const clientState = useClientSync(s => s)

  const reload = useCallback(() => {
    let cancelled = false
    setView({ status: 'loading' })
    void list().then(
      (snapshot) => { if (!cancelled) setView({ status: 'ready', snapshot }) },
      (error: unknown) => {
        if (cancelled) return
        setView({ status: 'error', message: error instanceof Error ? error.message : String(error) })
      },
    )
    return () => { cancelled = true }
  }, [list])

  useEffect(() => reload(), [reload])

  const entries = view.status === 'ready' ? view.snapshot.entries : []
  const enabled = entries.filter(entry => entry.enabled).length
  const active = entries.filter(entry => entry.fiberPhase === 'active').length
  const failed = entries.filter(entry => entry.fiberPhase === 'failed')

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <div className={styles.head}>
          <h2 className={styles.title}>{t('title')}</h2>
          <Button variant="outline" size="sm" onClick={() => { reload() }}>{t('refresh')}</Button>
        </div>
        <p className={styles.desc}>{t('desc')}</p>

        {view.status === 'loading' ? <p className={styles.hint}>{t('loading')}</p> : null}

        {view.status === 'error'
          ? (
            <div className={styles.errorRow}>
              <span className={styles.errorText}>{t('error')}：{view.message}</span>
              <Button variant="outline" size="sm" onClick={() => { reload() }}>{t('retry')}</Button>
            </div>
          )
          : null}

        {view.status === 'ready'
          ? (
            <div className={styles.stats}>
              <div className={styles.stat}><span className={styles.statValue}>{entries.length}</span><span className={styles.statLabel}>{t('total')}</span></div>
              <div className={styles.stat}><span className={styles.statValue}>{enabled}</span><span className={styles.statLabel}>{t('enabled')}</span></div>
              <div className={styles.stat}><span className={styles.statValue}>{active}</span><span className={styles.statLabel}>{t('active')}</span></div>
              <div className={styles.stat}><span className={styles.statValue}>{failed.length}</span><span className={styles.statLabel}>{t('failed')}</span></div>
            </div>
          )
          : null}

        {failed.length > 0
          ? (
            <ul className={styles.list}>
              {failed.map(entry => (
                <li key={entry.entryId} className={styles.row}>
                  <StateDot state="error" />
                  <span className={styles.name}>{entry.moduleName}</span>
                </li>
              ))}
            </ul>
          )
          : null}
      </section>

      <section className={styles.card}>
        <div className={styles.head}>
          <h2 className={styles.title}>{t('clientTitle')}</h2>
          <Button variant="outline" size="sm" onClick={retryClient}>{t('resync')}</Button>
        </div>
        <p className={styles.desc}>{t('clientDesc')}</p>
        {clientState.syncing ? <p className={styles.hint}>{t('clientSyncing')}</p> : null}
        {!clientState.syncing && clientState.failures.length === 0
          ? <p className={styles.hint}>{t('clientOk')}</p>
          : null}
        {clientState.failures.length > 0
          ? (
            <ul className={styles.list}>
              {clientState.failures.map(failure => (
                <li key={failure.id} className={styles.row}>
                  <StateDot state="error" />
                  <span className={styles.name}>{failure.id}</span>
                  <span className={styles.module}>{failure.message}</span>
                </li>
              ))}
            </ul>
          )
          : null}
      </section>

      <section className={styles.card}>
        <h2 className={styles.title}>{t('exportTitle')}</h2>
        <p className={styles.desc}>{t('exportDesc')}</p>
      </section>

      <section className={styles.card}>
        <h2 className={styles.title}>{t('archiveTitle')}</h2>
        <p className={styles.desc}>{t('archiveDesc')}</p>
      </section>
    </div>
  )
}
