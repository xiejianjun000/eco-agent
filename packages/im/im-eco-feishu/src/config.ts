// @ts-nocheck
/**
 * Plugin configuration: Feishu app credentials, reply policy, agent workspace,
 * HTTP admin API, and session persistence. Secrets are stored here for
 * simplicity; a DSH Credential reference can be added later.
 * @module dsh-feishu-gateway/config
 */

import z from '@deepseek-ai/schemastery'
import type Schema from '@deepseek-ai/schemastery'
import { settingsNamespace } from '@deepseek-ai/dsh-settings'

/** Settings document namespace owned by this plugin. */
export const FEISHU_SETTINGS_NAMESPACE = settingsNamespace('feishu-gateway')

/** User-facing configuration; every field defaults at the schema boundary. */
export interface FeishuGatewayConfig {
  feishu?: {
    /** Feishu open-platform app id. */
    appId?: string
    /** Feishu open-platform app secret. */
    appSecret?: string
    /** `feishu` (CN) or `lark` (international). */
    domain?: 'feishu' | 'lark'
    /** The bot's own open_id; optional, @ detection works without it. */
    botOpenId?: string
    /** Group reply policy: `at` replies only when mentioned; `all` replies to every message. */
    replyMode?: 'at' | 'all'
  }
  /** Agent working directory (cwd of the DSH session). */
  workspace?: string
  /**
   * The "processing" hint text shown in Feishu while the agent works. Only used
   * as a fallback when the native Typing reaction is disabled (`reporting.typingReaction: false`)
   * or the reaction API fails.
   * @deprecated replaced by the native Typing reaction indicator.
   */
  hintText?: string
  /**
   * Long-task reporting.
   *
   * - `'stream'` (default): a live interactive card streams the agent's progress —
   *   thinking, tool calls, answer draft — patched as the session events arrive,
   *   ending with a summary card plus the final Markdown answer.
   * - `'final'`: only the final answer is sent (plus the Typing reaction), no
   *   streaming card.
   */
  reporting?: {
    /** `'stream'` shows the full streaming thinking process; `'final'` only the result. */
    mode?: 'stream' | 'final'
    /** Show the native Feishu Typing reaction while the answer is being produced. */
    typingReaction?: boolean
    /** Show the model's reasoning (thinking) in the streaming card. */
    showReasoning?: boolean
    /** Show tool-call activity in the streaming card. */
    showToolCalls?: boolean
    /** Minimum interval between card patches (ms); Feishu rate-limits card updates. */
    patchIntervalMs?: number
    /** Max characters rendered in the streaming card body (card payload is size-limited). */
    maxBodyChars?: number
    /** Emoji reaction added on failure instead of Typing (hermes-style). */
    failureReaction?: string
    /** Custom title of the streaming card while the agent is working. */
    cardTitleStreaming?: string
    /** Custom title of the streaming card when the turn completes. */
    cardTitleDone?: string
  }
  /**
   * Interactive card answering for in-conversation Q&A: permission approvals
   * (`approval/request`, e.g. sandbox escalation) and the model's
   * `ask_user_question` tool are answered by clicking Feishu cards.
   */
  interactions?: {
    /** Answer permission-approval requests with Feishu cards (click 允许/拒绝). */
    approvalCards?: boolean
    /** Answer the model's `ask_user_question` tool with Feishu cards (click options). */
    userQuestionsCards?: boolean
    /**
     * What happens to the approval card after the user clicks.
     * - `'update'` (recommended): the click response instantly replaces the
     *   card with a decided state (buttons removed, result shown) + a toast.
     *   Feishu's recall API would leave a "撤回了一条消息" placeholder, so this
     *   is the cleanest available "processed" interaction.
     * - `'recall'`: recall the card message (it disappears behind Feishu's
     *   recall placeholder); falls back to `'update'` when recall fails.
     */
    approvalCardDispose?: 'update' | 'recall'
  }
  /** Regex list that resets the conversation (e.g. `/new`, "另起会话"). */
  newSessionPatterns?: string[]
  /** Persistence file for the Feishu-conversation → DSH-session mapping. */
  sessionsFile?: string
  http?: {
    /** Admin HTTP API port; 0 disables the API. */
    port?: number
    /** Bearer token for the admin API; empty disables auth. */
    token?: string
  }
}

export const Config: Schema<FeishuGatewayConfig> = z.object({
  feishu: z.object({
    appId: z.string().required(),
    appSecret: z.string().required(),
    domain: z.union([z.const('feishu'), z.const('lark')]).default('feishu'),
    botOpenId: z.string().default(''),
    replyMode: z.union([z.const('at'), z.const('all')]).default('at'),
  }),
  // Group-topic and private sessions both anchor to this fixed workspace so
  // the Web UI groups every DSH session created by the gateway.
  workspace: z.string().default('/root/Documents/DSH-Workspace'),
  hintText: z.string().default('爸爸，我正在努力处理中……'),
  reporting: z.object({
    mode: z.union([z.const('stream'), z.const('final')]).default('stream'),
    typingReaction: z.boolean().default(true),
    showReasoning: z.boolean().default(true),
    showToolCalls: z.boolean().default(true),
    patchIntervalMs: z.number().default(1100),
    maxBodyChars: z.number().default(900),
    failureReaction: z.string().default('CrossMark'),
    cardTitleStreaming: z.string().default('🤖 DSH 处理中…'),
    cardTitleDone: z.string().default('🤖 DSH 处理完成'),
  }),
  interactions: z.object({
    approvalCards: z.boolean().default(true),
    userQuestionsCards: z.boolean().default(true),
    approvalCardDispose: z.union([z.const('update'), z.const('recall')]).default('update'),
  }),
  newSessionPatterns: z
    .array(z.string())
    .default(['^/new$', '^(另起|新开|开启|新建)?\\s*(一个)?\\s*(新|全新)?\\s*会话', '^重新开始$', '^换个话题$']),
  sessionsFile: z.string().default('data/dsh-feishu-sessions.json'),
  http: z.object({
    port: z.number().default(0),
    token: z.string().default(''),
  }),
})

/** Resolve the effective runtime config (defaults applied by the schema). */
export function resolveConfig(config: FeishuGatewayConfig = {}): FeishuGatewayConfig {
  return Config(config)
}
