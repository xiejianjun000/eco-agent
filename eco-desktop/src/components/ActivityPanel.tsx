// ActivityPanel.tsx — 右侧活动栏（IDE 风格）
// 多标签：文档编辑器 | 网页浏览器 | 产出物 | 地图画图
// 各标签可切换，面板整体可收缩

import React, { useState } from 'react'
import { bus, EVENTS } from '../events'
import CollaborativeEditor, { AnnotationSidebar, CollaborativeEditorHandle } from './CollaborativeEditor'
import { Annotation } from '../types/annotation'

interface Props {
  collapsed: boolean
  onToggle: () => void
  width?: number
}

type ActivityTab = 'doc' | 'browser' | 'artifact' | 'map'

export default function ActivityPanel({ collapsed, onToggle, width = 380 }: Props) {
  const [tab, setTab] = useState<ActivityTab>('doc')

  // 如果折叠，只显示标签栏
  if (collapsed) {
    return (
      <div style={{ width: 40, borderLeft: '1px solid #1a2f1a', background: '#0d150d', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 8 }}>
        {([
          ['doc', '📝'], ['browser', '🌐'], ['artifact', '📦'], ['map', '🗺️']
        ] as [ActivityTab, string][]).map(([id, icon]) => (
          <button key={id} onClick={() => { setTab(id); onToggle() }} title={id}
            style={{ background: 'transparent', border: 'none', fontSize: 16, padding: '8px 0', cursor: 'pointer', color: tab === id ? '#5ae0a0' : '#5a7a6a' }}>
            {icon}
          </button>
        ))}
        <button onClick={onToggle} title="展开" style={{ background: 'transparent', border: 'none', fontSize: 12, color: '#5a7a6a', cursor: 'pointer', marginTop: 'auto', padding: 10 }}>◀</button>
      </div>
    )
  }

  return (
    <div style={{ width, borderLeft: '1px solid #1a2f1a', background: '#0d150d', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      {/* 标签栏 */}
      <div style={{ display: 'flex', borderBottom: '1px solid #1a2f1a' }}>
        {([
          ['doc', '📝 文档'], ['browser', '🌐 浏览器'], ['artifact', '📦 产出'], ['map', '🗺️ 地图']
        ] as [ActivityTab, string][]).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            flex: 1, padding: '8px 2px', border: 'none', background: tab === id ? '#1a2f1a' : 'transparent',
            color: tab === id ? '#5ae0a0' : '#5a7a6a', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap'
          }}>{label}</button>
        ))}
        <button onClick={onToggle} title="收缩" style={{ padding: '0 8px', background: 'transparent', border: 'none', color: '#5a7a6a', cursor: 'pointer' }}>▶</button>
      </div>

      {/* 内容区 */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {tab === 'doc' && <DocEditorPanel />}
        {tab === 'browser' && <BrowserPanel />}
        {tab === 'artifact' && <ArtifactPanel />}
        {tab === 'map' && <MapPanel />}
      </div>
    </div>
  )
}

// ─── 文档编辑器（人机协同）────────────────
function DocEditorPanel() {
  const [doc, setDoc] = useState<string>('案卷.docx')
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const editorRef = React.useRef<CollaborativeEditorHandle>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  function handleSelect(id: string) {
    setSelectedId(id)
  }

  // 批注侧栏操作 → 调用编辑器命令式方法
  function handleAccept(id: string) {
    editorRef.current?.accept(id)
  }
  function handleReject(id: string) {
    editorRef.current?.reject(id)
  }
  function handleEdit(id: string) {
    setEditingId(id)
    const ann = annotations.find(a => a.id === id)
    if (ann) setEditText(ann.suggestion || ann.originalText)
  }
  function handleAddHuman() {
    editorRef.current?.addHumanAnnotation()
  }

  // 编辑保存
  function saveEdit() {
    // 通过编辑器的 edit + accept 流程处理（简化：直接用编辑器内部逻辑）
    if (editingId && editorRef.current) {
      // 这里简化处理，真实场景需要编辑器暴露 setSuggestionAndAccept
      setEditingId(null)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', borderBottom: '1px solid #1a2f1a', overflowX: 'auto' }}>
        {['案卷.docx', '询问笔录.docx', '监测报告.pdf'].map(d => (
          <button key={d} onClick={() => setDoc(d)} style={{
            padding: '6px 10px', border: 'none', borderRight: '1px solid #1a2f1a', background: doc === d ? '#1a2f1a' : 'transparent',
            color: doc === d ? '#5ae0a0' : '#8a9a8a', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap'
          }}>{d}</button>
        ))}
      </div>
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* 协同编辑器 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <CollaborativeEditor
            ref={editorRef}
            docTitle={doc}
            onAnnotationsChange={setAnnotations}
          />
        </div>
        {/* 批注侧栏 */}
        <AnnotationSidebar
          annotations={annotations}
          selectedAnnId={selectedId}
          onSelect={handleSelect}
          onAccept={handleAccept}
          onReject={handleReject}
          onEdit={handleEdit}
          onAddHuman={handleAddHuman}
        />
      </div>
    </div>
  )
}

// ─── 网页浏览器 ───────────────────────────
function BrowserPanel() {
  const [url, setUrl] = useState('https://www.mee.gov.cn')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', gap: 4, padding: '6px 8px', borderBottom: '1px solid #1a2f1a' }}>
        <input value={url} onChange={e => setUrl(e.target.value)}
          style={{ flex: 1, padding: '4px 8px', borderRadius: 4, border: '1px solid #1a2f1a', background: '#0a0f0a', color: '#e0eae0', fontSize: 11, outline: 'none' }}
          placeholder="输入网址或搜索" />
        <button style={{ background: '#1a2f1a', border: 'none', color: '#5ae0a0', padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 11 }}>前往</button>
      </div>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8, background: '#111811' }}>
        <div style={{ fontSize: 28 }}>🌐</div>
        <div style={{ fontSize: 12, color: '#5a7a6a' }}>内置浏览器将在此显示</div>
        <div style={{ fontSize: 10, color: '#2a5a3a' }}>预置站点: 生态环境部 · 排污许可平台 · 监测总站</div>
      </div>
    </div>
  )
}

// ─── 产出物 ──────────────────────────────
function ArtifactPanel() {
  const [artifacts] = useState([
    { title: '案卷评查意见书.docx', time: '10:23', type: 'doc' },
    { title: '超标浓度分析图表.png', time: '10:25', type: 'chart' },
    { title: '污染扩散模拟图.png', time: '10:28', type: 'map' },
  ])
  return (
    <div style={{ padding: 8 }}>
      {artifacts.map(a => (
        <div key={a.title} style={{ padding: '10px', background: '#0f1a0f', borderRadius: 8, marginBottom: 8, border: '1px solid #1a2f1a' }}>
          <div style={{ fontSize: 12, color: '#8ae0b8', fontWeight: 600 }}>
            {a.type === 'doc' ? '📄' : a.type === 'chart' ? '📊' : '🗺️'} {a.title}
          </div>
          <div style={{ fontSize: 10, color: '#5a7a6a', marginTop: 4 }}>{a.time}</div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button style={{ padding: '3px 8px', fontSize: 10, background: '#1a2f1a', color: '#5ae0a0', border: 'none', borderRadius: 4, cursor: 'pointer' }}>插入文档</button>
            <button style={{ padding: '3px 8px', fontSize: 10, background: 'transparent', color: '#5a7a6a', border: '1px solid #1a2f1a', borderRadius: 4, cursor: 'pointer' }}>下载</button>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── 地图画图 ─────────────────────────────
function MapPanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 绘图工具条 */}
      <div style={{ display: 'flex', gap: 2, padding: '6px 8px', borderBottom: '1px solid #1a2f1a' }}>
        {['✏️点', '📏线', '⬜面', '⭕圆', '📐测距', '🎯标注'].map(t => (
          <button key={t} style={{ padding: '4px 6px', fontSize: 10, background: '#1a2f1a', color: '#8ae0b8', border: 'none', borderRadius: 4, cursor: 'pointer' }}>{t}</button>
        ))}
      </div>
      {/* 地图画布占位 */}
      <div style={{ flex: 1, background: '#0a1a0f', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
        <div style={{ textAlign: 'center', color: '#3a6a4a' }}>
          <div style={{ fontSize: 30 }}>🗺️</div>
          <div style={{ fontSize: 11, marginTop: 6 }}>Cesium 卫星地图 + Terra Draw</div>
          <div style={{ fontSize: 10, color: '#2a5a3a', marginTop: 4 }}>污染范围 · 采样点 · 警戒线</div>
        </div>
        {/* 模拟标注 */}
        <div style={{ position: 'absolute', top: '30%', left: '40%', width: 10, height: 10, borderRadius: '50%', background: '#f04040', boxShadow: '0 0 8px #f04040' }} />
        <div style={{ position: 'absolute', top: '30%', left: '40%', fontSize: 10, color: '#f0a0a0', marginTop: 14, whiteSpace: 'nowrap' }}>污染源</div>
      </div>
    </div>
  )
}
