/**
 * Browser half: put selected text into the composer as a quote.
 *
 * One registration into `conversation.input.dock` — the seat that carries the
 * Session's input actions — and the control itself renders through a body
 * portal, so a selection anywhere (chat prose, a right-Sidebar document) is
 * quotable. Unloading removes the control and nothing else.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only: pulls ctx.locale / ctx.slots merges.
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import { QuoteDock } from './QuoteDock.tsx'
import { en, NS, zh, type QuoteKey } from './locales.ts'

/** This plugin's identity in the dock list. */
export const QUOTE_DOCK_ID = 'eco-quote'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** eco quote control copy. */
    ecoQuote: QuoteKey
  }
}

/** Required browser services (cordis fiber inject). */
export const inject = ['slots', 'locale']

/**
 * Register the dictionary and the quote control's seat.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-eco-quote: dictionaries')
  ctx.slots.inject('conversation.input.dock', () => ctx.slots.register({
    name: 'conversation.input.dock',
    id: QUOTE_DOCK_ID,
    order: 60,
    locale: NS,
  }, QuoteDock))
}
