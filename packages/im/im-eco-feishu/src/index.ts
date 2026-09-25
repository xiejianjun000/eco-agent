// @ts-nocheck
/**
 * @dsh-external/dsh-feishu-gateway — Feishu gateway plugin bundle for DeepSeek
 * Harness. Mounts a long-connection Feishu listener; every Feishu message is
 * routed to a stable DSH session (resume/create via the agents service), and
 * the final assistant text is replied as a Markdown-rich post message. Also
 * provides proactive push and an optional admin HTTP API.
 *
 * Plugin lifecycle: register settings, start the Feishu long connection, start
 * the admin API, and return a disposer that unwinds everything.
 * @module @dsh-external/dsh-feishu-gateway
 */

import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-agent-default-model'
import type {} from '@deepseek-ai/dsh-settings'
import type {} from '@deepseek-ai/dsh-session'
import {
  Config,
  FEISHU_SETTINGS_NAMESPACE,
  resolveConfig,
  type FeishuGatewayConfig,
} from './config.ts'
import { FeishuClient } from './feishu.ts'
import { SessionMap } from './session-map.ts'
import { ChatHandler } from './chat.ts'
import { InteractionService } from './interactions.ts'
import { PushService } from './push.ts'
import { AdminServer } from './server.ts'
import { logger } from './logger.ts'

export const name = '@deepseek-ai/dsh-im-eco-feishu'

export { Config }

export const inject = ['settings', 'agents', 'agentDefaultModel']

/** Plugin entry: register settings, then mount the gateway. */
export async function apply(ctx: Context, config: FeishuGatewayConfig = {}): Promise<() => void> {
  // Fail loud on an invalid stored section before anything mounts.
  const settings = ctx.settings.register(FEISHU_SETTINGS_NAMESPACE, Config, {
    base: config,
    applies: 'live',
    validate: (value) => {
      resolveConfig(value)
    },
  })
  const runtime = settings.get()

  const appId = runtime.feishu?.appId ?? ''
  const appSecret = runtime.feishu?.appSecret ?? ''
  if (!appId || !appSecret) {
    throw new Error('dsh-feishu-gateway: feishu.appId and feishu.appSecret are required (configure via settings: feishu-gateway)')
  }

  const feishu = new FeishuClient({
    appId,
    appSecret,
    domain: runtime.feishu?.domain ?? 'feishu',
  })
  const sessionMap = new SessionMap(runtime.sessionsFile ?? 'data/dsh-feishu-sessions.json')
  const interactions = new InteractionService({ ctx, config: runtime, feishu, sessions: sessionMap })
  const chat = new ChatHandler({ ctx, config: runtime, feishu, sessions: sessionMap, interactions })
  const push = new PushService(feishu)

  // In-conversation Q&A: permission approvals + ask_user_question over cards.
  interactions.registerApprovalAnswerer()
  interactions.registerUserQuestionsProvider()

  // Feishu long connection: receive messages + card button clicks.
  await feishu.startEventSubscription({
    'im.message.receive_v1': chat.handleMessage,
    'card.action.trigger': interactions.handleCardAction,
  })

  // Optional admin HTTP API (health / push / sessions).
  const admin = new AdminServer({
    feishu,
    push,
    sessions: sessionMap,
    port: runtime.http?.port ?? 0,
    token: runtime.http?.token ?? '',
  })
  await admin.start()

  logger.info(
    'feishu-gateway',
    `ready (domain=${runtime.feishu?.domain ?? 'feishu'} replyMode=${runtime.feishu?.replyMode ?? 'at'} workspace=${runtime.workspace ?? ''} adminPort=${runtime.http?.port ?? 0})`,
  )

  return async () => {
    interactions.dispose()
    sessionMap.flush()
    feishu.close()
    await admin.stop().catch(() => undefined)
    logger.info('feishu-gateway', 'disposed')
  }
}
