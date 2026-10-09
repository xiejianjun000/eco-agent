import { Context } from '@eco-agent/cordis'
import { onTestFinished } from 'vitest'
import SessionStore from '@eco-agent/dsh-session'
import FileSystem from '@eco-agent/dsh-fs-local'
import Subprocess from '@eco-agent/dsh-subprocess-local'
import Sandbox from '@eco-agent/dsh-sandbox-local'
import SandboxPolicy from '@eco-agent/dsh-sandbox-policy'
import SessionProjections from '@eco-agent/dsh-session-projection'
import type { SandboxMode } from '@eco-agent/dsh-sandbox'
import NodeRuntime from '../src/index.ts'
import type { Config } from '../src/index.ts'

export async function mountRuntime(ctx: Context, config: Config = {}, policy: { mode?: SandboxMode; workspaceRoot?: string } = {}) {
  onTestFinished(async () => { await ctx.fiber.dispose() })
  if (!ctx.get('sessions')) await ctx.plugin(SessionStore)
  if (!ctx.get('fs')) await ctx.plugin(FileSystem)
  if (!ctx.get('subprocess')) await ctx.plugin(Subprocess)
  if (!ctx.get('sandbox')) await ctx.plugin(Sandbox, {})
  if (!ctx.get('sessionProjections')) await ctx.plugin(SessionProjections)
  if (!ctx.get('sandboxPolicy')) await ctx.plugin(SandboxPolicy, { mode: 'danger-full-access', ...policy })
  await ctx.plugin(NodeRuntime, config)
  return ctx.ptcRuntime as NodeRuntime
}
