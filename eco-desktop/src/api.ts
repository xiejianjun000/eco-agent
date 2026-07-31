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
export async function aiReview(text: string, docTitle: string): Promise<AiReviewItem[]> {
  const system = `你是生态环境执法案卷评查专家。请审查以下案卷，找出程序瑕疵、违法事实问题、证据缺失、法律适用错误。
返回 JSON 数组，每项格式：
{
  "start": 字符位置(从0开始),
  "length": 高亮长度,
  "originalText": "原文片段",
  "suggestion": "建议的修改文本",
  "note": "问题说明",
  "type": "error|warning|suggestion|question"
}
只返回 JSON，不要其他文字。`

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
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  const content = data.choices?.[0]?.message?.content || ''

  // 解析 JSON（LLM 可能带 markdown 代码块）
  try {
    const cleaned = content.replace(/```json|```/g, '').trim()
    const parsed = JSON.parse(cleaned)
    if (Array.isArray(parsed)) return parsed
    if (parsed.items && Array.isArray(parsed.items)) return parsed.items
    return []
  } catch {
    // 尝试提取数组
    const match = content.match(/\[[\s\S]*\]/)
    if (match) {
      try { return JSON.parse(match[0]) } catch { return [] }
    }
    return []
  }
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
