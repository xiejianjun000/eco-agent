// @ts-nocheck
/**
 * In-conversation Q&A over Feishu interactive cards (click to answer).
 *
 * Two DSH capability seams are bridged to Feishu cards:
 *
 * 1. **Permission approvals** — the `approval/request` waterfall (sandbox
 *    escalation, out-of-workspace writes, …). The gateway claims requests that
 *    belong to a Feishu-owned session, pushes an interactive card with
 *    `✅ 允许一次` / `🚫 拒绝` buttons, and resolves the outcome when a button
 *    is clicked (or `'cancelled'` when the ask's signal aborts). Requests for
 *    sessions this gateway does not own are delegated via `next()` so the web
 *    UI (or the fail-closed default) still answers them.
 * 2. **The model's `ask_user_question` tool** — via `ctx.userQuestions`. The
 *    gateway never claims the single UI-provider slot (in a web profile that
 *    slot belongs to the DSH Web UI, and stealing it makes the apiProxy host
 *    fail with `DUPLICATE_PROVIDER`); it wraps `service.ask` at the service
 *    boundary instead: sessions owned by a Feishu conversation are answered
 *    with Feishu cards, every other session continues through the registered
 *    UI provider. Questions with options render clickable option buttons;
 *    option-less questions are answered by replying with text in the chat.
 *    Multi-question requests advance one card per question and settle once the
 *    last question is answered.
 *
 * Card clicks arrive over the same Feishu long connection as
 * `card.action.trigger` and are routed by the opaque `value` carried on the
 * card buttons.
 */

import type { Context } from '@deepseek-ai/cordis'
import type { ApprovalOutcome, ApprovalRequest } from '@deepseek-ai/dsh-user-approval'
import type {
  AskUserQuestionAnswer,
  AskUserQuestionItem,
  AskUserQuestionRequest,
} from '@deepseek-ai/dsh-user-questions'
import type { CardActionEvent, CardActionResponse, CardBody, FeishuClient } from './feishu.ts'
import type { SessionMap } from './session-map.ts'
import type { FeishuGatewayConfig } from './config.ts'
import { logger } from './logger.ts'

/** Opaque card-button payloads (routed back from `card.action.trigger`). */
interface ApprovalCardValue {
  kind: 'approval'
  /** The approval request id (audit pair id). */
  id: string
  /** `true` on the reject button. */
  reject?: boolean
}

interface QuestionCardValue {
  kind: 'question'
  /** The pending-question registry id. */
  id: string
  /** Question index in a multi-question request; absent on pre-bridge cards. */
  index?: number
  /** Selected option label, when clicked from an option button. */
  label?: string
}

type CardValue = ApprovalCardValue | QuestionCardValue

interface PendingApproval {
  id: string
  sessionId: string
  chatId: string
  /** Last user message id in the topic; cards reply into the thread when set. */
  lastUserMessageId?: string
  cardMessageId?: string
  resolve: (outcome: ApprovalOutcome) => void
  onAbort?: () => void
  settled: boolean
}

interface PendingQuestion {
  id: string
  sessionId: string
  chatId: string
  userOpenId: string
  /** Last user message id in the topic; cards reply into the thread when set. */
  lastUserMessageId?: string
  cardMessageId?: string
  questions: AskUserQuestionItem[]
  /** Index of the question the flow is currently asking (0-based). */
  currentIndex: number
  /** Answers collected per question while the card flow advances. */
  drafts: Array<{ selected: string[]; custom?: string }>
  resolve: (answer: AskUserQuestionAnswer) => void
  onAbort?: () => void
  settled: boolean
}

export interface InteractionServiceDeps {
  ctx: Context
  config: FeishuGatewayConfig
  feishu: FeishuClient
  sessions: SessionMap
}

const MAX_LINEAGE_HOPS = 5

export class InteractionService {
  private readonly approvals = new Map<string, PendingApproval>()
  private readonly questions = new Map<string, PendingQuestion>()
  private readonly disposers: Array<() => void> = []

  constructor(private readonly deps: InteractionServiceDeps) {}

  /**
   * Route one `card.action.trigger` (button click) to its pending interaction.
   * Returns the callback response: a toast + the instantly-updated decided card
   * (buttons removed), which Feishu applies within 3s of the click.
   */
  handleCardAction = async (data: CardActionEvent): Promise<CardActionResponse | void> => {
    const value = data.action?.value
    if (typeof value !== 'object' || value === null) return
    const cardValue = value as CardValue
    try {
      if (cardValue.kind === 'approval') {
        return this.settleApproval(data, cardValue)
      }
      if (cardValue.kind === 'question') {
        return this.settleQuestion(data, cardValue)
      }
    } catch (err) {
      logger.error('interactions', 'handle card action error:', err)
      return { toast: { type: 'error', content: '处理失败，请重试' } }
    }
  }

  /**
   * Consume a chat message as the free-text answer of a pending option-less
   * question. Called before routing; returns true when the message was an answer.
   */
  consumeTextAnswer(data: { message: { chat_id: string }; sender?: { sender_id?: { open_id?: string } } }, text: string): boolean {
    const chatId = data.message.chat_id
    const userOpenId = data.sender?.sender_id?.open_id ?? ''
    for (const pending of this.questions.values()) {
      if (pending.settled || pending.chatId !== chatId) continue
      if (pending.userOpenId && userOpenId && pending.userOpenId !== userOpenId) continue
      // Free-text answering applies to the current question only, and only when
      // it is option-less; option questions must be answered by clicking the
      // card buttons.
      const current = pending.questions[pending.currentIndex]
      if (current === undefined || (current.options?.length ?? 0) > 0) continue
      const index = pending.currentIndex
      this.answerCurrentQuestion(pending, { selected: [], custom: text })
      logger.info('interactions', `question ${pending.id} [${index + 1}/${pending.questions.length}] answered by text (${chatId})`)
      return true
    }
    return false
  }

  /** Register the `approval/request` answerer (claims Feishu-owned asks). */
  registerApprovalAnswerer(): void {
    const enabled = this.deps.config.interactions?.approvalCards ?? true
    if (!enabled) return
    const off = this.deps.ctx.on(
      'approval/request',
      (req, next) => this.answerApproval(req, next),
      { prepend: true },
    )
    this.disposers.push(off)
  }

  /**
   * Bridge `ctx.userQuestions` at the service boundary: Feishu-owned sessions
   * answer via Feishu cards, every other session continues through the
   * registered UI provider (the Web UI in a web profile).
   *
   * The gateway deliberately never claims the single provider slot. Cordis
   * activation is dependency-driven, and the gateway's inject deps are all
   * base-bundle services — in a web profile its `apply` runs BEFORE the web
   * api-gateway row, so `registerProvider` would SUCCEED here, silently
   * stealing the slot from the Web UI. The apiProxy host's own
   * `registerProvider` then throws `DUPLICATE_PROVIDER` in its constructor
   * and the whole web tree fails to activate. Wrapping `service.ask` instead
   * works in every activation order and in both the standalone and web
   * profiles, without disturbing the UI provider.
   */
  registerUserQuestionsProvider(): void {
    const enabled = this.deps.config.interactions?.userQuestionsCards ?? true
    if (!enabled) return
    const service = this.deps.ctx.get('userQuestions')
    if (service === undefined) {
      logger.warn('interactions', 'ctx.userQuestions unavailable; Feishu card Q&A disabled')
      return
    }
    const originalAsk = service.ask.bind(service)
    const bridgedAsk = (request: AskUserQuestionRequest): Promise<AskUserQuestionAnswer> => {
      const sessionId = request.agent?.id
      const conv = sessionId === undefined ? undefined : this.resolveConversation(sessionId)
      // Diagnostic: which branch each ask takes and why.
      logger.info(
        'interactions',
        `ask_user_question routed: session=${sessionId ?? '(none)'} feishuConv=${conv === undefined ? 'NO' : 'yes'} → ${sessionId !== undefined && conv !== undefined ? 'feishu-card' : 'delegate-to-UI'}`,
      )
      return sessionId !== undefined && conv !== undefined
        ? this.askUser(request)
        : originalAsk(request)
    }
    const mutableService = service as typeof service & { ask: typeof service.ask }
    mutableService.ask = bridgedAsk
    this.disposers.push(() => {
      if (mutableService.ask === bridgedAsk) mutableService.ask = originalAsk
    })
    logger.info(
      'interactions',
      'ctx.userQuestions bridged at the service boundary (Feishu sessions answer via cards)',
    )
  }

  dispose(): void {
    for (const pending of this.approvals.values()) {
      this.settleApprovalNow(pending, 'cancelled')
    }
    for (const pending of this.questions.values()) {
      pending.settled = true
      pending.onAbort?.()
      // The consumer (tool executor) owns the rejection; settle as empty.
      pending.resolve({ answers: [] })
    }
    for (const off of this.disposers.splice(0)) off()
  }

  // ---------------------------------------------------------------------------
  // Approvals
  // ---------------------------------------------------------------------------

  private answerApproval(
    req: ApprovalRequest,
    next: () => Promise<ApprovalOutcome>,
  ): Promise<ApprovalOutcome> {
    if (req.signal?.aborted === true) return Promise.resolve<ApprovalOutcome>('cancelled')
    const conv = this.resolveConversation(req.agent.session.id)
    if (conv === undefined) return next()
    const id = `appr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
    return new Promise<ApprovalOutcome>((resolve) => {
      const pending: PendingApproval = {
        id,
        sessionId: req.agent.session.id,
        chatId: conv.chatId,
        lastUserMessageId: conv.lastUserMessageId,
        resolve,
        settled: false,
      }
      const onAbort = (): void => {
        this.settleApprovalNow(pending, 'cancelled')
      }
      pending.onAbort = onAbort
      req.signal?.addEventListener('abort', onAbort, { once: true })
      this.approvals.set(id, pending)
      void this.pushApprovalCard(pending, req).catch((err) => {
        logger.error('interactions', 'push approval card failed:', err)
        this.approvals.delete(id)
        req.signal?.removeEventListener('abort', onAbort)
        resolve('unavailable')
      })
    })
  }

  private async pushApprovalCard(pending: PendingApproval, req: ApprovalRequest): Promise<void> {
    const tool = req.toolName || '未知工具'
    const reason = req.reason?.trim()
    const lines = [`**工具**：\`${escapeMd(tool)}\``]
    if (reason) lines.push(`**原因**：${escapeMd(reason)}`)
    const card: CardBody = {
      config: { wide_screen_mode: true },
      header: { title: { tag: 'plain_text', content: '🔐 需要你的授权' }, template: 'orange' },
      elements: [
        { tag: 'div', text: { tag: 'lark_md', content: lines.join('\n') } },
        {
          tag: 'action',
          actions: [
            {
              tag: 'button',
              text: { tag: 'plain_text', content: '✅ 允许一次' },
              type: 'primary',
              value: { kind: 'approval', id: pending.id } satisfies ApprovalCardValue,
            },
            {
              tag: 'button',
              text: { tag: 'plain_text', content: '🚫 拒绝' },
              type: 'danger',
              value: { kind: 'approval', id: pending.id, reject: true } satisfies ApprovalCardValue,
            },
          ],
        },
      ],
    }
    const messageId = await this.deps.feishu.push({
      receiveId: pending.chatId,
      receiveIdType: 'chat_id',
      msgType: 'interactive',
      content: JSON.stringify(card),
    })
    pending.cardMessageId = messageId
    logger.info('interactions', `approval ${pending.id} card pushed → ${pending.chatId}`)
  }

  private settleApproval(data: CardActionEvent, value: ApprovalCardValue): CardActionResponse {
    const pending = this.approvals.get(value.id)
    if (pending === undefined || pending.settled) return {}
    if (data.chatId && pending.chatId && data.chatId !== pending.chatId) return {}
    const outcome: ApprovalOutcome = value.reject === true ? 'rejected' : 'allowed-once'
    const card = this.settleApprovalNow(pending, outcome)
    const toast: CardActionResponse['toast'] =
      outcome === 'allowed-once'
        ? { type: 'success', content: '✅ 已允许（一次性）' }
        : { type: 'info', content: '🚫 已拒绝' }
    // `recall` mode: recall the card message instead of updating it; falls
    // back to the decided-state update when the recall is rejected.
    if (pending.cardMessageId && (this.deps.config.interactions?.approvalCardDispose ?? 'update') === 'recall') {
      void this.recallCard(pending.cardMessageId, card)
      return { toast }
    }
    return { toast, ...card === undefined ? {} : { card: { type: 'raw', data: card } } }
  }

  /**
   * Settle a pending approval. Resolves the outcome, then builds the decided
   * card (buttons removed) and best-effort patches it over REST as a fallback
   * for the response-side update. Returns the decided card for the callback
   * response.
   */
  private settleApprovalNow(pending: PendingApproval, outcome: ApprovalOutcome): CardBody | undefined {
    if (pending.settled) return undefined
    pending.settled = true
    pending.onAbort?.()
    this.approvals.delete(pending.id)
    pending.resolve(outcome)
    const label =
      outcome === 'allowed-once'
        ? '✅ 已允许（一次性）'
        : outcome === 'rejected'
          ? '🚫 已拒绝'
          : '⏹️ 已取消'
    const card = this.buildDecidedCard('🔐 授权', label, outcome === 'allowed-once' ? 'green' : 'red')
    if (pending.cardMessageId) {
      void this.deps.feishu.patchCard(pending.cardMessageId, card).catch(() => undefined)
    }
    logger.info('interactions', `approval ${pending.id} → ${outcome}`)
    return card
  }

  // ---------------------------------------------------------------------------
  // User questions (ask_user_question tool)
  // ---------------------------------------------------------------------------

  private askUser(request: AskUserQuestionRequest): Promise<AskUserQuestionAnswer> {
    const sessionId = request.agent?.id
    if (sessionId === undefined) {
      return Promise.reject(new Error('Feishu user interaction requires an agent-owned session'))
    }
    const conv = this.resolveConversation(sessionId)
    if (conv === undefined) {
      return Promise.reject(new Error('no Feishu conversation for session; cannot answer ask_user_question'))
    }
    const id = `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
    return new Promise<AskUserQuestionAnswer>((resolve, reject) => {
      const pending: PendingQuestion = {
        id,
        sessionId,
        chatId: conv.chatId,
        userOpenId: conv.userOpenId,
        lastUserMessageId: conv.lastUserMessageId,
        questions: request.questions,
        currentIndex: 0,
        drafts: request.questions.map(() => ({ selected: [] })),
        resolve,
        settled: false,
      }
      const onAbort = (): void => {
        if (pending.settled) return
        pending.settled = true
        this.questions.delete(id)
        reject(new Error('ask_user_question was aborted before the user answered'))
      }
      pending.onAbort = onAbort
      request.signal?.addEventListener('abort', onAbort, { once: true })
      this.questions.set(id, pending)
      void this.pushQuestionCard(pending).catch((err) => {
        logger.error('interactions', 'push question card failed:', err)
        if (pending.settled) return
        pending.settled = true
        this.questions.delete(id)
        request.signal?.removeEventListener('abort', onAbort)
        reject(err instanceof Error ? err : new Error(String(err)))
      })
    })
  }

  private async pushQuestionCard(pending: PendingQuestion, index = 0): Promise<void> {
    const question = pending.questions[index]
    if (question === undefined) return
    const options = question.options ?? []
    const lines: string[] = []
    if (question.header) lines.push(`**${escapeMd(question.header)}**`)
    lines.push(escapeMd(question.question ?? '请回答：'))
    if (question.detail) lines.push(`> ${escapeMd(question.detail)}`)
    const elements: NonNullable<CardBody['elements']> = [
      { tag: 'div', text: { tag: 'lark_md', content: lines.join('\n\n') } },
    ]
    if (options.length > 0) {
      elements.push({
        tag: 'action',
        actions: options.map((option, optionIndex) => ({
          tag: 'button',
          text: { tag: 'plain_text', content: truncate(option.label, 24) },
          type: optionIndex === 0 ? 'primary' : 'default',
          value: { kind: 'question', id: pending.id, index, label: option.label } satisfies QuestionCardValue,
        })),
      })
      if (question.multiSelect === true) {
        elements.push({ tag: 'note', elements: [{ tag: 'plain_text', content: '多选问题：点击任意选项即提交该选项。' }] })
      }
    } else {
      elements.push({ tag: 'note', elements: [{ tag: 'plain_text', content: '请在对话中直接回复消息作答。' }] })
    }
    const card: CardBody = {
      config: { wide_screen_mode: true },
      header: { title: { tag: 'plain_text', content: '❓ 需要你的回答' }, template: 'blue' },
      elements,
    }
    // Reply into the topic when possible so the question stays in the same
    // Feishu thread as the conversation; otherwise push to the chat.
    const messageId = pending.lastUserMessageId
      ? await this.deps.feishu.replyCard(pending.lastUserMessageId, card)
      : await this.deps.feishu.push({
        receiveId: pending.chatId,
        receiveIdType: 'chat_id',
        msgType: 'interactive',
        content: JSON.stringify(card),
      })
    pending.cardMessageId = messageId
    logger.info('interactions', `question ${pending.id} card pushed → ${pending.chatId}`)
  }

  private settleQuestion(data: CardActionEvent, value: QuestionCardValue): CardActionResponse {
    const pending = this.questions.get(value.id)
    if (pending === undefined || pending.settled) return {}
    if (data.chatId && pending.chatId && data.chatId !== pending.chatId) return {}
    // Cards carry the index of the question they were pushed for; a click on an
    // already-answered card (the flow advanced past it) is stale and ignored.
    const index = value.index ?? pending.currentIndex
    if (index !== pending.currentIndex) return {}
    if (value.label === undefined) return {}
    const more = pending.currentIndex < pending.questions.length - 1
    const card = this.answerCurrentQuestion(pending, { selected: [value.label] })
    logger.info('interactions', `question ${pending.id} [${index + 1}/${pending.questions.length}] answered by card click: ${value.label}`)
    return {
      toast: {
        type: 'success',
        content: more
          ? `✅ 已选择：${truncate(value.label, 16)}，请回答下一题`
          : `✅ 已选择：${truncate(value.label, 20)}`,
      },
      ...card === undefined ? {} : { card: { type: 'raw', data: card } },
    }
  }

  /**
   * Record the answer to the question at `pending.currentIndex`, then either
   * advance to the next question (patch the answered card to its decided state
   * and push the next question's card) or settle the whole request when the
   * last question was answered. Returns the decided card for the answered
   * question so the click/text response can apply it instantly.
   */
  private answerCurrentQuestion(
    pending: PendingQuestion,
    answer: { selected: string[]; custom?: string },
  ): CardBody | undefined {
    const draft = pending.drafts[pending.currentIndex] ??= { selected: [] }
    draft.selected = answer.selected
    if (answer.custom !== undefined) draft.custom = answer.custom
    const label = draft.selected.length > 0 ? draft.selected.join('、') : (draft.custom ?? '已作答')
    const decided = this.buildDecidedCard('❓ 问答', `你的选择：**${truncate(escapeMd(label), 60)}**`, 'green')
    const answers = (): AskUserQuestionAnswer => ({
      answers: pending.drafts.map((d, i) => ({
        id: pending.questions[i].id,
        selected: d.selected,
        custom: d.custom,
      })),
    })
    if (pending.currentIndex < pending.questions.length - 1) {
      if (pending.cardMessageId) {
        void this.deps.feishu.patchCard(pending.cardMessageId, decided).catch(() => undefined)
      }
      pending.currentIndex += 1
      void this.pushQuestionCard(pending, pending.currentIndex).catch((err) => {
        logger.error('interactions', 'push next question card failed:', err)
        // Never leave the tool call hanging: settle with the answers collected
        // so far (unanswered questions come back empty).
        this.settleQuestionNow(pending, answers())
      })
    } else {
      this.settleQuestionNow(pending, answers())
    }
    return decided
  }

  private settleQuestionNow(pending: PendingQuestion, answer: AskUserQuestionAnswer): CardBody | undefined {
    if (pending.settled) return undefined
    pending.settled = true
    pending.onAbort?.()
    this.questions.delete(pending.id)
    pending.resolve(answer)
    // Multi-question flows settle on the last card, so show the last answer.
    const last = answer.answers[answer.answers.length - 1]
    const selected = last?.selected ?? []
    const label = selected.length > 0 ? selected.join('、') : (last?.custom ?? '已作答')
    const card = this.buildDecidedCard('❓ 问答', `你的选择：**${truncate(escapeMd(label), 60)}**`, 'green')
    if (pending.cardMessageId) {
      void this.deps.feishu.patchCard(pending.cardMessageId, card).catch(() => undefined)
    }
    return card
  }

  // ---------------------------------------------------------------------------
  // Shared helpers
  // ---------------------------------------------------------------------------

  /** Resolve the Feishu conversation for a session (bounded lineage walk). */
  private resolveConversation(sessionId: string) {
    const direct = this.deps.sessions.infoForSession(sessionId)
    if (direct !== undefined) return direct
    // Walk parent lineage (subagent sessions ask on behalf of the Feishu root).
    const store = this.deps.ctx.get('sessions') as
      | { get(id: unknown): { header: { parentSession?: unknown } } | undefined }
      | undefined
    if (store === undefined) {
      logger.warn('interactions', `resolveConversation(${sessionId}): direct map miss and ctx.sessions unavailable — cannot answer as Feishu`)
      return undefined
    }
    let cursor: string | undefined = sessionId
    for (let hop = 0; hop < MAX_LINEAGE_HOPS && cursor !== undefined; hop += 1) {
      const current: { header: { parentSession?: unknown } } | undefined = store?.get(cursor)
      if (current === undefined) break
      const parentValue: unknown = current.header.parentSession
      if (parentValue === undefined) break
      const parentId: string = String(parentValue)
      const conv = this.deps.sessions.infoForSession(parentId)
      if (conv !== undefined) return conv
      cursor = parentId
    }
    logger.warn('interactions', `resolveConversation(${sessionId}): not a Feishu-owned session (direct+lineage miss, store=${store !== undefined})`)
    return undefined
  }

  /**
   * Build the decided card for a settled interaction: buttons removed, the
   * outcome shown, and a "processed" note — Feishu's card schema has no button
   * `disabled` state, so this IS the "grayed-out" interaction.
   */
  private buildDecidedCard(title: string, body: string, template: 'green' | 'red'): CardBody {
    return {
      config: { wide_screen_mode: true },
      header: { title: { tag: 'plain_text', content: title }, template },
      elements: [
        { tag: 'div', text: { tag: 'lark_md', content: body } },
        { tag: 'note', elements: [{ tag: 'plain_text', content: '该卡片已处理，无需再次操作。' }] },
      ],
    }
  }

  /** `recall` mode: delete the card message; fall back to the decided patch. */
  private async recallCard(cardMessageId: string, fallbackCard?: CardBody): Promise<void> {
    const deleted = await this.deps.feishu.deleteMessage(cardMessageId)
    if (!deleted && fallbackCard !== undefined) {
      await this.deps.feishu.patchCard(cardMessageId, fallbackCard).catch(() => undefined)
    }
  }
}

/** Escape `lark_md`-sensitive characters in user/agent-supplied text. */
function escapeMd(text: string): string {
  return text.replace(/([\\`*_~\[\]])/g, '\\$1')
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`
}
