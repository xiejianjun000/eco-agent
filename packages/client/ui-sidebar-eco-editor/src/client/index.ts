/**
 * Browser half: register the eco in-place editor into the right Sidebar's
 * document previewer.
 *
 * Two registrations and nothing else — the extension metadata the toolbar and
 * the viewer-choice list read, and the keyed document body rendered under that
 * metadata's id. Unplugging this plugin takes editing away again and leaves
 * every shipped viewer exactly as it was.
 *
 * The metadata sits in the `builtin` band on purpose. Product viewers keep
 * their defaults (equal band, earlier registration wins the tie), and editing
 * shows up as an extra choice in the viewer list rather than hijacking files
 * that already have a purpose-built view.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls ctx.locale / ctx.slots / ctx.documentPreviews merges, and the
// two generated Remote namespaces this body calls.
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client'
import type {} from '@deepseek-ai/dsh-api-workspace-files/remote'
import type {} from '@deepseek-ai/dsh-api-eco-workspace-write/remote'
import type { DocumentPreviewDefinition } from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client'
import { EditorBody } from './EditorBody.tsx'
import { en, NS, zh, type EditorKey } from './locales.ts'
import { setEditorRemote } from './remote-store.ts'

/** This renderer's identity, shared by metadata and the keyed document body. */
export const EDITOR_BODY_ID = '@deepseek-ai/dsh-client-ui-sidebar-eco-editor'

/**
 * Text suffixes the editor claims. Deliberately excludes the suffixes the
 * product renders with a purpose-built viewer (markdown, HTML, PDF, images) —
 * those keep their own default, and editing is still available for them through
 * the plain-text viewer's own affordances rather than by displacing them.
 */
export const EDITOR_EXTENSIONS: readonly string[] = [
  'txt', 'text', 'log', 'csv', 'tsv',
  'json', 'json5', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf', 'config', 'env', 'properties',
  'sh', 'bash', 'zsh', 'fish', 'ps1', 'bat', 'cmd',
  'sql', 'graphql', 'proto',
  'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs',
  'java', 'go', 'rs', 'rb', 'py', 'php', 'c', 'h', 'cpp', 'hpp', 'cs',
  'swift', 'kt', 'scala', 'r', 'lua', 'dart',
  'css', 'scss', 'less', 'vue', 'svelte',
]

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** eco document editor copy. */
    sidebarEcoEditor: EditorKey
  }
}

/** Required browser services: the slot registry, copy, the preview registry, and the Remote carrier. */
export const inject = [
  'slots', 'locale', 'documentPreviews', 'remote', 'remote.workspaceFiles', 'remote.ecoWorkspaceWrite',
]

/**
 * Register the editor's dictionary, the renderer metadata, and the body.
 *
 * Both Remote namespaces this body calls are declared in `inject` rather than
 * read lazily: the write channel's own plugin mounts its namespace, and the
 * read side's comes from the shared assembly, so this plugin simply waits for
 * what it needs instead of mounting anything itself.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  const t = ctx.locale.bind(NS)
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-sidebar-eco-editor: dictionaries')
  const definition: DocumentPreviewDefinition = {
    id: EDITOR_BODY_ID,
    extensions: EDITOR_EXTENSIONS,
    priority: 'builtin',
    title: () => t('viewer.title'),
    loading: 'renderer',
    wrap: false,
  }
  setEditorRemote(ctx.remote)
  ctx.effect(() => () => { setEditorRemote(undefined) }, 'ui-sidebar-eco-editor: withdraw remote')
  ctx.effect(() => ctx.documentPreviews.register(definition), 'ui-sidebar-eco-editor: metadata')
  ctx.effect(() => ctx.slots.inject('sidebar.right.tab.document', () => ctx.slots.register(
    { name: 'sidebar.right.tab.document', key: EDITOR_BODY_ID, locale: NS }, EditorBody,
  )), 'ui-sidebar-eco-editor: body')
}
