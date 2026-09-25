/**
 * Select-to-quote: a floating control over any text a person selects on the
 * page, writing that text into the current Session's composer as a quote block.
 *
 * The seat is `conversation.input.dock`, which is the only place this plugin can
 * reach the Session's input actions; the control itself is portalled to the body
 * because a selection can be anywhere on the page, including inside the right
 * Sidebar where a dock entry is not in the tree at all.
 *
 * Three deliberate omissions:
 * - A selection inside a text field is not quotable: quoting the composer into
 *   itself is never what a person means, and the control would sit on top of the
 *   text they are editing.
 * - The draft is read at click time, not at render time, so text typed after the
 *   selection was made is not lost.
 * - A refused or empty selection shows no control rather than a disabled one.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { NS } from './locales.ts'
import css from './QuoteDock.module.css'

/** Full props of the dock entry: the Session's input seat, actions, and copy. */
export type QuoteDockProps = PropsRuntime<'conversation.input.dock'> & PropsLocale<typeof NS>

/** Where the control is drawn, and what it would quote. */
interface Anchor {
  readonly x: number
  readonly y: number
  /** `above` unless the selection sits too close to the top edge to hold it. */
  readonly placement: 'above' | 'below'
  readonly text: string
}

/** Headroom the control needs above a selection before it flips below, in px. */
const TOP_ROOM = 76

/**
 * Read the selection under the pointer, if it is quotable.
 * @returns the anchor, or undefined when nothing usable is selected.
 */
function quotableSelection(): Anchor | undefined {
  const selection = window.getSelection()
  if (selection === null || selection.rangeCount === 0 || selection.isCollapsed) return undefined
  const text = selection.toString().trim()
  if (text.length === 0) return undefined
  const node = selection.anchorNode
  const element = node === null
    ? null
    : node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement
  // Editing surfaces opt out: their own selection is the draft being edited.
  if (element?.closest('textarea, input, [contenteditable="true"]') != null) return undefined
  const rect = selection.getRangeAt(0).getBoundingClientRect()
  if (rect.width === 0 && rect.height === 0) return undefined
  // A selection scrolled out of the viewport keeps a rect, but a fixed control
  // anchored to it would be drawn off-screen and unclickable; there is nothing
  // to quote from a passage nobody can see anyway.
  if (rect.bottom < 0 || rect.top > window.innerHeight) return undefined
  const above = rect.top >= TOP_ROOM
  return {
    x: rect.left + rect.width / 2,
    y: above ? rect.top : rect.bottom,
    placement: above ? 'above' : 'below',
    text,
  }
}

/**
 * Render the floating quote control for the current selection.
 * @param props - the Session's input values, actions, and locale.
 * @returns the portal, or null while nothing is selected.
 */
export function QuoteDock({ useInput, inputActions, t }: QuoteDockProps): ReactNode {
  const draft = useInput(state => state.draft)
  // The click reads the newest draft; the effect below only needs the setter.
  const latest = useRef(draft)
  latest.current = draft
  const [anchor, setAnchor] = useState<Anchor>()

  useEffect(() => {
    const sync = (): void => { setAnchor(quotableSelection()) }
    document.addEventListener('selectionchange', sync)
    // A scroll moves the selection out from under the control's fixed position.
    window.addEventListener('scroll', sync, true)
    return () => {
      document.removeEventListener('selectionchange', sync)
      window.removeEventListener('scroll', sync, true)
    }
  }, [])

  const onQuote = useCallback((text: string) => {
    const quoted = text.split('\n').map(line => `> ${line}`).join('\n')
    const base = latest.current
    inputActions.setDraft(base.length === 0 ? `${quoted}\n` : `${base}\n\n${quoted}\n`)
    window.getSelection()?.removeAllRanges()
    setAnchor(undefined)
  }, [inputActions])

  const style = useMemo(() => ({ left: `${String(anchor?.x ?? 0)}px`, top: `${String(anchor?.y ?? 0)}px` }), [anchor])
  if (anchor === undefined) return null
  return createPortal(
    <button
      type="button"
      className={css.action}
      data-placement={anchor.placement}
      style={style}
      // Keep the selection alive: a pointer-down that clears it would take the
      // text away before the click reads it.
      onMouseDown={(event) => { event.preventDefault() }}
      onClick={() => { onQuote(anchor.text) }}
    >
      {t('action.label')}
    </button>,
    document.body,
  )
}
