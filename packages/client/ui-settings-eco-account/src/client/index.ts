/**
 * eco Agent「账号与身份」设置页，浏览器 half（预留）。
 *
 * 默认在 bundle 的 cordis 配置里 disabled：开源自部署版没有账号体系。正式应用版
 * 启用时只需删掉那一行的 `disabled: true`。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import { AccountSection } from './AccountSection.tsx'
import type { AccountSectionInjected } from './AccountSection.tsx'
import { en, zh, type AccountKey } from './locales.ts'

export type { AccountKey } from './locales.ts'
export type { AccountSectionInjected, AccountSectionProps } from './AccountSection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「账号与身份」页面 copy。 */
    'settings.ecoAccount': AccountKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.ecoAccount'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale']

/**
 * Register the「账号与身份」section.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-account: copy dictionaries')

  const t = ctx.locale.bind(NS)
  const injected = (): AccountSectionInjected => ({ t })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'eco-account',
    order: 50,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, AccountSection))
}
