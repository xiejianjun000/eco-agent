import { clientBundle } from '../../client/tsdown.client.ts'

export default clientBundle(
  '@deepseek-ai/dsh-api-eco-workspace-write',
  ['lib/types/index.js'],
  { hostPhase: true },
)
