/**
 * eco Agent「帮助与关于」设置页，浏览器 half：注册 section。开源版第一需求 ——
 * 讲清是什么、源码在哪、问题往哪提。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import { AboutSection } from './AboutSection.tsx'
import type { AboutSectionInjected } from './AboutSection.tsx'
import { en, zh, type AboutKey } from './locales.ts'

export type { AboutKey } from './locales.ts'
export type { AboutSectionInjected, AboutSectionProps } from './AboutSection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「帮助与关于」页面 copy。 */
    'settings.ecoAbout': AboutKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.ecoAbout'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale']

/**
 * Register the「帮助与关于」section.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-about: copy dictionaries')

  const t = ctx.locale.bind(NS)
  const injected = (): AboutSectionInjected => ({ t })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'eco-about',
    order: 45,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, AboutSection))
}
