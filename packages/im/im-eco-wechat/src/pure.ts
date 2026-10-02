// @ts-nocheck
// dsh-wechat-bridge · 纯函数模块（零依赖）
//
// 从 lib/index.js 抽出的纯逻辑：流式文本消毒器、极简 cron 解析器、
// 流式发送安全断点。本模块不 import 任何 DSH 宿主包或第三方包，
// 因此单元测试可以在任意环境（含 GitHub Actions CI）零安装直接运行。
//
// 注意：修改这些函数时同步维护 test/unit.mjs 的对应断言。

// ---- 流式文本消毒器 ----
// 模型原始流里会混入工具调用 XML（<tool_calls>/<invoke>…）与思考块
// （<zhimayc-think>/<think>…），这些不该发给手机。文本按 token 分片到达，
// 标签可能被切在两片之间，所以用有状态扫描 + 尾部保留处理跨片标签。

const SANITIZE_OPEN_TAGS = ['<tool_calls>', '<invoke', '<zhimayc-think>', '<think>', '<thinking>', '<reasoning>', '<bash', '<tool_call', '<function_call', '<function-call', '<gongfeng-tool', '<approval']
const SANITIZE_CLOSE_TAGS = ['</invoke>', '</tool_calls>', '</zhimayc-think>', '</think>', '</thinking>', '</reasoning>', '</bash>', '</tool_call>', '</function_call>', '</function-call>', '</gongfeng-tool>', '</approval>']
const ALL_SANITIZE_TAGS = [...SANITIZE_OPEN_TAGS, ...SANITIZE_CLOSE_TAGS]

/** pending 尾部若是某个标签的前缀，返回应保留的字符数（等待后续分片补齐）。 */
function tagHoldLength(text) {
  const idx = text.lastIndexOf('<')
  if (idx < 0) return 0
  const tail = text.slice(idx)
  for (const tag of ALL_SANITIZE_TAGS) {
    if (tag.startsWith(tail) && tail.length < tag.length) return tail.length
  }
  return 0
}

/** 创建消毒器：feed() 逐片喂入并返回干净文本；flush() 结算残留。 */
export function createStreamSanitizer() {
  let pending = ''
  let suppress = 0
  return {
    feed(text) {
      pending += text
      const hold = tagHoldLength(pending)
      const limit = pending.length - hold
      let out = ''
      for (let i = 0; i < limit; i++) {
        const rest = pending.slice(i)
        let tag = null
        for (const t of SANITIZE_OPEN_TAGS) {
          if (rest.startsWith(t)) { tag = t; break }
        }
        if (tag) {
          suppress++
          i += tag.length - 1
          continue
        }
        tag = null
        for (const t of SANITIZE_CLOSE_TAGS) {
          if (rest.startsWith(t)) { tag = t; break }
        }
        if (tag) {
          if (suppress > 0) suppress--
          i += tag.length - 1
          continue
        }
        if (suppress === 0) out += pending[i]
      }
      pending = pending.slice(limit)
      return out
    },
    flush() {
      const out = suppress === 0 ? pending : ''
      pending = ''
      suppress = 0
      return out
    },
  }
}

// ---- 极简 cron 解析器（5 段：分 时 日 月 星期，星期 0=周日）----

function parseCronField(spec, min, max) {
  const set = new Set()
  for (const seg of String(spec).split(',')) {
    if (seg === '*') {
      for (let i = min; i <= max; i++) set.add(i)
    } else if (seg.startsWith('*/')) {
      const step = Number(seg.slice(2))
      if (!Number.isInteger(step) || step <= 0) return null
      for (let i = min; i <= max; i += step) set.add(i)
    } else if (seg.includes('-')) {
      const [a, b] = seg.split('-').map(Number)
      if (!Number.isInteger(a) || !Number.isInteger(b) || a < min || b > max || a > b) return null
      for (let i = a; i <= b; i++) set.add(i)
    } else {
      const n = Number(seg)
      if (!Number.isInteger(n) || n < min || n > max) return null
      set.add(n)
    }
  }
  return set
}

/** 解析 5 段 cron 表达式；无效返回 null。 */
export function parseCron(expr) {
  const parts = String(expr).trim().split(/\s+/)
  if (parts.length !== 5) return null
  const minute = parseCronField(parts[0], 0, 59)
  const hour = parseCronField(parts[1], 0, 23)
  const day = parseCronField(parts[2], 1, 31)
  const month = parseCronField(parts[3], 1, 12)
  const dow = parseCronField(parts[4], 0, 6)
  if (!minute || !hour || !day || !month || !dow) return null
  return { minute, hour, day, month, dow }
}

function cronMatches(cron, date) {
  return cron.minute.has(date.getMinutes()) &&
    cron.hour.has(date.getHours()) &&
    cron.day.has(date.getDate()) &&
    cron.month.has(date.getMonth() + 1) &&
    cron.dow.has(date.getDay())
}

/** fromTs 之后的下一个触发时刻（步进 1 分钟，最多扫 400 天；无匹配返回 null）。 */
export function nextCronAfter(cron, fromTs) {
  const d = new Date(fromTs + 60000)
  d.setSeconds(0, 0)
  for (let i = 0; i < 400 * 24 * 60; i++) {
    if (cronMatches(cron, d)) return d.getTime()
    d.setTime(d.getTime() + 60000)
  }
  return null
}

// ---- 流式发送安全断点 ----

/** 流式发送的安全断点字符：句读、空白、URL 分隔符之后断开，不会把词从中间切开。 */
const SEND_BREAK_RE = /[。！？；：，、…\s.!?;:,)）】」/?&=]/

/**
 * 在 text 末尾 window 个字符内找最后一个安全断开点，返回「发送到该位置（含断点）」的切割下标；
 * 找不到返回 -1（调用方应暂缓发送或硬切）。
 */
export function safeSendCut(text, window) {
  const from = Math.max(0, text.length - window)
  for (let i = text.length - 1; i >= from; i--) {
    if (SEND_BREAK_RE.test(text[i])) return i + 1
  }
  return -1
}

/** 用量数字格式化：743 → "743"，1300 → "1.3k"，111400 → "111.4k"。 */
export function fmtTokens(n) {
  const num = Number(n)
  if (!Number.isFinite(num) || num < 0) return '0'
  if (num < 1000) return String(Math.round(num))
  return `${(num / 1000).toFixed(1).replace(/\.0$/, '')}k`
}

// ---- 微信排版：markdown-lite → 微信友好纯文本（流式安全，逐行处理）----
// 微信不渲染 Markdown，模型回复里的 **加粗**、| 表格 |、> 引用、- 列表、
// # 标题、[链接](url)、`行内码` 会原样显示成符号。本渲染器把它们转成
// 微信里可读的纯文本。与流式消毒器同构：feed()/flush()，按完整行处理，
// 跨片的行与代码块状态都会保留到补齐为止。

const TABLE_LINE_RE = /^\s*\|.*\|\s*$/
const TABLE_SEP_RE = /^\s*\|[\s:\-|]+\|\s*$/

function tableCells(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
}

/** 把连续的表格行转成微信可读文本：两列转「a：b」，多列对齐，分隔行剔除。 */
function renderTableLines(lines) {
  const rows = []
  for (const line of lines) {
    if (TABLE_SEP_RE.test(line)) continue
    const cells = tableCells(line)
    if (cells.length > 0 && cells.some(c => c !== '')) rows.push(cells)
  }
  if (rows.length === 0) return lines.join('\n')
  const widths = []
  for (const cells of rows) {
    for (let i = 0; i < cells.length; i++) {
      const w = [...cells[i]].length
      if (w > (widths[i] ?? 0)) widths[i] = w
    }
  }
  return rows.map((cells) => {
    if (cells.length === 2) return `${cells[0]}：${cells[1]}`
    return cells.map((c, i) => (i === cells.length - 1 ? c : c.padEnd(widths[i] ?? 0, ' '))).join('  ')
  }).join('\n')
}

/** 行内标记：加粗/行内码/删除线/链接。 */
function renderInline(text) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/~~([^~]+)~~/g, '$1')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '$1（$2）')
}

/** 创建微信排版渲染器：feed() 逐片喂入返回渲染后文本；flush() 结算残留。 */
export function createWeChatMarkdownRenderer() {
  let partial = ''
  let inFence = false
  let tableBuf = []
  const emit = (out, line) => {
    if (inFence) {
      out.push(line)
      if (/^\s*```/.test(line)) inFence = false
      return
    }
    if (/^\s*```/.test(line)) { inFence = true; return }
    if (TABLE_LINE_RE.test(line)) { tableBuf.push(line); return }
    if (tableBuf.length > 0) { out.push(renderTableLines(tableBuf)); tableBuf = [] }
    let l = renderInline(line)
    l = l.replace(/^\s{0,3}#{1,6}\s+/, '')
    l = l.replace(/^\s{0,3}>\s?/, '')
    if (/^\s*[-*]\s+/.test(l)) l = l.replace(/^\s*[-*]\s+/, '• ')
    out.push(l)
  }
  return {
    feed(text) {
      if (!text) return ''
      partial += text
      const lines = partial.split('\n')
      partial = lines.pop() ?? ''
      const out = []
      for (const line of lines) emit(out, line)
      return out.length > 0 ? out.join('\n') + '\n' : ''
    },
    flush() {
      const out = []
      if (partial) emit(out, partial)
      if (tableBuf.length > 0) { out.push(renderTableLines(tableBuf)); tableBuf = [] }
      partial = ''
      inFence = false
      return out.length > 0 ? out.join('\n') : ''
    },
  }
}
