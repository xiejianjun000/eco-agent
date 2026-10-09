import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@eco-agent/cordis'
import Loader from '@eco-agent/cordis-plugin-loader'
import Include from '@eco-agent/cordis-plugin-include'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import LlmRuntime, { createUserMessage, LlmAdapter  } from '@eco-agent/dsh-llm'
import type { GenerateOptions, StreamChunk } from '@eco-agent/dsh-llm'
import SessionStore, { SessionId } from '@eco-agent/dsh-session'
import SessionProjectionRegistry from '@eco-agent/dsh-session-projection'
import SessionTitleService from '@eco-agent/dsh-session-title'
import * as providerPlugin from '@eco-agent/dsh-session-title-first-prompt-llm'

let root: string | undefined
let context: Context | undefined

class LoaderAdapter extends LlmAdapter {
  readonly requests: GenerateOptions[] = []

  override async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    this.requests.push(options)
    yield { type: 'text-delta', index: 0, text: 'Loader composed title' }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

afterEach(async () => {
  await context?.fiber.dispose()
  context = undefined
  if (root !== undefined) await rm(root, { recursive: true, force: true })
  root = undefined
})

async function loadComposition(): Promise<Context> {
  root = await mkdtemp(join(tmpdir(), 'dsh-title-loader-'))
  const configPath = join(root, 'cordis.yml')
  await writeFile(configPath, [
    "- name: '@eco-agent/dsh-llm'",
    "- name: '@eco-agent/dsh-session'",
    "- name: '@eco-agent/dsh-session-projection'",
    "- name: '@eco-agent/dsh-session-title'",
    '  config:',
    '    fallbackMaxWords: 5',
    '    fallbackMaxBytes: 40',
    '    maxTitleBytes: 80',
    "- name: '@eco-agent/dsh-session-title-first-prompt-llm'",
    '  config:',
    '    targetWords: 5',
    '    targetCjkCharacters: 10',
    '    maxInputBytes: 1000',
    '    maxOutputTokens: 32',
    '    timeoutMs: 1000',
    "    provider: 'title-route'",
    "    model: 'title-model'",
    '',
  ].join('\n'))

  context = new Context()
  context.baseUrl = pathToFileURL(root).href + '/'
  await context.plugin(Loader)
  context.loader.builtins.include = Include
  const modules = new Map<string, unknown>([
    ['@eco-agent/dsh-llm', LlmRuntime],
    ['@eco-agent/dsh-session', SessionStore],
    ['@eco-agent/dsh-session-projection', SessionProjectionRegistry],
    ['@eco-agent/dsh-session-title', SessionTitleService],
    ['@eco-agent/dsh-session-title-first-prompt-llm', providerPlugin],
  ])
  context.loader.internal = {
    version: 'v2',
    async import(specifier: string) {
      if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
      return modules.get(specifier)
    },
  } as unknown as NonNullable<typeof context.loader.internal>
  await context.loader.create({
    name: 'cordis:include',
    config: { path: pathToFileURL(configPath).href },
  })
  await context.loader.await()
  return context
}

describe('session-title Loader composition', () => {
  it('loads the service and one model provider with required deployment policy', async () => {
    const ctx = await loadComposition()
    const unloaded = [...ctx.loader.entries()]
      .filter(entry => entry.fiber === undefined && !entry.disabled)
      .map(entry => entry.options.name)
    expect(unloaded).toEqual([])

    const adapter = new LoaderAdapter()
    ctx.llm.registerAdapter(['title-route'], adapter)
    const session = ctx.sessions.create(SessionId('loader-title'))
    session.append('turn/start', {
      turn: 1,
    })
    const message = session.append('user/message', createUserMessage({
      content: [{ type: 'text', text: 'Compose a title through Loader' }],
      source: { kind: 'user' },
    }), { surfaceOp: 'append' })
    await new Promise(resolve => setTimeout(resolve, 0))
    session.append('request/header', {
      header: { config: { provider: 'main-route', model: 'main-model' } },
      reason: 'initial',
    })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(adapter.requests[0]).toMatchObject({ provider: 'title-route', model: 'title-model' })
    expect(ctx.sessionTitle.get(session)).toMatchObject({
      title: 'Loader composed title',
      messageSeqs: [message.seq],
      source: {
        kind: 'provider',
        provider: 'session-title-first-prompt-llm',
        model: { provider: 'title-route', model: 'title-model' },
      },
    })
  })
})
