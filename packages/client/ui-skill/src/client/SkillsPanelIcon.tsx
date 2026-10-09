/** The sidebar's Skills entry icon; the sidebar owns the button, label, and selected state around it. */

import type { ReactNode } from 'react'
import { IconSparkleRegular } from '@eco-agent/dsh-client-ui-primitives'
import type { PropsRuntime } from '@eco-agent/dsh-client-ui-slots'
import type {} from '@eco-agent/dsh-client-ui-sidebar/client'

/**
 * Render the skill glyph at the size the sidebar asks for.
 * @param props - the sidebar's icon share: the requested edge and whether the panel is selected.
 * @returns the icon element.
 */
export function SkillsPanelIcon({ size }: PropsRuntime<'sidebar.panellist'>): ReactNode {
  return <IconSparkleRegular size={size} />
}
