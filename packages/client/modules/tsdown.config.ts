import { clientBundle } from '../tsdown.client.ts'

export default clientBundle(
  '@eco-agent/dsh-client-modules',
  ['lib/types/index.js', 'lib/types/invariant.js'],
)
