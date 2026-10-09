import { clientBundle } from '../../client/tsdown.client.ts'

export default clientBundle(
  '@eco-agent/dsh-session-log-export',
  ['lib/types/index.js'],
  { hostPhase: true },
)
