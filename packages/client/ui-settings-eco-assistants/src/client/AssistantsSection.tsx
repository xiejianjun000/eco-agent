/**
 * 「我的助手」设置 section：微信助手（开关 + 扫码说明）与飞书助手（适配中占位）。
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import type { SettingsScope, SettingsScopeSnapshot } from '@deepseek-ai/dsh-client-ui-settings/client'
import type { PluginInventorySnapshot } from '@deepseek-ai/dsh-api-remotes/client'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import { StateDot, Switch } from '@deepseek-ai/dsh-client-ui-primitives'
import type { StateDotState } from '@deepseek-ai/dsh-client-ui-primitives'
import type { en } from './locales.ts'
import styles from './AssistantsSection.module.css'

/** wechat-bridge namespace 的配置视图（与后端 Config 字段对齐）。 */
export interface WechatConfig {
  enabled?: boolean
  token?: string
  accountId?: string
  allowFrom?: string[]
}

/** Injected dependencies of {@link AssistantsSection} (slot `inject`). */
export interface AssistantsSectionInjected {
  /** renderer 把 `hooks.wechat` 绑定成 `useWechat` 选择器。 */
  hooks: {
    wechat: SettingsScope<WechatConfig>
  }
  /** 原始 scope，供组件写配置。 */
  wechat: SettingsScope<WechatConfig>
  /** 宿主插件清单的只读快照 —— 微信助手真实运行状态的唯一来源。 */
  list: () => Promise<PluginInventorySnapshot>
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** `useWechat` 选择器 hook 的类型（renderer 绑定后注入）。 */
type WechatSelectorHook = <S>(sel: (s: SettingsScopeSnapshot<WechatConfig>) => S) => S

/** Props delivered by the slot outlet. */
export type AssistantsSectionProps = Partial<InjectFace<AssistantsSectionInjected>> & PropsRenderSlots<never>

/** Section-local view state of the bridge row's runtime phase. */
type BridgeView =
  | { readonly status: 'reading' }
  | { readonly status: 'error' }
  | { readonly status: 'ready'; readonly dot: StateDotState; readonly key: keyof typeof en }

/** Loader row id of the WeChat bridge, as the web-app bundle names it. */
const BRIDGE_ROW = 'wechat-bridge'

/**
 * Translate the bridge row into an honest run state. The switch is the user's
 * fact and decides first; the runtime Fiber phase then says whether the plugin
 * behind it actually came up. Never the reverse — a Fiber can stay mounted
 * while the plugin has stopped serving.
 * @param entries - the Host inventory rows.
 * @param switchEnabled - the current `wechat-bridge.enabled` config value.
 */
function bridgeState(
  entries: readonly { entryId: unknown; fiberPhase: string | null }[],
  switchEnabled: boolean,
): { dot: StateDotState; key: keyof typeof en } {
  // 关着的开关就是关着：配置已写入，插件内部按它停掉对外连接。Fiber 是否
  // 还挂着是插件自己的事，不该盖过用户设的开关。
  if (!switchEnabled) return { dot: 'idle', key: 'wechat.state.stopped' }
  // 行 id 可能带 Loader 的 `include:` 组前缀，比对前先剥掉。
  const row = entries.find(entry => String(entry.entryId).replace(/^include:/, '') === BRIDGE_ROW)
  if (row === undefined) return { dot: 'idle', key: 'wechat.state.absent' }
  switch (row.fiberPhase) {
    case 'active': return { dot: 'done', key: 'wechat.state.running' }
    case 'failed': return { dot: 'error', key: 'wechat.state.failed' }
    case 'pending':
    case 'loading': return { dot: 'ongoing', key: 'wechat.state.starting' }
    default: return { dot: 'idle', key: 'wechat.state.idle' }
  }
}

/** Render the assistants section. */
export function AssistantsSection(props: AssistantsSectionProps): ReactNode {
  const { useWechat, wechat, list, t } = props
  if (useWechat === undefined || wechat === undefined || list === undefined || t === undefined) return null
  return <Loaded useWechat={useWechat} wechat={wechat} list={list} t={t} />
}

/** Loaded render: subscriptions are live here. */
function Loaded({ useWechat, wechat, list, t }: {
  useWechat: WechatSelectorHook
  wechat: SettingsScope<WechatConfig>
  list: () => Promise<PluginInventorySnapshot>
  t: (key: keyof typeof en) => string
}): ReactNode {
  const snapshot = useWechat(s => s)
  const enabled = snapshot.value?.enabled ?? false
  const [view, setView] = useState<BridgeView>({ status: 'reading' })

  const reload = useCallback(() => {
    let cancelled = false
    setView({ status: 'reading' })
    void list().then(
      (snap) => {
        if (cancelled) return
        const state = bridgeState(snap.entries, enabled)
        setView({ status: 'ready', dot: state.dot, key: state.key })
      },
      () => { if (!cancelled) setView({ status: 'error' }) },
    )
    return () => { cancelled = true }
    // `enabled` 必须进依赖：否则 reload 闭包里读到的是首次渲染的开关值，
    // 开关拨过去、状态却停在旧答案上。
  }, [list, enabled])

  // 开关写完立刻重读：开关表达的是意图，运行状态才是事实。
  useEffect(() => reload(), [reload])

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <div className={styles.head}>
          <h2 className={styles.title}>{t('wechat.title')}</h2>
          <span className={styles.state}>
            <StateDot state={view.status === 'ready' ? view.dot : 'ongoing'} />
            {view.status === 'ready'
              ? t(view.key)
              : view.status === 'error' ? t('wechat.state.error') : t('wechat.state.reading')}
          </span>
        </div>
        <p className={styles.desc}>{t('wechat.desc')}</p>
        <Switch
          checked={enabled}
          onChange={(next) => { void wechat.set('enabled', next) }}
          label={t('wechat.enabled')}
        />
        <p className={styles.hint}>{t('wechat.enabledHint')}</p>
      </section>

      <section className={styles.card}>
        <h2 className={styles.title}>{t('feishu.title')}</h2>
        <p className={styles.desc}>{t('feishu.desc')}</p>
        <p className={styles.todo}>{t('feishu.todo')}</p>
      </section>
    </div>
  )
}
