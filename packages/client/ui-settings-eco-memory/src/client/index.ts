/**
 * eco Agent「记忆」设置页，浏览器 half：绑定宿主 memory namespace。
 * namespace 缺席时页面明说"没接入"，不伪造开关。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the ctx.settingsScope merge and the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import { MemorySection } from './MemorySection.tsx'
import type { MemoryConfig, MemorySectionInjected } from './MemorySection.tsx'
import { en, zh, type MemoryKey } from './locales.ts'

export type { MemoryKey } from './locales.ts'
export type { MemoryConfig, MemorySectionInjected, MemorySectionProps } from './MemorySection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「记忆」页面 copy。 */
    'settings.ecoMemory': MemoryKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.ecoMemory'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale', 'settingsScope']

/** Narrow a wire section into the memory config view. */
function decodeMemoryConfig(section: unknown): MemoryConfig {
  if (typeof section !== 'object' || section === null || Array.isArray(section)) return {}
  return section
}

/**
 * Register the「记忆」section and bind the memory namespace scope.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-memory: copy dictionaries')

  const memoryScope = ctx.settingsScope.bind<MemoryConfig>({
    namespace: 'memory',
    decode: decodeMemoryConfig,
  })

  const t = ctx.locale.bind(NS)
  const injected = (): MemorySectionInjected => ({
    hooks: { memory: memoryScope },
    t,
  })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'eco-memory',
    // 紧邻「模型」（order 10）之下：模型与记忆同属 agent 的"脑"，排在一起才成组。
    order: 12,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, MemorySection))
}
