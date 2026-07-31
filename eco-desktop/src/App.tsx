// App.tsx — ECO AGENT Desktop 主框架（IDE 式工作台）
// 布局：
//   左侧导航（可收缩）
//   中间 = [对话面板 | 画布面板]（可拖拽分栏）
//   右侧活动栏（文档/浏览器/产出/地图，可收缩）
//   底部命令中心（输入 + 状态）
//
// 各栏之间可拖拽调整大小，各栏顶部有收缩按钮

import React, { useState, useEffect } from 'react'
import SplitPane from './components/SplitPane'
import ActivityPanel from './components/ActivityPanel'
import CanvasPanel from './components/CanvasPanel'
import CommandCenter from './components/CommandCenter'
import { checkServer, chat } from './api'
import { bus, EVENTS } from './events'

const MODULES = [
  { id: 'chat', icon: '💬', label: '对话' },
  { id: 'calendar', icon: '📅', label: '日历' },
  { id: 'enforcement', icon: '⚖️', label: '执法督察' },
  { id: 'eia', icon: '📋', label: '环评排污' },
  { id: 'airtrace', icon: '🌪️', label: '大气溯源' },
  { id: 'monitor', icon: '📊', label: '环境监测' },
  { id: 'gov', icon: '🏛️', label: '政务' },
  { id: 'knowledge', icon: '📚', label: '知识库' },
  { id: 'mcp', icon: '🔌', label: 'MCP连接' },
] as const

type ModuleId = typeof MODULES[number]['id']
type Mode = 'cloud' | 'local'

export default function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>('enforcement')
  const [mode, setMode] = useState<Mode>('cloud')
  const [navCollapsed, setNavCollapsed] = useState(false)
  const [chatCollapsed, setChatCollapsed] = useState(false)
  const [activityCollapsed, setActivityCollapsed] = useState(false)
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  async function refresh() {
    setStatus('connecting')
    const ok = await checkServer()
    setStatus(ok ? 'connected' : 'disconnected')
  }
  useEffect(() => { refresh() }, [])

  const currentLabel = MODULES.find(m => m.id === activeModule)?.label || ''

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#0a0f0a', color: '#e0eae0', fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif" }}>
      {/* 顶部区域：左导航 + 中央 + 右活动栏（横向排列） */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* 左侧导航 */}
        {!navCollapsed ? (
          <SideNav collapsed={false} setNavCollapsed={setNavCollapsed} mode={mode} setMode={setMode}
            activeModule={activeModule} navigate={setActiveModule} />
        ) : (
          <div style={{ width: 36, borderRight: '1px solid #1a2f1a', background: '#0f1a0f', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 10 }}>
            <span style={{ fontSize: 16, marginBottom: 10 }}>🌿</span>
            {MODULES.map(m => (
              <button key={m.id} onClick={() => setActiveModule(m.id)} title={m.label}
                style={{ background: activeModule === m.id ? '#1a2f1a' : 'transparent', border: 'none', fontSize: 15, padding: '8px 0', cursor: 'pointer', color: activeModule === m.id ? '#5ae0a0' : '#5a7a6a' }}>
                {m.icon}
              </button>
            ))}
            <button onClick={() => setNavCollapsed(false)} title="展开" style={{ background: 'transparent', border: 'none', fontSize: 12, color: '#5a7a6a', cursor: 'pointer', marginTop: 'auto', padding: 10 }}>▶</button>
          </div>
        )}

        {/* 中央工作区 */}
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {/* 顶部工具栏 */}
          <header style={{ padding: '6px 12px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 8, minHeight: 34 }}>
            <span style={{ fontSize: 13 }}>{MODULES.find(m => m.id === activeModule)?.icon}</span>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{currentLabel}</span>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 10, color: '#5a7a6a' }}>{mode === 'cloud' ? '☁️ DeepSeek' : '💻 Ollama'}</span>
              <button onClick={() => bus.emit(EVENTS.GENERATE, { title: `${currentLabel}分析图表`, type: 'line' }, 'toolbar')}
                style={{ padding: '3px 10px', fontSize: 11, background: '#2d7a5f', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
                📊 生成图表
              </button>
            </div>
          </header>

          {/* 中央 [对话 | 画布] 可拖拽分栏 */}
          <div style={{ flex: 1, minHeight: 0 }}>
            <SplitPane
              id="main-split"
              direction="horizontal"
              initialRatio={35}
              leftLabel={chatCollapsed ? '' : '💬 对话'}
              rightLabel="🎨 画布"
              leftCollapsed={chatCollapsed}
              onLeftToggle={() => setChatCollapsed(!chatCollapsed)}
              left={<ChatPane module={activeModule} />}
              right={<CanvasPanel moduleLabel={currentLabel} />}
              minRatio={20}
              maxRatio={60}
            />
          </div>
        </main>

        {/* 右侧活动栏（文档/浏览器/产出/地图） */}
        <ActivityPanel collapsed={activityCollapsed} onToggle={() => setActivityCollapsed(!activityCollapsed)} />
      </div>

      {/* 底部命令中心（全宽横条） */}
      <CommandCenter status={status} mode={mode} moduleContext={currentLabel} onReconnect={refresh} />
    </div>
  )
}

// ─── 左侧导航 ─────────────────────────────
function SideNav({ collapsed, setNavCollapsed, mode, setMode, activeModule, navigate }: any) {
  return (
    <aside style={{
      width: 150, background: '#0f1a0f', borderRight: '1px solid #1a2f1a',
      display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden'
    }}>
      <div style={{ padding: '10px 12px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 15 }}>🌿</span>
        <span style={{ fontWeight: 700, color: '#5ae0a0', whiteSpace: 'nowrap', fontSize: 12 }}>ECO AGENT</span>
        <button onClick={() => setNavCollapsed(true)} style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: '#5a7a6a', cursor: 'pointer', fontSize: 10 }}>◀</button>
      </div>
      <div style={{ padding: '6px 8px', borderBottom: '1px solid #1a2f1a' }}>
        <div style={{ display: 'flex', background: '#1a2f1a', borderRadius: 6, padding: 2, gap: 2 }}>
          {(['cloud', 'local'] as Mode[]).map(m => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, padding: '3px 0', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 10,
              background: mode === m ? '#2d7a5f' : 'transparent', color: mode === m ? '#fff' : '#5a7a6a'
            }}>{m === 'cloud' ? '☁️' : '💻'}{m === 'cloud' ? '云' : '本'}</button>
          ))}
        </div>
      </div>
      <nav style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {MODULES.map(m => (
          <button key={m.id} onClick={() => navigate(m.id)} style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%',
            padding: '8px 10px', border: 'none', background: activeModule === m.id ? '#1a2f1a' : 'transparent',
            color: activeModule === m.id ? '#5ae0a0' : '#8a9a8a', cursor: 'pointer', fontSize: 12,
            borderLeft: activeModule === m.id ? '3px solid #5ae0a0' : '3px solid transparent'
          }}>
            <span style={{ fontSize: 13 }}>{m.icon}</span>
            <span style={{ whiteSpace: 'nowrap' }}>{m.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  )
}

// ─── 对话面板 ─────────────────────────────
function ChatPane({ module }: { module: ModuleId }) {
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([
    { role: 'assistant', content: '已打开案卷，正在评查。发现的问题会标注出来。您可以通过底部命令中心提问。' }
  ])
  const [loading, setLoading] = useState(false)
  const endRef = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  React.useEffect(() => {
    const off = bus.on('chat-request', async (e) => {
      const text = e.payload?.text || ''
      if (!text) return
      setMessages(prev => [...prev, { role: 'user', content: text }])
      setLoading(true)
      try {
        const reply = await chat([...messages, { role: 'user' as const, content: text }])
        setMessages(prev => [...prev, { role: 'assistant', content: reply }])
      } catch (err: any) {
        setMessages(prev => [...prev, { role: 'assistant', content: `[错误] ${err.message}` }])
      }
      setLoading(false)
    })
    return () => off()
  }, [messages])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: '10px' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 8, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '92%', padding: '8px 10px', borderRadius: 10, fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? '#1a2f1a' : '#0f1a0f',
              border: m.role === 'assistant' ? '1px solid #1a2f1a' : 'none'
            }}>{m.content}</div>
          </div>
        ))}
        {loading && <div style={{ color: '#5a7a6a', fontSize: 11 }}>思考中...</div>}
        <div ref={endRef} />
      </div>
    </div>
  )
}
