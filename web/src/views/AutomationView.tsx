import React, { useEffect, useRef, useState } from 'react';
import { api, type AutomationJob } from '../api';

export default function AutomationView(): React.ReactElement {
  const [jobs, setJobs] = useState<AutomationJob[]>([]);
  const [running, setRunning] = useState(false);
  const [desc, setDesc] = useState('');
  const [cronExpr, setCronExpr] = useState('');
  const [taskDesc, setTaskDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const timer = useRef<number | null>(null);

  const refresh = () => {
    api.automationJobs()
      .then((r) => { setJobs(r.jobs ?? []); setRunning(r.running ?? false); })
      .catch(() => {});
  };

  useEffect(() => {
    refresh();
    timer.current = window.setInterval(refresh, 10000);
    return () => { if (timer.current !== null) window.clearInterval(timer.current); };
  }, []);

  const add = async () => {
    if (busy) return;
    if (!desc.trim() && !cronExpr.trim()) { setMsg('请填自然语言描述或显式 cron 表达式'); return; }
    setBusy(true);
    setMsg('');
    try {
      const r = await api.automationAdd({
        description: desc.trim() || undefined,
        cron_expr: cronExpr.trim() || undefined,
        task_desc: taskDesc.trim() || undefined,
      });
      if (r.ok) { setDesc(''); setCronExpr(''); setTaskDesc(''); setMsg(`已创建任务 ${r.job_id}`); refresh(); }
      else setMsg(r.error ?? '创建失败');
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const run = async (id: string) => {
    const r = await api.automationRun(id).catch(() => null);
    setMsg(r && (r as { error?: string }).error ? `运行失败: ${(r as { error: string }).error}` : `已触发 ${id}`);
    refresh();
  };

  const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—');

  return (
    <div className="plugins-wrap">
      <div className="card">
        <div className="agents-head">
          <h2>自动任务（cron 定时巡查）</h2>
          <span className="meta">
            调度器 {running ? '运行中' : '已停止'} · {jobs.length} 个任务 · 每 10 秒自动刷新
          </span>
          <button className="btn ghost" onClick={refresh}>刷新</button>
        </div>

        <div className="spawn-row">
          <input
            className="dyn-name"
            placeholder="自然语言（如：每天 9 点巡查娄底市空气质量）"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
        </div>
        <div className="spawn-row" style={{ marginTop: 8 }}>
          <input
            className="dyn-name"
            placeholder="或显式 cron 表达式（如：0 9 * * *）"
            value={cronExpr}
            onChange={(e) => setCronExpr(e.target.value)}
          />
        </div>
        <div className="spawn-row" style={{ marginTop: 8 }}>
          <input
            className="dyn-name"
            placeholder="任务描述（配合 cron 表达式，可选）"
            value={taskDesc}
            onChange={(e) => setTaskDesc(e.target.value)}
          />
        </div>
        <div className="goal-actions">
          <button className="btn" onClick={() => void add()} disabled={busy}>
            {busy ? '创建中' : '+ 新建定时任务'}
          </button>
          {msg && <span className="meta">{msg}</span>}
        </div>
      </div>

      <div className="card">
        <h2>已配置任务</h2>
        {jobs.length === 0 && (
          <div className="empty">暂无定时任务——用自然语言或 cron 表达式新建（如「每天 9 点巡查娄底市空气质量」）。</div>
        )}
        {jobs.map((j) => (
          <div key={j.job_id} className="row">
            <div style={{ flex: 1 }}>
              <div className="title mono">{j.cron_expr}</div>
              <div className="desc">{j.task_desc}</div>
              <div className="muted">
                上次 {fmt(j.last_run)} · 下次 {fmt(j.next_run)} · 已跑 {j.run_count} 次
                {j.fail_count > 0 ? ` · 失败 ${j.fail_count}` : ''}
              </div>
            </div>
            <span className={`badge ${j.enabled ? 'olive' : ''}`}>{j.enabled ? '启用' : '停用'}</span>
            <button className="tb-btn" title="手动触发一次" onClick={() => void run(j.job_id)}>▶ 运行</button>
            <button
              className="tb-btn danger"
              title="删除任务"
              onClick={() => { void api.automationRemove(j.job_id).then(refresh).catch(() => {}); }}
            >删除</button>
          </div>
        ))}
      </div>
    </div>
  );
}
