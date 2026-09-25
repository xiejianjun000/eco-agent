/**
 * Browser half: contribute content actions to the right Sidebar's tab menu.
 *
 * Registration is one list entry. The kit keeps its own layout gestures and
 * renders whatever this entry returns after them; an entry that renders nothing
 * — a tab that is not a workspace file — leaves the menu exactly as it was.
 * Removing this plugin removes the items and nothing else.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls ctx.locale / ctx.slots / ctx.remote merges.
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import { writeClipboard } from '@deepseek-ai/dsh-client-ui-primitives'
import { setTabActions } from './actions-store.ts'
import { TabActions, type TabActionsInjected } from './TabActions.tsx'
import { en, NS, zh, type TabActionsKey } from './locales.ts'

/** This plugin's identity in the menu-item list. */
export const TAB_ACTIONS_ID = '@deepseek-ai/dsh-client-ui-sidebar-eco-tabactions'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** eco tab content-action copy. */
    sidebarEcoTabActions: TabActionsKey
  }
}

/** Required browser services: the slot registry, copy, and the Session Remote. */
export const inject = ['slots', 'locale', 'remote', 'remote.session']

/**
 * Register the dictionary and this plugin's tab-menu items.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-sidebar-eco-tabactions: dictionaries')
  const actions: TabActionsInjected = {
    copy: text => writeClipboard(text),
    reveal: async (path) => {
      // The Remote reports its own refusal; only an unclassified throw becomes
      // "false" here, and either way the menu item says what happened.
      const result = await ctx.remote.session.openWorkspacePath({ path, action: 'reveal' })
      return result.ok ? result.value.opened : false
    },
  }
  setTabActions(actions)
  ctx.effect(() => () => { setTabActions(undefined) }, 'ui-sidebar-eco-tabactions: clear actions')
  ctx.effect(() => ctx.slots.inject('sidebar.right.tab.menu.item', () => ctx.slots.register(
    { name: 'sidebar.right.tab.menu.item', id: TAB_ACTIONS_ID, locale: NS }, TabActions,
  )), 'ui-sidebar-eco-tabactions: menu items')
}
