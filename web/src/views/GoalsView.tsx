import React, { useEffect, useRef, useState } from 'react';
import { api, type GoalInfo } from '../api';

const STATUS_LABEL: Record<string, string> = {
  active: '进行中',
  paused: '已暂停',
  blocked: '受阻',
  completed: '已完成',
};

function statusBadge(s: string): string {
  if (s === 'completed') return 'badge olive';
  if (s === 'blocked') return 'badge red';
  if (s === 'paused') return 'badge amber';
  return 'badge terra';
}

function fmtTime(ts?: number): string {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const p = (n: number) => n.toString().padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function GoalsView(): React.ReactElement {
  const [goals, setGoals] = useState<GoalInfo[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [objective, setObjective] = useState('');
  const [maxRounds, setMaxRounds] = useState(10);
  const [autoRun, setAutoRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  const refresh = () => {
    api.goals().then((r) => {
      setGoals(r.goals ?? []);
      setStats(r.stats ?? {});
    }).catch(() => {});
  };

  useEffect(() => {
    refresh();
    timer.current = window.setInterval(refresh, 5000);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, []);

  const create = async () => {
    const text = objective.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await api.goalCreate({ objective: text, max_goal_rounds: maxRounds, auto_run: autoRun });
      setObjective('');
      refresh();
    } catch (e) {
      window.alert(`创建失败: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const act = async (id: string, action: string, reason = '') => {
    await api.goalAction(id, action, reason ? { reason } : {}).catch(() => {});
    refresh();
  };

  return (
    <div className="goals-wrap">
      <div className="card">
        <div className="agents-head">
          <h2>目标</h2>
          <span className="meta">
            进行中 {stats.active ?? 0} · 已暂停 {stats.paused ?? 0} · 受阻 {stats.blocked ?? 0} · 已完成 {stats.completed ?? 0}
          </span>
          <button className="btn ghost" onClick={refresh}>刷新</button>
        </div>
        <div className="spawn-row">
          <textarea
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="输入目标描述（如：对标 DSH 全部靠齐，包括 web ui 输出都一样）"
            rows={2}
          />
          <label className="goal-opt">
            轮次上限
            <input
              type="number"
              min={1}
              max={256}
              value={maxRounds}
              onChange={(e) => setMaxRounds(Number(e.target.value) || 10)}
            />
          </label>
          <label className="goal-opt">
            <input type="checkbox" checked={autoRun} onChange={(e) => setAutoRun(e.target.checked)} />
            立即开跑
          </label>
          <button className="btn" onClick={() => void create()} disabled={busy || !objective.trim()}>
            {busy ? '创建中' : '创建'}
          </button>
        </div>
      </div>

      <div className="goal-grid">
        {goals.length === 0 && (
          <div className="card">
            <div className="empty">暂无目标——在上方创建一个，勾选「立即开跑」后会由后台子代理自动逐轮推进。</div>
          </div>
        )}
        {goals.map((g) => (
          <div key={g.id} className="card goal-card">
            <div className="agents-head">
              <span className={statusBadge(g.status)}>{STATUS_LABEL[g.status] ?? g.status}</span>
              {g.armed && <span className="badge">⚡ 自动续轮</span>}
              <span className="meta">{g.id}</span>
            </div>
            <div className="goal-objective">{g.objective}</div>
            <div className="goal-meta">
              轮次 {g.rounds ?? 0}/{g.max_goal_rounds ?? 10} · 创建 {fmtTime(g.created_at)} · 更新 {fmtTime(g.updated_at)}
            </div>
            {g.blocked_reason && <div className="agent-error">🚧 {g.blocked_reason}</div>}
            {g.last_result && (
              <div className="goal-last">最近结果：{g.last_result.slice(0, 180)}{g.last_result.length > 180 ? '…' : ''}</div>
            )}
            <div className="goal-actions">
              {g.status === 'active' && (
                <button className="tb-btn" onClick={() => void act(g.id, 'pause')}>⏸ 暂停目标</button>
              )}
              {g.status === 'paused' && (
                <button className="tb-btn" onClick={() => void act(g.id, 'resume')}>▶ 恢复目标</button>
              )}
              {g.status === 'blocked' && (
                <button className="tb-btn" onClick={() => void act(g.id, 'resume')}>▶ 恢复目标</button>
              )}
              {(g.status === 'active' || g.status === 'paused') && (
                <button className="tb-btn" onClick={() => void act(g.id, 'complete', '手动完成')}>✅ 完成</button>
              )}
              {(g.status === 'active' || g.status === 'paused') && (
                <button className="tb-btn" onClick={() => void act(g.id, 'block', '人工标记阻塞')}>🚧 阻塞</button>
              )}
              {g.status === 'paused' && (
                <button className="tb-btn" onClick={() => void act(g.id, 'run')}>▶ 立即跑一轮</button>
              )}
              {g.status === 'completed' && <span className="goal-final">✅ 已达成</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
