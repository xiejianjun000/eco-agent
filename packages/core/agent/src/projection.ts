import type { TurnBoundaryProjection } from './types.ts'
import type {} from '@eco-agent/dsh-session-projection'

declare module '@eco-agent/dsh-session-projection/types' {
  interface SessionProjectionStateMap {
    /** The agent session's open/last turn and step boundary facts (whole value). */
    turnBoundary: TurnBoundaryProjection
  }
}

export {}
