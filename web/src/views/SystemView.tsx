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

  const load = async () => {
    try {
      const [sys, met, t] = await Promise.all([api.system(), api.metrics(), api.tools()]);
      setSystem(sys);
      setMetrics(met);
      setTools(t.tools);
      setCategories(t.categories);
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
