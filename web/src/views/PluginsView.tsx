import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';

type Tab = 'plugins' | 'dyn' | 'slots';

interface PluginRow { name: string; status?: string; description?: string; tools?: string[] }
interface DynRow { plugin_id: string; running: boolean; size_bytes: number; defined_at: number }
interface SlotRow { slot: string; id: string; title: string; description: string }

function fmtBytes(n: number): string {
  return n < 1024 ? `${n}B` : `${(n / 1024).toFixed(1)}KB`;
}

export default function PluginsView(): React.ReactElement {
  const [tab, setTab] = useState<Tab>('plugins');
  const [plugins, setPlugins] = useState<PluginRow[]>([]);
  const [dyns, setDyns] = useState<DynRow[]>([]);
  const [dynStats, setDynStats] = useState<Record<string, number>>({});
  const [slots, setSlots] = useState<SlotRow[]>([]);
  const [code, setCode] = useState('');
  const [pname, setPname] = useState('');
  const [source, setSource] = useState<string | null>(null);
  const [slotData, setSlotData] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  const refresh = () => {
    api.plugins().then((r) => setPlugins(r.plugins ?? [])).catch(() => {});
    api.dynplugins().then((r) => {
      setDyns(r.plugins ?? []);
      setDynStats(r.stats ?? {});
    }).catch(() => {});
    api.slots().then((r) => setSlots(r.slots ?? [])).catch(() => {});
  };

  useEffect(() => {
    refresh();
    timer.current = window.setInterval(refresh, 5000);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, []);

  const define = async () => {
    const text = code.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const r = await api.dynpluginDefine({ code: text, name: pname.trim() || undefined });
      if (r.ok) {
        setCode('');
        setPname('');
        refresh();
      } else {
        window.alert(`定义失败: ${r.precheck?.error ?? 'unknown'}`);
      }
    } catch (e) {
      window.alert(`定义失败: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="plugins-wrap">
      <div className="side-tabs" style={{ marginBottom: 12 }}>
        <button className={`side-tab${tab === 'plugins' ? ' active' : ''}`} onClick={() => setTab('plugins')}>
          插件清单（{plugins.length}）
        </button>
        <button className={`side-tab${tab === 'dyn' ? ' active' : ''}`} onClick={() => setTab('dyn')}>
          动态插件（{dyns.length}）
        </button>
        <button className={`side-tab${tab === 'slots' ? ' active' : ''}`} onClick={() => setTab('slots')}>
          插槽（{slots.length}）
        </button>
      </div>

      {tab === 'plugins' && (
        <div className="card">
          <div className="agents-head">
            <h2>插件清单</h2>
            <span className="meta">运行 {dynStats.running ?? 0} 个动态插件 · 每 5 秒自动刷新</span>
            <button className="btn ghost" onClick={refresh}>刷新</button>
          </div>
          {plugins.length === 0 && <div className="empty">暂无静态插件（plugins/ 目录）。</div>}
          {plugins.map((p) => (
            <div key={p.name} className="row">
              <div style={{ flex: 1 }}>
                <div className="title mono">{p.name}</div>
                <div className="desc">{p.description ?? ''}</div>
                {p.tools && p.tools.length > 0 && (
                  <div className="muted">工具：{p.tools.join(', ')}</div>
                )}
              </div>
              <span className={`badge ${p.status === 'loaded' ? 'olive' : 'amber'}`}>
                {p.status ?? '未加载'}
              </span>
              {p.status === 'loaded' ? (
                <button className="tb-btn" onClick={() => api.pluginAction(p.name, 'unload').then(refresh).catch(() => {})}>卸载</button>
              ) : (
                <button className="tb-btn" onClick={() => api.pluginAction(p.name, 'load').then(refresh).catch(() => {})}>加载</button>
              )}
              <button className="tb-btn" onClick={() => api.pluginAction(p.name, 'reload').then(refresh).catch(() => {})}>重载</button>
            </div>
          ))}
        </div>
      )}

      {tab === 'dyn' && (
        <>
          <div className="card">
            <div className="agents-head">
              <h2>动态插件定义（DSH define/run/stop/undefine 循环）</h2>
              <span className="meta">运行 {dynStats.running ?? 0} · 已定义 {dynStats.defined ?? dyns.length}</span>
            </div>
            <div className="spawn-row">
              <input
                className="dyn-name"
                placeholder="插件名（注释用，可选）"
                value={pname}
                onChange={(e) => setPname(e.target.value)}
              />
            </div>
            <textarea
              className="dyn-code"
              placeholder={'define 插件代码（Python 模块，含 apply(ctx, config)，可选 inject=[]）：\ndef apply(ctx, config=None):\n    ctx.smoke_ok = True\n    return None'}
              rows={8}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <div className="goal-actions">
              <button className="btn" onClick={() => void define()} disabled={busy || !code.trim()}>
                {busy ? '定义中' : 'define'}
              </button>
            </div>
          </div>
          <div className="card">
            <h2>已定义动态插件</h2>
            {dyns.length === 0 && <div className="empty">暂无——在上面 define 一个（define 只定义不执行，run 才激活）。</div>}
            {dyns.map((d) => (
              <div key={d.plugin_id} className="row">
                <div style={{ flex: 1 }}>
                  <div className="title mono">{d.plugin_id}</div>
                  <div className="muted">{fmtBytes(d.size_bytes)} · 定义于 {new Date(d.defined_at * 1000).toLocaleString()}</div>
                </div>
                <span className={`badge ${d.running ? 'olive' : ''}`}>{d.running ? '运行中' : '已停止'}</span>
                {d.running ? (
                  <button className="tb-btn" onClick={() => api.dynpluginStop(d.plugin_id).then(refresh).catch(() => {})}>stop</button>
                ) : (
                  <button className="tb-btn" onClick={() => api.dynpluginRun(d.plugin_id).then(refresh).catch(() => {})}>run</button>
                )}
                <button
                  className="tb-btn"
                  onClick={() => api.dynpluginSource(d.plugin_id).then((r) => setSource(r.source ?? null)).catch(() => {})}
                >源码</button>
                <button className="tb-btn" onClick={() => { api.dynpluginUndefine(d.plugin_id).then(refresh).catch(() => {}); setSource(null); }}>undefine</button>
              </div>
            ))}
            {source !== null && (
              <pre className="agent-result" style={{ maxHeight: 260, overflow: 'auto' }}>{source}</pre>
            )}
          </div>
        </>
      )}

      {tab === 'slots' && (
        <div className="card">
          <h2>插槽注册（DSH Slot UI）</h2>
          {slots.length === 0 && <div className="empty">暂无插槽注册。</div>}
          {slots.map((s) => (
            <div key={`${s.slot}/${s.id}`} className="row">
              <div style={{ flex: 1 }}>
                <div className="title mono">{s.slot} / {s.id}</div>
                <div className="desc">{s.title} — {s.description}</div>
              </div>
              <button
                className="tb-btn"
                onClick={() => api.slotData(s.id).then((d) => setSlotData(d)).catch(() => {})}
              >查看数据</button>
            </div>
          ))}
          {slotData !== null && (
            <pre className="agent-result" style={{ maxHeight: 260, overflow: 'auto' }}>
              {JSON.stringify(slotData, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
