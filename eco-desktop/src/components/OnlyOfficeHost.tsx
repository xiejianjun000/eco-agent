// OnlyOfficeHost.tsx — ONLYOFFICE Desktop Editors 集成宿主
// 通过 Tauri sidecar 启动 ONLYOFFICE 本地服务，WebView 中 iframe 加载
// 当前为集成方案骨架：检测 ONLYOFFICE 是否可用，可用则嵌入，否则回退到内置编辑器

import React, { useState, useEffect } from 'react'

interface Props {
  docPath?: string
  docTitle: string
}

export default function OnlyOfficeHost({ docPath, docTitle }: Props) {
  const [onlyOfficeAvailable, setOnlyOfficeAvailable] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)

  // 检测 ONLYOFFICE 是否安装
  useEffect(() => {
    // 真实场景：检查本地 ONLYOFFICE Desktop Editors 安装
    // 这里用简单检测（模拟）：尝试连接本地 ONLYOFFICE 服务
    const check = async () => {
      try {
        // ONLYOFFICE Desktop Editors 本地服务默认端口
        const res = await fetch('http://localhost:42656/status', { signal: AbortSignal.timeout(2000) })
        setOnlyOfficeAvailable(res.ok)
      } catch {
        setOnlyOfficeAvailable(false)
      }
    }
    check()
  }, [])

  if (onlyOfficeAvailable === null) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#5a7a6a', fontSize: 12 }}>
        🔍 检测 ONLYOFFICE...
      </div>
    )
  }

  if (!onlyOfficeAvailable) {
    // ONLYOFFICE 不可用 → 回退提示（由外层决定用内置编辑器）
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 10 }}>
        <div style={{ fontSize: 32 }}>📝</div>
        <div style={{ color: '#8ae0b8', fontSize: 13 }}>{docTitle}</div>
        <div style={{ color: '#5a7a6a', fontSize: 11, maxWidth: 280, textAlign: 'center' }}>
          ONLYOFFICE 未检测到（需安装 ONLYOFFICE Desktop Editors）
        </div>
        <div style={{ fontSize: 10, color: '#2a5a3a' }}>
          已回退到内置协同编辑器 · 安装 ONLYOFFICE 后可获得完整 DOCX/XLSX/PDF 编辑
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', gap: 6, padding: '6px 10px', borderBottom: '1px solid #1a2f1a', alignItems: 'center', fontSize: 11, color: '#5a7a6a' }}>
        <span>📄 ONLYOFFICE · {docTitle}</span>
        <span style={{ marginLeft: 'auto', color: '#4cd28a' }}>● 已连接</span>
      </div>
      {/* ONLYOFFICE iframe 嵌入点 */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#1a1a1a', color: '#8a9a8a', fontSize: 12 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
          <div>ONLYOFFICE 编辑器将在此 iframe 中加载</div>
          <div style={{ fontSize: 10, marginTop: 4, color: '#5a7a6a' }}>docPath: {docPath || '未指定'}</div>
        </div>
      </div>
    </div>
  )
}
