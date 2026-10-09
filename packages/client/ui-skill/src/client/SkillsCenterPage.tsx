/**
 * eco 技能中心面板：本会话组合可用的技能清单（浏览/调用侧，8088 负责上传/审核/广场）。
 * 数据来自 `skills/list` Remote（复用插件闭包的 per-session 单飞缓存）；调用走宿主
 * pre-step 的 `/name` 识别链路，卡片提供一键复制调用命令。
 */
import { useEffect, useState } from 'react'
import type { SkillEntry } from '@eco-agent/dsh-api-remotes/client'
import type { SessionId } from '@eco-agent/dsh-session/types'
import { IconSparkleRegular, Tag } from '@eco-agent/dsh-client-ui-primitives'
import type { InjectFace, PropsLocale, PropsRuntime } from '@eco-agent/dsh-client-ui-slots'
import { NS } from './locales.ts'
import css from './SkillsCenterPage.module.css'

/** Registration-side business face for the skills panel. */
export interface SkillsCenterFace {
  /**
   * One session's user-invocable skill catalog. Reuses the plugin's
   * per-session single-flight cache, so the '/' menu and this panel share
   * one RPC per session.
   */
  fetchCatalog: (sessionId: SessionId) => Promise<readonly SkillEntry[]>
}

/** Full props assembled by the main slot renderer. */
export type SkillsCenterPageProps =
  PropsRuntime<'main'>
  & PropsLocale<typeof NS>
  & InjectFace<SkillsCenterFace>

/** The page's four load states; absence of a selected session is its own empty branch. */
type LoadState =
  | { phase: 'noSession' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; skills: readonly SkillEntry[] }

/** How long the copied hint stays on a card's invoke button. */
const COPIED_MS = 2_000

/**
 * The Skills center page: one card per invocable skill of the selected
 * session's composition. The selection follows the main view's retained
 * session (the DocumentTitle rule); without one the page shows the
 * enter-a-session guidance instead of an error.
 * @param props - runtime slot currency, the session list hook, the catalog
 *   fetch face, and the namespace translator.
 * @returns the skills panel body.
 */
export function SkillsCenterPage({ useSessions, fetchCatalog, t }: SkillsCenterPageProps): React.ReactNode {
  const sessionId = useSessions(
    state => Object.values(state.byId).find(session => (session.retainedBy.mainView ?? 0) > 0)?.id,
  )
  const [state, setState] = useState<LoadState>({ phase: sessionId === undefined ? 'noSession' : 'loading' })
  const [copiedName, setCopiedName] = useState<string | undefined>(undefined)

  // The catalog follows the selected session: a switch refetches through the
  // shared cache (usually already warm by the '/' menu prewarm).
  useEffect(() => {
    if (sessionId === undefined) {
      setState({ phase: 'noSession' })
      return
    }
    let alive = true
    setState({ phase: 'loading' })
    fetchCatalog(sessionId).then(
      (skills) => {
        if (alive) setState({ phase: 'ready', skills })
      },
      (error) => {
        if (alive) setState({ phase: 'error', message: error instanceof Error ? error.message : String(error) })
      },
    )
    return () => {
      alive = false
    }
  }, [sessionId, fetchCatalog])

  // The copied hint clears itself; the cleanup covers a fast second copy.
  useEffect(() => {
    if (copiedName === undefined) return
    const timer = setTimeout(() => { setCopiedName(undefined) }, COPIED_MS)
    return () => { clearTimeout(timer) }
  }, [copiedName])

  const copyInvoke = (skill: SkillEntry): void => {
    void navigator.clipboard.writeText(`/${skill.name} `).then(
      () => { setCopiedName(skill.name) },
      (error) => { console.error('[ui-skill] copy failed:', error) },
    )
  }

  let body: React.ReactNode
  switch (state.phase) {
    case 'noSession':
      body = (
        <div className={css.notice}>
          <IconSparkleRegular size={20} className={css.noticeIcon} />
          <p>{t('panel.noSession')}</p>
        </div>
      )
      break
    case 'loading':
      body = <div className={css.notice}><p>{t('panel.loading')}</p></div>
      break
    case 'error':
      body = <div className={`${css.notice} ${css.noticeError}`}><p>{t('panel.error', { message: state.message })}</p></div>
      break
    case 'ready':
      body = state.skills.length === 0
        ? <div className={css.notice}><p>{t('panel.empty')}</p></div>
        : (
          <ul className={css.list} aria-label={t('panel.listAria')}>
            {state.skills.map(skill => (
              <li key={skill.name} className={css.card}>
                <div className={css.cardHead}>
                  <span className={css.name} title={`/${skill.name}`}>{`/${skill.name}`}</span>
                  <Tag tone={skill.modelInvocable ? 'info' : 'neutral'}>
                    {skill.modelInvocable ? t('card.model') : t('card.userOnly')}
                  </Tag>
                  <button
                    type="button"
                    className={css.copy}
                    onClick={() => { copyInvoke(skill) }}
                    aria-label={t('card.copyAria', { name: skill.name })}
                    title={t('card.copyAria', { name: skill.name })}
                  >
                    {copiedName === skill.name ? t('card.copied') : t('card.copy')}
                  </button>
                </div>
                <p className={css.description}>{skill.description}</p>
                {skill.whenToUse !== undefined && skill.whenToUse.length > 0
                  ? <p className={css.whenToUse}>{t('card.whenToUse', { whenToUse: skill.whenToUse })}</p>
                  : null}
              </li>
            ))}
          </ul>
        )
      break
  }

  return (
    <div className={css.root}>
      <header className={css.header}>
        <h1 className={css.title}>
          <IconSparkleRegular size={16} className={css.titleIcon} />
          {t('panel.title')}
        </h1>
        {state.phase === 'ready'
          ? <span className={css.count}>{t('panel.count', { count: state.skills.length })}</span>
          : null}
      </header>
      {body}
    </div>
  )
}
