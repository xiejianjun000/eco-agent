/**
 * 「账号与身份」设置 section（预留）。
 *
 * 开源自部署版没有账号体系，所以这个插件默认是关的。留着它，是为了正式应用版
 * 启用时不用改代码 —— 去掉 cordis 行上的 disabled 就插上了。
 */
import type { ReactNode } from 'react'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { en } from './locales.ts'
import styles from './AccountSection.module.css'

/** Injected dependencies of {@link AccountSection} (slot `inject`). */
export interface AccountSectionInjected {
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** Props delivered by the slot outlet. */
export type AccountSectionProps = Partial<InjectFace<AccountSectionInjected>> & PropsRenderSlots<never>

/** Render the account section. */
export function AccountSection(props: AccountSectionProps): ReactNode {
  const { t } = props
  if (t === undefined) return null

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <h2 className={styles.title}>{t('title')}</h2>
        <p className={styles.desc}>{t('desc')}</p>
        <p className={styles.hint}>{t('reserved')}</p>
      </section>
    </div>
  )
}
