// App.tsx — ECO AGENT Desktop 主框架
// 布局：左导航 | [中央: 对话框 | 文档编辑栏] | 右情报面板 | 底命令中心
// 核心：审核文档在对话框右侧的编辑栏打开

import React, { useState, useEffect, useRef } from 'react'
import CommandCenter from './components/CommandCenter'
import RightPanel from './components/RightPanel'
import { bus, EVENTS } from './events'
import { checkServer, chat } from './api'

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

// ─── 打开的文档（审核文档列表）──────────────────
interface OpenDoc {
  id: string
  name: string        // 文件名
  type: 'docx' | 'pdf' | 'xlsx' | 'md'
  module: string      // 所属模块
  active: boolean
}

export default function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>('enforcement')
  const [mode, setMode] = useState<Mode>('cloud')
  const [collapsed, setCollapsed] = useState(false)
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  async function refresh() {
    setStatus('connecting')
    const ok = await checkServer()
    setStatus(ok ? 'connected' : 'disconnected')
  }
  useEffect(() => { refresh() }, [])

  const currentLabel = MODULES.find(m => m.id === activeModule)?.label || ''

  return (
    <div style={{ height: '100vh', display: 'flex', background: '#0a0f0a', color: '#e0eae0', fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif" }}>
      {/* 左侧导航 */}
      <SideNav collapsed={collapsed} setCollapsed={setCollapsed} mode={mode} setMode={setMode}
        activeModule={activeModule} navigate={setActiveModule} />

      {/* 中央工作区 = [对话框 | 文档编辑栏] */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <header style={{ padding: '8px 16px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span style={{ fontSize: 15 }}>{MODULES.find(m => m.id === activeModule)?.icon}</span>
          <span style={{ fontWeight: 600 }}>{currentLabel}</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#5a7a6a' }}>{mode === 'cloud' ? '☁️ DeepSeek' : '💻 Ollama'}</span>
        </header>
        <WorkArea module={activeModule} />
      </main>

      {/* 右侧情报面板 */}
      <RightPanel moduleContext={currentLabel} />

      {/* 底部命令中心 */}
      <CommandCenter status={status} mode={mode} moduleContext={currentLabel} onReconnect={refresh} />
    </div>
  )
}

// ─── 左侧导航 ─────────────────────────────────
function SideNav({ collapsed, setCollapsed, mode, setMode, activeModule, navigate }: any) {
  return (
    <aside style={{
      width: collapsed ? 52 : 160, transition: 'width .2s', background: '#0f1a0f',
      borderRight: '1px solid #1a2f1a', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden'
    }}>
      <div style={{ padding: '12px 12px', borderBottom: '1px solid #1a2f1a', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 16 }}>🌿</span>
        {!collapsed && <span style={{ fontWeight: 700, color: '#5ae0a0', whiteSpace: 'nowrap', fontSize: 13 }}>ECO AGENT</span>}
      </div>
      <div style={{ padding: '6px 8px', borderBottom: '1px solid #1a2f1a' }}>
        <div style={{ display: 'flex', background: '#1a2f1a', borderRadius: 6, padding: 2, gap: 2 }}>
          {(['cloud', 'local'] as Mode[]).map(m => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, padding: '3px 0', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 10,
              background: mode === m ? '#2d7a5f' : 'transparent', color: mode === m ? '#fff' : '#5a7a6a'
            }}>{m === 'cloud' ? '☁️' : '💻'}{!collapsed && (m === 'cloud' ? '云' : '本')}</button>
          ))}
        </div>
      </div>
      <nav style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {MODULES.map(m => (
          <button key={m.id} onClick={() => navigate(m.id)} style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%',
            padding: '8px 12px', border: 'none', background: activeModule === m.id ? '#1a2f1a' : 'transparent',
            color: activeModule === m.id ? '#5ae0a0' : '#8a9a8a', cursor: 'pointer', fontSize: 12,
            borderLeft: activeModule === m.id ? '3px solid #5ae0a0' : '3px solid transparent'
          }}>
            <span style={{ fontSize: 14 }}>{m.icon}</span>
            {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{m.label}</span>}
          </button>
        ))}
      </nav>
      <button onClick={() => setCollapsed(!collapsed)} style={{
        padding: '8px', border: 'none', borderTop: '1px solid #1a2f1a',
        background: 'transparent', color: '#5a7a6a', cursor: 'pointer', fontSize: 11
      }}>{collapsed ? '→' : '←'}</button>
    </aside>
  )
}

// ─── 中央工作区：[对话框 | 文档编辑栏] ───────────
function WorkArea({ module }: { module: ModuleId }) {
  const [openDocs, setOpenDocs] = useState<OpenDoc[]>([])
  const [activeDoc, setActiveDoc] = useState<string | null>(null)

  // 模拟初始文档（不同模块不同文档）
  useEffect(() => {
    const moduleDocs: Record<ModuleId, OpenDoc[]> = {
      enforcement: [
        { id: 'd1', name: 'XX公司超标排放案.docx', type: 'docx', module: 'enforcement', active: true },
        { id: 'd2', name: '询问笔录.docx', type: 'docx', module: 'enforcement', active: false },
        { id: 'd3', name: '监测报告.pdf', type: 'pdf', module: 'enforcement', active: false },
        { id: 'd4', name: '处罚决定书.docx', type: 'docx', module: 'enforcement', active: false },
      ],
      eia: [
        { id: 'e1', name: 'XX化工环评报告.docx', type: 'docx', module: 'eia', active: true },
        { id: 'e2', name: '排污许可申请表.docx', type: 'docx', module: 'eia', active: false },
        { id: 'e3', name: '工程分析章节.pdf', type: 'pdf', module: 'eia', active: false },
      ],
      chat: [], calendar: [], airtrace: [], monitor: [], gov: [], knowledge: [], mcp: [],
    }
    const docs = moduleDocs[module] || []
    setOpenDocs(docs)
    setActiveDoc(docs.find(d => d.active)?.id || null)
  }, [module])

  // 订阅事件：打开文档
  useEffect(() => {
    const off = bus.on(EVENTS.OPEN_DOC, (e) => {
      const doc = e.payload as OpenDoc
      setOpenDocs(prev => prev.some(d => d.id === doc.id) ? prev : [...prev, doc])
      setActiveDoc(doc.id)
    })
    return () => off()
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
      {/* 左：对话框 */}
      <div style={{ width: '38%', minWidth: 320, borderRight: '1px solid #1a2f1a', display: 'flex', flexDirection: 'column' }}>
        <ChatPane module={module} />
      </div>

      {/* 右：文档编辑栏 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* 文档标签栏 */}
        {openDocs.length > 0 && (
          <div style={{ display: 'flex', borderBottom: '1px solid #1a2f1a', background: '#0d150d', overflowX: 'auto' }}>
            {openDocs.map(d => (
              <button key={d.id} onClick={() => setActiveDoc(d.id)} style={{
                padding: '6px 14px', border: 'none', borderRight: '1px solid #1a2f1a', cursor: 'pointer', whiteSpace: 'nowrap',
                background: activeDoc === d.id ? '#1a2f1a' : 'transparent',
                color: activeDoc === d.id ? '#5ae0a0' : '#8a9a8a', fontSize: 12
              }}>
                📄 {d.name}
                <span style={{ marginLeft: 6, cursor: 'pointer', opacity: 0.6 }} onClick={(e) => { e.stopPropagation(); setOpenDocs(prev => prev.filter(x => x.id !== d.id)) }}>×</span>
              </button>
            ))}
          </div>
        )}
        {/* 文档编辑器（ONLYOFFICE 占位） */}
        <div style={{ flex: 1, overflow: 'auto', padding: activeDoc ? 0 : 40, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10 }}>
          {activeDoc ? (
            <div style={{ width: '100%', height: '100%' }}>
              {/* 模拟 ONLYOFFICE 编辑区 */}
              <div style={{ background: '#111811', padding: '16px 40px', height: '100%', overflow: 'auto', color: '#d0d8d0' }}>
                <div style={{ color: '#5a7a6a', fontSize: 11, marginBottom: 12 }}>
                  正在编辑: {openDocs.find(d => d.id === activeDoc)?.name} · ONLYOFFICE 将在此嵌入
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 16, color: '#e0eae0' }}>
                  {openDocs.find(d => d.id === activeDoc)?.name.replace(/\.[^.]+$/, '')}
                </div>
                <div style={{ fontSize: 13, lineHeight: 2, color: '#b0b8b0' }}>
                  <p>一、案件基本情况</p>
                  <p>当事人：XX化工有限公司</p>
                  <p>统一社会信用代码：91431300XXXXXXXXXX</p>
                  <p>地址：娄底市XX区XX路XX号</p>
                  <p>&nbsp;</p>
                  <p>二、违法事实</p>
                  <p>2026年6月12日，我局执法人员对该公司进行现场检查，发现其废气排放口</p>
                  <p>二氧化硫浓度为<span style={{ color: '#f0a040' }}>450mg/m³</span>，超过《钢铁烧结、球团工业大气污染物排放标准》</p>
                  <p>（GB 28662-2012）表1限值（<span style={{ color: '#f0a040' }}>200mg/m³</span>），超标125%。</p>
                  <p>&nbsp;</p>
                  <p>三、现场检查情况</p>
                  <p>检查时，该公司正在生产，污染防治设施<span style={{ color: '#f04040' }}>未正常运行</span>。</p>
                  <p>&nbsp;</p>
                  <p>四、证据材料</p>
                  <p>1. 现场检查（勘察）笔录 1 份；</p>
                  <p>2. 调查询问笔录 2 份；</p>
                  <p>3. 监测报告 1 份（编号：娄环监字[2026]第XXX号）；</p>
                  <p>4. 现场照片、影像资料 1 套。</p>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div style={{ fontSize: 36 }}>📄</div>
              <div style={{ color: '#5a7a6a', fontSize: 13 }}>没有打开的文档</div>
              <div style={{ color: '#2a5a3a', fontSize: 11 }}>在左侧对话中要求打开文档，或在模块列表中选择</div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── 对话框（AI 对话）───────────────────────
function ChatPane({ module }: { module: ModuleId }) {
  const [messages, setMessages] = useState([
    { role: 'assistant' as const, content: `我已打开案卷，正在评查。发现的问题会在右侧标注。您可以直接问我："第几页有什么问题"、"这家企业以前被罚过吗"。` }
  ])
  const [loading, setLoading] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // 接收底部命令中心的对话请求
  useEffect(() => {
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
      <div style={{ padding: '8px 14px', borderBottom: '1px solid #1a2f1a', fontSize: 12, color: '#5a7a6a' }}>
        💬 对话 · {MODULES.find(m => m.id === module)?.label}
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '12px' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 10, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '92%', padding: '8px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? '#1a2f1a' : '#0f1a0f',
              border: m.role === 'assistant' ? '1px solid #1a2f1a' : 'none'
            }}>{m.content}</div>
          </div>
        ))}
        {loading && <div style={{ color: '#5a7a6a', fontSize: 12 }}>思考中...</div>}
        <div ref={endRef} />
      </div>
    </div>
  )
}
