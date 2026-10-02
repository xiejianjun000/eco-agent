/**
 * The Host-reaching actions this plugin's menu items call, held at module scope.
 *
 * A slot registration carries no `inject` for a list seat, and a menu item is a
 * plain component with no context to read from — so the actions the plugin body
 * builds are published here instead. Module scope is the right scope: one
 * browser bundle loads this plugin at most once, and unloading clears the
 * holder so a stale closure cannot outlive its Remote.
 */
import type { TabActionsInjected } from './TabActions.tsx'

/** The published actions, or undefined while the plugin is not mounted. */
let published: TabActionsInjected | undefined

/**
 * Publish the actions, or clear them on unload.
 * @param actions - the actions menu items call, or undefined to clear.
 */
export function setTabActions(actions: TabActionsInjected | undefined): void {
  published = actions
}

/**
 * Read the published actions.
 * @returns the actions, or undefined when this plugin is not mounted.
 */
export function tabActions(): TabActionsInjected | undefined {
  return published
}
