/** Parent adapter that fails if the composition-only Loader test starts a turn. */

import type { Context } from '@eco-agent/cordis'
import type { GenerateOptions, StreamChunk } from '@eco-agent/dsh-llm'
import { LlmAdapter } from '@eco-agent/dsh-llm'

class CompositionOnlyAdapter extends LlmAdapter {
  async * stream(_options: GenerateOptions): AsyncIterable<StreamChunk> {
    throw new Error('subagent-codex Loader composition must not invoke a model')
  }
}

export const name = 'codex-loader-composition-fixture'
export const inject = ['llm']

/**
 * Register a parent adapter solely so the host composition is complete.
 * @param ctx - Loader context supplying the LLM seam.
 */
export function apply(ctx: Context): void {
  ctx.llm.registerAdapter(['mock'], new CompositionOnlyAdapter())
}
