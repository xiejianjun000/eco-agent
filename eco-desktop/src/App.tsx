import React, { useState, useEffect } from 'react'

// ─── 模块导航 ─────────────────────────────
const MODULES = [
  { id: 'chat', icon: '💬', label: '对话' },
  { id: 'calendar', icon: '📅', label: '日历' },
  { id: 'enforcement', icon: '⚖️', label: '执法督察' },
  { id: 'eia', icon: '📋', label: '环评排污许可' },
  { id: 'airtrace', icon: '🌪️', label: '大气溯源预测' },
  { id: 'monitor', icon: '📊', label: '环境监测' },
  { id: 'gov', icon: '🏛️', label: '政务' },
  { id: 'knowledge', icon: '📚', label: '知识库' },
  { id: 'mcp', icon: '🔌', label: 'MCP连接' },
]

// ─── 模式状态 ─────────────────────────────
type Mode = 'cloud' | 'local'

export default function App() {
  const [activeModule, setActiveModule] = useState('chat')
  const [mode, setMode] = useState<Mode>('cloud')
  const [collapsed, setCollapsed] = useState(false)
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  useEffect(() => {
    checkConnection()
  }, [])

  async function checkConnection() {
    setStatus('connecting')
    try {
      const res = await fetch('http://127.0.0.1:8000/v1/models')
      setStatus(res.ok ? 'connected' : 'disconnected')
    } catch {
      setStatus('disconnected')
    }
  }

  return (
    <div style={{ height: '100vh', display: 'flex', background: '#0a0f0a', color: '#e0eae0', fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif" }}>
      {/* 左侧导航 */}
      <aside style={{
        width: collapsed ? 56 : 180, transition: 'width .2s', background: '#0f1a0f',
        borderRight: '1px solid #1a2f1a', display: 'flex', flexDirection: 'column',
        overflow: 'hidden', flexShrink: 0
      }}>
        {/* Logo */}
        <div style={{ padding: '14px 16px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 20 }}>🌿</span>
          {!collapsed && <span style={{ fontWeight: 700, color: '#5ae0a0', whiteSpace: 'nowrap' }}>ECO AGENT</span>}
        </div>

        {/* 本地/云端切换 */}
        <div style={{ padding: '10px 12px', borderBottom: '1px solid #1a2f1a' }}>
          <div style={{
            display: 'flex', background: '#1a2f1a', borderRadius: 6, padding: 3, gap: 2
          }}>
            {(['cloud', 'local'] as Mode[]).map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: '4px 0', borderRadius: 4, border: 'none', cursor: 'pointer',
                background: mode === m ? '#2d7a5f' : 'transparent',
                color: mode === m ? '#fff' : '#5a7a6a', fontSize: 11
              }}>
                {m === 'cloud' ? '☁️ 云端' : '💻 本地'}
              </button>
            ))}
          </div>
          {!collapsed && <div style={{ fontSize: 10, color: '#5a7a6a', marginTop: 4, textAlign: 'center' }}>
            {mode === 'cloud' ? 'DeepSeek API' : 'Ollama 本地模型'}
          </div>}
        </div>

        {/* 模块导航 */}
        <nav style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
          {MODULES.map(m => (
            <button key={m.id} onClick={() => setActiveModule(m.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%',
              padding: '10px 16px', border: 'none', background: activeModule === m.id ? '#1a2f1a' : 'transparent',
              color: activeModule === m.id ? '#5ae0a0' : '#8a9a8a', cursor: 'pointer', fontSize: 13,
              borderLeft: activeModule === m.id ? '3px solid #5ae0a0' : '3px solid transparent'
            }}>
              <span style={{ fontSize: 16 }}>{m.icon}</span>
              {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{m.label}</span>}
            </button>
          ))}
        </nav>

        {/* 折叠按钮 */}
        <button onClick={() => setCollapsed(!collapsed)} style={{
          padding: '10px', border: 'none', borderTop: '1px solid #1a2f1a',
          background: 'transparent', color: '#5a7a6a', cursor: 'pointer', fontSize: 12
        }}>
          {collapsed ? '→' : '← 折叠'}
        </button>
      </aside>

      {/* 主工作区 */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* 顶部工具栏 */}
        <header style={{
          padding: '10px 20px', borderBottom: '1px solid #1a2f1a',
          display: 'flex', alignItems: 'center', gap: 12
        }}>
          <span style={{ fontWeight: 600 }}>
            {MODULES.find(m => m.id === activeModule)?.icon}{' '}
            {MODULES.find(m => m.id === activeModule)?.label}
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: status === 'connected' ? '#4cd28a' : status === 'connecting' ? '#f0c040' : '#f04040' }} />
            <span style={{ color: '#5a7a6a', fontSize: 11 }}>
              {status === 'connected' ? '已连接' : status === 'connecting' ? '连接中' : '未连接'}
            </span>
            <button onClick={checkConnection} style={{
              background: '#1a2f1a', border: 'none', color: '#5ae0a0', padding: '3px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 11
            }}>重连</button>
            <button style={{
              background: '#2d7a5f', border: 'none', color: '#fff', padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 11
            }}>生成报告</button>
          </div>
        </header>

        {/* 模块内容 */}
        <section style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          <ModuleView module={activeModule} />
        </section>

        {/* 底部状态栏 */}
        <footer style={{
          padding: '6px 20px', borderTop: '1px solid #1a2f1a', color: '#5a7a6a', fontSize: 11,
          display: 'flex', gap: 16
        }}>
          <span>🤖 智能体: 待命</span>
          <span>🔧 工具: 113</span>
          <span>🔄 同步: 正常</span>
          <span style={{ marginLeft: 'auto' }}>模式: {mode === 'cloud' ? '云端' : '本地'}</span>
        </footer>
      </main>
    </div>
  )
}

// ─── 模块视图 ─────────────────────────────
function ModuleView({ module }: { module: string }) {
  // 每个模块一个可加载的子组件
  const views: Record<string, () => React.ReactElement> = {
    chat: () => <ChatModule />,
    calendar: () => <Placeholder title="📅 日历" desc="智能体值班推送日程将显示在这里" />,
    enforcement: () => <Placeholder title="⚖️ 执法督察" desc="案卷评查：ONLYOFFICE 文档 + 卫星地图 + 证据链" />,
    eia: () => <Placeholder title="📋 环评排污许可" desc="报告审查：编辑器 + 标准匹配 + 污染预测" />,
    airtrace: () => <Placeholder title="🌪️ 大气溯源预测" desc="Cesium 地图 + 风场粒子 + 后向轨迹" />,
    monitor: () => <Placeholder title="📊 环境监测" desc="实时看板：CNEMC 数据 + 地图点位" />,
    gov: () => <Placeholder title="🏛️ 政务" desc="内置浏览器访问政务平台" />,
    knowledge: () => <Placeholder title="📚 知识库" desc="Obsidian Vault 集成" />,
    mcp: () => <Placeholder title="🔌 MCP连接" desc="工具与平台代理管理" />,
  }
  return views[module]?.() ?? <Placeholder title="?" desc="" />
}

// 占位模块
function Placeholder({ title, desc }: { title: string; desc: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12 }}>
      <div style={{ fontSize: 40 }}>{title.split(' ')[0]}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#8ae0b8' }}>{title}</div>
      <div style={{ fontSize: 13, color: '#5a7a6a' }}>{desc}</div>
      <div style={{ fontSize: 11, color: '#2a5a3a', marginTop: 8 }}>骨架已就绪 · 模块深化开发中</div>
    </div>
  )
}

// 对话模块（先可用）
function ChatModule() {
  const [messages, setMessages] = useState([
    { role: 'assistant' as const, content: '你好！我是 ECO AGENT，生态环境法规 AI 助手。有什么可以帮您？' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function send() {
    if (!input.trim() || loading) return
    const msg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user' as const, content: msg }])
    setLoading(true)
    try {
      const res = await fetch('http://127.0.0.1:8000/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [...messages, { role: 'user', content: msg }], stream: false })
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant' as const, content: data.choices?.[0]?.message?.content || '' }])
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant' as const, content: `[连接错误] ${e.message}` }])
    }
    setLoading(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
            <div style={{
              maxWidth: '80%', padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? '#1a2f1a' : '#0f1a0f',
              border: m.role === 'assistant' ? '1px solid #1a2f1a' : 'none'
            }}>{m.content}</div>
          </div>
        ))}
        {loading && <div style={{ color: '#5a7a6a', fontSize: 12 }}>思考中...</div>}
      </div>
      <div style={{ display: 'flex', gap: 8, padding: 8 }}>
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="输入问题..."
          style={{ flex: 1, padding: '10px', borderRadius: 8, border: '1px solid #1a2f1a', background: '#0f1a0f', color: '#e0eae0', fontSize: 14, outline: 'none' }} />
        <button onClick={send} disabled={loading || !input.trim()}
          style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: loading ? '#1a2f1a' : '#2d7a5f', color: '#fff', cursor: 'pointer' }}>
          发送
        </button>
      </div>
    </div>
  )
}
