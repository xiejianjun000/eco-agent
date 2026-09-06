import React, { useEffect, useState } from 'react';
import { api, type ConnectorInfo } from '../api';

export default function ConnectorsView(): React.ReactElement {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [connected, setConnected] = useState(0);
  const [toolTotal, setToolTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const refresh = () => {
    api.connectors()
      .then((r) => {
        setConnectors(r.connectors ?? []);
        setConnected(r.connected ?? 0);
        setToolTotal(r.tool_total ?? 0);
      })
      .catch(() => {});
  };

  useEffect(() => { refresh(); }, []);

  const refreshAll = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.connectorsRefresh();
      setConnectors(r.connectors ?? []);
      setConnected(r.connected ?? 0);
    } catch (e) {
      window.alert(`重连失败: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const transportLabel: Record<string, string> = { sse: 'SSE', stdio: 'STDIO', http: 'HTTP' };

  return (
    <div className="plugins-wrap">
      <div className="card">
        <div className="agents-head">
          <h2>连接器（MCP 服务）</h2>
          <span className="meta">
            {connectors.length} 个 · 已连接 {connected} · 共 {toolTotal} 个远程工具
          </span>
          <button className="btn" onClick={() => void refreshAll()} disabled={busy}>
            {busy ? '连接中…' : '重连全部'}
          </button>
          <button className="btn ghost" onClick={refresh}>刷新状态</button>
        </div>

        {connectors.length === 0 && (
          <div className="empty">未配置 MCP 连接器——在 .env 的 ECO_MCP_SERVERS 里配置后点「重连全部」。</div>
        )}

        {connectors.map((c) => (
          <div key={c.name} className="row">
            <div style={{ flex: 1 }}>
              <div className="title mono">{c.name}</div>
              <div className="muted">
                <span className={`badge ${c.transport}`}>{transportLabel[c.transport] ?? c.transport}</span>
                {' '}{c.url || '（stdio 本地进程）'}{c.has_headers ? ' · 🔑鉴权头' : ''}
              </div>
              {c.connected && c.tools.length > 0 && (
                <div className="muted" style={{ marginTop: 4 }}>
                  {c.tool_count} 个工具：
                  {expanded === c.name
                    ? ` ${c.tools.join(', ')}`
                    : ` ${c.tools.slice(0, 6).join(', ')}${c.tools.length > 6 ? ' …' : ''}`}
                  {c.tools.length > 6 && (
                    <button
                      className="tb-btn"
                      style={{ marginLeft: 6 }}
                      onClick={() => setExpanded(expanded === c.name ? null : c.name)}
                    >{expanded === c.name ? '收起' : '展开'}</button>
                  )}
                </div>
              )}
              {c.last_error && <div className="muted" style={{ color: 'var(--red)' }}>错误：{c.last_error}</div>}
            </div>
            <span className={`badge ${c.connected ? 'olive' : 'amber'}`}>
              {c.connected ? '已连接' : '未连接'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
