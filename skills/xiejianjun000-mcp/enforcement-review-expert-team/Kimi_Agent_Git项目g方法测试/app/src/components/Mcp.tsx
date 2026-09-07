import { useState } from 'react';
import type { ReactNode } from 'react';
import {
  connections as seed, logs, statusMeta,
  type McpConn, type McpStatus,
} from '../data/mcp';

function StatusBadge({ status }: { status: McpStatus }): ReactNode {
  const m = statusMeta[status];
  return <span className={`mcp-badge ${m.cls}`}>{m.label}</span>;
}

export default function Mcp(): ReactNode {
  const [conns, setConns] = useState<McpConn[]>(seed);
  const [testing, setTesting] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [wizard, setWizard] = useState(false);
  const [wStep, setWStep] = useState(0);
  const [wAddr, setWAddr] = useState('');
  const [wCred, setWCred] = useState('');

  const flash = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 1800);
  };

  const toggle = (id: string) => {
    setConns((cs) => cs.map((c) =>
      c.id === id ? { ...c, status: c.status === 'connected' ? 'off' : 'connected' } : c,
    ));
  };

  const test = (id: string) => {
    setTesting(id);
    window.setTimeout(() => {
      setTesting(null);
      const c = conns.find((x) => x.id === id);
      if (c && c.status === 'error') {
        flash(`「${c.name}」测试仍失败`);
      } else {
        flash(`「${c?.name ?? ''}」连接正常`);
      }
    }, 1200);
  };

  const retry = (id: string) => {
    setConns((cs) => cs.map((c) => (c.id === id ? { ...c, status: 'connected', errorMsg: undefined } : c)));
    flash('已重新触发备份');
  };

  const finishWizard = () => {
    const name = wStep === 0 ? '自定义工具' : '新接入工具';
    setConns((cs) => [
      ...cs,
      {
        id: 'custom-' + Date.now(), name, desc: '用户自助接入的外部工具',
        status: 'connected', lastCall: '刚刚',
        endpoint: wAddr || 'https://custom.internal/v1', auth: wCred ? 'API Key' : '无', quota: '—',
      },
    ]);
    setWizard(false); setWStep(0); setWAddr(''); setWCred('');
    flash('工具已接通');
  };

  return (
    <div className="mod">
      <div className="mod-head">
        <div>
          <h2 className="mod-title">MCP 连接</h2>
          <p className="mod-sub">这里管理平台与外部工具的连接。接通后，AI 助理可以直接使用这些工具帮您干活，例如查地图、读文档、连打印机。</p>
        </div>
        <button className="btn btn-primary" onClick={() => setWizard(true)}>＋ 接入工具</button>
      </div>

      <div className="mcp-grid">
        {conns.map((c) => (
          <div key={c.id} className={`mcp-card${c.status === 'error' ? ' is-err' : ''}`}>
            <div className="mcp-card-top">
              <div className="mcp-name">{c.name}</div>
              <StatusBadge status={c.status} />
            </div>
            <div className="mcp-desc">{c.desc}</div>
            <div className="mcp-meta">
              {c.callsToday != null && <span>今日调用 {c.callsToday} 次</span>}
              {c.lastCall && <span>最近 {c.lastCall}</span>}
            </div>
            {c.status === 'error' && c.errorMsg && (
              <div className="mcp-err-msg">⚠ {c.errorMsg}</div>
            )}
            <div className="mcp-card-actions">
              <button
                className={`mcp-switch${c.status === 'connected' ? ' on' : ''}`}
                onClick={() => toggle(c.id)}
                aria-label="切换"
              >
                <span className="knob" />
              </button>
              {c.status === 'error' ? (
                <button className="btn btn-warn sm" onClick={() => retry(c.id)}>重试</button>
              ) : c.status === 'off' ? (
                <button className="btn btn-primary sm" onClick={() => toggle(c.id)}>接通</button>
              ) : (
                <button className="btn btn-ghost sm" onClick={() => test(c.id)} disabled={testing === c.id}>
                  {testing === c.id ? <span className="spin-ring" /> : '测试'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mcp-log card">
        <div className="card-h">调用记录<span className="muted-sm">AI 做过什么，可追溯</span></div>
        <div className="mcp-log-list">
          {logs.map((l, i) => (
            <div key={i} className="mcp-log-row">
              <span className="mcp-log-time">{l.time}</span>
              <span className="expert-chip">{l.expert}</span>
              <span className="mcp-log-tool">{l.tool}</span>
              <span className="mcp-log-act">{l.action}</span>
              <span className={`mcp-result ${l.ok ? 'ok' : 'fail'}`}>{l.ok ? '成功' : '失败'}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={`mcp-adv card${advanced ? ' open' : ''}`}>
        <div className="card-h clickable" onClick={() => setAdvanced((v) => !v)}>
          高级设置（一般无需修改）
          <span className="adv-chev">{advanced ? '▾' : '▸'}</span>
        </div>
        {advanced && (
          <div className="mcp-adv-body">
            <table className="mcp-adv-table">
              <thead><tr><th>工具</th><th>接入地址</th><th>鉴权方式</th><th>调用配额</th></tr></thead>
              <tbody>
                {conns.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td><td className="mono">{c.endpoint}</td>
                    <td>{c.auth}</td><td>{c.quota}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {toast && <div className="toast ok">{toast}</div>}

      {wizard && (
        <div className="modal-mask" onClick={() => setWizard(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-h">接入外部工具</div>
            <div className="wiz-steps">
              {['选工具', '填地址与凭证', '自动测试'].map((s, i) => (
                <span key={s} className={`wiz-step${i === wStep ? ' cur' : ''}${i < wStep ? ' done' : ''}`}>{i + 1}. {s}</span>
              ))}
            </div>
            {wStep === 0 && (
              <div className="wiz-body">
                <label className="wiz-field"><span>工具类型</span>
                  <select className="input" defaultValue="doc"><option value="doc">文档处理服务</option><option value="print">打印服务</option><option value="custom">自定义 HTTP 服务</option></select>
                </label>
              </div>
            )}
            {wStep === 1 && (
              <div className="wiz-body">
                <label className="wiz-field"><span>接入地址</span>
                  <input className="input" placeholder="https://..." value={wAddr} onChange={(e) => setWAddr(e.target.value)} />
                </label>
                <label className="wiz-field"><span>访问凭证<span className="hint">向信息中心索取</span></span>
                  <input className="input" placeholder="API Key / Token" value={wCred} onChange={(e) => setWCred(e.target.value)} />
                </label>
              </div>
            )}
            {wStep === 2 && (
              <div className="wiz-body center">
                <span className="spin-ring big" /><div className="muted">正在自动测试连接…</div>
              </div>
            )}
            <div className="modal-actions">
              {wStep > 0 && <button className="btn btn-ghost" onClick={() => setWStep((s) => s - 1)}>上一步</button>}
              {wStep < 2 && <button className="btn btn-primary" onClick={() => setWStep((s) => s + 1)}>下一步</button>}
              {wStep === 2 && <button className="btn btn-primary" onClick={finishWizard}>完成接通</button>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
