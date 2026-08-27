// CommandCenter.tsx — 底部命令中心（G2 单一职责）
// 输入框 + 状态 + 快捷操作融合，全局常驻

import React, { useState } from 'react'
import { bus, EVENTS } from '../events'

interface Props {
  status: 'disconnected' | 'connecting' | 'connected'
  mode: 'cloud' | 'local'
  moduleContext: string
  onReconnect: () => void
}

export default function CommandCenter({ status, mode, moduleContext, onReconnect }: Props) {
  const [cmd, setCmd] = useState('')

  function submit() {
    if (!cmd.trim()) return
    // 命令发到全局事件总线，任何模块可响应
    bus.emit(EVENTS.COMMAND, { text: cmd, module: moduleContext }, 'command-center')
    // 同时在右侧对话面板触发 AI（通过事件通知）
    bus.emit('chat-request', { text: cmd, module: moduleContext }, 'command-center')
    setCmd('')
  }

  return (
    <footer style={{
      borderTop: '1px solid #1a2f1a', background: '#0f1a0f', padding: '8px 16px'
    }}>
      {/* 命令输入行 */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ color: '#5ae0a0', fontSize: 14 }}>⚡</span>
        <input
          value={cmd}
          onChange={e => setCmd(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit() }}
          placeholder={`在${moduleContext}中执行命令或提问...`}
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 8, border: '1px solid #1a2f1a',
            background: '#0a0f0a', color: '#e0eae0', fontSize: 13, outline: 'none'
          }}
        />
        <button onClick={submit} style={{
          padding: '8px 16px', borderRadius: 8, border: 'none', background: '#2d7a5f',
          color: '#fff', cursor: 'pointer', fontSize: 13
        }}>发送</button>
        <button style={{
          padding: '8px 12px', borderRadius: 8, border: 'none', background: '#1a2f1a',
          color: '#8ae0b8', cursor: 'pointer', fontSize: 13
        }}>🎤</button>
      </div>

      {/* 状态行 */}
      <div style={{ display: 'flex', gap: 16, marginTop: 4, alignItems: 'center', fontSize: 10, color: '#5a7a6a' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: status === 'connected' ? '#4cd28a' : status === 'connecting' ? '#f0c040' : '#f04040' }} />
          {status === 'connected' ? '服务已连接' : status === 'connecting' ? '连接中...' : '服务未连接'}
        </span>
        <span>🤖 智能体: 待命</span>
        <span>🔧 工具: 113</span>
        <span>🔄 同步: 正常</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <span style={{ color: mode === 'cloud' ? '#5ae0a0' : '#f0c040' }}>{mode === 'cloud' ? '☁️ 云端模式' : '💻 本地模式'}</span>
          {status !== 'connected' && (
            <button onClick={onReconnect} style={{ background: 'transparent', border: '1px solid #1a2f1a', color: '#5a7a6a', fontSize: 10, borderRadius: 4, padding: '1px 6px', cursor: 'pointer' }}>重连</button>
          )}
        </span>
      </div>
    </footer>
  )
}
