// @ts-nocheck
import * as fs from 'node:fs'
import * as path from 'node:path'
import { randomUUID } from 'node:crypto'
import { logger } from './logger.ts'

/**
 * Maps a Feishu conversation to a stable DSH session id so multi-turn chats
 * stay in the same DSH session until the user explicitly starts a new one.
 * Persisted to JSON so the mapping survives gateway restarts.
 */

/** Feishu-side conversation identity, kept per DSH session for reverse routing. */
export interface ConversationInfo {
  /** Feishu conversation key (see {@link conversationKey}). */
  key: string
  /** Feishu chat id (`oc_…`). */
  chatId: string
  /** `p2p` private chat or `group`. */
  chatType: 'p2p' | 'group'
  /** The user's open_id in this conversation. */
  userOpenId: string
  /** The last user message id received in this conversation (reaction target). */
  lastUserMessageId?: string
  /** Feishu topic/thread id for group messages (present when the conversation is a thread). */
  threadId?: string
  /** Feishu root message id for group replies (the top of the thread). */
  rootId?: string
}

export class SessionMap {
  private readonly map = new Map<string, string>()
  private readonly conv = new Map<string, ConversationInfo>()

  constructor(private readonly file: string) {
    this.load()
  }

  /** Whether a Feishu conversation key already has a mapped DSH session. */
  has(key: string): boolean {
    return this.map.has(key)
  }

  /** Get or create the DSH session id for a Feishu conversation key. */
  idFor(key: string): string {
    let id = this.map.get(key)
    if (!id) {
      id = `feishu-${randomUUID()}`
      this.map.set(key, id)
      this.persist()
    }
    return id
  }

  /** Remember the Feishu-side identity of a DSH session (reverse routing). */
  recordSession(key: string, sessionId: string, info: ConversationInfo): void {
    this.conv.set(sessionId, info)
    this.persist()
  }

  /** Look up the Feishu conversation that owns a DSH session id. */
  infoForSession(sessionId: string): ConversationInfo | undefined {
    return this.conv.get(sessionId)
  }

  /** Whether this gateway owns the session (reverse routing / interaction routing). */
  ownsSession(sessionId: string): boolean {
    return this.conv.has(sessionId)
  }

  /** Drop the mapping; the next message starts a fresh DSH session (/new). */
  reset(key: string): void {
    const id = this.map.get(key)
    this.map.delete(key)
    if (id !== undefined) this.conv.delete(id)
    this.persist()
    logger.info('session-map', `conversation ${key} reset`)
  }

  /**
   * Re-point every conversation key at a new DSH session id (wedged-session
   * self-heal): when a session identity is permanently conflicted, the
   * conversation continues on a fresh id while the Feishu↔session mapping
   * stays stable.
   */
  remap(oldSessionId: string, newSessionId: string): void {
    let changed = false
    for (const [key, id] of this.map) {
      if (id === oldSessionId) {
        this.map.set(key, newSessionId)
        changed = true
      }
    }
    const info = this.conv.get(oldSessionId)
    if (info !== undefined) {
      this.conv.delete(oldSessionId)
      this.conv.set(newSessionId, info)
      changed = true
    }
    if (changed) {
      this.persist()
      logger.warn('session-map', `remapped ${oldSessionId} → ${newSessionId}`)
    }
  }

  list(): Array<{ key: string; sessionId: string }> {
    return [...this.map.entries()].map(([k, v]) => ({ key: k, sessionId: v }))
  }

  flush(): void {
    this.persist()
  }

  private persist(): void {
    if (!this.file) return
    try {
      const dir = path.dirname(this.file)
      fs.mkdirSync(dir, { recursive: true })
      const tmp = `${this.file}.tmp`
      const payload = {
        sessions: Object.fromEntries(this.map),
        conversations: Object.fromEntries(this.conv),
      }
      fs.writeFileSync(tmp, JSON.stringify(payload, null, 2), 'utf-8')
      fs.renameSync(tmp, this.file)
    } catch (err) {
      logger.error('session-map', 'persist failed:', err)
    }
  }

  private load(): void {
    if (!this.file || !fs.existsSync(this.file)) return
    try {
      const raw = JSON.parse(fs.readFileSync(this.file, 'utf-8')) as Record<string, unknown>
      // New format: { sessions, conversations }. Old format: flat key→sessionId.
      if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'sessions' in raw) {
        const sessions = raw.sessions as Record<string, string>
        for (const [k, v] of Object.entries(sessions)) {
          if (k && typeof v === 'string') this.map.set(k, v)
        }
        const conversations = (raw.conversations ?? {}) as Record<string, ConversationInfo>
        for (const [k, v] of Object.entries(conversations)) {
          if (k && v && typeof v === 'object' && typeof v.chatId === 'string') {
            this.conv.set(k, v)
          }
        }
      } else {
        for (const [k, v] of Object.entries(raw)) {
          if (k && typeof v === 'string') this.map.set(k, v)
        }
      }
      logger.info('session-map', `loaded ${this.map.size} mappings from ${this.file}`)
    } catch (err) {
      logger.error('session-map', 'load failed:', err)
    }
  }
}

/**
 * Feishu conversation key.
 * - p2p: the user's open_id (one DSH session per user).
 * - group: scoped to the topic/thread the message belongs to, so each Feishu
 *   group topic keeps its own independent DSH session. `topicId` is the
 *   thread_id / root_id when present, otherwise the originating message id
 *   (later replies in that thread carry it as their root/thread id). Omit
 *   `topicId` for the legacy `chatId:userId` key (still used by tests).
 */
export function conversationKey(
  chatId: string,
  chatType: string,
  userId: string,
  topicId?: string,
): string {
  if (chatType === 'group') {
    return topicId ? `${chatId}:topic:${topicId}` : `${chatId}:${userId}`
  }
  return userId
}
