/**
 * eco Agent「我的助手」设置页，浏览器 half：注册「我的助手」section，
 * 把微信助手（`wechat-bridge` namespace）的配置绑定成一个可读写的作用域。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the ctx.settingsScope merge and the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
// Type-only: pulls ctx.remote.pluginInventory（微信助手的运行状态来源）。
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import { AssistantsSection } from './AssistantsSection.tsx'
import type { AssistantsSectionInjected, WechatConfig } from './AssistantsSection.tsx'
import { en, zh, type AssistantsKey } from './locales.ts'

export type { AssistantsKey } from './locales.ts'
export type { AssistantsSectionInjected, AssistantsSectionProps, WechatConfig } from './AssistantsSection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「我的助手」页面 copy。 */
    'settings.assistants': AssistantsKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.assistants'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale', 'settingsScope', 'remote', 'remote.pluginInventory']

/** Narrow a wire section into the wechat-bridge config view. */
function decodeWechatConfig(section: unknown): WechatConfig {
  if (typeof section !== 'object' || section === null || Array.isArray(section)) return {}
  return section
}

/**
 * Register the「我的助手」section once the settings.section declaration is on
 * the ledger, and bind the wechat-bridge namespace scope for live config.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-assistants: copy dictionaries')

  // 微信助手配置作用域（读写 wechat-bridge namespace）。
  const wechatScope = ctx.settingsScope.bind<WechatConfig>({
    namespace: 'wechat-bridge',
    decode: decodeWechatConfig,
  })

  const t = ctx.locale.bind(NS)
  const list: AssistantsSectionInjected['list'] = async () => {
    const result = await ctx.remote.pluginInventory.list()
    if (!result.ok) {
      throw new Error(`pluginInventory.list failed: ${result.error.code}: ${result.error.message}`)
    }
    return result.value
  }
  const injected = (): AssistantsSectionInjected => ({
    // hooks 供 renderer 绑定 useWechat 选择器；wechat 供组件写入。
    hooks: { wechat: wechatScope },
    wechat: wechatScope,
    list,
    t,
  })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'assistants',
    // 紧邻 MCP 服务（22）：微信/飞书与 MCP 同为"外部接入"，成组才看得出来。
    order: 23,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, AssistantsSection))
}
