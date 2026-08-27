// SplitPane.tsx — 可拖拽分栏（IDE 核心交互）
// 支持水平/垂直拖拽调整面板比例，各栏可伸缩

import React, { useState, useRef, useCallback } from 'react'

interface SplitPaneProps {
  id: string
  left: React.ReactNode
  right: React.ReactNode
  direction?: 'horizontal' | 'vertical'  // horizontal=左右分栏, vertical=上下分栏
  initialRatio?: number                  // 初始比例 (0-100)
  leftLabel?: string
  rightLabel?: string
  leftCollapsed?: boolean
  rightCollapsed?: boolean
  onLeftToggle?: () => void
  onRightToggle?: () => void
  minRatio?: number
  maxRatio?: number
}

export default function SplitPane({
  id, left, right, direction = 'horizontal',
  initialRatio = 50, leftLabel = '', rightLabel = '',
  leftCollapsed = false, rightCollapsed = false,
  onLeftToggle, onRightToggle,
  minRatio = 15, maxRatio = 85,
}: SplitPaneProps) {
  const [ratio, setRatio] = useState(initialRatio)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    const startPos = direction === 'horizontal' ? e.clientX : e.clientY
    const startRatio = ratio
    const container = containerRef.current
    if (!container) return
    const size = direction === 'horizontal' ? container.offsetWidth : container.offsetHeight

    const handleMove = (ev: MouseEvent) => {
      const delta = direction === 'horizontal' ? ev.clientX - startPos : ev.clientY - startPos
      const newRatio = startRatio + (delta / size) * 100
      setRatio(Math.max(minRatio, Math.min(maxRatio, newRatio)))
    }
    const handleUp = () => {
      setIsDragging(false)
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
  }, [ratio, direction, minRatio, maxRatio])

  const isRow = direction === 'horizontal'

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        flexDirection: isRow ? 'row' : 'column',
        height: '100%', width: '100%', minWidth: 0, minHeight: 0,
        position: 'relative',
      }}
    >
      {/* 左/上面板 */}
      {!leftCollapsed && (
        <div style={{
          flexBasis: `${ratio}%`, flexGrow: 0, flexShrink: 0,
          minWidth: 0, minHeight: 0, overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}>
          {leftLabel && <PaneHeader label={leftLabel} onToggle={onLeftToggle} collapsed={false} />}
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>{left}</div>
        </div>
      )}

      {/* 拖拽手柄 */}
      {!leftCollapsed && !rightCollapsed && (
        <div
          onMouseDown={handleMouseDown}
          style={{
            cursor: isRow ? 'col-resize' : 'row-resize',
            flexBasis: isRow ? 6 : 6,
            flexGrow: 0, flexShrink: 0,
            background: isDragging ? '#2d7a5f' : '#1a2f1a',
            transition: 'background .15s',
            ...(isRow ? { width: 6, height: '100%' } : { width: '100%', height: 6 }),
          }}
          title="拖拽调整大小"
        />
      )}

      {/* 右/下面板 */}
      {!rightCollapsed && (
        <div style={{
          flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}>
          {rightLabel && <PaneHeader label={rightLabel} onToggle={onRightToggle} collapsed={false} />}
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>{right}</div>
        </div>
      )}

      {/* 全部折叠时的恢复按钮 */}
      {leftCollapsed && (
        <div style={{ width: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0d150d', borderRight: '1px solid #1a2f1a' }}>
          <button onClick={onLeftToggle} title="展开" style={{ background: 'transparent', border: 'none', color: '#5a7a6a', cursor: 'pointer', fontSize: 14 }}>◀</button>
        </div>
      )}
    </div>
  )
}

// ─── 面板头部（含收缩按钮）──────────────────
function PaneHeader({ label, onToggle, collapsed }: { label: string; onToggle?: () => void; collapsed: boolean }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', padding: '4px 10px',
      borderBottom: '1px solid #1a2f1a', background: '#0d150d', flexShrink: 0,
      minHeight: 28,
    }}>
      <span style={{ fontSize: 11, color: '#5a7a6a', flex: 1 }}>{label}</span>
      {onToggle && (
        <button onClick={onToggle} style={{
          background: 'transparent', border: 'none', color: '#5a7a6a', cursor: 'pointer',
          fontSize: 10, padding: '2px 6px'
        }} title={collapsed ? '展开' : '收缩'}>
          {collapsed ? '◀' : '▶'}
        </button>
      )}
    </div>
  )
}
