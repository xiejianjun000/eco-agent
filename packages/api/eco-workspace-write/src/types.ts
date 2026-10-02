/**
 * Wire vocabulary of the workspace write channel: the Session-derived scope,
 * one write's outcome, and the domain failure codes a caller can branch on.
 *
 * The read side (`workspaceFiles`) deliberately exposes no mutations. This
 * package is the narrow counterpart that does, and every method resolves its
 * path through the same workspace confinement the read side uses — a write can
 * never land outside the Session's workspace root, which is a stricter rule
 * than reads follow (reads may reach outside on purpose).
 * @module @deepseek-ai/dsh-api-eco-workspace-write/types
 */

import type { SessionId } from '@deepseek-ai/dsh-session/types'

declare module '@deepseek-ai/dsh-typert-protocol' {
  interface RemoteErrorDetailsMap {
    /** The path resolves outside the Session's workspace root; nothing was written. */
    'eco-write/outside-workspace': { readonly path: string }
    /** An entry exists at the path and it is not a regular file (directory, symlink, or other). */
    'eco-write/not-regular-file': { readonly path: string; readonly kind: string }
    /** The guarded write found a different version than the caller expected; nothing was written. */
    'eco-write/stale-version': { readonly path: string }
    /** The content exceeds the configured byte cap; the file is left untouched. */
    'eco-write/too-large': { readonly path: string; readonly limit: number }
    /** The content carries NUL bytes, which no text file in this product holds. */
    'eco-write/not-text': { readonly path: string }
  }
}

/** Header-derived write context for one Session identity. */
export interface EcoWriteScope {
  /** Session identity received on the wire. */
  readonly sessionId: SessionId
  /** Session workspace root, or the deployment fallback when its header has no cwd. */
  readonly workspaceRoot: string
}

/** Result of one accepted write. */
export interface EcoWriteResult {
  /** Workspace-relative path of the written file, echoing the request. */
  readonly path: string
  /** Freshness token of the file after the write; pass it back as `expectedVersion` to guard the next one. */
  readonly version: string
  /** Whether this write created the file rather than replacing it. */
  readonly created: boolean
}

/** A literal replacement inside one file, mirroring `FsEditRequest`. */
export interface EcoWriteEdit {
  /** Exact text to find; an empty string is refused. */
  readonly oldString: string
  /** Replacement text; empty deletes the found span. */
  readonly newString: string
  /** Replace every occurrence instead of only the first. */
  readonly replaceAll: boolean
}
