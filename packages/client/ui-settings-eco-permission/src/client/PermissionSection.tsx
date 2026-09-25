/**
 * 「权限与审批」设置 section：新会话的默认权限预设。
 *
 * 权限 namespace 由宿主注册，是否可用由连接决定 —— 不可用就明说不可用，
 * 不摆一个改不动的假开关。
 */
import type { ReactNode } from 'react'
import type { SettingsScope, SettingsScopeSnapshot } from '@deepseek-ai/dsh-client-ui-settings/client'
import type { InjectFace, PropsRenderSlots } from '@deepseek-ai/dsh-client-ui-slots'
import type { en } from './locales.ts'
import styles from './PermissionSection.module.css'

/** The permission namespace as this section reads it. */
export interface PermissionConfig {
  defaultPreset?: string
}

/** Injected dependencies of {@link PermissionSection} (slot `inject`). */
export interface PermissionSectionInjected {
  /** renderer 把 `hooks.permission` 绑定成 `usePermission` 选择器。 */
  hooks: { permission: SettingsScope<PermissionConfig> }
  /** 原始 scope，供组件写配置。 */
  permission: SettingsScope<PermissionConfig>
  /** Section copy. */
  t: (key: keyof typeof en) => string
}

/** Props delivered by the slot outlet. */
export type PermissionSectionProps = Partial<InjectFace<PermissionSectionInjected>> & PropsRenderSlots<never>

type Translate = (key: keyof typeof en) => string

/** `usePermission` 选择器 hook 的类型。 */
type PermissionSelectorHook = <S>(sel: (s: SettingsScopeSnapshot<PermissionConfig>) => S) => S

/** Preset machine values, in ascending order of trust. */
const PRESETS = [
  { value: 'read-only', labelKey: 'preset.readOnly', shortKey: 'readonly' },
  { value: 'workspace-write', labelKey: 'preset.workspaceWrite', shortKey: 'readonly' },
  { value: 'danger-full-access', labelKey: 'preset.fullAccess', shortKey: 'readonly' },
  { value: 'auto', labelKey: 'preset.auto', shortKey: 'readonly' },
] as const satisfies readonly { value: string; labelKey: keyof typeof en; shortKey: keyof typeof en }[]

/** Human name for a preset machine value. */
const PRESET_SHORT_NAME: Record<string, string> = {
  'read-only': '只读',
  'workspace-write': '工作区写入',
  'danger-full-access': '完全访问',
  'auto': '逐次复核',
}

function presetShortName(value: string): string {
  return PRESET_SHORT_NAME[value] ?? value
}

/** Render the permissions section. */
export function PermissionSection(props: PermissionSectionProps): ReactNode {
  const { usePermission, permission, t } = props
  if (usePermission === undefined || permission === undefined || t === undefined) return null
  return <Loaded usePermission={usePermission} permission={permission} t={t} />
}

/** Loaded render: subscriptions are live here. */
function Loaded({ usePermission, permission, t }: {
  usePermission: PermissionSelectorHook
  permission: SettingsScope<PermissionConfig>
  t: Translate
}): ReactNode {
  const snapshot = usePermission(s => s)
  const current = snapshot.value?.defaultPreset ?? ''

  if (snapshot.status === 'loading') {
    return (
      <div className={styles.root}>
        <section className={styles.card}>
          <h2 className={styles.title}>{t('title')}</h2>
          <p className={styles.hint}>{t('loading')}</p>
        </section>
      </div>
    )
  }

  if (snapshot.status === 'unavailable') {
    return (
      <div className={styles.root}>
        <section className={styles.card}>
          <h2 className={styles.title}>{t('title')}</h2>
          <p className={styles.desc}>{t('unavailable')}</p>
        </section>
      </div>
    )
  }

  return (
    <div className={styles.root}>
      <section className={styles.card}>
        <h2 className={styles.title}>{t('title')}</h2>
        <p className={styles.desc}>{t('desc')}</p>
        <ul className={styles.list}>
          {PRESETS.map(preset => (
            <li key={preset.value}>
              <button
                type="button"
                className={preset.value === current ? styles.optionActive : styles.option}
                aria-pressed={preset.value === current}
                disabled={!snapshot.writable}
                onClick={() => { void permission.set('defaultPreset', preset.value) }}
              >
                <span className={styles.optionName}>{presetShortName(preset.value)}</span>
                <span className={styles.optionDesc}>{t(preset.labelKey)}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className={styles.hint}>{t('hint')}</p>
      </section>
    </div>
  )
}
