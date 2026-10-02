// @ts-nocheck
import * as http from 'node:http'
import type { FeishuClient } from './feishu.ts'
import { PushService } from './push.ts'
import { SessionMap } from './session-map.ts'
import { logger } from './logger.ts'

/** Optional admin HTTP API: health check, proactive push, session overview. */

export interface AdminServerOptions {
  feishu: FeishuClient
  push: PushService
  sessions: SessionMap
  port: number
  token: string
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = ''
    req.on('data', (chunk) => {
      data += chunk
      if (data.length > 1_000_000) {
        reject(new Error('body too large'))
        req.destroy()
      }
    })
    req.on('end', () => resolve(data))
    req.on('error', reject)
  })
}

function sendJson(res: http.ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
  res.end(JSON.stringify(body))
}

function isAuthorized(req: http.IncomingMessage, token: string): boolean {
  if (!token) return true
  const header = req.headers.authorization ?? ''
  return header === `Bearer ${token}` || header === token
}

export class AdminServer {
  private server: http.Server | null = null
  private readonly startedAt = Date.now()

  constructor(private readonly opts: AdminServerOptions) {}

  async start(): Promise<void> {
    if (this.opts.port <= 0) return
    const { port, token } = this.opts
    this.server = http.createServer(async (req, res) => {
      try {
        await this.route(req, res, token)
      } catch (err) {
        sendJson(res, 500, { ok: false, error: err instanceof Error ? err.message : String(err) })
      }
    })
    await new Promise<void>((resolve, reject) => {
      this.server!.once('error', reject)
      this.server!.listen(port, '0.0.0.0', () => resolve())
    })
    logger.info('server', `admin API listening on :${port}`)
  }

  private async route(req: http.IncomingMessage, res: http.ServerResponse, token: string): Promise<void> {
    const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)

    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, {
        ok: true,
        uptimeSec: Math.floor((Date.now() - this.startedAt) / 1000),
        ws: this.opts.feishu.getWSStatus(),
      })
      return
    }

    if (req.method === 'GET' && url.pathname === '/api/sessions') {
      if (!isAuthorized(req, token)) return sendJson(res, 401, { ok: false, error: 'unauthorized' })
      const sessions = this.opts.sessions.list()
      sendJson(res, 200, { ok: true, count: sessions.length, sessions })
      return
    }

    if (req.method === 'POST' && url.pathname === '/api/push') {
      if (!isAuthorized(req, token)) return sendJson(res, 401, { ok: false, error: 'unauthorized' })
      const body = await readBody(req)
      let payload: {
        receive_id: string
        receive_id_type?: 'open_id' | 'user_id' | 'union_id' | 'email' | 'chat_id'
        msg_type?: 'text' | 'post' | 'interactive' | 'image'
        content: string
      }
      try {
        payload = JSON.parse(body)
      } catch {
        return sendJson(res, 400, { ok: false, error: 'invalid JSON' })
      }
      if (!payload.receive_id || !payload.content) {
        return sendJson(res, 400, { ok: false, error: 'receive_id and content are required' })
      }
      try {
        const messageId = await this.opts.push.pushRaw(
          payload.receive_id,
          payload.msg_type ?? 'text',
          payload.content,
          payload.receive_id_type ?? 'open_id',
        )
        sendJson(res, 200, { ok: true, message_id: messageId })
      } catch (err) {
        sendJson(res, 502, { ok: false, error: err instanceof Error ? err.message : String(err) })
      }
      return
    }

    sendJson(res, 404, { ok: false, error: 'Not Found' })
  }

  async stop(): Promise<void> {
    if (!this.server) return
    await new Promise<void>((resolve, reject) => {
      this.server!.close(err => (err ? reject(err) : resolve()))
    })
    this.server = null
  }
}
