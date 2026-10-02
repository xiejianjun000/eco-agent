/**
 * eco Agent「权限与审批」设置页，浏览器 half：注册 section，绑定宿主 permission
 * namespace 的作用域，读写新会话的默认权限预设。
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls the ctx.settingsScope merge and the settings.section slot.
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
// Type-only: pulls ctx.locale.
import type {} from '@deepseek-ai/dsh-client-locale/client'
// Type-only: pulls ctx.slots (SlotRegistry) merge.
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import { PermissionSection } from './PermissionSection.tsx'
import type { PermissionConfig, PermissionSectionInjected } from './PermissionSection.tsx'
import { en, zh, type PermissionKey } from './locales.ts'

export type { PermissionKey } from './locales.ts'
export type { PermissionConfig, PermissionSectionInjected, PermissionSectionProps } from './PermissionSection.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** 「权限与审批」页面 copy。 */
    'settings.ecoPermission': PermissionKey
  }
}

/** Dictionary namespace owned by this plugin. */
const NS = 'settings.ecoPermission'

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale', 'settingsScope']

/** Narrow a wire section into the permission config view. */
function decodePermissionConfig(section: unknown): PermissionConfig {
  if (typeof section !== 'object' || section === null || Array.isArray(section)) return {}
  return section
}

/**
 * Register the「权限与审批」section and bind the permission namespace scope.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-settings-eco-permission: copy dictionaries')

  const permissionScope = ctx.settingsScope.bind<PermissionConfig>({
    namespace: 'permission',
    decode: decodePermissionConfig,
  })

  const t = ctx.locale.bind(NS)
  const injected = (): PermissionSectionInjected => ({
    hooks: { permission: permissionScope },
    permission: permissionScope,
    t,
  })

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'eco-permission',
    // 24 而非 25：上游「已归档会话」也在 25，同 order 的相对次序由装载顺序
    // 决定、重启可能变。让出一位，导航顺序才稳定。
    order: 24,
    label: () => t('nav'),
    locale: NS,
    inject: injected,
  }, PermissionSection))
}
