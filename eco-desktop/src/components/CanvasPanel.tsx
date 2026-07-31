// CanvasPanel.tsx — 中央画布面板
// 生成分析图表、可视化数据、展示地图分析结果

import React, { useState } from 'react'
import { bus, EVENTS } from '../events'

interface Chart {
  id: string
  title: string
  type: 'line' | 'bar' | 'pie' | 'scatter' | 'map'
  data: string
}

export default function CanvasPanel({ moduleLabel }: { moduleLabel: string }) {
  const [charts, setCharts] = useState<Chart[]>([])
  const [activeChart, setActiveChart] = useState<string | null>(null)

  // 订阅：AI 生成图表请求
  React.useEffect(() => {
    const off = bus.on(EVENTS.GENERATE, (e) => {
      const c: Chart = {
        id: e.traceId,
        title: e.payload?.title || '分析图表',
        type: e.payload?.type || 'line',
        data: e.payload?.data || '',
      }
      setCharts(prev => [...prev, c])
      setActiveChart(c.id)
    })
    return () => off()
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0f0a' }}>
      {/* 画布工具栏 */}
      <div style={{ display: 'flex', gap: 6, padding: '6px 10px', borderBottom: '1px solid #1a2f1a', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#5a7a6a' }}>🎨 画布 · {moduleLabel}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {(['line', 'bar', 'pie', 'scatter'] as const).map(t => (
            <button key={t} onClick={() => {
              const c: Chart = { id: `c${Date.now()}`, title: `${t} 图表`, type: t, data: 'mock' }
              setCharts(prev => [...prev, c]); setActiveChart(c.id)
            }} style={{ padding: '3px 8px', fontSize: 10, background: '#1a2f1a', color: '#8ae0b8', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
              {t === 'line' ? '📈 折线' : t === 'bar' ? '📊 柱状' : t === 'pie' ? '🍩 饼图' : '✨ 散点'}
            </button>
          ))}
          <button style={{ padding: '3px 8px', fontSize: 10, background: 'transparent', color: '#5a7a6a', border: '1px solid #1a2f1a', borderRadius: 4, cursor: 'pointer' }}>清空</button>
        </div>
      </div>

      {/* 图表标签栏 */}
      {charts.length > 0 && (
        <div style={{ display: 'flex', borderBottom: '1px solid #1a2f1a', overflowX: 'auto' }}>
          {charts.map(c => (
            <button key={c.id} onClick={() => setActiveChart(c.id)} style={{
              padding: '5px 12px', border: 'none', borderRight: '1px solid #1a2f1a', cursor: 'pointer', whiteSpace: 'nowrap',
              background: activeChart === c.id ? '#1a2f1a' : 'transparent',
              color: activeChart === c.id ? '#5ae0a0' : '#8a9a8a', fontSize: 11
            }}>
              {c.title}
              <span style={{ marginLeft: 6, opacity: 0.5 }} onClick={(e) => { e.stopPropagation(); setCharts(prev => prev.filter(x => x.id !== c.id)) }}>×</span>
            </button>
          ))}
        </div>
      )}

      {/* 画布主体 */}
      <div style={{ flex: 1, overflow: 'auto', padding: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {activeChart ? (
          <ChartRenderer chart={charts.find(c => c.id === activeChart)!} />
        ) : (
          <div style={{ textAlign: 'center', color: '#3a5a4a' }}>
            <div style={{ fontSize: 32 }}>🖼️</div>
            <div style={{ fontSize: 13, marginTop: 8 }}>空白画布</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>点击上方按钮生成分析图表，或让 AI 生成可视化</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── 图表渲染器（简化实现，后续接 ECharts）────
function ChartRenderer({ chart }: { chart: Chart }) {
  const { title, type } = chart
  const data = [42, 38, 55, 61, 48, 72, 65, 58]

  const colors = ['#5ae0a0', '#4cd28a', '#3a8a6f', '#2d7a5f', '#7ae0b8', '#8ae0c0', '#f0a040', '#f0c040']

  return (
    <div style={{ width: '90%', maxWidth: 600, background: '#111811', borderRadius: 12, padding: 16, border: '1px solid #1a2f1a' }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#8ae0b8', marginBottom: 12 }}>{title}</div>

      {type === 'line' && (
        <svg viewBox="0 0 300 120" style={{ width: '100%' }}>
          <polyline
            points={data.map((v, i) => `${i * 42},${120 - v}`).join(' ')}
            fill="none" stroke="#5ae0a0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          />
          {data.map((v, i) => (
            <circle key={i} cx={i * 42} cy={120 - v} r="3" fill="#7ae0b8" />
          ))}
        </svg>
      )}
      {type === 'bar' && (
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 120 }}>
          {data.map((v, i) => (
            <div key={i} style={{
              flex: 1, height: `${v}%`, background: colors[i % colors.length],
              borderRadius: '4px 4px 0 0', minWidth: 20, position: 'relative',
            }}>
              <span style={{ position: 'absolute', top: -18, left: '50%', transform: 'translateX(-50%)', fontSize: 9, color: '#5a7a6a' }}>{v}</span>
            </div>
          ))}
        </div>
      )}
      {type === 'pie' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <svg viewBox="0 0 100 100" width="120" height="120">
            <circle cx="50" cy="50" r="40" fill="none" stroke={colors[0]} strokeWidth="20" strokeDasharray="100 251" strokeLinecap="butt" transform="rotate(-90 50 50)" />
            <circle cx="50" cy="50" r="40" fill="none" stroke={colors[1]} strokeWidth="20" strokeDasharray="60 251" strokeDashoffset="-100" strokeLinecap="butt" transform="rotate(-90 50 50)" />
            <circle cx="50" cy="50" r="40" fill="none" stroke={colors[2]} strokeWidth="20" strokeDasharray="50 251" strokeDashoffset="-160" strokeLinecap="butt" transform="rotate(-90 50 50)" />
          </svg>
          <div>
            {['污染源A', '污染源B', '其他'].map((l, i) => (
              <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 4, color: '#b0b8b0' }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: colors[i] }} />
                {l} · {[40, 25, 35][i]}%
              </div>
            ))}
          </div>
        </div>
      )}
      {type === 'scatter' && (
        <svg viewBox="0 0 300 120" style={{ width: '100%' }}>
          {data.map((v, i) => (
            <circle key={i} cx={i * 42 + 10} cy={120 - v - Math.sin(i * 1.7) * 20} r="4" fill={colors[i % colors.length]} opacity="0.8" />
          ))}
        </svg>
      )}

      <div style={{ fontSize: 10, color: '#2a5a3a', marginTop: 8, textAlign: 'center' }}>
        数据来源: 环境监测 · 模拟数据演示 · 接入 ECharts 后显示真实图表
      </div>
    </div>
  )
}
