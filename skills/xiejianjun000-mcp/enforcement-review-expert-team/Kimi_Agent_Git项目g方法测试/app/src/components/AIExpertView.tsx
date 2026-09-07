import { useState, type ReactNode } from 'react';
import { experts, type Expert } from '../data/assistant';

export default function AIExpertView(): ReactNode {
  const [toast, setToast] = useState<string | null>(null);

  const assign = (e: Expert) => {
    setToast(`已向「${e.name}」指派任务（演示）`);
    window.setTimeout(() => setToast(null), 1800);
  };

  const activeCount = experts.filter(e => e.active).length;

  return (
    <div className="ai-expert-page">
      <div className="sec-head">
        <span className="sec-title">AI 专家工作台</span>
        <span className="sec-count">{activeCount}/{experts.length} 位在岗 · 累计调度 312 次</span>
      </div>

      <div className="expert-grid">
        {experts.map((e, i) => (
          <div key={e.id} className="expert-card" style={{ animationDelay: `${i * 50}ms` }}>
            <div className="exp-top">
              <span className="exp-avatar">{e.name.charAt(0)}</span>
              <div className="exp-id">
                <div className="exp-name">{e.name}</div>
                <div className="exp-role">{e.role}</div>
              </div>
            </div>
            <div className="exp-status">
              <span className={`exp-dot${e.active ? ' live' : ''}`} />
              {e.status}
            </div>
            <div className="exp-foot">
              <span className="exp-metric">{e.metric}</span>
              <button className="exp-assign" onClick={() => assign(e)}>指派任务</button>
            </div>
          </div>
        ))}
      </div>

      {toast && <div className="toast ok">{toast}</div>}
    </div>
  );
}
