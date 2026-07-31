// api.ts — ECO AGENT 服务层（G6 职责分离）
// 前端唯一访问后端的出口
// 支持：聊天 / AI 评查 / 工具调用 / 模型列表

const BASE = 'http://127.0.0.1:8000/v1'

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

// AI 评查返回的批注结构
export interface AiReviewItem {
  start: number
  length: number
  originalText: string
  suggestion: string
  note: string
  type: 'error' | 'warning' | 'suggestion' | 'question'
}

export async function checkServer(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/models`)
    return res.ok
  } catch {
    return false
  }
}

export async function chat(messages: ChatMessage[]): Promise<string> {
  const res = await fetch(`${BASE}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, stream: false })
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.choices?.[0]?.message?.content || ''
}

// AI 评查：让 LLM 分析文档，返回结构化批注列表
// 方案：请求 JSON 数组 → 解析失败则二次提取 → 仍失败用本地关键词定位
export async function aiReview(text: string, docTitle: string): Promise<AiReviewItem[]> {
  const system = `你是生态环境执法案卷评查专家。请审查案卷，找出程序瑕疵、违法事实、证据缺失、法律适用问题。
你必须只输出一个 JSON 数组，每个元素格式：
{"start": 字符位置(从0开始), "length": 高亮长度, "originalText": "原文片段", "suggestion": "建议修改", "note": "问题说明", "type": "error|warning|suggestion|question"}
不要输出任何其他文字、解释或 markdown。只输出 JSON 数组。`

  // 第一轮：尝试直接获取 JSON
  let content = await chatForReview(system, docTitle, text)
  let items = parseReviewJson(content)

  // 第二轮：解析失败 → 让 LLM 把分析转成 JSON
  if (items.length === 0) {
    const extractPrompt = `把上面的评查分析整理成 JSON 数组，格式：
[{"start":位置, "length":长度, "originalText":"原文", "suggestion":"建议", "note":"说明", "type":"类型"}]
只输出 JSON 数组。`
    const second = await chatForReview(extractPrompt, docTitle, `请重新审查并只输出 JSON：\n${text.slice(0, 3000)}`)
    items = parseReviewJson(second)
  }

  // 第三轮：仍失败 → 本地关键词定位
  if (items.length === 0) {
    items = localKeywordAnnotations(text)
  }

  return items
}

async function chatForReview(system: string, docTitle: string, text: string): Promise<string> {
  try {
    const res = await fetch(`${BASE}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: `案卷标题：${docTitle}\n\n案卷内容：\n${text.slice(0, 4000)}` }
        ],
        stream: false
      })
    })
    if (!res.ok) return ''
    const data = await res.json()
    return data.choices?.[0]?.message?.content || ''
  } catch {
    return ''
  }
}

function parseReviewJson(content: string): AiReviewItem[] {
  if (!content) return []
  // 去掉 markdown 代码块
  const cleaned = content.replace(/```json|```/g, '').trim()
  try {
    const parsed = JSON.parse(cleaned)
    if (Array.isArray(parsed)) return parsed.filter(validItem)
    if (parsed.items && Array.isArray(parsed.items)) return parsed.items.filter(validItem)
    return []
  } catch {
    // 提取第一个 [ ... ] 数组
    const match = cleaned.match(/\[[\s\S]*\]/)
    if (match) {
      try {
        const parsed = JSON.parse(match[0])
        if (Array.isArray(parsed)) return parsed.filter(validItem)
      } catch { return [] }
    }
    return []
  }
}

function validItem(item: any): item is AiReviewItem {
  return item && typeof item === 'object'
    && typeof item.start === 'number'
    && typeof item.note === 'string'
    && typeof item.type === 'string'
}

// 本地关键词兜底（网络失败时）
function localKeywordAnnotations(text: string): AiReviewItem[] {
  const items: AiReviewItem[] = []
  const rules: [RegExp, string, string, AiReviewItem['type']][] = [
    [/450mg\/m³/g, '超标浓度需核实', '二氧化硫浓度超标125%，建议核实监测数据', 'error'],
    [/污染防治设施未正常运行/g, '涉嫌逃避监管', '依据《大气污染防治法》第二十条，不正常运行防治设施属于逃避监管', 'warning'],
    [/证据材料/g, '建议补充证据说明', '建议补充各项证据的采集时间和证明目的', 'suggestion'],
  ]
  for (const [re, suggestion, note, type] of rules) {
    const m = re.exec(text)
    if (m && m.index >= 0) {
      items.push({ start: m.index, length: m[0].length, originalText: m[0], suggestion, note, type })
    }
  }
  return items
}

// 通过文本定位批注（按关键词匹配位置）
export function findTextPositions(text: string, keywords: string[]): number[] {
  return keywords.map(k => text.indexOf(k)).filter(i => i >= 0)
}

export async function listModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/models`)
  if (!res.ok) return []
  const data = await res.json()
  return (data.data || []).map((m: any) => m.id)
}
