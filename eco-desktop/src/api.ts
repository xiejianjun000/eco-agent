// api.ts — ECO AGENT 服务层（G6 职责分离）
// 前端唯一访问后端的出口

const BASE = 'http://127.0.0.1:8000/v1'

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
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

export async function listModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/models`)
  if (!res.ok) return []
  const data = await res.json()
  return (data.data || []).map((m: any) => m.id)
}
