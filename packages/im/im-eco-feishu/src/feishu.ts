// @ts-nocheck
import * as lark from '@larksuiteoapi/node-sdk'
import { logger } from './logger.ts'

/**
 * Feishu client wrapper: long-connection event subscription (WSClient +
 * EventDispatcher), message replies (text / Markdown post), and proactive push.
 */

export interface FeishuClientOptions {
  appId: string
  appSecret: string
  domain: 'feishu' | 'lark'
  verificationToken?: string
  encryptKey?: string
}

/** Lark API response shape. */
interface LarkResponse<T = unknown> {
  code?: number
  msg?: string
  data?: T
}

export interface CardBody {
  config?: { streaming_mode?: boolean; update_multi?: boolean; wide_screen_mode?: boolean }
  header?: {
    title: { tag: 'plain_text'; content: string }
    template?: string
  }
  elements: Array<{
    tag: string
    content?: string
    [k: string]: unknown
  }>
}

/**
 * `card.action.trigger` callback response (returned over the long connection).
 * Feishu honors this within 3s of the click: `toast` shows a client toast and
 * `card` instantly replaces the card content (方式一: immediate update). The
 * card schema has no button `disabled` state, so "disabling" the buttons means
 * replacing the card with a decided state that has no actions.
 */
export interface CardActionResponse {
  toast?: { type: 'info' | 'success' | 'error' | 'warning'; content: string }
  card?: { type: 'raw'; data: CardBody }
}

export type MessageType = 'text' | 'post' | 'interactive' | 'image' | 'file' | 'audio' | 'media'
export type ReceiveIdType = 'open_id' | 'user_id' | 'union_id' | 'email' | 'chat_id'

export interface PushOptions {
  receiveId: string
  receiveIdType: ReceiveIdType
  msgType: MessageType
  content: string
  uuid?: string
}

/** Feishu im.message.receive_v1 event (relevant fields). */
export interface FeishuMessageEvent {
  event_id?: string
  sender: {
    sender_id?: { union_id?: string; user_id?: string; open_id?: string }
    sender_type: string
  }
  message: {
    message_id: string
    create_time: string
    chat_id: string
    chat_type: string // "p2p" | "group"
    message_type: string // "text" | "post" | ...
    content: string // JSON string
    root_id?: string // top-level message id when this message is a reply in a thread
    thread_id?: string // the Feishu topic/thread id, if the message lives in one
    mentions?: Array<{
      key: string
      id: { union_id?: string; user_id?: string; open_id?: string }
      mentioned_type?: string
      name: string
      tenant_key?: string
    }>
  }
}

export class FeishuClient {
  readonly client: lark.Client
  private wsClient: lark.WSClient | null = null

  constructor(private readonly opts: FeishuClientOptions) {
    this.client = new lark.Client({
      appId: opts.appId,
      appSecret: opts.appSecret,
      domain: opts.domain === 'lark' ? lark.Domain.Lark : lark.Domain.Feishu,
      loggerLevel: lark.LoggerLevel.info,
    })
  }

  /** Start the long-connection event subscription. */
  async startEventSubscription(handlers: {
    'im.message.receive_v1'?: (data: FeishuMessageEvent) => Promise<void> | void
    /**
     * Interactive card button clicks (`card.action.trigger`), delivered over the
     * same long connection. `value` carries the opaque payload the card buttons
     * were built with (e.g. the approval / question id). Return a
     * {@link CardActionResponse} to show a toast and/or instantly update the card.
     */
    'card.action.trigger'?: (
      data: CardActionEvent,
    ) => Promise<CardActionResponse | void> | CardActionResponse | void
    [eventName: string]: ((data: any) => Promise<unknown> | unknown) | undefined
  }): Promise<void> {
    const dispatcherHandlers: Record<string, ((data: any) => Promise<unknown> | unknown) | undefined> = { ...handlers }
    if (handlers['card.action.trigger'] !== undefined) {
      dispatcherHandlers['card.action.trigger'] = (raw: Record<string, unknown>) =>
        handlers['card.action.trigger']!(normalizeCardAction(raw))
    }
    const dispatcher = new lark.EventDispatcher({
      verificationToken: this.opts.verificationToken || undefined,
      encryptKey: this.opts.encryptKey || undefined,
    }).register(dispatcherHandlers)

    this.wsClient = new lark.WSClient({
      appId: this.opts.appId,
      appSecret: this.opts.appSecret,
      domain: this.opts.domain === 'lark' ? lark.Domain.Lark : lark.Domain.Feishu,
      loggerLevel: lark.LoggerLevel.info,
      autoReconnect: true,
      handshakeTimeoutMs: 30_000,
    })
    await this.wsClient.start({ eventDispatcher: dispatcher })
    logger.info('feishu', 'long-connection event subscription started')
  }

  getWSStatus(): { state: string; reconnectAttempts: number } {
    if (!this.wsClient) return { state: 'idle', reconnectAttempts: 0 }
    const s = this.wsClient.getConnectionStatus()
    return { state: s.state, reconnectAttempts: s.reconnectAttempts }
  }

  close(): void {
    if (this.wsClient) {
      try {
        this.wsClient.close()
      } catch (err) {
        logger.warn('feishu', 'close ws error:', err)
      }
      this.wsClient = null
    }
  }

  /** Cached bot open_id (used for @-mention detection). */
  private botOpenIdCache: string | undefined

  /**
   * Resolve the bot's own open_id via `/open-apis/bot/v3/info`. Cached after
   * the first successful call. Returns undefined on failure so callers fall
   * back to other mention-detection strategies.
   */
  async getBotOpenId(): Promise<string | undefined> {
    if (this.botOpenIdCache) return this.botOpenIdCache
    try {
      const res = await this.client.request({ url: '/open-apis/bot/v3/info', method: 'GET' } as never) as { bot?: { open_id?: string } } | undefined
      const openId = res?.bot?.open_id
      if (openId) {
        this.botOpenIdCache = openId
        return openId
      }
    } catch (err) {
      logger.warn('feishu', 'getBotOpenId failed:', err)
    }
    return undefined
  }

  /** Reply with a plain-text message. */
  async replyText(messageId: string, text: string, replyInThread = false): Promise<void> {
    await this.reply(messageId, 'text', JSON.stringify({ text }), replyInThread)
  }

  /** Reply with an interactive card; returns the created card message id. */
  async replyCard(messageId: string, card: CardBody, replyInThread = false): Promise<string> {
    return this.reply(messageId, 'interactive', JSON.stringify(card), replyInThread)
  }

  /**
   * Reply with a Markdown-rich post message (md tag): Feishu renders bold /
   * inline code / lists / links without using cards. Long text is chunked
   * (≤1800 chars per md paragraph, ≤10 paragraphs per message).
   */
  async replyMarkdown(messageId: string, text: string, replyInThread = false): Promise<void> {
    const chunks = splitMarkdown(text, 1800)
    const MAX_CHUNKS_PER_MSG = 10
    for (let i = 0; i < chunks.length; i += MAX_CHUNKS_PER_MSG) {
      const batch = chunks.slice(i, i + MAX_CHUNKS_PER_MSG)
      const content = JSON.stringify({
        zh_cn: {
          title: '',
          content: batch.map(c => [{ tag: 'md', text: c }]),
        },
      })
      await this.reply(messageId, 'post', content, replyInThread)
    }
  }

  /** Reply with an arbitrary message type; returns the created message id. */
  async reply(messageId: string, msgType: MessageType, content: string, replyInThread = false): Promise<string> {
    const res = await this.client.im.message.reply({
      path: { message_id: messageId },
      data: { msg_type: msgType, content, ...(replyInThread ? { reply_in_thread: true } : {}) },
    })
    this.assertOk(res, 'reply')
    return res.data?.message_id ?? ''
  }

  /** Proactively push a message to a user/group. */
  async push(opts: PushOptions): Promise<string> {
    const res = await this.client.im.message.create({
      params: { receive_id_type: opts.receiveIdType },
      data: {
        receive_id: opts.receiveId,
        msg_type: opts.msgType,
        content: opts.content,
        ...(opts.uuid ? { uuid: opts.uuid } : {}),
      },
    })
    this.assertOk(res, 'push')
    return res.data?.message_id ?? ''
  }

  /** Update an already-sent card message (used for streaming replies). */
  async patchCard(messageId: string, card: CardBody): Promise<void> {
    const res = await this.client.im.message.patch({
      path: { message_id: messageId },
      data: { content: JSON.stringify(card) },
    })
    this.assertOk(res, 'patchCard')
  }

  /**
   * Recall (delete) a message this bot sent. NOTE: Feishu shows a
   * "撤回了一条消息" placeholder at the original position — this is not a clean
   * disappearance. Best-effort; returns false when the recall is rejected.
   */
  async deleteMessage(messageId: string): Promise<boolean> {
    try {
      const res = await this.client.im.message.delete({
        path: { message_id: messageId },
      })
      this.assertOk(res, 'deleteMessage')
      return true
    } catch (err) {
      logger.warn('feishu', `deleteMessage ${messageId} failed:`, err)
      return false
    }
  }

  /**
   * Add an emoji reaction to a message (native "typing" indicator while the
   * answer is being produced — hermes-style). Returns the reaction id needed
   * to remove it later, or undefined on failure.
   */
  async addReaction(messageId: string, emojiType: string): Promise<string | undefined> {
    try {
      const res = await this.client.im.messageReaction.create({
        path: { message_id: messageId },
        data: { reaction_type: { emoji_type: emojiType } },
      })
      this.assertOk(res, 'addReaction')
      return res.data?.reaction_id
    } catch (err) {
      logger.warn('feishu', `addReaction ${emojiType} on ${messageId} failed:`, err)
      return undefined
    }
  }

  /** Remove an emoji reaction added by this bot (best-effort). */
  async removeReaction(messageId: string, reactionId: string): Promise<boolean> {
    try {
      const res = await this.client.im.messageReaction.delete({
        path: { message_id: messageId, reaction_id: reactionId },
      })
      this.assertOk(res, 'removeReaction')
      return true
    } catch (err) {
      logger.warn('feishu', `removeReaction ${reactionId} on ${messageId} failed:`, err)
      return false
    }
  }

  private assertOk(res: LarkResponse, scope: string): void {
    if (res.code !== undefined && res.code !== 0) {
      throw new Error(`Feishu API error [${scope}]: code=${res.code}, msg=${res.msg}`)
    }
  }
}

/** `card.action.trigger` payload over the long connection (raw shape). */
export interface CardActionEvent {
  /** Raw event payload; message/chat ids may nest under `context` (v2). */
  raw?: Record<string, unknown>
  /** The card message id (`context.open_message_id` / top-level `open_message_id`). */
  messageId?: string
  /** The chat the card lives in (`context.open_chat_id` / top-level `open_chat_id`). */
  chatId?: string
  /** The operator (clicker) identity. */
  operator?: { openId?: string; userId?: string; name?: string }
  /** The clicked element: `value` carries the payload the card buttons carried. */
  action?: { value?: unknown; tag?: string; name?: string; option?: string }
  /** Feishu's dedup token for this click. */
  token?: string
}

/** Normalize a raw `card.action.trigger` payload into {@link CardActionEvent}. */
export function normalizeCardAction(data: Record<string, unknown>): CardActionEvent {
  const context = (typeof data.context === 'object' && data.context !== null ? data.context : {}) as Record<string, unknown>
  const operator = (typeof data.operator === 'object' && data.operator !== null ? data.operator : {}) as Record<string, unknown>
  const action = (typeof data.action === 'object' && data.action !== null ? data.action : {}) as Record<string, unknown>
  return {
    raw: data,
    messageId: String(context.open_message_id ?? data.open_message_id ?? '') || undefined,
    chatId: String(context.open_chat_id ?? data.open_chat_id ?? '') || undefined,
    operator: {
      openId: String(operator.open_id ?? '') || undefined,
      userId: String(operator.user_id ?? '') || undefined,
      name: String(operator.name ?? '') || undefined,
    },
    action: {
      value: action.value,
      tag: typeof action.tag === 'string' ? action.tag : undefined,
      name: typeof action.name === 'string' ? action.name : undefined,
      option: typeof action.option === 'string' ? action.option : undefined,
    },
    token: typeof data.token === 'string' ? data.token : undefined,
  }
}

/**
 * Split long text into Markdown chunks: prefer line breaks; never split a ```
 * fenced code block.
 */
export function splitMarkdown(text: string, maxLen: number): string[] {
  if (!text) return ['']
  if (text.length <= maxLen) return [text]

  const chunks: string[] = []
  let rest = text
  while (rest.length > maxLen) {
    const window = rest.slice(0, maxLen)
    let cut = window.lastIndexOf('\n')
    if (cut <= 0) cut = maxLen
    const fences = (rest.slice(0, Math.min(rest.length, maxLen + 3)).match(/```/g) ?? []).length
    if (fences % 2 === 1) {
      const fenceEnd = rest.indexOf('```', 3)
      if (fenceEnd > 0 && fenceEnd < rest.length) cut = fenceEnd + 3
    }
    chunks.push(rest.slice(0, cut).trimEnd())
    rest = rest.slice(cut).trimStart()
  }
  if (rest) chunks.push(rest)
  return chunks
}
