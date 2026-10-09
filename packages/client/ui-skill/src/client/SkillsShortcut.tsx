/** eco 技能中心：会话头「技能」直达按钮，跳转侧栏全局面板的 Skills 页。 */
import type { PropsLocale, PropsRuntime } from '@eco-agent/dsh-client-ui-slots'
import type {} from '@eco-agent/dsh-client-ui-conversation/client'
import { NS } from './locales.ts'

/** Face carried flat into props by the slot renderer. */
export interface SkillsShortcutInjected {
  openSkills: () => void
}

/** Full props for the session-header Skills shortcut (same contract shape as PluginsShortcut). */
export type SkillsShortcutProps =
  PropsRuntime<'conversation.session.header.actions'>
  & PropsLocale<typeof NS>
  & SkillsShortcutInjected

/**
 * Render the header shortcut; the header band owns the button chrome around it.
 * @param props - runtime slot currency, the namespace translator, and the flat navigation callback.
 * @returns the shortcut button.
 */
export function SkillsShortcut({ t, openSkills }: SkillsShortcutProps): React.ReactNode {
  return (
    <button type="button" onClick={openSkills} aria-label={t('shortcut.aria')} title={t('shortcut.aria')}>
      {t('shortcut.label')}
    </button>
  )
}
