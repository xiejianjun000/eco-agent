/** eco 会话枢纽：会话头「插件」直达按钮，跳转侧栏全局面板的 Plugins 页。 */
import type { PropsLocale, PropsRuntime } from '@eco-agent/dsh-client-ui-slots'
import type {} from '@eco-agent/dsh-client-ui-conversation/client'
import { NS } from './locales.ts'

/** Face carried flat into props by the slot renderer. */
export interface PluginsShortcutInjected {
  openPlugins: () => void
}

/** Full props for the session-header Plugins shortcut (same contract shape as JobListAction). */
export type PluginsShortcutProps =
  PropsRuntime<'conversation.session.header.actions'>
  & PropsLocale<typeof NS>
  & PluginsShortcutInjected

/**
 * Render the header shortcut; the header band owns the button chrome around it.
 * @param props - runtime slot currency, the namespace translator, and the flat navigation callback.
 * @returns the shortcut button.
 */
export function PluginsShortcut({ t, openPlugins }: PluginsShortcutProps): React.ReactNode {
  return (
    <button type="button" onClick={openPlugins} aria-label={t('plugins.aria')} title={t('plugins.aria')}>
      {t('plugins.label')}
    </button>
  )
}
