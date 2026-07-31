// App.tsx — ECO AGENT Desktop 主框架
// G6 职责分离：UI 层 / 服务层 / 状态管理层解耦
// 布局：左导航 + 中央工作区 + 右情报面板 + 底命令中心

import React, { useState, useEffect } from 'react'
import CommandCenter from './components/CommandCenter'
import RightPanel from './components/RightPanel'
import { bus, EVENTS } from './events'
import { checkServer, chat } from './api'

// ─── 模块注册表（G2 单一职责）─────────────────
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
  const [activeModule, setActiveModule] = useState<ModuleId>('chat')
  const [mode, setMode] = useState<Mode>('cloud')
  const [collapsed, setCollapsed] = useState(false)
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  async function refresh() {
    setStatus('connecting')
    const ok = await checkServer()
    setStatus(ok ? 'connected' : 'disconnected')
  }

  useEffect(() => { refresh() }, [])

  // 模块导航通过事件总线广播
  function navigate(id: ModuleId) {
    setActiveModule(id)
    bus.emit(EVENTS.NAVIGATE, { module: id }, 'nav')
  }

  const currentLabel = MODULES.find(m => m.id === activeModule)?.label || ''

  return (
    <div style={{ height: '100vh', display: 'flex', background: '#0a0f0a', color: '#e0eae0', fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif" }}>
      {/* 左侧导航 */}
      <aside style={{
        width: collapsed ? 56 : 170, transition: 'width .2s', background: '#0f1a0f',
        borderRight: '1px solid #1a2f1a', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden'
      }}>
        <div style={{ padding: '14px 14px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18 }}>🌿</span>
          {!collapsed && <span style={{ fontWeight: 700, color: '#5ae0a0', whiteSpace: 'nowrap' }}>ECO AGENT</span>}
        </div>

        {/* 模式开关 */}
        <div style={{ padding: '8px 10px', borderBottom: '1px solid #1a2f1a' }}>
          <div style={{ display: 'flex', background: '#1a2f1a', borderRadius: 6, padding: 3, gap: 2 }}>
            {(['cloud', 'local'] as Mode[]).map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: '4px 0', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 10,
                background: mode === m ? '#2d7a5f' : 'transparent', color: mode === m ? '#fff' : '#5a7a6a'
              }}>{m === 'cloud' ? '☁️' : '💻'}{!collapsed && (m === 'cloud' ? ' 云端' : ' 本地')}</button>
            ))}
          </div>
        </div>

        {/* 模块导航 */}
        <nav style={{ flex: 1, overflow: 'auto', padding: '6px 0' }}>
          {MODULES.map(m => (
            <button key={m.id} onClick={() => navigate(m.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%',
              padding: '9px 14px', border: 'none', background: activeModule === m.id ? '#1a2f1a' : 'transparent',
              color: activeModule === m.id ? '#5ae0a0' : '#8a9a8a', cursor: 'pointer', fontSize: 13,
              borderLeft: activeModule === m.id ? '3px solid #5ae0a0' : '3px solid transparent'
            }}>
              <span style={{ fontSize: 15 }}>{m.icon}</span>
              {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{m.label}</span>}
            </button>
          ))}
        </nav>

        <button onClick={() => setCollapsed(!collapsed)} style={{
          padding: '10px', border: 'none', borderTop: '1px solid #1a2f1a',
          background: 'transparent', color: '#5a7a6a', cursor: 'pointer', fontSize: 12
        }}>{collapsed ? '→' : '←'}</button>
      </aside>

      {/* 中央工作区 */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* 模块头部 */}
        <header style={{ padding: '10px 20px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16 }}>{MODULES.find(m => m.id === activeModule)?.icon}</span>
          <span style={{ fontWeight: 600 }}>{currentLabel}</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#5a7a6a' }}>{mode === 'cloud' ? 'DeepSeek API' : 'Ollama 本地'}</span>
        </header>

        {/* 工作区内容 */}
        <section style={{ flex: 1, overflow: 'auto' }}>
          <ModuleView module={activeModule} />
        </section>
      </main>

      {/* 右侧情报面板 */}
      <RightPanel moduleContext={currentLabel} />

      {/* 底部命令中心 */}
      <CommandCenter status={status} mode={mode} moduleContext={currentLabel} onReconnect={refresh} />
    </div>
  )
}

// ─── 模块视图（G2 单一职责，每个模块独立实现）────
function ModuleView({ module }: { module: ModuleId }) {
  const views: Record<ModuleId, () => React.ReactElement> = {
    chat: () => <ChatModule />,
    calendar: () => <Placeholder icon="📅" title="日历" desc="智能体值班推送日程" />,
    enforcement: () => <Placeholder icon="⚖️" title="执法督察" desc="案卷评查：文档 + 地图 + 证据链" />,
    eia: () => <Placeholder icon="📋" title="环评排污许可" desc="报告审查：编辑器 + 标准匹配" />,
    airtrace: () => <Placeholder icon="🌪️" title="大气溯源预测" desc="Cesium 地图 + 风场 + 轨迹" />,
    monitor: () => <Placeholder icon="📊" title="环境监测" desc="CNEMC 实时看板 + 地图点位" />,
    gov: () => <Placeholder icon="🏛️" title="政务" desc="内置浏览器访问政务平台" />,
    knowledge: () => <Placeholder icon="📚" title="知识库" desc="Obsidian Vault 集成" />,
    mcp: () => <Placeholder icon="🔌" title="MCP连接" desc="工具与平台代理管理" />,
  }
  return views[module]?.() ?? <Placeholder icon="?" title="" desc="" />
}

function Placeholder({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
      <div style={{ fontSize: 44 }}>{icon}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#8ae0b8' }}>{title}</div>
      <div style={{ fontSize: 13, color: '#5a7a6a' }}>{desc}</div>
      <div style={{ fontSize: 11, color: '#2a5a3a', marginTop: 8 }}>模块骨架已就绪 · 深化开发中</div>
    </div>
  )
}

// ─── 对话模块（P0 可用）──────────────────────
function ChatModule() {
  const [messages, setMessages] = useState([
    { role: 'assistant' as const, content: '你好！我是 ECO AGENT。请通过底部命令中心与我对话，或选择左侧模块开始专业工作。' }
  ])
  const [loading, setLoading] = useState(false)

  // 订阅命令中心发来的对话请求
  useEffect(() => {
    const off = bus.on('chat-request', async (e) => {
      const text = e.payload?.text || ''
      if (!text) return
      setLoading(true)
      setMessages(prev => [...prev, { role: 'user', content: text }])
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
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 10, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '80%', padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? '#1a2f1a' : '#0f1a0f',
              border: m.role === 'assistant' ? '1px solid #1a2f1a' : 'none'
            }}>{m.content}</div>
          </div>
        ))}
        {loading && <div style={{ color: '#5a7a6a', fontSize: 12 }}>思考中...</div>}
      </div>
      <div style={{ padding: '0 16px 12px', fontSize: 11, color: '#3a5a4a', textAlign: 'center' }}>
        提示：使用底部命令中心输入，可全局感知当前模块上下文
      </div>
    </div>
  )
}
