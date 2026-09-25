// @ts-nocheck
import { FeishuClient } from './feishu.ts'
import type { CardBody, MessageType, ReceiveIdType } from './feishu.ts'
import { logger } from './logger.ts'

/**
 * Proactive push service: push messages to Feishu users/groups at any time
 * (scheduled tasks, monitoring alerts, external webhook callbacks).
 */
export class PushService {
  constructor(private readonly feishu: FeishuClient) {}

  /** Push a plain-text message. */
  async pushText(
    receiveId: string,
    text: string,
    receiveIdType: ReceiveIdType = 'open_id',
    uuid?: string,
  ): Promise<string> {
    const messageId = await this.feishu.push({
      receiveId,
      receiveIdType,
      msgType: 'text',
      content: JSON.stringify({ text }),
      uuid,
    })
    logger.info('push', `text → ${receiveIdType}=${receiveId}: ${text.slice(0, 60)}`)
    return messageId
  }

  /** Push a Markdown-rich post message (renders bold/code/lists/links). */
  async pushMarkdown(
    receiveId: string,
    text: string,
    receiveIdType: ReceiveIdType = 'open_id',
    uuid?: string,
  ): Promise<string> {
    const chunks = splitForPush(text)
    let last = ''
    for (const chunk of chunks) {
      last = await this.feishu.push({
        receiveId,
        receiveIdType,
        msgType: 'post',
        content: JSON.stringify({ zh_cn: { title: '', content: [[{ tag: 'md', text: chunk }]] } }),
        uuid,
      })
    }
    return last
  }

  /** Push a card message. */
  async pushCard(
    receiveId: string,
    card: CardBody,
    receiveIdType: ReceiveIdType = 'open_id',
    uuid?: string,
  ): Promise<string> {
    const messageId = await this.feishu.push({
      receiveId,
      receiveIdType,
      msgType: 'interactive',
      content: JSON.stringify(card),
      uuid,
    })
    return messageId
  }

  /** Push with an explicit msg_type / content. */
  async pushRaw(
    receiveId: string,
    msgType: MessageType,
    content: string,
    receiveIdType: ReceiveIdType = 'open_id',
    uuid?: string,
  ): Promise<string> {
    return this.feishu.push({ receiveId, receiveIdType, msgType, content, uuid })
  }
}

function splitForPush(text: string, maxLen = 1800): string[] {
  if (text.length <= maxLen) return [text]
  const chunks: string[] = []
  let rest = text
  while (rest.length > maxLen) {
    let cut = rest.slice(0, maxLen).lastIndexOf('\n')
    if (cut <= 0) cut = maxLen
    chunks.push(rest.slice(0, cut).trimEnd())
    rest = rest.slice(cut).trimStart()
  }
  if (rest) chunks.push(rest)
  return chunks
}
