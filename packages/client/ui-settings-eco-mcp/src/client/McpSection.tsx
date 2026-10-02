/**
 * 「MCP 服务」设置 section：远程 MCP 服务的真实运行姿态。
 *
 * 数据只有一个来源 —— 宿主 `pluginInventory.list()` 返回的 Loader 行，字段是
 * `enabled` 与 `fiberPhase`。页面不推测工具数、不推测端点健康：判定不了的一律
 * 画成灰点，绝不用一个绿点假装连上了。
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import type { PluginInventorySnapshot } from '@deepseek-ai/dsh-api-remotes/client'
import { Button, StateDot, Tag } from '@deepseek-ai/dsh-client-ui-primitives'
import type { StateDotState } from '@deepseek-ai/dsh-client-ui-primitives'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { en } from './locales.ts'
import styles from './McpSection.module.css'

/** One Loader entry as the inventory reports it. */
type Entry = PluginInventorySnapshot['entries'][number]

/** Injected dependencies of {@link McpSection} (slot `inject`). */
export interface McpSectionInjected {
  /** Read a current Host inventory snapshot. */
  list: () => Promise<PluginInventorySnapshot>
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** Props delivered by the slot outlet. */
export type McpSectionProps = Partial<InjectFace<McpSectionInjected>> & PropsRenderSlots<never>

type Translate = (key: keyof typeof en) => string

/** Section-local view state. */
type ViewState =
  | { readonly status: 'loading' }
  | { readonly status: 'error'; readonly message: string }
  | { readonly status: 'ready'; readonly snapshot: PluginInventorySnapshot }

/**
 * Translate runtime facts into an honest display state. A row the Loader
 * disabled is idle-grey regardless of any stale phase it still reports.
 * @param entry - one inventory entry.
 * @returns dot tone plus the copy key naming that state.
 */
function displayState(entry: Entry): { dot: StateDotState; key: keyof typeof en } {
  if (!entry.enabled) return { dot: 'idle', key: 'state.disabled' }
  switch (entry.fiberPhase) {
    case 'active': return { dot: 'done', key: 'state.active' }
    case 'failed': return { dot: 'error', key: 'state.failed' }
    case 'pending': return { dot: 'ongoing', key: 'state.pending' }
    case 'loading': return { dot: 'ongoing', key: 'state.loading' }
    case 'unloading': return { dot: 'warning', key: 'state.unloading' }
    default: return { dot: 'idle', key: 'state.idle' }
  }
}

/**
 * Display name for one service row. The deployment-facing identity is the
 * Loader row id, not the module specifier: two rows can load the same MCP
 * client package with different server URLs, and the row id is the only thing
 * that tells them apart. Deployments name an external-MCP row after its
 * `serverName` (`eco-matrix-remote`), so the row id, the setting page, and the
 * `mcp__<serverName>__*` tool namespace all spell the same service.
 * @param entry - one inventory entry.
 */
function displayName(entry: Entry): string {
  // Loader 组会给行 id 加 `include:` 前缀；那是组装事实，不是服务名。
  return String(entry.entryId).replace(/^include:/, '')
}

/**
 * Where one service row lives, read off the package that provides it — the
 * only fact the inventory carries. `dsh-mcp-client` bridges an *external*
 * server (a spawned local process or a remote HTTP endpoint; which one is
 * deployment config this page does not read), while `dsh-mcp-resources`
 * exposes resources this process owns. Anything else is left unlabelled
 * rather than guessed.
 * @param entry - one inventory entry.
 * @returns the copy key naming the row's origin, or undefined to omit.
 */
function kindKey(entry: Entry): keyof typeof en | undefined {
  if (entry.moduleName.includes('/dsh-mcp-client')) return 'kind.external'
  if (entry.moduleName.includes('/dsh-mcp-resources')) return 'kind.local'
  return undefined
}

/**
 * Whether one Loader row is an MCP service row. Settings UI packages carry
 * "mcp" in their own name, so they are excluded: this list is about services,
 * not about every plugin that happens to mention MCP.
 * @param entry - one inventory entry.
 * @returns true when the row provides or brokers an MCP service.
 */
function isMcpEntry(entry: Entry): boolean {
  const name = entry.moduleName.toLocaleLowerCase()
  if (name.includes('ui-settings') || name.includes('ui-eco-')) return false
  return name.includes('mcp')
}

/** Render the MCP services section. */
export function McpSection(props: McpSectionProps): ReactNode {
  const { list, t } = props
  if (list === undefined || t === undefined) return null
  return <Loaded list={list} t={t} />
}

/** Loaded render: subscriptions and reads are live here. */
function Loaded({ list, t }: { list: () => Promise<PluginInventorySnapshot>; t: Translate }): ReactNode {
  const [view, setView] = useState<ViewState>({ status: 'loading' })

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

  const services = view.status === 'ready'
    ? view.snapshot.entries.filter(isMcpEntry)
    : []

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

        {view.status === 'ready' && services.length === 0 ? <p className={styles.hint}>{t('empty')}</p> : null}

        {services.length > 0
          ? (
            <ul className={styles.list}>
              {services.map((entry) => {
                const state = displayState(entry)
                const kind = kindKey(entry)
                return (
                  <li key={entry.entryId} className={styles.row}>
                    <StateDot state={state.dot} />
                    <span className={styles.name}>{displayName(entry)}</span>
                    <Tag>{t(state.key)}</Tag>
                    {kind === undefined ? null : <Tag tone="neutral">{t(kind)}</Tag>}
                    <span className={styles.module}>{entry.moduleName}</span>
                  </li>
                )
              })}
            </ul>
          )
          : null}

        <p className={styles.hint}>{t('hint')}</p>
      </section>
    </div>
  )
}
