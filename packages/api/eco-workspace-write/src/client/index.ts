/**
 * Browser half of the workspace write channel.
 *
 * This package mounts its own generated Remote namespace rather than waiting
 * for a shared assembly to select it: the write endpoint exists on the page
 * only while this plugin is mounted, so unplugging the plugin takes the write
 * channel off the page with it. The shared assembly stays untouched, and a
 * deployment that does not compose this package never offers the endpoint.
 *
 * `types.ts` is what the protocol publishes; there is nothing else to register.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-api-gateway/client'
import ecoWorkspaceWriteRemote from './remote.js'

export type * from '../types.ts'

/** Required browser service: the Remote carrier this contribution mounts into. */
export const inject = ['remote']

/**
 * Client plugin body: mount the `ecoWorkspaceWrite` namespace for this plugin's lifetime.
 * @param ctx - client root context carrying the Remote face.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(async () => {
    const dispose = await ctx.remote.$mount(ecoWorkspaceWriteRemote)
    return () => { void dispose() }
  }, 'eco-workspace-write: remote namespace')
}
