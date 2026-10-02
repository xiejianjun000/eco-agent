/** Suggestion cards rendered below the composer in the hero (new-session) state. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { InputActions } from '@deepseek-ai/dsh-client-ui-conversation/client'
import { writeClipboard } from '@deepseek-ai/dsh-client-ui-primitives'
import { CheckGlyph, CopyGlyph } from './icons.tsx'
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

/** How long one copy result stays on screen, in ms. */
const FEEDBACK_MS = 1400

/** Result of one copy attempt, as a card's trailing control shows it. */
type CopyState = 'idle' | 'done' | 'failed'

/** What one card's copy control needs. */
interface CopyControlProps {
  /** Prompt text this control writes. */
  readonly text: string
  /** Locale-bound copy. */
  readonly t: (key: SuggestionKey) => string
}

/**
 * One card's copy control: a glyph button writing that card's whole prompt.
 *
 * A clipboard write is a host request, not a promise the UI can keep: a
 * refused write (permission denied, insecure context) reports `false`, and the
 * control says so instead of showing the success tick regardless.
 * @param props - text to write and the card's copy.
 * @returns the copy button.
 */
function CopyControl({ text, t }: CopyControlProps): ReactNode {
  const [state, setState] = useState<CopyState>('idle')
  // Late writes from an unmounted or re-clicked control must not repaint it.
  const epoch = useRef(0)
  useEffect(() => () => { epoch.current += 1 }, [])
  const onCopy = useCallback(() => {
    const mine = epoch.current + 1
    epoch.current = mine
    void writeClipboard(text).then((ok) => {
      if (epoch.current !== mine) return
      setState(ok ? 'done' : 'failed')
      window.setTimeout(() => {
        if (epoch.current === mine) setState('idle')
      }, FEEDBACK_MS)
    })
  }, [text])

  const label = state === 'done' ? t('copy.done') : state === 'failed' ? t('copy.failed') : t('copy.label')
  return (
    <button
      type="button"
      className={css.copy}
      data-copy-state={state}
      aria-label={label}
      title={label}
      onClick={onCopy}
    >
      {state === 'done' ? <CheckGlyph /> : <CopyGlyph />}
    </button>
  )
}

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
          // A row, not a button: a copy control nested inside the send button
          // would be invalid markup and unreachable from the keyboard.
          <div key={role} className={css.card}>
            <button
              type="button"
              className={css.label}
              onClick={() => { send(prompt) }}
            >
              {t(role)}
            </button>
            <CopyControl text={t(prompt)} t={t} />
          </div>
        ))}
      </div>
      <div className={css.elements}>{t('elements')}</div>
    </div>
  )
}
