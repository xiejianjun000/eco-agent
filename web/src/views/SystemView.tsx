import React, { useEffect, useState } from 'react';
import { api, type ToolEntry } from '../api';

interface ComponentState {
  available?: boolean;
  loaded?: boolean;
  provider?: string;
  error?: string;
  job_count?: number;
  total_nodes?: number;
  [key: string]: unknown;
}

export default function SystemView(): React.ReactElement {
  const [system, setSystem] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [tools, setTools] = useState<ToolEntry[]>([]);
  const [categories, setCategories] = useState<Record<string, number>>({});
  const [q, setQ] = useState('');
  const [error, setError] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>(() => {
    const saved = window.localStorage.getItem('eco-theme');
    return saved === 'dark' || saved === 'light' ? saved : 'system';
  });
  const [gate, setGate] = useState<boolean | null>(null);
  const [presets, setPresets] = useState<{ id: string; role: string; name: string; files: string[] }[]>([]);

  const applyTheme = (t: 'light' | 'dark' | 'system') => {
    setTheme(t);
    const resolved = t === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : t;
    window.localStorage.setItem('eco-theme', t);
    document.documentElement.dataset.theme = resolved;
    window.dispatchEvent(new CustomEvent('eco-theme-changed', { detail: resolved }));
  };

  const toggleGate = async (enabled: boolean) => {
    try {
      const r = await api.permissionGate(enabled);
      setGate(r.enabled);
    } catch (e) {
      window.alert(`切换失败: ${(e as Error).message}`);
    }
  };

  const load = async () => {
    try {
      const [sys, met, t] = await Promise.all([api.system(), api.metrics(), api.tools()]);
      setSystem(sys);
      setMetrics(met);
      setTools(t.tools);
      setCategories(t.categories);
      const pg = (sys.components as Record<string, { enabled?: boolean }>).permission_gate;
      setGate(pg?.enabled ?? null);
      api.presets().then((r) => setPresets(r.presets ?? [])).catch(() => {});
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const comps = (system?.components ?? {}) as Record<string, ComponentState>;

  return (
    <div>
      <div className="grid">
        <div className="card">
          <div className="stat">{Object.keys(categories).length}</div>
          <div className="stat-label">工具分类（govmcp 政务工具）</div>
        </div>
        <div className="card">
          <div className="stat">{tools.length}</div>
          <div className="stat-label">已注册工具总数</div>
        </div>
        <div className="card">
          <div className="stat">{comps.llm?.available ? '可用' : '未配置'}</div>
          <div className="stat-label">
            LLM 提供商：{comps.llm?.provider ?? 'unknown'}
          </div>
        </div>
        <div className="card">
          <div className="stat">{comps.soul?.loaded ? '已加载' : '未加载'}</div>
          <div className="stat-label">SOUL 人格配置</div>
        </div>
      </div>

      <div className="card">
        <h2>设置</h2>
        <div className="setting-row">
          <span className="setting-label">外观</span>
          <div className="seg">
            {(['light', 'dark', 'system'] as const).map((t) => (
              <button
                key={t}
                className={`seg-btn${theme === t ? ' active' : ''}`}
                onClick={() => applyTheme(t)}
              >
                {t === 'light' ? '亮色' : t === 'dark' ? '暗色' : '跟随系统'}
              </button>
            ))}
          </div>
        </div>
        <div className="setting-row">
          <span className="setting-label">权限闸门（L1-L4）</span>
          <div className="seg">
            <button
              className={`seg-btn${gate === true ? ' active' : ''}`}
              onClick={() => void toggleGate(true)}
            >
              启用
            </button>
            <button
              className={`seg-btn${gate === false ? ' active' : ''}`}
              onClick={() => void toggleGate(false)}
            >
              停用
            </button>
          </div>
          {gate === null && <span className="muted">加载中…</span>}
        </div>
        <div className="setting-row">
          <span className="setting-label">LLM 提供商</span>
          <span className="badge blue">{comps.llm?.provider ?? 'unknown'}</span>
          <span className="muted">（模型与密钥经 .env 环境变量配置，此处只读）</span>
        </div>
        <div className="setting-row">
          <span className="setting-label">Agent 预设</span>
          <div className="preset-list">
            {presets.length === 0 ? (
              <span className="muted">加载中…</span>
            ) : (
              presets.map((p) => (
                <span key={p.id} className={`badge ${p.role === 'main' ? 'terra' : 'blue'}`} title={p.files.join(', ')}>
                  {p.name}
                </span>
              ))
            )}
          </div>
          <span className="muted">（profiles/ 目录清单，主预设 + {presets.length - 1} 个角色人格）</span>
        </div>
      </div>

      <div className="card">
        <h2>组件状态</h2>
        {Object.entries(comps).map(([name, c]) => (
          <div key={name} className="row">
            <div className="title">{name}</div>
            <span className={`badge ${c.error ? 'red' : c.available !== false ? 'olive' : 'amber'}`}>
              {c.error ? '异常' : c.available !== false ? '正常' : '待配置'}
            </span>
          </div>
        ))}
        {error && <div className="muted" style={{ marginTop: 8 }}>错误: {error}</div>}
      </div>

      <div className="card">
        <h2>指标</h2>
        {metrics && (
          <div className="mono muted">
            <pre style={{ margin: 0 }}>{JSON.stringify(metrics, null, 2)}</pre>
          </div>
        )}
      </div>

      <div className="card">
        <h2>工具目录</h2>
        <input
          className="search-input"
          placeholder="筛选工具（名称/描述/标签）…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {tools
          .filter((t) => {
            const ql = q.trim().toLowerCase();
            if (!ql) return true;
            return t.name.toLowerCase().includes(ql) || t.description.toLowerCase().includes(ql)
              || t.tags.some((tag) => tag.toLowerCase().includes(ql));
          })
          .slice(0, 100)
          .map((t) => (
            <div key={t.name} className="row">
              <div style={{ flex: 1 }}>
                <div className="title mono">{t.name}</div>
                <div className="desc">{t.description}</div>
              </div>
              <span className="badge blue">{t.category}</span>
            </div>
          ))}
        {tools.length > 100 && <div className="muted">仅显示前 100 个，用筛选框缩小范围</div>}
      </div>
    </div>
  );
}
