/**
 * The Remote face the editor body calls.
 *
 * `sidebar.right.tab.document` is a keyed slot whose registration carries no
 * `inject`, so the body component cannot receive the Remote through standard
 * props. The plugin publishes it here instead and withdraws it on unload — the
 * same pattern the tab-action menu items use, for the same reason.
 */
import type { ClientRemote } from '@deepseek-ai/dsh-api-gateway/client'

let published: ClientRemote | undefined

/**
 * Publish the Remote face for the editor body, or withdraw it.
 * @param remote - the live Client Remote, or `undefined` on plugin teardown.
 */
export function setEditorRemote(remote: ClientRemote | undefined): void {
  published = remote
}

/**
 * The Remote face the editor body should call.
 * @returns the published Remote, or `undefined` when the plugin is unloaded.
 */
export function editorRemote(): ClientRemote | undefined {
  return published
}
