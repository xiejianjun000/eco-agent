/** The standalone SDK-minimal bundle's complete declared Cordis tree. */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as yaml from 'js-yaml'
import { describe, expect, it } from 'vitest'
import { entryListSchema } from '@eco-agent/cordis-plugin-include'

function packageName(specifier: string): string {
  return specifier.startsWith('@') ? specifier.split('/').slice(0, 2).join('/') : specifier.split('/')[0]!
}

describe('dsh-sdk-minimal bundle', () => {
  it('declares one standalone allowlisted tree with every row dependency', () => {
    const root = fileURLToPath(new URL('..', import.meta.url))
    const manifest = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')) as {
      dependencies?: Record<string, string>
      dsh?: { bundle?: { patch?: string } }
    }
    expect(manifest.dsh?.bundle?.patch).toBe('./cordis.patch.yml')
    const patches = yaml.load(
      readFileSync(resolve(root, manifest.dsh!.bundle!.patch!), 'utf8'),
      { schema: entryListSchema },
    ) as Array<{ insert?: Array<{ id?: string; inject?: string[]; name?: string; config?: Record<string, unknown>; disabled?: unknown }> }>
    expect(patches).toHaveLength(1)
    const rows = patches[0]?.insert ?? []
    expect(rows.map(row => [row.id, row.name])).toEqual([
      ['sdk-app-startup', '@eco-agent/dsh-sdk-app'],
      ['sdk-jsonrpc-server', '@eco-agent/dsh-sdk-jsonrpc-server'],
      ['deepseek-llm-api-extensions', '@eco-agent/dsh-deepseek-llm-api-extensions'],
      ['session-log-deepseek', '@eco-agent/dsh-session-log-deepseek'],
      ['plugin-package-inventory-deepseek', '@eco-agent/dsh-plugin-package-inventory-deepseek'],
      ['llm-deepseek', '@eco-agent/dsh-llm-deepseek-api-key'],
      ['sandbox', '@eco-agent/dsh-sandbox-local'],
      ['session-projection', '@eco-agent/dsh-session-projection'],
      ['sandbox-policy', '@eco-agent/dsh-sandbox-policy'],
      ['subprocess', '@eco-agent/dsh-subprocess-local'],
      ['pty', '@eco-agent/dsh-terminal'],
      ['terminal-bash', '@eco-agent/dsh-terminal-bash'],
      ['terminal-pwsh', '@eco-agent/dsh-terminal-bash'],
      ['timer', '@eco-agent/cordis-plugin-timer'],
      ['llm', '@eco-agent/dsh-llm'],
      ['session', '@eco-agent/dsh-session'],
      ['session-title', '@eco-agent/dsh-session-title'],
      ['system-prompt', '@eco-agent/dsh-system-prompt'],
      ['tools', '@eco-agent/dsh-tools'],
      ['mcp-resources', '@eco-agent/dsh-mcp-resources'],
      ['agent', '@eco-agent/dsh-agent'],
      ['llm-retry', '@eco-agent/dsh-llm-retry'],
      ['jobs', '@eco-agent/dsh-jobs-local'],
      ['invariants', '@eco-agent/dsh-invariants'],
      ['session-invariant', '@eco-agent/dsh-session/invariant'],
      ['agent-invariant', '@eco-agent/dsh-agent/invariant'],
      ['scope-invariant', '@eco-agent/dsh-scope/invariant'],
      ['agent-loop-invariant', '@eco-agent/dsh-agent-loop/invariant'],
      ['agent-loop', '@eco-agent/dsh-agent-loop'],
      ['persistent-bash', '@eco-agent/dsh-tool-bash-persistent'],
      ['persistent-pwsh', '@eco-agent/dsh-tool-pwsh-persistent'],
      ['sessions', '@eco-agent/dsh-session-persistence-jsonl'],
    ])
    expect(rows.find(row => row.id === 'sdk-app-startup')?.config).toEqual({ profile: 'sdk-minimal' })
    expect(rows.find(row => row.id === 'sdk-jsonrpc-server')).toMatchObject({
      inject: ['sdkAppStartup', 'loader'],
      config: { maxTokensAsSuccess: false },
    })
    expect(rows.find(row => row.id === 'llm-deepseek')?.config).toEqual({
      apiKeyEnv: 'DEEPSEEK_API_KEY',
      defaultContextWindow: { __jsExpr: 'Number(process.env.DSH_CONTEXT_WINDOW ?? 1000000)' },
      streamIdleTimeoutMs: 172800000,
    })
    expect(rows.find(row => row.id === 'system-prompt')?.config).toEqual({
      includeHarnessIdentity: false,
      includeRuntimeContext: false,
      personaPrefix: { __jsExpr: "process.env.DSH_SYSTEM_PROMPT ?? 'You are a helpful software engineer assistant.'" },
    })
    expect(rows.find(row => row.id === 'agent-loop')?.config).toEqual({ agents: [] })
    expect(rows.find(row => row.id === 'terminal-bash')).toMatchObject({
      disabled: { __jsExpr: "process.platform === 'win32'" },
    })
    expect(rows.find(row => row.id === 'terminal-pwsh')).toMatchObject({
      disabled: { __jsExpr: "process.platform !== 'win32'" },
      config: { shellDialect: 'pwsh', timeoutMs: 300000 },
    })
    expect(Object.keys(manifest.dependencies ?? {}).sort()).toEqual(
      [...new Set(rows.map(row => row.name).filter((name): name is string => name !== undefined).map(packageName))].sort(),
    )
  })
})
