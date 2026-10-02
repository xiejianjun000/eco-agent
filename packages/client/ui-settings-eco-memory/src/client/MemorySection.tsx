/**
 * 「记忆」设置 section。
 *
 * 记忆完全取决于宿主有没有注册 `memory` namespace。没有就直说没有 ——
 * 这条来自 WorkBuddy 源码里写死的原则：拦截能力不具备时，开关必须显示为关。
 * 这里连开关都不画。
 */
import type { ReactNode } from 'react'
import type { SettingsScope, SettingsScopeSnapshot } from '@deepseek-ai/dsh-client-ui-settings/client'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { en } from './locales.ts'
import styles from './MemorySection.module.css'

/** The memory namespace as this section reads it. */
export interface MemoryConfig {
  enabled?: boolean
}

/** Injected dependencies of {@link MemorySection} (slot `inject`). */
export interface MemorySectionInjected {
  /** renderer 把 `hooks.memory` 绑定成 `useMemory` 选择器。 */
  hooks: { memory: SettingsScope<MemoryConfig> }
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** Props delivered by the slot outlet. */
export type MemorySectionProps = Partial<InjectFace<MemorySectionInjected>> & PropsRenderSlots<never>

type Translate = (key: keyof typeof en) => string

/** `useMemory` 选择器 hook 的类型。 */
type MemorySelectorHook = <S>(sel: (s: SettingsScopeSnapshot<MemoryConfig>) => S) => S

/** Render the memory section. */
export function MemorySection(props: MemorySectionProps): ReactNode {
  const { useMemory, t } = props
  if (useMemory === undefined || t === undefined) return null
  return <Loaded useMemory={useMemory} t={t} />
}

/** Loaded render: subscriptions are live here. */
function Loaded({ useMemory, t }: { useMemory: MemorySelectorHook; t: Translate }): ReactNode {
  const snapshot = useMemory(s => s)

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <h2 className={styles.title}>{t('title')}</h2>
        <p className={styles.desc}>{t('desc')}</p>

        {snapshot.status === 'loading' ? <p className={styles.hint}>{t('loading')}</p> : null}

        {snapshot.status === 'unavailable'
          ? (
            <>
              <p className={styles.unavailable}>{t('unavailable')}</p>
              <p className={styles.hint}>{t('unavailableHint')}</p>
            </>
          )
          : null}

        {snapshot.status === 'ready'
          ? <p className={styles.hint}>{t('desc')}</p>
          : null}
      </section>
    </div>
  )
}
