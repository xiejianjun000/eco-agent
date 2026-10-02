/**
 * Workspace write channel: guarded full-file text writes and literal edits
 * inside one Session's workspace, exposed as `ecoWorkspaceWrite`.
 *
 * This is the counterpart the read-only `workspaceFiles` service deliberately
 * does not carry. Every method confines its path to the Session's workspace
 * root before touching the filesystem, refuses symlinks and non-regular
 * entries, and — when the caller passes `expectedVersion` — refuses to clobber
 * a file that changed underneath it. Nothing here deletes, renames, or creates
 * directories: `dsh-fs` exposes no such operation, and inventing one at this
 * layer would mean writing file-removal code the product has not reviewed.
 *
 * The intended caller is the sidebar document editor, whose draft is a whole
 * file's text; a save is therefore a write, not an edit, and `editText` is
 * offered for the smaller in-place case an agent-driven caller already has.
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@deepseek-ai/dsh-fs'
import type { FsTarget, FsVersion } from '@deepseek-ai/dsh-fs'
import type {} from '@deepseek-ai/dsh-sandbox-policy'
import type { SandboxExecutionPolicy } from '@deepseek-ai/dsh-sandbox'
import type {} from '@deepseek-ai/dsh-session'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-session-persistence'
import { Remote, RemoteError, TypertRemoteService, type TypertLookup } from '@deepseek-ai/dsh-typert-protocol'
import type { EcoWriteEdit, EcoWriteResult, EcoWriteScope } from './types.ts'

export type * from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Host owner of the `ecoWorkspaceWrite` Remote namespace. */
    ecoWorkspaceWrite: EcoWorkspaceWrite
  }
}

declare module '@deepseek-ai/dsh-typert-protocol' {
  interface TypertLookupMap {
    /** Resolve a Session id to its workspace root without loading its event body or activating an Agent. */
    ecoWriteScope: TypertLookup<EcoWriteScope, SessionId>
  }
}

/** Deployment cap on one write's content. */
export interface Config {
  /** Inclusive byte cap on one write; a larger payload is refused, never truncated. */
  readonly maxBytes: number
}

/**
 * Host owner of the `ecoWorkspaceWrite` Remote namespace.
 */
export class EcoWorkspaceWrite extends TypertRemoteService {
  static inject = ['fs', 'sandboxPolicy', 'sessions', 'typert']

  static Config: z<Config> = z.object({
    maxBytes: z.number().step(1).min(1).default(8 * 1024 * 1024),
  })

  /**
   * @param ctx - Host context carrying the filesystem, Sessions, and the sandbox policy.
   * @param config - deployment cap on one write.
   */
  constructor(ctx: Context, private readonly config: Config) {
    super(ctx, 'ecoWorkspaceWrite')
    ctx.inject(['sessions', 'typert'], (scope) => {
      scope.typert.lookups.register('ecoWriteScope', {
        parameter: 'ecoWriteScope',
        wire: 'ecoWriteScopeId',
        hostTypeSymbol: '@deepseek-ai/dsh-api-eco-workspace-write#EcoWriteScope',
        wireTypeSymbol: '@deepseek-ai/dsh-session/types#SessionId',
        resolve: async (sessionId) => {
          const live = scope.sessions.get(sessionId)?.header
          const stored = live === undefined
            ? await scope.get('sessionPersistence')?.stat(sessionId)
            : undefined
          const header = live ?? stored?.header
          if (header === undefined) return undefined
          return {
            sessionId,
            workspaceRoot: header.cwd ?? scope.sandboxPolicy.workspaceRoot,
          }
        },
      })
    })
  }

  /**
   * Write a whole file's text inside the Session's workspace.
   * @param ecoWriteScope - header-derived workspace root for the Session identity on the wire.
   * @param path - workspace path, absolute or relative to the workspace root.
   * @param text - the file's full new content.
   * @param expectedVersion - freshness token the file must still carry; omit for an unconditional overwrite.
   * @param signal - caller cancellation.
   * @returns the workspace path, the version the write produced, and whether it created the file.
   */
  @Remote
  async writeText(
    ecoWriteScope: EcoWriteScope,
    path: string,
    text: string,
    expectedVersion: string | undefined,
    signal: AbortSignal,
  ): Promise<EcoWriteResult> {
    const target = await this.locateWritable(ecoWriteScope, path, signal)
    this.refusePayload(path, text)
    const outcome = await this.guarded(
      path,
      () => this.ctx.fs.writeText(
        target,
        text,
        expectedVersion === undefined
          ? undefined
          : { kind: 'replaceIfVersion', version: expectedVersion as FsVersion },
        signal,
        this.policyFor(ecoWriteScope),
      ),
    )
    return { path, version: outcome.version, created: outcome.operation === 'create' }
  }

  /**
   * Replace one literal span inside a file in the Session's workspace.
   * @param ecoWriteScope - header-derived workspace root for the Session identity on the wire.
   * @param path - workspace path, absolute or relative to the workspace root.
   * @param edit - the literal search/replace request.
   * @param expectedVersion - freshness token the file must still carry; omit for an unconditional edit.
   * @param signal - caller cancellation.
   * @returns the workspace path and the version the edit produced.
   */
  @Remote
  async editText(
    ecoWriteScope: EcoWriteScope,
    path: string,
    edit: EcoWriteEdit,
    expectedVersion: string | undefined,
    signal: AbortSignal,
  ): Promise<{ path: string; version: string }> {
    const target = await this.locateWritable(ecoWriteScope, path, signal)
    const outcome = await this.guarded(
      path,
      () => this.ctx.fs.editText(
        target,
        { oldString: edit.oldString, newString: edit.newString, replaceAll: edit.replaceAll },
        expectedVersion === undefined ? undefined : { version: expectedVersion as FsVersion },
        signal,
        this.policyFor(ecoWriteScope),
      ),
    )
    return { path, version: outcome.version }
  }

  /**
   * The per-call sandbox policy one write runs under.
   *
   * The Session is what carries the boundary: its immutable cwd is the
   * workspace-write root, and its last `sandbox/mode` event is the mode. Passing
   * the resolved policy is what lets the write land at all — the filesystem
   * backend's own default is the deployment root, which refuses a path inside a
   * Session workspace that is not the deployment root.
   * @param scope - the write's resolved Session scope.
   * @returns the policy to hand the filesystem backend.
   */
  private policyFor(scope: EcoWriteScope): SandboxExecutionPolicy {
    const session = this.ctx.sessions.get(scope.sessionId)
    return this.ctx.sandboxPolicy.resolve(session === undefined ? {} : { session })
  }

  /** Resolve one writable target: inside the workspace, and either absent or an existing regular file. */
  private async locateWritable(
    scope: EcoWriteScope,
    path: string,
    signal: AbortSignal,
  ): Promise<FsTarget> {
    const { workspaceRoot } = scope
    const root = await this.ctx.fs.resolve(workspaceRoot, { signal })
    const entry = await this.ctx.fs.lstat(path, { cwd: workspaceRoot }, signal)
    if (entry !== undefined && entry.type !== 'file') {
      throw new RemoteError(
        'eco-write/not-regular-file',
        `"${path}" is a ${entry.type}`,
        { path, kind: entry.type },
      )
    }
    const target = await this.ctx.fs.resolve(path, { cwd: workspaceRoot, signal })
    if (!this.ctx.fs.contains(root, target)) {
      throw new RemoteError('eco-write/outside-workspace', `"${path}" is outside the workspace`, { path })
    }
    return target
  }

  /** Reject a payload no text file in this product should carry. */
  private refusePayload(path: string, text: string): void {
    if (Buffer.byteLength(text, 'utf8') > this.config.maxBytes) {
      throw new RemoteError(
        'eco-write/too-large',
        `"${path}" exceeds the ${this.config.maxBytes} byte write cap`,
        { path, limit: this.config.maxBytes },
      )
    }
    if (text.includes('\u0000')) {
      throw new RemoteError('eco-write/not-text', `"${path}" contains NUL bytes`, { path })
    }
  }

  /** Run one filesystem mutation and translate its staleness code into the domain failure. */
  private async guarded<T>(path: string, run: () => Promise<T>): Promise<T> {
    try {
      return await run()
    } catch (cause) {
      if ((cause as { code?: unknown } | undefined)?.code === 'FS_STALE_VERSION') {
        throw new RemoteError(
          'eco-write/stale-version',
          `"${path}" changed since the version you are editing; reload before saving`,
          { path },
          { cause },
        )
      }
      throw cause
    }
  }
}

export default EcoWorkspaceWrite
