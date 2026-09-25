/**
 * eco Agent「数据与诊断」设置页，浏览器 half：注册 section，绑定宿主插件清单
 * 与浏览器模块同步状态。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the ctx.settingsScope merge and the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
// Type-only: pulls ctx.remote.pluginInventory and ctx.modules.
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-modules/client'
import { DiagnosticsSection } from './DiagnosticsSection.tsx'
import type { DiagnosticsSectionInjected } from './DiagnosticsSection.tsx'
import { en, zh, type DiagnosticsKey } from './locales.ts'

export type { DiagnosticsKey } from './locales.ts'
export type { DiagnosticsSectionInjected, DiagnosticsSectionProps } from './DiagnosticsSection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「数据与诊断」页面 copy。 */
    'settings.ecoDiagnostics': DiagnosticsKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.ecoDiagnostics'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale', 'remote', 'remote.pluginInventory', 'modules']

/**
 * Register the「数据与诊断」section.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-diagnostics: copy dictionaries')

  const t = ctx.locale.bind(NS)
  const list: DiagnosticsSectionInjected['list'] = async () => {
    const result = await ctx.remote.pluginInventory.list()
    if (!result.ok) {
      throw new Error(`pluginInventory.list failed: ${result.error.code}: ${result.error.message}`)
    }
    return result.value
  }
  const injected = (): DiagnosticsSectionInjected => ({
    hooks: { clientSync: ctx.modules.entries.state },
    list,
    retryClient: () => {
      void ctx.modules.entries.retry().catch((error: unknown) => { ctx.logger.error(error) })
    },
    t,
  })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'eco-diagnostics',
    order: 40,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, DiagnosticsSection))
}
