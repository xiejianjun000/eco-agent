import React, { useEffect, useState } from 'react';
import { api, type MemoryNode } from '../api';

export default function MemoryView(): React.ReactElement {
  const [nodes, setNodes] = useState<MemoryNode[]>([]);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [n, s] = await Promise.all([api.memoryNodes(100), api.memoryStats()]);
      setNodes(n.nodes);
      setStats(s);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const search = async () => {
    if (!q.trim()) {
      await load();
      return;
    }
    try {
      const r = await api.memorySearch(q.trim());
      setNodes(r.nodes);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const total = typeof stats?.total_nodes === 'number' ? stats.total_nodes : 0;
  const byType = (stats?.by_type ?? {}) as Record<string, { count: number }>;

  return (
    <div>
      <div className="grid">
        <div className="card">
          <div className="stat">{total}</div>
          <div className="stat-label">记忆节点总数</div>
        </div>
        <div className="card">
          <div className="stat">{Object.keys(byType).length}</div>
          <div className="stat-label">节点类型数</div>
        </div>
        <div className="card">
          <div className="stat">{typeof stats?.total_edges === 'number' ? stats.total_edges : 0}</div>
          <div className="stat-label">关联边</div>
        </div>
      </div>

      <div className="card">
        <input
          className="search-input"
          placeholder="搜索记忆（关键词）…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void search();
          }}
        />
        <button className="btn ghost" onClick={() => void search()}>搜索</button>
        {error && <div className="muted" style={{ marginTop: 8 }}>错误: {error}</div>}
      </div>

      <div className="card">
        <h2>记忆节点（按评分排序）</h2>
        {nodes.length === 0 && <div className="empty">暂无记忆节点——使用系统后，执法案例与知识会自动沉淀到这里。</div>}
        {nodes.map((n) => (
          <div key={n.id} className="row">
            <div style={{ flex: 1 }}>
              <div className="title">{n.title || n.id}</div>
              <div className="desc">
                {n.type} · 评分 {n.score}
                {n.updated_at ? ` · 更新 ${String(n.updated_at).slice(0, 10)}` : ''}
              </div>
            </div>
            <span className={`badge ${n.score >= 70 ? 'olive' : n.score >= 40 ? 'amber' : ''}`}>
              {n.score >= 70 ? '热' : n.score >= 40 ? '温' : '冷'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
