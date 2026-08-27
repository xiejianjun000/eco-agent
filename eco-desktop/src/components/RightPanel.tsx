// RightPanel.tsx — 右侧情报面板（G2 单一职责）
// 动态加载 4 个标签：对话提取 / 产出物 / 工具 / 进化

import React, { useState, useEffect, useRef } from 'react'
import { bus, EVENTS } from '../events'
import { chat } from '../api'

type Tab = 'chat' | 'artifacts' | 'tools' | 'evolution'

interface Msg { role: 'user' | 'assistant'; content: string }
interface Artifact { id: string; title: string; type: string; time: string }
interface Evolution { id: string; title: string; detail: string; time: string }

export default function RightPanel({ moduleContext }: { moduleContext: string }) {
  const [tab, setTab] = useState<Tab>('chat')
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [evolutions, setEvolutions] = useState<Evolution[]>([])
  const [toolOpen, setToolOpen] = useState<'doc' | 'browser' | 'draw' | null>(null)
  const msgEndRef = useRef<HTMLDivElement>(null)

  // 订阅事件：产出物就绪 / 进化
  useEffect(() => {
    const off1 = bus.on(EVENTS.ARTIFACT_READY, (e) => {
      setArtifacts(prev => [{
        id: e.traceId, title: e.payload?.title || '新产出物', type: e.payload?.type || 'doc', time: new Date().toLocaleTimeString()
      }, ...prev])
    })
    const off2 = bus.on(EVENTS.EVOLUTION, (e) => {
      setEvolutions(prev => [{
        id: e.traceId, title: e.payload?.title || '进化事件', detail: e.payload?.detail || '', time: new Date().toLocaleTimeString()
      }, ...prev])
    })
    return () => { off1(); off2() }
  }, [])

  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function sendMsg() {
    if (!input.trim()) return
    const msg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    try {
      const full = [...messages, { role: 'user' as const, content: msg }]
      const reply = await chat(full)
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
      // 如果回复像是产出物，通知总线
      if (reply.length > 100 && (reply.includes('报告') || reply.includes('文书'))) {
        bus.emit(EVENTS.ARTIFACT_READY, { title: 'AI 生成分析', type: 'ai' }, 'right-panel')
      }
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `[错误] ${e.message}` }])
    }
  }

  return (
    <div style={{ width: 320, borderLeft: '1px solid #1a2f1a', background: '#0d150d', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      {/* 标签页 */}
      <div style={{ display: 'flex', borderBottom: '1px solid #1a2f1a' }}>
        {([
          ['chat', '💬 对话'], ['artifacts', '📦 产出'], ['tools', '🔧 工具'], ['evolution', '🧬 进化']
        ] as [Tab, string][]).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            flex: 1, padding: '8px 4px', border: 'none', background: tab === id ? '#1a2f1a' : 'transparent',
            color: tab === id ? '#5ae0a0' : '#5a7a6a', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap'
          }}>{label}</button>
        ))}
      </div>

      {/* 内容区 */}
      <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
        {tab === 'chat' && (
          <>
            <div style={{ fontSize: 11, color: '#5a7a6a', marginBottom: 6 }}>当前上下文: {moduleContext}</div>
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 8, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '90%', padding: '8px 10px', borderRadius: 8, fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap',
                  background: m.role === 'user' ? '#1a2f1a' : '#0f1a0f',
                  border: m.role === 'assistant' ? '1px solid #1a2f1a' : 'none'
                }}>{m.content}</div>
              </div>
            ))}
            <div ref={msgEndRef} />
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendMsg()}
                placeholder="追问 AI..." style={{ flex: 1, padding: '6px 8px', borderRadius: 6, border: '1px solid #1a2f1a', background: '#0f1a0f', color: '#e0eae0', fontSize: 12, outline: 'none' }} />
              <button onClick={sendMsg} style={{ padding: '6px 10px', borderRadius: 6, border: 'none', background: '#2d7a5f', color: '#fff', cursor: 'pointer', fontSize: 12 }}>发送</button>
            </div>
          </>
        )}

        {tab === 'artifacts' && (
          <div>
            {artifacts.length === 0 && <div style={{ color: '#3a5a4a', fontSize: 12, textAlign: 'center', marginTop: 20 }}>暂无产出物<br/>AI 生成报告后会显示在这里</div>}
            {artifacts.map(a => (
              <div key={a.id} style={{ padding: '10px', background: '#0f1a0f', borderRadius: 8, marginBottom: 8, border: '1px solid #1a2f1a' }}>
                <div style={{ fontSize: 13, color: '#8ae0b8', fontWeight: 600 }}>📄 {a.title}</div>
                <div style={{ fontSize: 11, color: '#5a7a6a', marginTop: 4 }}>{a.time} · {a.type}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <button style={{ padding: '3px 8px', fontSize: 11, background: '#1a2f1a', color: '#5ae0a0', border: 'none', borderRadius: 4, cursor: 'pointer' }}>插入文档</button>
                  <button style={{ padding: '3px 8px', fontSize: 11, background: 'transparent', color: '#5a7a6a', border: '1px solid #1a2f1a', borderRadius: 4, cursor: 'pointer' }}>同步Obsidian</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'tools' && (
          <div>
            <div style={{ fontSize: 11, color: '#5a7a6a', marginBottom: 8 }}>按需加载的嵌入式工具</div>
            {([
              ['doc', '📝 文档编辑器', '编辑 DOCX/PDF/XLSX/MD'],
              ['browser', '🌐 网站浏览器', '访问政务平台'],
              ['draw', '✏️ 勘查画图', '卫星地图标注绘制'],
            ] as [string, string, string][]).map(([id, label, desc]) => (
              <button key={id} onClick={() => setToolOpen(toolOpen === id ? null : id as any)} style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '10px 12px',
                background: toolOpen === id ? '#1a2f1a' : '#0f1a0f', border: '1px solid #1a2f1a',
                borderRadius: 8, marginBottom: 8, cursor: 'pointer', color: '#e0eae0'
              }}>
                <div style={{ fontSize: 13 }}>{label}</div>
                <div style={{ fontSize: 11, color: '#5a7a6a', marginTop: 2 }}>{desc}</div>
              </button>
            ))}
            {toolOpen && (
              <div style={{ padding: '12px', background: '#0d150d', border: '1px solid #1a2f1a', borderRadius: 8, marginTop: 4 }}>
                {toolOpen === 'doc' && <div style={{ fontSize: 12, color: '#5a7a6a' }}>📝 ONLYOFFICE 编辑器将在此嵌入</div>}
                {toolOpen === 'browser' && <div style={{ fontSize: 12, color: '#5a7a6a' }}>🌐 Tauri WebView 浏览器将在此嵌入</div>}
                {toolOpen === 'draw' && <div style={{ fontSize: 12, color: '#5a7a6a' }}>✏️ OpenLayers + Terra Draw 将在此嵌入</div>}
                <button onClick={() => setToolOpen(null)} style={{ marginTop: 8, padding: '3px 10px', fontSize: 11, background: 'transparent', color: '#5a7a6a', border: '1px solid #1a2f1a', borderRadius: 4, cursor: 'pointer' }}>关闭</button>
              </div>
            )}
          </div>
        )}

        {tab === 'evolution' && (
          <div>
            {evolutions.length === 0 && <div style={{ color: '#3a5a4a', fontSize: 12, textAlign: 'center', marginTop: 20 }}>暂无进化记录<br/>智能体反思与技能改进会沉淀在这里</div>}
            {evolutions.map(ev => (
              <div key={ev.id} style={{ padding: '10px', background: '#0f1a0f', borderRadius: 8, marginBottom: 8, border: '1px solid #1a2f1a' }}>
                <div style={{ fontSize: 13, color: '#8ae0b8', fontWeight: 600 }}>🧬 {ev.title}</div>
                <div style={{ fontSize: 11, color: '#5a7a6a', marginTop: 4 }}>{ev.detail}</div>
                <div style={{ fontSize: 10, color: '#3a5a4a', marginTop: 4 }}>{ev.time}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
