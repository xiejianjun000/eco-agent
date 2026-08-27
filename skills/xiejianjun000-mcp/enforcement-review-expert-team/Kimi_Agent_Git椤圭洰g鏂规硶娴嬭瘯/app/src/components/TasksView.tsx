import type { ReactNode } from 'react';
import { todos, weekSummary, type TodoItem } from '../data/assistant';
import { IconChevron } from './icons';

interface Props {
  onNavigate: (id: string) => void;
}

const levelMeta: Record<TodoItem['level'], { label: string; cls: string }> = {
  urgent: { label: '紧急', cls: 'red' },
  due: { label: '临期', cls: 'amber' },
  normal: { label: '普通', cls: 'blue' },
};

export default function TasksView({ onNavigate }: Props): ReactNode {
  return (
    <div className="tasks-page">
      {/* 概览条 */}
      <div className="tasks-summary">
        <div className="task-stat">
          <span className="task-stat-num urgent">{todos.filter(t => t.level === 'urgent').length}</span>
          <span className="task-stat-label">紧急</span>
        </div>
        <div className="task-stat">
          <span className="task-stat-num due">{todos.filter(t => t.level === 'due').length}</span>
          <span className="task-stat-label">临期</span>
        </div>
        <div className="task-stat">
          <span className="task-stat-num">{todos.filter(t => t.level === 'normal').length}</span>
          <span className="task-stat-label">普通</span>
        </div>
        <div className="task-stat">
          <span className="task-stat-num">{todos.length}</span>
          <span className="task-stat-label">共计</span>
        </div>
      </div>

      {/* 待办列表 */}
      <section className="sec">
        <div className="sec-head">
          <span className="sec-title">全部待办</span>
          <span className="sec-count">{todos.length} 项</span>
        </div>
        <div className="todo-list">
          {todos.map((t, i) => {
            const m = levelMeta[t.level];
            return (
              <div
                key={t.id}
                className={`todo-row${t.level === 'urgent' ? ' urgent' : ''}`}
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <span className={`badge ${m.cls}`}>
                  <span className="bdot" />
                  {m.label}
                </span>
                <div className="todo-body">
                  <div className="todo-title">{t.title}</div>
                  <div className="todo-meta">
                    {t.source} · {t.deadline}
                  </div>
                </div>
                <button className="todo-go" onClick={() => onNavigate(t.target)}>
                  去处理 →
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {/* 一周小结 */}
      <section className="sec">
        <div className="week-card" onClick={() => onNavigate('review')}>
          <span className="week-label">本周</span>
          <span className="week-item">
            立案 <b>{weekSummary.cases}</b>
          </span>
          <span className="week-sep">·</span>
          <span className="week-item">
            评查通过 <b className="olive">{weekSummary.passed}</b>
          </span>
          <span className="week-sep">·</span>
          <span className="week-item">
            否决拦截 <b className="terra">{weekSummary.veto}</b>
          </span>
          <span className="week-sep">·</span>
          <span className="week-item">
            文书生成 <b className="olive">{weekSummary.docs}</b>
          </span>
          <span className="week-go">
            进入评查看板 <IconChevron />
          </span>
        </div>
      </section>
    </div>
  );
}
