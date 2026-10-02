/**
 * Content actions one right-Sidebar tab offers, contributed to the kit's tab
 * menu.
 *
 * The kit owns the gestures on the layout itself — split, float, close — and
 * this plugin contributes only what means something about the tab's *content*:
 * the file behind it. Every item is gated on the tab really being a workspace
 * file: a browser or terminal tab renders nothing here rather than showing
 * items that would do nothing.
 */

import type { ReactNode } from 'react'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { SidebarRightTabMenuOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import { parseFileAddress } from '@deepseek-ai/dsh-util-workspace-path'
import { tabActions } from './actions-store.ts'
import { flashNotice } from './notice.ts'
import type { TabActionsKey } from './locales.ts'
import css from './TabActions.module.css'

/** Actions the plugin body supplies; they need Host reach the menu item lacks. */
export interface TabActionsInjected {
  /** Copy text to the host clipboard, reporting whether the write was accepted. */
  readonly copy: (text: string) => Promise<boolean>
  /** Hand one path to the Host's native file manager, revealing the file in it. */
  readonly reveal: (path: string) => Promise<boolean>
}

/** Owner values plus copy. */
export type TabActionsProps = SidebarRightTabMenuOwnerProps & PropsLocale<'sidebarEcoTabActions'>

/**
 * Render this plugin's tab-menu items for one tab.
 * @param props - the tab whose menu is open, the dismiss callback, and copy.
 * @returns menu items, or nothing when the tab is not a workspace file.
 */
export function TabActions({ tab, dismiss, t }: TabActionsProps): ReactNode {
  const actions = tabActions()
  const file = parseFileAddress(tab.contentId)
  if (file === undefined || actions === undefined) return null

  const name = file.path.slice(file.path.lastIndexOf('/') + 1)

  /**
   * Close the menu, run the action, and report only what a person could not
   * already see: a reveal that worked is its own feedback, a refusal is not.
   * @param task - the action; resolves whether it succeeded.
   * @param ok - copy shown on success, or nothing to stay silent.
   * @param fail - copy shown on refusal.
   */
  const run = (task: () => Promise<boolean>, ok: TabActionsKey | undefined, fail: TabActionsKey): void => {
    dismiss()
    void task().then((done) => {
      if (done) {
        if (ok !== undefined) flashNotice(t(ok))
        return
      }
      flashNotice(t(fail), true)
    })
  }
  const copyPath = (): void => {
    run(() => actions.copy(file.path), 'notice.copied', 'notice.copyFailed')
  }
  const copyName = (): void => {
    run(() => actions.copy(name), 'notice.copied', 'notice.copyFailed')
  }
  const reveal = (): void => {
    run(() => actions.reveal(file.path), undefined, 'notice.revealFailed')
  }

  return (
    <>
      <button type="button" role="menuitem" className={css.item} onClick={copyPath}>
        {t('menu.copyPath')}
      </button>
      <button type="button" role="menuitem" className={css.item} onClick={copyName}>
        {t('menu.copyName')}
      </button>
      <button type="button" role="menuitem" className={css.item} onClick={reveal}>
        {t('menu.reveal')}
      </button>
    </>
  )
}
