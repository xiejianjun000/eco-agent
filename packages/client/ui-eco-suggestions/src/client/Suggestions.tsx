/** Suggestion cards rendered below the composer in the hero (new-session) state. */

import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { InputActions } from '@deepseek-ai/dsh-client-ui-conversation/client'
import { NS, type SuggestionKey } from './locales.ts'
import css from './Suggestions.module.css'

/** Full props of the suggestion-cards entry. */
export type SuggestionsProps = PropsRuntime<'conversation.input.suggestions'> & PropsLocale<typeof NS>

/** One role card: a locale key plus its prompt key. */
interface RoleCard {
  readonly role: SuggestionKey
  readonly prompt: SuggestionKey
}

const ROLES: readonly RoleCard[] = [
  { role: 'role.enterprise', prompt: 'prompt.enterprise' },
  { role: 'role.enforcement', prompt: 'prompt.enforcement' },
  { role: 'role.inspection', prompt: 'prompt.inspection' },
  { role: 'role.approval', prompt: 'prompt.approval' },
  { role: 'role.research', prompt: 'prompt.research' },
  { role: 'role.training', prompt: 'prompt.training' },
]

/**
 * Render the six professional-role cards and the twelve-element coverage line.
 * @param props - session-maybe runtime props and locale seat.
 * @returns the card strip, or null while there is no input face to fill.
 */
export function Suggestions({ inputActions, t }: SuggestionsProps) {
  const send = (prompt: SuggestionKey): void => {
    const text = t(prompt)
    if (text === prompt) return
    const actions: InputActions | undefined = inputActions
    if (actions === undefined) return
    actions.setDraft(text)
    actions.submit()
  }

  return (
    <div className={css.root} data-eco-suggestions>
      <div className={css.cards}>
        {ROLES.map(({ role, prompt }) => (
          <button
            key={role}
            type="button"
            className={css.card}
            onClick={() => { send(prompt) }}
          >
            {t(role)}
          </button>
        ))}
      </div>
      <div className={css.elements}>{t('elements')}</div>
    </div>
  )
}
