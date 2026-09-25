// @ts-nocheck
// dsh-wechat-bridge — DSH 微信桥接插件
//
// 把手机微信（腾讯 iLink / ClawBot 官方开放协议）连接到 DeepSeek Harness 的
// AI 助手：微信收到文字/语音消息 → 交给 DSH Agent → 把回复流式发回微信。
//
// 设计原则（对照《安全铁律》与合规要求）：
//   1. 只做消息中转 —— 插件本身不执行任何来自微信内容的系统命令、不代开链接。
//   2. 白名单 —— allowFrom 只允许名单内的联系人（默认全开，建议收紧）。
//   3. 纯链接消息默认拦截，不送入 AI。
//   4. 本文件为原创实现；微信协议走腾讯官方开放的 iLink Bot API，
//      底层使用 MIT 许可的独立开源客户端 wechat-ilink-client（见 THIRD_PARTY_NOTICES.md）。

import { randomUUID, createHash, randomBytes } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync, statSync, readdirSync, renameSync, copyFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, basename, isAbsolute, resolve, sep } from 'node:path'
import { spawn } from 'node:child_process'
import z from '@deepseek-ai/schemastery'
import { installModelSelection } from '@deepseek-ai/dsh-agent'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import { resolveDshHome } from '@deepseek-ai/dsh-home-paths'
import qrcode from 'qrcode'
import { WeChatClient, MessageType, MessageItemType, TypingStatus, UploadMediaType, encryptAesEcb, aesEcbPaddedSize, buildCdnUploadUrl } from 'wechat-ilink-client'
import { parseCron, nextCronAfter, safeSendCut, createStreamSanitizer, createWeChatMarkdownRenderer, fmtTokens } from './pure.ts'

// 兼容导出：集成测试与外部消费者仍从插件入口导入这些纯函数
export { parseCron, nextCronAfter, safeSendCut, createStreamSanitizer, createWeChatMarkdownRenderer, fmtTokens }

export const name = 'wechat-bridge'
// 本 Cordis 分支对 ctx 属性访问是严格模式：用到的服务必须声明在 inject 里
// （timer 用于 ctx.setInterval 的 fiber 级定时器；tools 用于注册微信专属工具）
export const inject = ['agents', 'sessions', 'timer', 'tools', 'settings']

/** 插件配置（可在 DSH 设置界面或 cordis.patch.yml 中调整）。 */
export const Config = z.object({
  enabled: z.boolean().default(false).description('启用微信桥接（关闭后不登录、不收发消息）。'),
  token: z.string().default('').description('已有 iLink Bot Token（留空则用扫码登录，推荐）。'),
  accountId: z.string().default('').description('已有 iLink 账号 ID（与 token 配套，留空自动读取）。'),
  baseUrl: z.string().default('https://ilinkai.weixin.qq.com').description('iLink 服务地址。'),
  allowFrom: z.array(z.string()).default(['*']).description('消息白名单（iLink 用户 ID；"*" 表示所有人）。'),
  admins: z.array(z.string()).default([]).description('管理员列表（iLink 用户 ID）：可执行 /new /stop /status 等控制命令；为空则所有人可执行。'),
  workDir: z.string().default('').description('AI 工作目录（留空则用 DSH 当前工作区）。'),
  blockLinks: z.boolean().default(true).description('拦截纯链接消息，不送入 AI（安全铁律）。'),
  streaming: z.boolean().default(true).description('边生成边分段发送回复（关闭则整段完成后发送）。'),
  idleTimeoutMins: z.number().default(60).description('空闲多少分钟后自动结束本次会话（0 = 永不）。'),
  maxReplyChars: z.number().default(1500).description('单条微信回复的最大字符数，超出自动分段。'),
  loginCooldownSecs: z.number().default(30).description('登录失败 / 凭证过期后，重试前的等待秒数。'),
  singleton: z.boolean().default(true).description('多实例互斥：同一时间只允许一个桥接实例运行（防止双实例抢消息）。'),
  typing: z.boolean().default(true).description('思考时向微信发送"正在输入…"状态提示。'),
  waitNoteSecs: z.number().default(10).description('AI 思考超过该秒数仍无输出时，主动发一条"正在处理"提示（0=关闭）。'),
  outbox: z.boolean().default(true).description('文件回传：AI 把文件保存到工作目录 wechat-outbox/<联系人>/ 后自动发送到微信。'),
  wechatMarkdown: z.boolean().default(true).description('把回复里的 Markdown（加粗/表格/引用/列表/链接）转成微信友好的纯文本。'),
  groups: z.boolean().default(true).description('处理群聊消息（开启后仅响应 @机器人 的消息）。'),
  groupRequireMention: z.boolean().default(true).description('群聊仅当消息 @机器人 时才响应（关闭则响应群内所有文字消息）。'),
  pollWatchdogSecs: z.number().default(90).description('长轮询静默超过该秒数判定假死，自动重启监听（0=关闭）。'),
  usageFooter: z.boolean().default(true).description('每轮 AI 回复末尾附上模型与用量统计（严格对齐 GUI 格式：模型 · out · in cw cr · ctx% 路径）。'),
  usageFooterPath: z.string().default('~/.dsh-wechat-bridge').description('用量尾注末尾的路径标签。'),
})

const DEFAULT_BASE_URL = 'https://ilinkai.weixin.qq.com'
const TICK_MS = 350          // 流式缓冲的节拍
const FLUSH_IDLE_MS = 450    // 距上次发送超过该时长即发送缓冲
const FLUSH_SIZE = 240       // 缓冲超过该字数即发送
const SEEN_CAP = 1000        // 去重集合上限
const MAX_LOG_BYTES = 2 * 1024 * 1024
const OVERRIDE_FILENAME = 'override.json'   // 运行时覆盖配置（白名单/管理员，热加载）
const CHAT_INDEX_FILENAME = 'chats.json'    // 联系人 → 会话 ID 索引（重启恢复用）
const OVERRIDE_CHECK_MS = 5000              // override.json 热加载检查间隔
const CHAT_INDEX_TTL_MS = 30 * 24 * 3600 * 1000  // 索引条目 30 天未活跃则清理

/** 读取 UTF-8 JSON（容忍 BOM：用户可能用记事本等工具编辑过状态/覆盖文件）。 */
function readJsonFile(path) {
  const raw = readFileSync(path, 'utf8')
  return JSON.parse(raw.charCodeAt(0) === 0xFEFF ? raw.slice(1) : raw)
}

/** 运行时覆盖配置：避开 DSH patch 重载缺陷，白名单/管理员可热调整。 */
function loadOverride(stateDir) {
  try {
    const parsed = readJsonFile(join(stateDir, OVERRIDE_FILENAME))
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
  } catch { /* 无覆盖文件 */ }
  return {}
}

/** 联系人 → 会话 ID 的持久索引（重启后恢复上下文）。 */
function loadChatIndex(stateDir) {
  try {
    const parsed = readJsonFile(join(stateDir, CHAT_INDEX_FILENAME))
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
  } catch { /* 首次运行 */ }
  return {}
}

function saveChatIndex(stateDir, index) {
  try {
    if (!existsSync(stateDir)) mkdirSync(stateDir, { recursive: true })
    writeFileSync(join(stateDir, CHAT_INDEX_FILENAME), JSON.stringify(index, null, 2))
  } catch { /* 索引写失败不致命，仅失去重启恢复能力 */ }
}

/** 简单文件日志（桌面应用里控制台不可见，落盘方便排查）。 */
export function makeFileLogger(stateDir) {
  const file = join(stateDir, 'bridge.log')
  const write = (level, ...parts) => {
    try {
      if (!existsSync(stateDir)) mkdirSync(stateDir, { recursive: true })
      let body
      try { body = readFileSync(file, 'utf8') } catch { body = '' }
      const line = `[${new Date().toISOString()}] [${level}] ${parts.map(p => typeof p === 'string' ? p : String(p)).join(' ')}\n`
      if (Buffer.byteLength(body) > MAX_LOG_BYTES) body = body.slice(body.length / 2)
      writeFileSync(file, body + line)
    } catch { /* 日志失败不影响主流程 */ }
  }
  return {
    info: (...p) => write('info', ...p),
    warn: (...p) => write('warn', ...p),
    error: (...p) => write('error', ...p),
  }
}

/** 把 ctx.logger 与文件日志合并，两边各写一份。 */
export function makeLogger(ctx, stateDir) {
  const file = makeFileLogger(stateDir)
  const mirror = (method, ...parts) => {
    const text = parts.map(p => (p instanceof Error ? `${p.message}` : String(p))).join(' ')
    try { ctx.logger?.[method]?.(`[wechat-bridge] ${text}`) } catch { /* ignore */ }
    file[method]?.(text)
  }
  return {
    info: (...p) => mirror('info', ...p),
    warn: (...p) => mirror('warn', ...p),
    error: (...p) => mirror('error', ...p),
  }
}

/** 状态文件：凭证、长轮询游标、最后登录时间。 */
function loadState(stateDir) {
  const file = join(stateDir, 'state.json')
  try {
    const parsed = readJsonFile(file)
    if (parsed && typeof parsed === 'object' && parsed.version === 1) return parsed
  } catch { /* 首次运行 */ }
  return { version: 1, credentials: null, syncBuf: '', lastLoginAt: 0 }
}

function saveState(stateDir, state) {
  try {
    if (!existsSync(stateDir)) mkdirSync(stateDir, { recursive: true })
    writeFileSync(join(stateDir, 'state.json'), JSON.stringify(state, null, 2))
  } catch (error) {
    // 写状态失败不致命，但会导致每次重启都要重新扫码
    console.error(`[wechat-bridge] 状态写入失败: ${error?.message ?? error}`)
  }
}

/** 把二维码内容渲染成 HTML 页面（页面自带自动刷新），按需在默认浏览器打开。
 *  内容可能是微信 liteapp 链接（用本地编码器生成二维码图）、图片 URL 或 base64。 */
async function renderQrPage(stateDir, log, qrContent, openInBrowser = true) {
  try {
    if (!existsSync(stateDir)) mkdirSync(stateDir, { recursive: true })
    let src = qrContent
    if (/^https?:\/\//i.test(qrContent)) {
      // 微信登录链接：本地生成二维码图片，手机微信扫码即可打开
      src = await qrcode.toDataURL(qrContent, { margin: 1, width: 320 })
    } else if (!/^data:image\//i.test(qrContent)) {
      // 假设是 base64 编码的图片内容
      src = `data:image/png;base64,${qrContent}`
    }
    const raw = String(qrContent).replace(/</g, '&lt;')
    const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="refresh" content="4"><title>DSH 微信桥接 - 扫码登录</title>
<style>
body{font-family:"Microsoft YaHei",sans-serif;background:#111;color:#eee;display:flex;
flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;}
h1{font-size:22px;font-weight:normal;margin:0 0 8px;}
p{color:#aaa;font-size:14px;margin:0 0 20px;text-align:center;line-height:1.8;}
img{width:300px;height:300px;background:#fff;border-radius:8px;padding:8px;}
a{color:#6af;word-break:break-all;max-width:640px;font-size:12px;margin-top:20px;text-align:center;}
</style></head><body>
<h1>DSH 微信桥接 · 扫码登录</h1>
<p>用手机微信扫描下方二维码（或把下方链接发到手机后点开）确认授权。<br>二维码约 60 秒过期，本页面每 4 秒自动刷新；扫码成功后即可关闭。</p>
<img src="${src}" alt="登录二维码">
<a href="${raw}">${raw}</a>
</body></html>`
    const file = join(stateDir, 'login.html')
    writeFileSync(file, html)
    if (openInBrowser) {
      if (process.platform === 'win32') {
        spawn('cmd', ['/c', 'start', '', file], { detached: true, stdio: 'ignore', windowsHide: true }).unref()
      } else if (process.platform === 'darwin') {
        // macOS 没有 xdg-open；用 `open` 打开浏览器（否则 spawn 抛 ENOENT 崩溃进程）。
        spawn('open', [file], { detached: true, stdio: 'ignore' }).unref()
      } else {
        spawn('xdg-open', [file], { detached: true, stdio: 'ignore' }).unref()
      }
      log.info(`二维码页面已生成并尝试在浏览器打开：${file}`)
    } else {
      log.info('二维码已刷新（已打开的登录页会自动更新，无需重新打开）。')
    }
  } catch (error) {
    log.warn(`二维码页面生成失败，可复制下方原始链接到手机打开：\n${String(qrContent).slice(0, 500)}`)
  }
}

/** 提取一条 iLink 消息里的可用文字（文字消息或语音转写）。 */
function extractUsableText(msg) {
  const direct = WeChatClient.extractText(msg)
  if (direct && direct.trim()) return direct.trim()
  for (const item of msg.item_list ?? []) {
    if (item.type === MessageItemType.VOICE && item.voice_item?.text && item.voice_item.text.trim()) {
      return item.voice_item.text.trim()
    }
  }
  return ''
}

/** 消息是否含有媒体（图片/文件/视频），用于给出不支持提示。 */
function hasMediaItem(msg) {
  return (msg.item_list ?? []).some(item =>
    item.type === MessageItemType.IMAGE ||
    item.type === MessageItemType.FILE ||
    item.type === MessageItemType.VIDEO)
}

/** 消息中的图片条目。 */
function imageItems(msg) {
  return (msg.item_list ?? []).filter(item => item.type === MessageItemType.IMAGE)
}

/** 消息中的文件条目。 */
function fileItems(msg) {
  return (msg.item_list ?? []).filter(item => item.type === MessageItemType.FILE)
}

/** 清洗文件名：去掉路径分隔与非法字符，防路径穿越。 */
function sanitizeFileName(name) {
  const base = String(name ?? '').replace(/[\\/:*?"<>|\r\n\t]/g, '_').trim()
  const cleaned = base.replace(/^\.+/, '')
  return cleaned.slice(0, 120) || 'file'
}

/** 工具注册要求的 output 声明：把 { content:[{type:'text',text}] } 渲染为模型可见文本。 */
function textToolOutput() {
  return {
    schema: {
      type: 'object',
      properties: { content: { type: 'array', items: {} } },
      required: ['content'],
      additionalProperties: false,
    },
    render(_args, value) {
      const text = (value?.content ?? [])
        .map(block => (typeof block?.text === 'string' ? block.text : ''))
        .join('')
        .trim()
      return [{ type: 'text', text: text || '(无输出)' }]
    },
  }
}

/** 按文件头魔数推断图片扩展名。 */
function guessImageExtension(data) {
  if (!data || data.length < 4) return '.jpg'
  if (data[0] === 0xff && data[1] === 0xd8) return '.jpg'
  if (data[0] === 0x89 && data[1] === 0x50 && data[2] === 0x4e && data[3] === 0x47) return '.png'
  if (data[0] === 0x52 && data[1] === 0x49 && data[2] === 0x46 && data[3] === 0x46) return '.webp'
  if (data[0] === 0x47 && data[1] === 0x49 && data[2] === 0x46) return '.gif'
  return '.jpg'
}

/** 定时任务最近触发时间（重启后不重复触发同一分钟）。 */
function loadJobState(stateDir) {
  try {
    const parsed = readJsonFile(join(stateDir, 'jobs-state.json'))
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
  } catch { /* 首次运行 */ }
  return {}
}

function saveJobState(stateDir, state) {
  try {
    if (!existsSync(stateDir)) mkdirSync(stateDir, { recursive: true })
    writeFileSync(join(stateDir, 'jobs-state.json'), JSON.stringify(state, null, 2))
  } catch { /* 忽略 */ }
}

const URL_ONLY = /^\s*(https?:\/\/\S+)(\s+https?:\/\/\S+)*\s*$/i

/** 默认微信客户端实现（测试可整体替换）。 */
let defaultClientFactory = WeChatClient

/** 测试专用：替换默认微信客户端实现（集成测试注入 FakeClient）。 */
export function setClientFactoryForTests(factory) {
  defaultClientFactory = factory
}

function truncate(text, max) {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1)}…`
}

const HELP_TEXT = `【DSH 微信助手】使用说明：
• 直接发消息，AI 会处理并流式回复
• /new    开始新会话（清空上下文）
• /stop   停止当前任务
• /status 查看当前状态
• /help   显示本说明
安全提示：纯链接消息默认不处理；机器人只做消息中转。
控制命令（/new /stop /status）仅管理员可用。`

/** 把一段文本按 maxChars 切块（尽量在换行处断开）。 */
function splitForSend(text, maxChars) {
  if (text.length <= maxChars) return [text]
  const parts = []
  let rest = text
  while (rest.length > maxChars) {
    let cut = rest.lastIndexOf('\n', maxChars)
    if (cut <= 0) cut = maxChars
    parts.push(rest.slice(0, cut))
    rest = rest.slice(cut).replace(/^\n+/, '')
  }
  if (rest) parts.push(rest)
  return parts
}

/**
 * 桥接主类：管理凭证、长轮询、每个联系人的 Agent 会话与流式回传。
 * clientFactory 供测试注入模拟微信客户端（默认使用真实 wechat-ilink-client）。
 */
export class WeChatBridge {
  constructor(ctx, config, log, clientFactory = defaultClientFactory) {
    this.ctx = ctx
    this.config = config
    this.log = log ?? makeLogger(ctx, join(resolveDshHome(), 'wechat-bridge'))
    this.clientFactory = clientFactory
    this.stateDir = join(resolveDshHome(), 'wechat-bridge')
    this.state = loadState(this.stateDir)
    this.chats = new Map()       // key -> chat 记录
    this.seen = new Set()        // 已处理消息 id
    this.client = null
    this.phase = 'idle'          // idle | login | running
    this.disposed = false
    this.ticker = null
    this.monitorTask = null
    this.retryTimer = null
    this.lastPollAt = 0          // 最近一次长轮询 poll 事件时间（假死看门狗用）
    this.attachedClients = new WeakSet()
    this.lockPath = join(this.stateDir, 'bridge.lock')
    this.lockOwned = false
    this.lastLockBeat = 0
    // v3：运行时覆盖配置 + 会话索引（重启恢复）
    this.override = loadOverride(this.stateDir)
    this.overrideMtime = 0
    this.lastOverrideCheck = 0
    this.chatIndex = loadChatIndex(this.stateDir)
    // v4：定时任务
    this.jobState = loadJobState(this.stateDir)
    this.jobRuntime = new Map()
    this.jobsBoundTo = null
    this.lastOutboxScan = 0
    this.toolDisposers = []    // 本插件注册的 ctx.tools 工具的注销函数
    this.sendFailures = new Map() // outbox 发送失败计数（连续失败上限防刷屏）
  }

  /** 某联系人的文件回传目录（AI 把文件存这里即自动发送）。 */
  outboxDirFor(key) {
    return join(this.resolveWorkDir(), 'wechat-outbox', String(key).replace(/[^A-Za-z0-9._-]/g, '_'))
  }

  /** 在 Agent 的作用域内注册文件回传说明（仅该 Agent 可见）。 */
  setupAgentScope(agentCtx, chatKey) {
    if (this.config.outbox === false) return
    try {
      const systemPrompt = agentCtx.get('systemPrompt')
      const dir = this.outboxDirFor(chatKey)
      // 禁用 shell 工具：微信对话没有命令执行环境，bash 空命令会超时卡住。
      // 从源头移除，比 prompt 提示更可靠（AI 仍可能调用 bash 导致 60s 超时）。
      // 用 agentCtx.tools（scope-aware）而非 get('tools')（host 单例，restrict 会抛 scope 错误）。
      const tools = agentCtx.tools
      if (tools?.restrict) {
        tools.restrict({ deny: ['bash', 'pwsh'] })
      }
      systemPrompt?.section({
        name: 'wechat-no-shell',
        order: 390,
        text: '[微信环境限制] 微信对话没有可用的 shell 执行环境（bash/pwsh 命令会超时卡住）。查询生态环境数据直接用 mcp__eco-matrix-remote__* 工具，工具返回的数据已足够回答，不要再用 shell 命令做二次处理或验证。',
      })
      systemPrompt?.section({
        name: 'wechat-outbox',
        order: 400,
        text: `[微信文件回传] 用户向你要"文件"（HTML 报告、文档、表格、数据文件等）时，用工具 wechat_send_file（直接写入文件内容）或 wechat_send_local_file（发送工作目录里已有的文件）交付，文件会自动发送到用户微信，不要只把文件内容当文本贴在聊天里。也可以直接把文件保存到目录：${dir}，同样会自动发送。`,
      })
    } catch { /* 注册失败不影响主流程 */ }
  }

  /** 由工具调用方（Agent）定位对应的微信会话对象。 */
  chatForCaller(agent) {
    const sessionId = String(agent?.session?.id ?? '')
    if (!sessionId) return null
    for (const chat of this.chats.values()) {
      if (!chat.tornDown && chat.sessionId != null && String(chat.sessionId) === sessionId) return chat
    }
    return null
  }

  /** 把文本内容写入联系人的 outbox 目录（随后由 scanOutboxes 自动发送）。 */
  async deliverFile(chat, filename, content) {
    const dir = this.outboxDirFor(chat.key)
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
    const name = sanitizeFileName(filename)
    const file = join(dir, `wechat-send-${Date.now()}-${name}`)
    writeFileSync(file, String(content ?? ''), 'utf8')
    this.log.info(`工具 wechat_send_file 已写入：${file}`)
    return { file, name }
  }

  /** 把工作目录内的本地文件加入联系人的 outbox 队列（随后自动发送）。 */
  async deliverLocalFile(chat, pathText) {
    const workDir = resolve(this.resolveWorkDir())
    const target = resolve(isAbsolute(pathText) ? pathText : join(workDir, pathText))
    // 安全边界：只允许发送工作目录内的文件（防外发工作区外的任意文件）
    if (target !== workDir && !target.startsWith(workDir + sep)) {
      throw new Error('只允许发送工作目录内的文件。')
    }
    if (!existsSync(target) || !statSync(target).isFile()) throw new Error('文件不存在或不是普通文件。')
    const dir = this.outboxDirFor(chat.key)
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
    const name = sanitizeFileName(basename(target))
    const file = join(dir, `wechat-send-${Date.now()}-${name}`)
    copyFileSync(target, file)
    this.log.info(`工具 wechat_send_local_file 已入队：${file}`)
    return { file, name }
  }

  /** 注册微信桥接专属工具（全局注册，不依赖 Agent 预设组合，微信侧智能体必然可见）。 */
  registerTools(ctx) {
    if (!ctx?.tools?.register) return
    const mkDisposer = (def) => {
      try { return ctx.tools.register(def) } catch (error) {
        this.log.warn(`工具注册失败（${def.name}）：${error?.message ?? error}`)
        return null
      }
    }
    const d1 = mkDisposer({
      name: 'wechat_send_file',
      description: '把内容保存为文件并自动发送到当前微信用户（微信桥接专用）。当用户要求"生成/给我一个文件、报告、文档、HTML、表格、数据文件"时，优先调用本工具直接交付文件，而不是把内容当文本贴在聊天里。',
      parameters: {
        type: 'object',
        properties: {
          filename: { type: 'string', description: '文件名（含扩展名，如 report.html、数据表.csv）' },
          content: { type: 'string', description: '文件完整内容（UTF-8 文本）。二进制文件请改用 wechat_send_local_file。' },
        },
        required: ['filename', 'content'],
        additionalProperties: false,
      },
      output: textToolOutput(),
      execute: async (args, exec) => {
        const chat = this.chatForCaller(exec?.agent)
        if (!chat) throw new Error('当前会话未关联微信联系人，无法发送文件。')
        const done = await this.deliverFile(chat, String(args?.filename ?? 'file.txt'), String(args?.content ?? ''))
        return { content: [{ type: 'text', text: `已把「${done.name}」写入微信回传队列，稍后会自动发送到用户微信。` }] }
      },
    })
    if (d1) this.toolDisposers.push(d1)
    const d2 = mkDisposer({
      name: 'wechat_send_local_file',
      description: '把工作目录里已有的本地文件（图片、PDF、Office、压缩包等）发送到当前微信用户（微信桥接专用）。',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: '文件路径（绝对路径，或相对工作目录的路径）' },
        },
        required: ['path'],
        additionalProperties: false,
      },
      output: textToolOutput(),
      execute: async (args, exec) => {
        const chat = this.chatForCaller(exec?.agent)
        if (!chat) throw new Error('当前会话未关联微信联系人，无法发送文件。')
        const done = await this.deliverLocalFile(chat, String(args?.path ?? ''))
        return { content: [{ type: 'text', text: `已把「${done.name}」加入微信回传队列，稍后会自动发送到用户微信。` }] }
      },
    })
    if (d2) this.toolDisposers.push(d2)
    this.log.info(`已注册微信专属工具：${this.toolDisposers.length} 个（wechat_send_file / wechat_send_local_file）。`)
  }

  /**
   * 上传本地文件到微信 CDN（AES-128-ECB 加密）。
   * 兼容 getUploadUrl 的两种响应：新版 `upload_full_url`（预签名完整地址）与
   * 旧版 `upload_param`+filekey。下载参数取自 CDN 响应头 `x-encrypted-param`。
   * （wechat-ilink-client@0.1.0 只认旧字段，服务端已切新字段，故在此自实现上传段。）
   */
  async uploadToWeChatCdn(filePath, toUserId, mediaType = UploadMediaType.FILE) {
    // 大小上限：50MB 以上文件不做内存整读，直接拒绝（微信文件消息一般远小于此）
    const fileStat = statSync(filePath)
    if (fileStat.size > 50 * 1024 * 1024) {
      throw new Error(`文件 ${basename(filePath)} 超过 50MB，暂不支持回传。`)
    }
    const plaintext = readFileSync(filePath)
    const rawsize = plaintext.length
    const rawfilemd5 = createHash('md5').update(plaintext).digest('hex')
    const filesize = aesEcbPaddedSize(rawsize)
    const filekey = randomBytes(16).toString('hex')
    const aeskey = randomBytes(16)
    const resp = await this.client.api.getUploadUrl({
      filekey,
      media_type: mediaType,
      to_user_id: toUserId,
      rawsize,
      rawfilemd5,
      filesize,
      no_need_thumb: true,
      aeskey: aeskey.toString('hex'),
    })
    const fullUrl = String(resp?.upload_full_url ?? '').trim()
    const cdnUrl = fullUrl || (resp?.upload_param
      ? buildCdnUploadUrl({ cdnBaseUrl: this.client.api.cdnBaseUrl, uploadParam: resp.upload_param, filekey })
      : '')
    if (!cdnUrl) throw new Error(`getUploadUrl 未返回可用上传地址：${JSON.stringify(resp).slice(0, 200)}`)
    const ciphertext = encryptAesEcb(plaintext, aeskey)
    let downloadParam = ''
    let lastError = null
    for (let attempt = 1; attempt <= 3 && !downloadParam; attempt++) {
      try {
        let res
        if (typeof this.client.uploadCdn === 'function') {
          // 测试注入口：模拟 CDN 上传（集成测试用 FakeClient）
          const fake = await this.client.uploadCdn(cdnUrl, ciphertext)
          downloadParam = fake?.downloadParam ?? ''
        } else {
          res = await fetch(cdnUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: new Uint8Array(ciphertext),
          })
          if (!res.ok) throw new Error(`CDN 上传失败（HTTP ${res.status}）`)
          downloadParam = res.headers.get('x-encrypted-param') ?? ''
        }
        if (!downloadParam && attempt < 3) { lastError = new Error('CDN 响应缺少 x-encrypted-param'); await this.sleep(1000) }
      } catch (error) {
        lastError = error
        if (attempt < 3) await this.sleep(1000)
      }
    }
    if (!downloadParam) throw lastError ?? new Error('CDN 上传失败')
    return {
      filekey,
      downloadEncryptedQueryParam: downloadParam,
      aeskey: aeskey.toString('hex'),
      fileSize: rawsize,
      fileSizeCiphertext: filesize,
    }
  }

  /** 扫描各会话的 outbox 目录，把新文件发到微信并移入 sent/。 */
  async scanOutboxes() {
    if (!this.client || this.phase !== 'running') return
    for (const chat of this.chats.values()) {
      const dir = this.outboxDirFor(chat.key)
      let entries = []
      try { entries = readdirSync(dir, { withFileTypes: true }) } catch { continue }
      for (const entry of entries) {
        if (!entry.isFile()) continue
        const file = join(dir, entry.name)
        const sentDir = join(dir, 'sent')
        try {
          if (!existsSync(sentDir)) mkdirSync(sentDir, { recursive: true })
          const isImage = /\.(png|jpe?g|gif|webp|bmp)$/i.test(entry.name)
          const uploaded = await this.uploadToWeChatCdn(file, chat.to, isImage ? UploadMediaType.IMAGE : UploadMediaType.FILE)
          // 发给微信时去掉内部前缀（wechat-send-<时间戳>-），保留原始文件名
          const displayName = entry.name.replace(/^wechat-send-\d+-/, '') || entry.name
          if (isImage) {
            await this.client.sendUploadedImage(chat.to, uploaded, undefined, chat.contextToken || '')
          } else {
            await this.client.sendUploadedFile(chat.to, displayName, uploaded, undefined, chat.contextToken || '')
          }
          renameSync(file, join(sentDir, entry.name))
          this.sendFailures.delete(file)
          this.log.info(`已回传文件（${chat.isGroup ? `群 ${chat.to}` : `联系人 ${chat.to}`}）：${entry.name}`)
        } catch (error) {
          // 连续失败上限：避免每 2 秒重试刷屏；超过 5 次移入 failed/ 停止重试
          this.sendFailures ??= new Map()
          const fails = (this.sendFailures.get(file) ?? 0) + 1
          this.sendFailures.set(file, fails)
          if (fails >= 5) {
            this.sendFailures.delete(file)
            const failedDir = join(dir, 'failed')
            try {
              if (!existsSync(failedDir)) mkdirSync(failedDir, { recursive: true })
              renameSync(file, join(failedDir, entry.name))
              this.log.warn(`文件回传连续失败 ${fails} 次，已移入 failed/：${entry.name}`)
            } catch { /* 移动失败忽略 */ }
          } else {
            this.log.warn(`文件回传失败（${entry.name}，第 ${fails} 次）：${error?.message ?? error}`)
          }
        }
      }
    }
  }

  /** 生效的消息白名单（override.json 优先于 patch 配置）。 */
  effectiveAllowFrom() {
    if (Array.isArray(this.override.allowFrom) && this.override.allowFrom.length > 0) return this.override.allowFrom
    return this.config.allowFrom ?? ['*']
  }

  /** 生效的管理员列表（override.json 优先）。 */
  effectiveAdmins() {
    if (Array.isArray(this.override.admins)) return this.override.admins
    return this.config.admins ?? []
  }

  /** 检查并热加载 override.json（约 5 秒一次，按 mtime 判断变化）。 */
  refreshOverride() {
    const now = Date.now()
    if (now - this.lastOverrideCheck < OVERRIDE_CHECK_MS) return
    this.lastOverrideCheck = now
    try {
      const path = join(this.stateDir, OVERRIDE_FILENAME)
      if (!existsSync(path)) {
        // 文件被删除：回退到 patch 配置
        if (this.overrideMtime !== 0 || Object.keys(this.override).length > 0) {
          this.overrideMtime = 0
          this.override = {}
          this.log.info('override.json 已移除，恢复使用 patch 配置。')
        }
        return
      }
      const mtime = statSync(path).mtimeMs
      if (mtime === this.overrideMtime) return
      this.overrideMtime = mtime
      const next = loadOverride(this.stateDir)
      this.override = next
      this.log.info(`已热加载 override.json：allowFrom=${JSON.stringify(this.effectiveAllowFrom())}，admins=${JSON.stringify(this.effectiveAdmins())}，jobs=${(Array.isArray(next.jobs) ? next.jobs : []).length} 个。`)
    } catch { /* 读取失败保留旧值 */ }
  }

  /** 定时任务配置（override.json 热加载）。 */
  effectiveJobs() {
    return Array.isArray(this.override.jobs) ? this.override.jobs : []
  }

  /** 定时任务运行态同步（override 变化后重建）。 */
  syncJobs() {
    if (this.jobsBoundTo === this.override) return
    this.jobsBoundTo = this.override
    this.jobRuntime = new Map()
    for (const job of this.effectiveJobs()) {
      if (!job || typeof job !== 'object' || typeof job.cron !== 'string' || typeof job.prompt !== 'string') {
        this.log.warn(`定时任务配置无效（缺少 cron/prompt）：${JSON.stringify(job)}`)
        continue
      }
      const parsed = parseCron(job.cron)
      if (!parsed) {
        this.log.warn(`定时任务 cron 表达式无效：${job.cron}`)
        continue
      }
      const id = job.id ?? `job-${this.jobRuntime.size}`
      // 修复：首次加载（无历史记录）不立即补跑，从"下一次 cron 时刻"开始
      const lastRun = this.jobState[id] ?? Date.now()
      const nextRun = nextCronAfter(parsed, lastRun)
      this.jobRuntime.set(id, { job, parsed, nextRun })
    }
  }

  /** 检查并触发到期的定时任务。 */
  checkJobs(now) {
    this.syncJobs()
    if (this.jobRuntime.size === 0) return
    for (const [id, entry] of this.jobRuntime) {
      if (entry.nextRun == null || now < entry.nextRun) continue
      this.jobState[id] = now
      saveJobState(this.stateDir, this.jobState)
      entry.nextRun = nextCronAfter(entry.parsed, now)
      this.fireJob(id, entry.job).catch(error => this.log.error(`定时任务执行异常（${id}）：${error?.stack ?? error?.message ?? error}`))
    }
  }

  /** 执行一个定时任务：给目标联系人派活（回复经正常流式链路回传）。 */
  async fireJob(id, job) {
    const to = job.to
    if (!to) {
      this.log.warn(`定时任务 ${id} 缺少目标联系人（to），跳过。`)
      return
    }
    // 安全：任务目标必须是管理员（防止配置被篡改后骚扰他人）
    const admins = this.effectiveAdmins()
    if (admins.length > 0 && !admins.includes(to)) {
      this.log.warn(`定时任务 ${id} 的目标 ${to} 不是管理员，已拒绝。`)
      return
    }
    if (!this.client || this.phase !== 'running') {
      this.log.warn(`定时任务 ${id} 触发时客户端未就绪，跳过本次。`)
      return
    }
    const key = `u:${to}`
    const chat = this.ensureChat(key, to)
    try {
      await this.ensureAgentFor(chat)
    } catch (error) {
      this.log.error(`定时任务 ${id} 创建/恢复 Agent 失败：${error?.message ?? error}`)
      return
    }
    // 任务推送前先点亮"正在输入…"，让用户有感知
    this.setTyping(chat, true).catch(() => {})
    chat.agent.followup(createUserMessage({
      content: [{ type: 'text', text: `[定时任务] ${job.prompt}` }],
      source: { kind: 'user' },
    }))
    this.log.info(`定时任务 ${id} 已触发：给 ${to} 派活「${truncate(job.prompt, 40)}」。`)
  }

  /** 目标 PID 是否存活（跨实例/跨进程锁检测）。 */
  static pidAlive(pid) {
    if (!Number.isInteger(pid) || pid <= 0) return false
    try { process.kill(pid, 0); return true } catch { return false }
  }

  /** 抢占单例锁：已有一个健康实例在跑时返回 false。 */
  acquireSingleton() {
    try {
      if (!existsSync(this.stateDir)) mkdirSync(this.stateDir, { recursive: true })
      const lock = readJsonFile(this.lockPath)
      if (lock && typeof lock === 'object') {
        const fresh = Date.now() - (lock.heartbeat ?? 0) < 90000
        if (WeChatBridge.pidAlive(lock.pid) && fresh) return false
      }
    } catch { /* 无锁或锁损坏 → 抢占 */ }
    return this.writeLock()
  }

  /** 写入/刷新锁。 */
  writeLock() {
    try {
      if (!existsSync(this.stateDir)) mkdirSync(this.stateDir, { recursive: true })
      writeFileSync(this.lockPath, JSON.stringify({ pid: process.pid, startedAt: Date.now(), heartbeat: Date.now() }))
      return true
    } catch {
      return true // 锁写不了也继续运行（单机场景）
    }
  }

  /** 释放锁（仅当锁属于自己）。 */
  releaseSingleton() {
    if (!this.lockOwned) return
    this.lockOwned = false
    try { unlinkSync(this.lockPath) } catch { /* 忽略 */ }
  }

  /** 绑定入站消息/错误/过期事件（每个 client 只绑定一次）。 */
  attachListeners(client) {
    if (this.attachedClients.has(client)) return
    this.attachedClients.add(client)
    client.on('message', (msg) => { this.onMessage(msg).catch(e => this.log.error(`消息处理异常：${e?.message ?? e}`)) })
    client.on('error', e => this.log.warn(`iLink 客户端错误：${e?.message ?? e}`))
    client.on('poll', () => { this.lastPollAt = Date.now() })
    client.on('sessionExpired', () => {
      this.log.warn('凭证已过期，稍后自动重新扫码。')
      try { client.stop() } catch { /* 已停止则忽略 */ }
      this.state.credentials = null
      saveState(this.stateDir, this.state)
      this.client = null
      this.phase = 'login'
    })
  }

  /** 决定当前应使用的凭证：配置 > 已保存状态。 */
  currentCredentials() {
    if (this.config.token) {
      return {
        token: this.config.token,
        accountId: this.config.accountId || this.state.credentials?.accountId || '',
        baseUrl: this.config.baseUrl || DEFAULT_BASE_URL,
      }
    }
    return this.state.credentials
  }

  /** 计算 Agent 工作目录：配置 > DSH 工作区 > 用户主目录。 */
  resolveWorkDir() {
    if (this.config.workDir) return this.config.workDir
    try {
      const registry = this.ctx.get('workspaceRegistry')
      const first = registry?.list?.()[0]
      const path = first?.path ?? first?.record?.path
      if (path) return path
    } catch { /* 忽略 */ }
    return homedir()
  }

  /** 启动：有凭证直接进入运行态，否则走扫码登录。 */
  async start() {
    // 单例互斥：发现另一个健康实例时自动停用（防止双实例抢消息、回复交错）
    if (this.config.singleton !== false) {
      this.lockOwned = this.acquireSingleton()
      if (!this.lockOwned) {
        this.log.warn('检测到另一个微信桥接实例正在运行（bridge.lock），本实例自动停用。')
        this.disposed = true
        return
      }
      this.lastLockBeat = Date.now()
    }
    // 优先使用 Cordis 的 ctx.setInterval（随 fiber 自动清理），否则退回全局定时器
    if (typeof this.ctx.setInterval === 'function') {
      this.ticker = this.ctx.setInterval(() => this.tick(), TICK_MS)
    } else {
      this.ticker = setInterval(() => this.tick(), TICK_MS)
      this.ticker.unref?.()
    }
    const creds = this.currentCredentials()
    if (creds?.token) {
      this.log.info(`使用已有凭证启动（账号 ${creds.accountId || '未知'}）。`)
      this.phase = 'running'
      this.lastPollAt = Date.now()
    } else {
      this.log.info('未找到凭证，进入扫码登录流程。')
      this.phase = 'login'
    }
    this.monitorTask = this.monitorLoop().catch(error => this.log.error(`运行循环异常：${error?.message ?? error}`))
  }

  /** 扫码登录：生成二维码页面 → 轮询确认 → 保存凭证。 */
  async loginFlow() {
    const baseUrl = this.config.baseUrl || DEFAULT_BASE_URL
    const loginClient = new this.clientFactory({ baseUrl })
    // 每次登录尝试只在首个二维码时弹浏览器；后续刷新只更新页面内容（页面自带自动刷新）
    let opened = false
    const result = await loginClient.login({
      timeoutMs: 8 * 60 * 1000,
      onQRCode: async (qr) => {
        await renderQrPage(this.stateDir, this.log, qr, !opened)
        opened = true
      },
      onStatus: status => this.log.info(`扫码状态：${status}`),
    })
    if (!result.connected) throw new Error(result.message || '扫码登录未完成')
    this.state.credentials = {
      token: result.botToken,
      accountId: result.accountId ?? '',
      baseUrl: result.baseUrl || baseUrl,
      userId: result.userId ?? '',
    }
    this.state.lastLoginAt = Date.now()
    saveState(this.stateDir, this.state)
    this.log.info(`扫码登录成功：账号 ${this.state.credentials.accountId || '未知'}，扫码人 ${result.userId || '未知'}（可加入 allowFrom 白名单）。`)
    const client = new this.clientFactory({
      token: result.botToken,
      accountId: result.accountId ?? '',
      baseUrl: result.baseUrl || baseUrl,
    })
    this.attachListeners(client)
    return client
  }

  /** 主循环：登录（如需）→ 长轮询监听，失败按冷却时间重试。 */
  async monitorLoop() {
    while (!this.disposed) {
      if (this.phase === 'running') {
        if (!this.client) {
          // 凭证还在但 client 没建（例如过期重登后）
          const creds = this.currentCredentials()
          if (creds?.token) {
            this.client = new this.clientFactory({
              token: creds.token,
              accountId: creds.accountId || '',
              baseUrl: creds.baseUrl || this.config.baseUrl || DEFAULT_BASE_URL,
            })
            this.attachListeners(this.client)
          } else {
            this.phase = 'login'
            continue
          }
        }
        const client = this.client
        try {
          this.log.info('开始接收微信消息…')
          await client.start({
            longPollTimeoutMs: 25000,
            loadSyncBuf: () => this.state.syncBuf || '',
            saveSyncBuf: (buf) => {
              this.state.syncBuf = buf
              saveState(this.stateDir, this.state)
            },
          })
        } catch (error) {
          this.log.warn(`长轮询中断：${error?.message ?? error}`)
        }
        if (this.disposed) return
        if (this.phase === 'running') {
          // 意外中断且凭证仍在：冷却后重连
          await this.sleep(this.config.loginCooldownSecs * 1000)
        }
        continue
      }
      // phase === 'login'
      try {
        this.log.info('开始扫码登录（二维码页面即将打开）…')
        this.client = await this.loginFlow()
        this.phase = 'running'
      } catch (error) {
        this.log.warn(`登录失败：${error?.message ?? error}，${this.config.loginCooldownSecs} 秒后重试。`)
        await this.sleep(this.config.loginCooldownSecs * 1000)
      }
    }
  }

  sleep(ms) {
    return new Promise((resolve) => {
      this.retryTimer = setTimeout(resolve, ms)
    })
  }

  /** 入站消息统一入口（EventEmitter 回调，异步执行）。 */
  async onMessage(msg) {
    if (this.disposed || !msg || msg.message_type !== MessageType.USER) return
    const isGroup = Boolean(msg.group_id)
    if (isGroup && !this.config.groups) {
      // 群聊功能关闭：只记日志，避免在群里刷屏
      this.log.info(`收到群消息（群聊功能未开启，已忽略）：group=${msg.group_id}`)
      return
    }
    const userId = msg.from_user_id
    if (!userId) return

    // 白名单按发送者校验（群里每个成员都按自己的身份过滤）
    const allow = this.effectiveAllowFrom()
    if (!allow.includes('*') && !allow.includes(userId)) {
      this.log.info(`非白名单联系人消息已忽略：${userId}`)
      return
    }

    // 去重（同一消息可能被长轮询重复投递）
    const dedupeKey = msg.message_id ?? `${userId}:${msg.create_time_ms ?? 0}:${msg.item_list?.length ?? 0}`
    if (dedupeKey != null && this.seen.has(dedupeKey)) return
    this.seen.add(dedupeKey)
    if (this.seen.size > SEEN_CAP) {
      const it = this.seen.values().next().value
      if (it !== undefined) this.seen.delete(it)
    }

    const text = extractUsableText(msg)
    if (isGroup) {
      // 群聊：仅响应 @机器人 的消息。协议 @ 格式未公开，先按账号 ID/本地名/"@" 开头
      // 匹配，并记诊断日志（含原始字段），实测后可据此修正。
      this.log.info(`群消息诊断：group=${msg.group_id} from=${userId} to=${msg.to_user_id ?? '?'} 内容=${truncate(text.replace(/\n/g, ' '), 60)}`)
      if (!this.isGroupMentioned(text)) return
      if (this.config.blockLinks && text && URL_ONLY.test(text.trim())) {
        this.log.info(`已拦截群内纯链接消息（group=${msg.group_id} from=${userId}）。`)
        return
      }
    }

    const key = isGroup ? `g:${msg.group_id}` : `u:${userId}`
    const chat = this.ensureChat(key, isGroup ? msg.group_id : userId)
    chat.isGroup = isGroup
    chat.from = userId
    chat.contextToken = msg.context_token ?? chat.contextToken
    chat.lastActive = Date.now()
    // 即时反馈：消息一收到就点亮微信"正在输入…"（群聊无此能力，跳过）
    if (!isGroup) this.setTyping(chat, true).catch(() => {})
    // 持久化上下文令牌：重启后定时任务才能主动发消息
    // （首条消息时索引可能还没有条目，先建再写）
    const indexEntry = this.chatIndex[key] ?? (this.chatIndex[key] = {})
    if (msg.context_token && indexEntry.contextToken !== msg.context_token) {
      indexEntry.contextToken = msg.context_token
      indexEntry.lastActive = Date.now()
      saveChatIndex(this.stateDir, this.chatIndex)
    }

    // 串行化单个联系人的操作，避免 /new、/stop 与普通消息竞态
    chat.opQueue = chat.opQueue.then(() => this.handleInbound(chat, msg))
  }

  /** 群聊消息是否 @ 了机器人（兼容：完整账号 ID、本地名、"@" 开头）。 */
  isGroupMentioned(text) {
    if (!this.config.groupRequireMention) return true
    const t = String(text ?? '').trim()
    if (!t) return false
    const account = String(this.state.credentials?.accountId ?? this.config.accountId ?? '').trim()
    if (account && t.includes(account)) return true
    const local = account.split('@')[0]
    if (local && t.includes(local)) return true
    if (t.startsWith('@')) return true
    return false
  }

  ensureChat(key, userId) {
    let chat = this.chats.get(key)
    // 正在拆除的会话（/new 后的旧对象）不复用，保证新消息拿到全新对象
    if (!chat || chat.tornDown) {
      chat = {
        key,
        to: userId,
        tornDown: false,
        // 优先取持久化的上下文令牌（定时任务主动发消息需要）
        contextToken: this.chatIndex[key]?.contextToken ?? '',
        agent: null,
        handle: null,
        sessionId: null,
        buffer: '',
        footer: '',
        lastSeq: 0,
        busy: false,
        lastActive: Date.now(),
        lastFlush: 0,
        opQueue: Promise.resolve(),
      }
      this.chats.set(key, chat)
    }
    return chat
  }

  /** 处理一条已过白名单的消息：命令或普通转发。 */
  async handleInbound(chat, msg) {
    if (this.disposed) return
    // 本对象可能已被 /new 或空闲回收拆除（排队期间发生）：改走当前活跃会话对象
    if (chat.tornDown || this.chats.get(chat.key) !== chat) {
      chat = this.ensureChat(chat.key, chat.to)
      chat.isGroup = Boolean(msg.group_id)
      chat.from = msg.from_user_id
      chat.contextToken = msg.context_token ?? chat.contextToken
      chat.lastActive = Date.now()
    }
    const text = extractUsableText(msg)

    const trimmed = text.trim()
    if (trimmed.startsWith('/')) {
      await this.handleCommand(chat, trimmed)
      return
    }

    if (!text) {
      if (hasMediaItem(msg)) {
        const hasUnsupported = (msg.item_list ?? []).some(item => item.type === MessageItemType.VIDEO)
        if (hasUnsupported) {
          await this.reply(chat, '视频暂未开放；图片和文件可以直接发。')
        }
        // 纯图片/纯文件消息：走下方下载处理（text 为空时仍转发路径）
      }
      if (!imageItems(msg).length && !fileItems(msg).length) return
    }

    // 安全铁律：纯链接不自动处理
    if (text && this.config.blockLinks && URL_ONLY.test(text)) {
      this.log.info(`已拦截纯链接消息（来自 ${chat.to}）。`)
      await this.reply(chat, '【安全提示】纯链接消息不自动处理，已拦截。请用文字描述你的需求。')
      return
    }

    // 微信图片：下载到工作目录，把路径交给 AI 用工具读取分析
    let imageNote = ''
    const images = imageItems(msg)
    if (images.length > 0) {
      try {
        const dir = join(this.resolveWorkDir(), 'wechat-attachments')
        if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
        const saved = []
        let index = 0
        for (const item of images) {
          const media = await this.client.downloadMedia(item)
          if (!media?.data) continue
          const ext = guessImageExtension(media.data)
          const file = join(dir, `wechat-img-${Date.now()}-${index++}${ext}`)
          writeFileSync(file, media.data)
          saved.push(file)
          this.log.info(`微信图片已保存：${file}（${media.data.length} 字节）`)
        }
        if (saved.length > 0) {
          imageNote = `\n\n[微信图片] 用户刚发来 ${saved.length} 张图片，已保存到本地：\n${saved.join('\n')}\n请读取并分析这些图片（可用 OCR、python、图片查看等工具），然后回复用户。`
          await this.reply(chat, `📷 收到 ${saved.length} 张图片，正在分析…`)
        }
      } catch (error) {
        this.log.error(`图片下载失败：${error?.stack ?? error?.message ?? error}`)
        await this.reply(chat, '⚠️ 图片下载失败，请重试或改用文字描述。')
        return
      }
    }

    // 微信文件：下载到工作目录，把路径交给 AI 用工具读取分析
    let fileNote = ''
    const files = fileItems(msg)
    if (files.length > 0) {
      try {
        const dir = join(this.resolveWorkDir(), 'wechat-attachments')
        if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
        const saved = []
        let index = 0
        for (const item of files) {
          const media = await this.client.downloadMedia(item)
          if (!media?.data) continue
          const name = sanitizeFileName(media.fileName || item.file_item?.file_name || 'file')
          const file = join(dir, `wechat-file-${Date.now()}-${index++}-${name}`)
          writeFileSync(file, media.data)
          saved.push({ file, name, bytes: media.data.length })
          this.log.info(`微信文件已保存：${file}（${media.data.length} 字节）`)
        }
        if (saved.length > 0) {
          fileNote = `\n\n[微信文件] 用户刚发来 ${saved.length} 个文件，已保存到本地：\n${saved.map(s => `${s.file}（文件名：${s.name}，${s.bytes} 字节）`).join('\n')}\n请读取并分析这些文件，然后回复用户。`
          await this.reply(chat, `📎 收到 ${saved.length} 个文件（${saved.map(s => s.name).join('、')}），正在分析…`)
        }
      } catch (error) {
        this.log.error(`文件下载失败：${error?.stack ?? error?.message ?? error}`)
        await this.reply(chat, '⚠️ 文件下载失败，请重试。')
        return
      }
    }

    // 确保有 Agent（优先恢复持久化会话；/new 后或首次消息时新建）
    if (!chat.agent) {
      try {
        await this.ensureAgentFor(chat)
      } catch (error) {
        this.log.error(`创建/恢复 Agent 失败：${error?.stack ?? error?.message ?? error}`)
        await this.reply(chat, `⚠️ AI 启动失败：${truncate(error?.message ?? String(error), 120)}`)
        return
      }
    }

    try {
      const content = [{ type: 'text', text: text || `用户发来媒体消息（无文字）${imageNote || fileNote ? '' : '，但下载失败'}` }]
      if (imageNote) content[0].text += imageNote
      if (fileNote) content[0].text += fileNote
      chat.agent.followup(createUserMessage({
        content,
        source: { kind: 'user' },
      }))
      const mediaDesc = [images.length ? `${images.length} 图` : '', files.length ? `${files.length} 文件` : ''].filter(Boolean).join('，')
      this.log.info(`已转发消息给 AI（${chat.isGroup ? `群 ${chat.to} 成员 ${chat.from}` : `联系人 ${chat.to}`}，${(text || '').length} 字${mediaDesc ? `，${mediaDesc}` : ''}）。`)
    } catch (error) {
      this.log.error(`消息入队失败：${error?.message ?? error}`)
      await this.reply(chat, `⚠️ 消息处理失败：${truncate(error?.message ?? String(error), 120)}`)
    }
  }

  /** 确保联系人有可用 Agent：优先恢复持久化会话，否则新建。 */
  async ensureAgentFor(chat) {
    const indexEntry = this.chatIndex[chat.key]
    let resumed = false
    if (indexEntry?.sessionId) {
      resumed = await this.tryResumeAgentFor(chat, indexEntry.sessionId)
    }
    if (!resumed) await this.createAgentFor(chat)
  }

  /** 为某个联系人创建独立的 DSH Agent 会话。 */
  async createAgentFor(chat) {
    const agents = this.ctx.get('agents')
    const defaultModel = this.ctx.get('agentDefaultModel')
    const selection = typeof defaultModel?.currentSelection === 'function' ? defaultModel.currentSelection() : undefined
    const sessionId = SessionId(`wechat-${randomUUID()}`)
    const options = {
      sessionId,
      meta: { cwd: this.resolveWorkDir() },
    }
    if (selection?.provider && selection?.model) {
      options.agentOptions = { provider: selection.provider, model: selection.model }
      // 注意：agent-loop 会对 setup 的返回值调用 ?.commit()（事务提交语义），
      // 因此这里必须用块体写法返回 undefined（与 dsh-headless 的用法一致），
      // 不能把 installModelSelection 的 disposer 作为返回值传出去。
      options.setup = async (agentCtx) => {
        installModelSelection(agentCtx, { current: selection, assembled: undefined })
        this.setupAgentScope(agentCtx, chat.key)
        // 挂载默认 preset：注入 standard 工具 + 远程 MCP（eco-matrix）工具，
        // 让微信侧智能体拥有完整能力（shell/fs/生态环境 MCP 等），而不是只有微信文件工具。
        const presets = this.ctx.get('agentPresets')
        if (presets) await presets.mount(agentCtx)
      }
    }
    const { agent, dispose } = await agents.create(options)
    chat.agent = agent
    chat.handle = { dispose }
    chat.sessionId = sessionId
    chat.model = selection?.model || ''
    chat.lastSeq = agent.session.seq
    chat.buffer = ''
    chat.footer = ''
    chat.busy = false
    chat.sanitizer = createStreamSanitizer()
    // 持久化联系人 → 会话索引（重启后恢复上下文）；合并式保存，保留已有的 contextToken
    this.chatIndex[chat.key] = { ...(this.chatIndex[chat.key] ?? {}), sessionId: String(sessionId), lastActive: Date.now() }
    saveChatIndex(this.stateDir, this.chatIndex)
    this.log.info(`已为联系人 ${chat.to} 创建会话 ${String(sessionId)}。`)
  }

  /** 恢复联系人上一次的持久化会话；失败（无持久化/损坏/冲突）返回 false。 */
  async tryResumeAgentFor(chat, sessionId) {
    try {
      const agents = this.ctx.get('agents')
      const defaultModel = this.ctx.get('agentDefaultModel')
      const selection = typeof defaultModel?.currentSelection === 'function' ? defaultModel.currentSelection() : undefined
      const options = { resumeSessionId: SessionId(sessionId) }
      if (selection?.provider && selection?.model) {
        options.agentOptions = { provider: selection.provider, model: selection.model }
        // 与 create 一致：块体写法返回 undefined（agent-loop 对返回值调用 ?.commit()）
        options.setup = async (agentCtx) => {
          installModelSelection(agentCtx, { current: selection, assembled: undefined })
          this.setupAgentScope(agentCtx, chat.key)
          const presets = this.ctx.get('agentPresets')
          if (presets) await presets.mount(agentCtx)
        }
      }
      const { agent, dispose } = await agents.resume(options)
      chat.agent = agent
      chat.handle = { dispose }
      chat.sessionId = sessionId
      chat.model = selection?.model || ''
      chat.lastSeq = agent.session.seq
      chat.buffer = ''
      chat.footer = ''
      chat.busy = false
      chat.sanitizer = createStreamSanitizer()
      // 合并式保存，保留 onMessage 刚写入的 contextToken（此前会被覆盖丢失）
      this.chatIndex[chat.key] = { ...(this.chatIndex[chat.key] ?? {}), sessionId, lastActive: Date.now() }
      saveChatIndex(this.stateDir, this.chatIndex)
      this.log.info(`已为联系人 ${chat.to} 恢复会话 ${sessionId}（上下文延续）。`)
      return true
    } catch (error) {
      this.log.warn(`会话恢复失败（联系人 ${chat.to}，${sessionId}）：${error?.message ?? error}，将新建会话。`)
      return false
    }
  }

  /** 斜杠命令。控制命令（/new /stop /status）按管理员列表鉴权。 */
  async handleCommand(chat, trimmed) {
    const cmd = trimmed.toLowerCase().split(/\s+/)[0]
    const CONTROL_COMMANDS = ['/new', '/stop', '/status']
    if (CONTROL_COMMANDS.includes(cmd)) {
      const admins = this.effectiveAdmins()
      // 群聊命令按发送者（chat.from）鉴权，私聊 chat.from 与 chat.to 相同
      const operator = chat.from ?? chat.to
      const isAdmin = admins.length === 0 || admins.includes(operator)
      if (!isAdmin) {
        this.log.warn(`非管理员 ${operator} 尝试执行控制命令：${cmd}，已拒绝。`)
        await this.reply(chat, '该命令仅管理员可用。')
        return
      }
    }
    switch (cmd) {
      case '/help':
        await this.reply(chat, HELP_TEXT)
        break
      case '/new': {
        this.log.info(`联系人 ${chat.to} 请求新会话。`)
        await this.reply(chat, '已开始新会话，之前的上下文已清空。')
        await this.teardownChat(chat)
        break
      }
      case '/stop': {
        if (chat.agent && chat.busy) {
          chat.agent.cancel({ kind: 'user' })
          await this.reply(chat, '已请求停止当前任务。')
        } else {
          await this.reply(chat, '当前没有正在执行的任务。')
        }
        break
      }
      case '/status': {
        const agentState = chat.agent ? String(chat.agent.status ?? 'unknown') : '无会话'
        const busyText = chat.busy ? '（忙）' : ''
        const sessionInfo = chat.sessionId ? `会话：${String(chat.sessionId).slice(0, 12)}…` : '会话：无'
        await this.reply(chat, `【状态】\nAgent：${agentState}${busyText}\n${sessionInfo}\n发送 /new 可开始新会话。`)
        break
      }
      default:
        await this.reply(chat, `未知命令「${trimmed}」。可用命令：/help /new /stop /status`)
    }
  }

  /** 向微信发送回复（自动按配置切段；非流式长回复按 (i/n) 编号）。 */
  async reply(chat, text) {
    const maxChars = Math.max(200, Number(this.config.maxReplyChars) || 1500)
    const parts = splitForSend(String(text), maxChars)
    const numbered = this.config.streaming === false && parts.length > 1
    for (let i = 0; i < parts.length; i++) {
      const part = numbered ? `(${i + 1}/${parts.length}) ${parts[i]}` : parts[i]
      try {
        await this.client.sendText(chat.to, part, chat.contextToken || '')
        this.log.info(`已回传（${chat.isGroup ? `群 ${chat.to}` : `联系人 ${chat.to}`}）：${truncate(part.replace(/\n/g, ' '), 80)}`)
      } catch (error) {
        this.log.error(`发送失败（${chat.isGroup ? `群 ${chat.to}` : `联系人 ${chat.to}`}）：${error?.message ?? error}`)
        return
      }
      if (parts.length > 1) await this.sleep(250)
    }
  }

  /** 切换微信"正在输入…"状态（尽力而为，失败静默；群聊无此能力）。 */
  async setTyping(chat, on) {
    try {
      if (this.config.typing === false || this.override.typing === false) return
      if (chat.isGroup) return
      if (!this.client || this.phase !== 'running') return
      // 缓存 typing ticket；失败时清空以便下次重取
      if (!chat.typingTicket) {
        const resp = await this.client.getTypingTicket(chat.to, chat.contextToken || '')
        chat.typingTicket = resp?.typing_ticket
        if (!chat.typingTicket) return
      }
      await this.client.sendTyping(chat.to, chat.typingTicket, on ? TypingStatus.TYPING : TypingStatus.CANCEL)
    } catch {
      chat.typingTicket = undefined // 票据可能失效，下次重取
    }
  }

  /** 释放某个联系人的会话（/new 或空闲超时）。keepIndex=true 时保留索引（插件卸载用，重启可恢复）。 */
  async teardownChat(chat, options = {}) {
    chat.tornDown = true
    const handle = chat.handle
    chat.agent = null
    chat.handle = null
    chat.sessionId = null
    chat.buffer = ''
    chat.footer = ''
    chat.busy = false
    chat.sanitizer = null
    chat.renderer = null
    // 只删除自己：拆除期间若已有新会话对象顶替，绝不误删
    if (this.chats.get(chat.key) === chat) this.chats.delete(chat.key)
    if (!options.keepIndex && this.chatIndex[chat.key]) {
      // 保留 contextToken（定时任务主动推送需要），仅清除会话 ID（下次消息新建会话）
      const prev = this.chatIndex[chat.key]
      if (prev?.contextToken) {
        this.chatIndex[chat.key] = { contextToken: prev.contextToken, lastActive: Date.now() }
      } else {
        delete this.chatIndex[chat.key]
      }
      saveChatIndex(this.stateDir, this.chatIndex)
    }
    if (handle) {
      try { await handle.dispose() } catch (error) {
        this.log.warn(`会话释放异常：${error?.message ?? error}`)
      }
    }
  }

  /** 全局节拍：消费会话日志 → 流式缓冲 → 定时发送；空闲回收；锁心跳；热加载覆盖配置。 */
  tick() {
    if (this.disposed) return
    const now = Date.now()
    // 长轮询假死看门狗：poll 事件长时间不来说明长轮询可能已静默挂起，
    // 主动 stop 客户端（monitorLoop 会按冷却时间自动重建监听）。
    const watchdogSecs = Number(this.config.pollWatchdogSecs)
    if (this.phase === 'running' && this.client && watchdogSecs > 0 && this.lastPollAt > 0 && now - this.lastPollAt > watchdogSecs * 1000) {
      this.log.warn(`长轮询静默超过 ${watchdogSecs} 秒，判定假死，重启监听。`)
      this.lastPollAt = Date.now() // 防重建期间反复触发
      try { this.client.stop() } catch { /* ignore */ }
    }
    // 单例锁心跳（20 秒一次）
    if (this.lockOwned && now - this.lastLockBeat > 20000) {
      this.lastLockBeat = now
      this.writeLock()
    }
    // override.json 热加载（5 秒一次）
    this.refreshOverride()
    // 定时任务检查（cron）
    this.checkJobs(now)
    // 文件回传扫描（约 2 秒一次）
    if (this.config.outbox !== false && now - this.lastOutboxScan > 2000) {
      this.lastOutboxScan = now
      this.scanOutboxes().catch(() => {})
    }
    for (const chat of [...this.chats.values()]) {
      // 空闲回收（没有 Agent 的残留会话同样回收，避免泄漏）
      const timeoutMs = Number(this.config.idleTimeoutMins) * 60 * 1000
      if (timeoutMs > 0 && now - chat.lastActive > timeoutMs && (!chat.agent || !chat.busy)) {
        this.log.info(`联系人 ${chat.to} 空闲超时，自动结束会话。`)
        this.teardownChat(chat).catch(e => this.log.warn(`回收异常：${e?.message ?? e}`))
        continue
      }
      if (!chat.agent) continue
      this.drain(chat, now)
    }
  }

  /** 读取会话新增事件，更新缓冲与忙闲状态，按需发送。 */
  drain(chat, now) {
    const session = chat.agent?.session
    if (!session) return
    // 新版 dsh 废弃了同步的 session.events 读取，事件日志改为私有；用 ownEvents() 兜底。
    // （彻底适配应走 sessionProjections 快照 / 异步 read，见 deprecation Agent Note。）
    const events = session.ownEvents?.() ?? []
    let dirty = false
    let turnEnded = false
    for (let i = chat.lastSeq; i < events.length; i++) {
      const event = events[i]
      if (event.type === 'turn/start') {
        chat.busy = true
        chat.footer = ''
        dirty = true
        // 思考开始：微信端显示"正在输入…"；记录起点用于"正在处理"提示
        chat.turnStartedAt = now
        chat.waitingNoteSent = false
        chat.sawOutput = false
        this.setTyping(chat, true).catch(() => {})
      } else if (event.type === 'assistant/message') {
        // 新版 dsh 移除了流式 assistant/chunk 事件，AI 回复由 assistant/message
        // 事件的 stream 字段携带 text-chunks（流式 delta）。逐个 delta 喂给
        // 消毒器与排版渲染器，还原流式发送与 Markdown 转纯文本；跳过 reasoning。
        const stream = event.data?.stream
        if (Array.isArray(stream)) {
          for (const record of stream) {
            if (record?.type !== 'text-chunks' || !Array.isArray(record.texts)) continue
            for (const text of record.texts) {
              if (typeof text !== 'string' || text === '') continue
              chat.sanitizer ??= createStreamSanitizer()
              let clean = chat.sanitizer.feed(text)
              if (clean) chat.sawOutput = true
              if (clean && this.config.wechatMarkdown !== false) {
                chat.renderer ??= createWeChatMarkdownRenderer()
                clean = chat.renderer.feed(clean)
              }
              if (clean) {
                chat.buffer += clean
                dirty = true
              }
            }
          }
        }
      } else if (event.type === 'turn/end') {
        chat.busy = false
        turnEnded = true
        // 思考结束：取消"正在输入…"
        this.setTyping(chat, false).catch(() => {})
        // 结算消毒器残留（若抑制态未闭合，残留会被丢弃），再结算排版渲染器
        // （渲染器可能扣住了表格行/半行，即使 sanitizer 无残留也必须 flush）
        let rest = chat.sanitizer?.flush() ?? ''
        if (this.config.wechatMarkdown !== false && chat.renderer) {
          rest = chat.renderer.feed(rest) + chat.renderer.flush()
        }
        if (rest) chat.buffer += rest
        const reason = event.data?.reason
        if (reason?.kind === 'error') {
          chat.footer = `\n⚠️ 出错了：${truncate(reason.error?.message ?? '未知错误', 200)}`
        } else if (reason?.kind === 'aborted') {
          chat.footer = '\n（已停止）'
        } else if (reason?.kind === 'blocked') {
          chat.footer = '\n（任务被暂停，等待人工处理）'
        } else if (this.config.usageFooter !== false) {
          // 正常结束：附加模型与用量统计（严格对齐 GUI 回合尾注格式，会话投影同源数据）
          try {
            const snap = this.ctx.get('sessionProjections')?.snapshot?.(chat.agent.session)
            const usage = snap?.values?.tokenUsage
            const pressure = snap?.values?.contextPressure
            const label = String(this.config.usageFooterPath || '~/.dsh-wechat-bridge')
            let footer = ''
            if (usage) {
              const pct = pressure?.contextWindow > 0 && pressure?.projectedTokens > 0
                ? Math.min(100, Math.round((pressure.projectedTokens / pressure.contextWindow) * 100))
                : null
              const parts = []
              parts.push(`out ${fmtTokens(usage.outputTokens)}`)
              parts.push(`in ${fmtTokens(usage.uncachedInputTokens)} cw ${fmtTokens(usage.cacheWriteTokens)} cr ${fmtTokens(usage.cacheReadTokens)}`)
              if (pct !== null) parts.push(`ctx ${pct}%`)
              footer = `${chat.model || 'model'} · ${parts.join(' · ')} ${label}`
            } else {
              // 投影不可用时的降级：tokenMeter.measure 的 provider 用量与表面积
              const meter = this.ctx.get('tokenMeter')
              if (meter?.measure) {
                const m = meter.measure(chat.agent.session)
                const u = m?.baseline?.kind === 'usage' ? m.baseline.usage : null
                const bits = []
                if (u?.completion_tokens != null) bits.push(`out ${fmtTokens(u.completion_tokens)}`)
                if (u?.prompt_tokens != null) bits.push(`in ${fmtTokens(u.prompt_tokens)}`)
                if (m?.surfaceTokens > 0) bits.push(`ctx ${fmtTokens(m.surfaceTokens)}`)
                if (bits.length > 0) footer = `${chat.model || 'model'} · ${bits.join(' · ')} ${label}`
              }
            }
            if (footer && chat.sawOutput) chat.footer = `\n${footer}`
          } catch (error) { this.log.warn(`用量统计失败：${error?.message ?? error}`) }
        }
        dirty = true
      }
      chat.lastSeq = i + 1
    }
    // 双保险反馈：思考超过阈值仍无可见输出时，主动告知"正在处理"（每轮一次）
    const waitSecs = Number(this.config.waitNoteSecs)
    if (!turnEnded && chat.busy && waitSecs > 0 && !chat.waitingNoteSent && !chat.sawOutput && (now - (chat.turnStartedAt ?? now)) > waitSecs * 1000) {
      chat.waitingNoteSent = true
      this.reply(chat, '⏳ 正在处理，请稍候…').catch(() => {})
    }
    if (!dirty) return
    const buffered = chat.buffer.length > 0
    const sizeReached = chat.buffer.length >= FLUSH_SIZE
    const idleReached = now - chat.lastFlush >= FLUSH_IDLE_MS
    const shouldSend = this.config.streaming === false ? turnEnded : (turnEnded || sizeReached || idleReached)
    if (!shouldSend) return
    if (!buffered && !chat.footer) return
    let payload = (chat.buffer + chat.footer).trim()
    if (!payload) return
    let keep = ''
    // 非回合结束的流式发送：按句读/空白/URL 边界切割，避免把词从中间切断
    // （模型流的停顿点常在词中间，直接整段发会产生"抓\n取成功"这类半词碎片）。
    // 词中间的部分留在缓冲里，等后续流补齐或回合结束时一起发。
    if (!turnEnded && this.config.streaming !== false) {
      if (payload.length >= FLUSH_SIZE) {
        const cut = safeSendCut(payload, 160)
        if (cut > 0 && cut < payload.length) {
          keep = payload.slice(cut)
          payload = payload.slice(0, cut)
        } else {
          // 长串没有任何安全断点（罕见）：按上限硬切，避免缓冲无限增长
          keep = payload.slice(FLUSH_SIZE)
          payload = payload.slice(0, FLUSH_SIZE)
        }
      } else {
        const cut = safeSendCut(payload, payload.length)
        if (cut > 0 && cut < payload.length) {
          keep = payload.slice(cut)
          payload = payload.slice(0, cut)
        } else {
          // 尚无安全断点：暂不发送，继续缓冲，防止半词碎片
          chat.lastFlush = now
          return
        }
      }
    }
    chat.buffer = keep.replace(/^\s+/, '')
    chat.footer = ''
    chat.lastFlush = now
    this.reply(chat, payload).catch(e => this.log.error(`回传异常：${e?.message ?? e}`))
  }

  /** 插件卸载：停止轮询、清定时器、释放全部会话。 */
  async dispose() {
    this.disposed = true
    if (this.ticker) {
      // ctx.setInterval 返回的是 disposer 函数；全局 setInterval 返回 Timeout
      if (typeof this.ticker === 'function') this.ticker()
      else clearInterval(this.ticker)
    }
    if (this.retryTimer) clearTimeout(this.retryTimer)
    try { this.client?.stop() } catch { /* ignore */ }
    this.client = null
    // 卸载时保留会话索引：重启后按联系人恢复上下文
    const pending = [...this.chats.values()].map(chat => this.teardownChat(chat, { keepIndex: true }))
    await Promise.allSettled(pending)
    this.releaseSingleton()
    this.log.info('wechat-bridge 已停止。')
  }
}

/** Cordis 插件入口。 */
export function apply(ctx, config) {
  const log = makeLogger(ctx, join(resolveDshHome(), 'wechat-bridge'))
  // 配置走 settings namespace，设置界面「我的助手」可实时读写；config 参数作为 base 兜底。
  ctx.inject(['settings'], (settingsCtx) => {
    const scope = settingsCtx.settings.register('wechat-bridge', Config, {
      base: config,
      applies: 'live',
    })
    // 常驻 effect 管理 bridge 生命周期，scope.watch 监听 enabled 动态启停。
    // 修复：原实现 initial enabled=false 时直接 return，导致 scope.watch 未注册，
    // 设置界面打开开关后无任何响应（开关是"死"的）。
    ctx.effect(() => {
      let bridge = null
      let stopBridge = null

      const sync = () => {
        const cfg = scope.get()
        if (!cfg.enabled) {
          if (bridge) {
            log.info('微信桥接已禁用，停止登录与收发。')
            stopBridge?.()
          } else {
            log.info('插件已加载但未启用（enabled=false），不进行登录与收发。')
          }
          return
        }
        if (!bridge) {
          bridge = new WeChatBridge(ctx, cfg, log)
          // 注册微信桥接专属工具（全局工具注册表，不依赖 Agent 预设；微信侧智能体必然可见）
          bridge.registerTools(ctx)
          void bridge.start()
          stopBridge = () => {
            for (const dispose of bridge.toolDisposers) {
              try { dispose() } catch { /* ignore */ }
            }
            bridge.toolDisposers = []
            void bridge.dispose()
            bridge = null
            stopBridge = null
          }
          log.info('微信桥接已启用，进入登录/收发流程。')
        } else {
          // 已启用：同步 enabled 之外的配置热更新
          bridge.config = cfg
        }
      }

      sync()
      // 配置热更新：设置界面改动后实时同步；enabled 切换时动态启停 bridge。
      const unwatch = scope.watch(() => sync())

      return () => {
        unwatch()
        stopBridge?.()
      }
    }, 'wechat-bridge')
  })
}
