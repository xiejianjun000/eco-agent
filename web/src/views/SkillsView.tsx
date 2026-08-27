import React, { useEffect, useState } from 'react';
import { api, type Skill } from '../api';

export default function SkillsView(): React.ReactElement {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const r = await api.skills();
      setSkills(r.skills);
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
      const r = await api.skillsSearch(q.trim());
      setSkills(r.skills);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      <div className="card">
        <div className="stat" style={{ fontSize: 20 }}>{skills.length} 个技能</div>
        <div className="stat-label">
          技能由 G7 技能孵化机制自动生成：同一任务模式出现 3 次即沉淀为可复用 Skill
        </div>
      </div>

      <div className="card">
        <input
          className="search-input"
          placeholder="搜索技能（名称/标签/描述）…"
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
        <h2>技能列表</h2>
        {skills.length === 0 && (
          <div className="empty">暂无已安装技能。技能会随着使用自动孵化，也可通过 `eco skills install` 安装。</div>
        )}
        {skills.map((s) => {
          const m = (s.manifest ?? {}) as { description?: string; tags?: string[]; version?: string; trust?: string };
          return (
            <div key={s.name} className="row">
              <div style={{ flex: 1 }}>
                <div className="title">{s.name}</div>
                <div className="desc">{m.description ?? '—'}</div>
                {(m.tags ?? []).map((t) => (
                  <span key={t} className="tag">{t}</span>
                ))}
              </div>
              <span className={`badge ${m.trust === 'community' ? 'amber' : 'olive'}`}>
                {m.version ?? 'v?'} · {m.trust ?? 'local'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
