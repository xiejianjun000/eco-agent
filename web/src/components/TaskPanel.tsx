/**
 * TaskPanel.tsx — 持久化任务面板（对标 WorkBuddy TaskList 视图）。
 * 自取 /tasks，展示任务标题/状态/优先级，可点击查看详情与状态机历史。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, type TaskItem, type TaskSummary } from '../api';
import Icon from './Icon';

const STATUS_LABEL: Record<string, string> = {
  created: '待开始', in_progress: '进行中', completed: '已完成',
  paused: '已暂停', canceled: '已取消',
};
const STATUS_CLASS: Record<string, string> = {
  created: 'st-created', in_progress: 'st-running', completed: 'st-ok',
  paused: 'st-pending', canceled: 'st-canceled',
};
const PRIO_LABEL: Record<string, string> = { low: '低', normal: '中', high: '高' };

export default function TaskPanel({ compact = false }: { compact?: boolean }) {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<TaskItem | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    api.taskList().then((r) => {
      setTasks(r.tasks ?? []);
      setCounts(r.status_counts ?? {});
    }).catch(() => { /* 面板失败不打扰 */ });
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 8000);
    return () => window.clearInterval(id);
  }, [load]);

  const openDetail = useCallback((id: string) => {
    api.taskGet(id).then((r) => { setSelected(r.task); setOpen(true); }).catch(() => {});
  }, []);

  const active = useMemo(() => {
    const n = (counts.in_progress ?? 0) + (counts.created ?? 0);
    return n;
  }, [counts]);

  return (
    <div className="task-panel">
      <div className="task-panel-head">
        <span className="task-panel-title">
          <Icon name="check" size={14} /> 任务
          {active > 0 && <span className="task-panel-badge">{active}</span>}
        </span>
        <button className="task-refresh" title="刷新" onClick={load}><Icon name="refresh" size={13} /></button>
      </div>
      {tasks.length === 0 ? (
        <div className="task-panel-empty">{compact ? '暂无任务' : '暂无任务。可在对话中让 agent 用 task_create 建立工作项。'}</div>
      ) : (
        <div className="task-panel-list">
          {tasks.map((t) => (
            <button key={t.id} className="task-row" onClick={() => openDetail(t.id)}>
              <span className={`task-dot ${STATUS_CLASS[t.status] ?? ''}`} />
              <span className="task-row-title">{t.title}</span>
              <span className={`task-status ${STATUS_CLASS[t.status] ?? ''}`}>{STATUS_LABEL[t.status] ?? t.status}</span>
              {t.priority && t.priority !== 'normal' && (
                <span className={`task-prio p-${t.priority}`}>{PRIO_LABEL[t.priority]}</span>
              )}
            </button>
          ))}
        </div>
      )}
      {open && selected && (
        <div className="task-detail-backdrop" onClick={() => setOpen(false)}>
          <div className="task-detail" onClick={(e) => e.stopPropagation()}>
            <div className="task-detail-head">
              <span className="task-detail-title">{selected.title}</span>
              <button className="tb-btn" onClick={() => setOpen(false)}>关闭</button>
            </div>
            <div className={`task-status-big ${STATUS_CLASS[selected.status] ?? ''}`}>
              {STATUS_LABEL[selected.status] ?? selected.status}
            </div>
            {selected.description && <div className="task-detail-desc">{selected.description}</div>}
            {selected.tags?.length > 0 && (
              <div className="task-detail-tags">{selected.tags.map((g) => <span key={g} className="task-tag">{g}</span>)}</div>
            )}
            {selected.history?.length > 0 && (
              <div className="task-history">
                <div className="task-history-title">状态迁移</div>
                {selected.history.map((h, i) => (
                  <div key={i} className="task-history-row">
                    <span className="task-history-dot" />
                    <span className="task-history-status">{STATUS_LABEL[h.status] ?? h.status}</span>
                    <span className="task-history-time">{new Date(h.at_ms).toLocaleString('zh-CN')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
