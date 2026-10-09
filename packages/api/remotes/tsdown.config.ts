import { clientBundle } from '../../client/tsdown.client.ts'

export default clientBundle(
  '@eco-agent/dsh-api-remotes',
  ['lib/types/index.js'],
  { hostPhase: true },
)
