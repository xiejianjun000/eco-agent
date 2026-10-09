/** Browser half of the eco suggestion-cards plugin. */

import type { Context } from '@eco-agent/cordis'
// Type-only: pulls the locale Context merge (ctx.locale).
import type {} from '@eco-agent/dsh-client-locale/client'
// Type-only: pulls the conversation SlotMap merge (the suggestions slot).
import type {} from '@eco-agent/dsh-client-ui-conversation/client'
// Type-only: pulls the renderer-owned slots service (ctx.slots).
import type {} from '@eco-agent/dsh-client-ui-renderer/client'
import { Suggestions } from './Suggestions.tsx'
import { en, NS, zh, type SuggestionKey } from './locales.ts'

declare module '@eco-agent/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** eco suggestion-card copy. */
    [NS]: SuggestionKey
  }
}

/** Required services (cordis fiber inject). */
export const inject = ['slots', 'locale']

/**
 * Mount the suggestion-cards entry below the hero composer.
 * @param ctx - the browser plugin context.
 */
export function apply(ctx: Context): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-eco-suggestions: dictionaries')
  ctx.slots.inject('conversation.input.suggestions', () => ctx.slots.register({
    name: 'conversation.input.suggestions',
    id: 'eco-suggestions',
    order: 0,
    locale: NS,
  }, Suggestions))
}
