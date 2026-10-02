/**
 * Browser half: register the eco media renderer (video / audio) into the right
 * Sidebar's document previewer.
 *
 * Two registrations and nothing else — the extension metadata the toolbar and
 * the viewer-choice list read, and the keyed document body rendered under that
 * metadata's id. Registering adds playback to every file whose suffix matches;
 * unregistering this plugin takes it away again, and the plain-text viewer the
 * product ships becomes the only choice for those files.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls ctx.locale / ctx.slots / ctx.documentPreviews merges.
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client'
import type { DocumentPreviewDefinition } from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client'
import { MediaBody } from './MediaBody.tsx'
import { MEDIA_BINARY_EXTENSIONS, MEDIA_EXTENSIONS } from './MediaBody.tsx'
import { en, NS, zh, type MediaKey } from './locales.ts'

/** This renderer's identity, shared by metadata and the keyed document body. */
export const MEDIA_BODY_ID = '@deepseek-ai/dsh-client-ui-sidebar-eco-media'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** eco media renderer copy. */
    sidebarEcoMedia: MediaKey
  }
}

/** Required browser services: the slot registry, copy, and the preview registry. */
export const inject = ['slots', 'locale', 'documentPreviews']

/**
 * Register the media renderer's dictionary, metadata, and body.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  const t = ctx.locale.bind(NS)
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-sidebar-eco-media: dictionaries')
  const definition: DocumentPreviewDefinition = {
    id: MEDIA_BODY_ID,
    extensions: MEDIA_EXTENSIONS,
    binaryExtensions: MEDIA_BINARY_EXTENSIONS,
    priority: 'builtin',
    title: () => t('title'),
    loading: 'bytes-complete',
    wrap: false,
  }
  ctx.effect(() => ctx.documentPreviews.register(definition), 'ui-sidebar-eco-media: metadata')
  ctx.effect(() => ctx.slots.inject('sidebar.right.tab.document', () => ctx.slots.register(
    { name: 'sidebar.right.tab.document', key: MEDIA_BODY_ID, locale: NS }, MediaBody,
  )), 'ui-sidebar-eco-media: body')
}
