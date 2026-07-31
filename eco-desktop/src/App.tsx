import React, { useState, useRef, useEffect } from 'react'

const API_BASE = 'http://127.0.0.1:8000/v1'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

function App() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '你好！我是 ECO AGENT，生态环境法规 AI 助手。有什么可以帮您？' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    checkConnection()
  }, [])

  async function checkConnection() {
    setStatus('connecting')
    try {
      const res = await fetch(`${API_BASE}/models`)
      if (res.ok) {
        setStatus('connected')
      } else {
        setStatus('disconnected')
      }
    } catch {
      setStatus('disconnected')
    }
  }

  async function sendMessage() {
    if (!input.trim() || loading) return
    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [...messages, { role: 'user', content: userMsg }],
          stream: false
        })
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const text = data.choices?.[0]?.message?.content || ''
      setMessages(prev => [...prev, { role: 'assistant', content: text }])
    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `[连接错误] ${err.message || ''}` }])
    }
    setLoading(false)
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#0a0f0a' }}>
      {/* Header */}
      <div style={{ padding: '12px 20px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ color: '#3a8a6f', fontWeight: 'bold', fontSize: 18 }}>ECO AGENT</span>
        <span style={{ color: '#5a7a6a', fontSize: 11 }}>大气带律师 · 生态环境法规 AI</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: status === 'connected' ? '#4cd28a' : status === 'connecting' ? '#f0c040' : '#f04040', display: 'inline-block' }} />
          <span style={{ color: '#5a7a6a', fontSize: 11 }}>
            {status === 'connected' ? '已连接' : status === 'connecting' ? '连接中...' : '未连接'}
          </span>
          <button onClick={checkConnection} style={{ background: '#1a2f1a', border: 'none', color: '#5ae0a0', padding: '2px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 11 }}>重连</button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 12, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '80%', padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? '#1a2f1a' : '#0f1a0f',
              color: m.role === 'user' ? '#c0eac0' : '#e0eae0',
              border: m.role === 'assistant' ? '1px solid #1a2f1a' : 'none',
            }}>{m.content}</div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', gap: 4, padding: 10 }}>
            <span style={{ color: '#5a7a6a', fontSize: 12 }}>思考中</span>
            <span style={{ color: '#5a7a6a' }}>...</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid #1a2f1a', display: 'flex', gap: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          placeholder="输入您的问题..."
          style={{ flex: 1, padding: '10px 14px', borderRadius: 8, border: '1px solid #1a2f1a', background: '#0f1a0f', color: '#e0eae0', fontSize: 14, outline: 'none' }}
          disabled={loading}
        />
        <button onClick={sendMessage} disabled={loading || !input.trim()}
          style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: loading ? '#1a2f1a' : '#2d7a5f', color: '#fff', fontSize: 14, cursor: 'pointer' }}>
          发送
        </button>
      </div>
    </div>
  )
}

export default App
