/**
 * One short, self-removing banner, drawn outside the React tree on purpose.
 *
 * A tab-menu item dismisses the menu the moment it acts, and the menu owns the
 * slot that rendered the item — so anything the item renders is unmounted in the
 * same tick, before a person could read it. The notice therefore lives on a host
 * element this module appends to `document.body` and removes when it empties.
 */

/** Host element id, stable so one plugin lifetime owns at most one host. */
const HOST_ID = 'eco-tabactions-notice-host'

/** How long one banner stays on screen, in ms. */
const NOTICE_MS = 1800

/** Append (or find) the banner host. */
function hostOf(): HTMLElement {
  const existing = document.getElementById(HOST_ID)
  if (existing !== null) return existing
  const host = document.createElement('div')
  host.id = HOST_ID
  Object.assign(host.style, {
    position: 'fixed',
    top: '16px',
    left: '50%',
    transform: 'translateX(-50%)',
    zIndex: '9999',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '6px',
    pointerEvents: 'none',
  } satisfies Partial<CSSStyleDeclaration>)
  document.body.appendChild(host)
  return host
}

/**
 * Show one banner and forget it.
 * @param text - resolved copy to show.
 * @param failed - refusal styling; a failure must not read as a success.
 */
export function flashNotice(text: string, failed = false): void {
  const host = hostOf()
  const banner = document.createElement('div')
  banner.textContent = text
  Object.assign(banner.style, {
    padding: '6px 12px',
    borderRadius: '8px',
    background: failed ? 'rgba(180, 83, 9, 0.95)' : 'rgba(17, 24, 39, 0.95)',
    color: '#f9fafb',
    fontSize: '12px',
    lineHeight: '18px',
    boxShadow: '0 4px 14px rgba(0, 0, 0, 0.24)',
  } satisfies Partial<CSSStyleDeclaration>)
  host.appendChild(banner)
  window.setTimeout(() => {
    banner.remove()
    // Leave nothing behind: an empty host is only noise in the accessibility tree.
    if (host.childElementCount === 0) host.remove()
  }, NOTICE_MS)
}
