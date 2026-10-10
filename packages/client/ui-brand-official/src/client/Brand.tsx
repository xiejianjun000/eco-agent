import { EcoLogo } from '@eco-agent/dsh-client-ui-primitives'
import type { SidebarBrandMarkOwnerProps } from '@eco-agent/dsh-client-ui-sidebar/client'

/**
 * Render the official mark with the presentation requested by its host surface.
 * @param props - Host-supplied mark presentation.
 * @returns the official eco mark.
 */
export function OfficialBrandMark({ size }: SidebarBrandMarkOwnerProps) {
  return <EcoLogo size={size} />
}

/**
 * Render the official name without its leading "eco": the mark slot already
 * carries the green eco wordmark, so the name renders only "Agent" and the
 * pair reads "eco Agent" instead of duplicating the word. The host's
 * `.brandName` styles (size, weight, tracking, color) apply to this span.
 * @returns the official name span.
 */
export function OfficialBrandName() {
  return <span>Agent</span>
}
