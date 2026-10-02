/**
 * eco Agent「MCP 服务」设置页，浏览器 half：注册 section，并把宿主插件清单
 * 的只读快照绑给页面（唯一数据源，不做推测性展示）。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the ctx.settingsScope merge and the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
// Type-only: pulls ctx.remote.pluginInventory.
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import { McpSection } from './McpSection.tsx'
import type { McpSectionInjected } from './McpSection.tsx'
import { en, zh, type McpKey } from './locales.ts'

export type { McpKey } from './locales.ts'
export type { McpSectionInjected, McpSectionProps } from './McpSection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「MCP 服务」页面 copy。 */
    'settings.ecoMcp': McpKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.ecoMcp'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale', 'remote', 'remote.pluginInventory']

/**
 * Register the「MCP 服务」section.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-mcp: copy dictionaries')

  const t = ctx.locale.bind(NS)
  const list: McpSectionInjected['list'] = async () => {
    const result = await ctx.remote.pluginInventory.list()
    if (!result.ok) {
      throw new Error(`pluginInventory.list failed: ${result.error.code}: ${result.error.message}`)
    }
    return result.value
  }
  const injected = (): McpSectionInjected => ({ list, t })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'eco-mcp',
    // 外部接入组：排在 Agent 预设（20）之后、渠道接入（23）之前。
    order: 22,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, McpSection))
}
