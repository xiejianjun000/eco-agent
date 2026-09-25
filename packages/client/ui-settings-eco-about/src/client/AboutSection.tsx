/**
 * 「帮助与关于」设置 section：开源版的第一需求 —— 告诉别人这东西是什么、
 * 从哪拿源码、在哪提问题。
 */
import type { ReactNode } from 'react'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { en } from './locales.ts'
import styles from './AboutSection.module.css'

/** Repository this open-source build comes from. */
const REPO_URL = 'https://github.com/xiejianjun000/eco-agent'

/** One outbound resource row. */
interface Link {
  href: string
  titleKey: keyof typeof en
  descKey: keyof typeof en
}

/** Outbound resources, in the order a newcomer needs them. */
const LINKS: readonly Link[] = [
  { href: REPO_URL, titleKey: 'repo', descKey: 'repoDesc' },
  { href: `${REPO_URL}/issues`, titleKey: 'issues', descKey: 'issuesDesc' },
  { href: `${REPO_URL}#readme`, titleKey: 'docs', descKey: 'docsDesc' },
]

/** Injected dependencies of {@link AboutSection} (slot `inject`). */
export interface AboutSectionInjected {
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** Props delivered by the slot outlet. */
export type AboutSectionProps = Partial<InjectFace<AboutSectionInjected>> & PropsRenderSlots<never>

/** Render the about section. */
export function AboutSection(props: AboutSectionProps): ReactNode {
  const { t } = props
  if (t === undefined) return null

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <h2 className={styles.title}>{t('title')}</h2>
        <p className={styles.desc}>{t('desc')}</p>
      </section>

      <section className={styles.card}>
        <h2 className={styles.title}>{t('edition')}</h2>
        <p className={styles.desc}>{t('editionDesc')}</p>
        <p className={styles.hint}>{t('versionHint')}</p>
      </section>

      <section className={styles.card}>
        <h2 className={styles.title}>{t('links')}</h2>
        <ul className={styles.list}>
          {LINKS.map(link => (
            <li key={link.href}>
              <a className={styles.link} href={link.href} target="_blank" rel="noreferrer">
                <span className={styles.linkTitle}>{t(link.titleKey)}</span>
                <span className={styles.linkDesc}>{t(link.descKey)}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
