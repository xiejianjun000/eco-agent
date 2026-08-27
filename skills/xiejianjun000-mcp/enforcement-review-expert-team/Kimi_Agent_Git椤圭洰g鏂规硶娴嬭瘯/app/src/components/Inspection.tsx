import { useState, type ReactNode } from 'react';
import {
  tasks, fixes, helps, TASK_TYPE_CLS, FIX_STATE_CLS,
  type InspectTask, type TaskCol, type FixItem,
} from '../data/inspection';

type Tab = 'tasks' | 'fixes' | 'helps';
const TABS: { id: Tab; label: string }[] = [
  { id: 'tasks', label: '督察任务' }, { id: 'fixes', label: '整改跟踪' }, { id: 'helps', label: '帮扶记录' },
];
const COLS: { id: TaskCol; label: string }[] = [
  { id: 'todo', label: '待开展' }, { id: 'doing', label: '进行中' }, { id: 'done', label: '已完成' },
];

export default function Inspection({ onNavigate }: { onNavigate: (id: string) => void }): ReactNode {
  const [tab, setTab] = useState<Tab>('tasks');
  return (
    <div className="insp">
      <div className="ov-bar">
        <div className="ov-card"><div className="ov-num">{tasks.filter((t) => t.col === 'doing').length}</div><div className="ov-label">进行中督察任务</div></div>
        <div className="ov-card"><div className="ov-num">{fixes.length}</div><div className="ov-label">待整改问题</div></div>
        <div className="ov-card"><div className="ov-num" style={{ color: 'var(--c-red)' }}>{fixes.filter((f) => f.remainDays < 0).length}</div><div className="ov-label">逾期未完成</div></div>
        <div className="ov-card"><div className="ov-num">{helps.length}</div><div className="ov-label">本月帮扶</div></div>
      </div>

      <div className="insp-body">
        <div className="insp-main">
          <div className="insp-tabs">
            {TABS.map((t) => (
              <button key={t.id} className={`ent-tab${tab === t.id ? ' on' : ''}`} onClick={() => setTab(t.id)}>{t.label}</button>
            ))}
          </div>
          <div className="insp-tab-body">
            {tab === 'tasks' && <TaskBoard />}
            {tab === 'fixes' && <FixTable />}
            {tab === 'helps' && <HelpTimeline />}
          </div>
        </div>

        <aside className="insp-side">
          <div className="card insp-ai">
            <div className="insp-ai-head"><span className="exp-avatar" style={{ background: 'rgba(201,124,62,.18)', color: 'var(--c-terra)' }}>督</span>督察精 提示</div>
            <div className="insp-ai-text">鑫顺建材整改已逾期，建议今日现场核查，路线已备好。</div>
            <button className="side-btn terra" onClick={() => onNavigate('map')}>查看地图 →</button>
          </div>
          <div className="card insp-gen">
            <div className="sec-title" style={{ marginBottom: 8 }}>一键生成</div>
            <button className="btn btn-ghost insp-gen-btn">督察通报</button>
            <button className="btn btn-ghost insp-gen-btn">整改通知书</button>
            <button className="btn btn-ghost insp-gen-btn">帮扶小结</button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function TaskBoard(): ReactNode {
  return (
    <div className="insp-board">
      {COLS.map((col) => {
        const list = tasks.filter((t) => t.col === col.id);
        return (
          <div className="insp-col" key={col.id}>
            <div className="insp-col-head">{col.label}<span>{list.length}</span></div>
            {list.map((t, i) => <TaskCard key={t.id} t={t} i={i} />)}
          </div>
        );
      })}
    </div>
  );
}

function TaskCard({ t, i }: { t: InspectTask; i: number }): ReactNode {
  return (
    <div className="card insp-task" style={{ animationDelay: `${i * 60}ms` }}>
      <div className="insp-task-top">
        <div className="insp-task-name">{t.name}</div>
        <span className={`badge ${TASK_TYPE_CLS[t.type]}`}>{t.type}</span>
      </div>
      {t.enterprises.length > 0 && (
        <div className="insp-task-ent">覆盖：{t.enterprises.join('、')}</div>
      )}
      <div className="insp-task-foot">
        <span className="insp-task-dead">期限 {t.deadline}</span>
      </div>
      <div className="pf-prog"><div className="pf-prog-track"><div className="pf-prog-fill" style={{ width: `${t.progress}%` }} /></div><span>{t.progress}%</span></div>
    </div>
  );
}

function FixTable(): ReactNode {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [verify, setVerify] = useState<FixItem | null>(null);
  const [closed, setClosed] = useState<Set<string>>(new Set());

  return (
    <div className="insp-fix">
      <div className="insp-fix-head">
        <span>问题描述</span><span>责任企业</span><span>整改期限</span><span>剩余</span><span>进度</span><span>操作</span>
      </div>
      {fixes.map((f) => {
        const overdue = f.remainDays < 0;
        const near = f.remainDays >= 0 && f.remainDays <= 3;
        const isClosed = closed.has(f.id);
        return (
          <div key={f.id} className={`insp-fix-row${expanded === f.id ? ' exp' : ''}`}>
            <div className="insp-fix-cell" onClick={() => setExpanded(expanded === f.id ? null : f.id)} style={{ cursor: 'pointer' }}>
              {f.problem}{f.note && <span className="insp-fix-note"> · {f.note}</span>}
            </div>
            <div className="insp-fix-cell">{f.company}</div>
            <div className="insp-fix-cell">{f.deadline}</div>
            <div className="insp-fix-cell">
              <span className={overdue ? 'insp-remain overdue' : near ? 'insp-remain near' : 'insp-remain'}>
                {overdue ? `逾期 ${Math.abs(f.remainDays)} 天` : `剩 ${f.remainDays} 天`}
              </span>
            </div>
            <div className="insp-fix-cell"><span className={`badge ${isClosed ? 'olive' : FIX_STATE_CLS[f.state]}`}>{isClosed ? '已销号' : f.state}</span></div>
            <div className="insp-fix-cell">
              {overdue && !isClosed && <button className="side-btn ghost" style={{ marginRight: 6 }}>催办</button>}
              {!isClosed && <button className="side-btn terra" onClick={() => setVerify(f)}>复核销号</button>}
            </div>
            {expanded === f.id && f.beforeAfter && (
              <div className="insp-fix-expand">
                <div className="insp-ba"><span className="insp-ba-label">整改前</span>{f.beforeAfter.before}</div>
                <div className="insp-ba"><span className="insp-ba-label">整改后</span>{f.beforeAfter.after}</div>
                <div className="insp-ba-rec">复核记录：督察精 8/6 现场复核，待上传影像</div>
              </div>
            )}
          </div>
        );
      })}

      {verify && (
        <div className="modal-mask" onClick={() => setVerify(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">复核销号 · {verify.company}</div>
            <div className="modal-text">请上传复核材料（现场照片 / 监测报告），确认后该问题标记为「已销号」。AI 不会代替您确认。</div>
            <div className="field"><label>复核材料</label><div className="insp-upload">点击上传或拖拽（照片 / PDF）</div></div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setVerify(null)}>取消</button>
              <button className="btn btn-primary" onClick={() => { setClosed((p) => new Set(p).add(verify.id)); setVerify(null); }}>确认销号</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function HelpTimeline(): ReactNode {
  return (
    <div className="timeline" style={{ padding: 4 }}>
      {helps.map((h) => (
        <div className="tl-row" key={h.date + h.company}>
          <span className="tl-dot" style={{ background: 'var(--c-olive)' }} />
          <div className="tl-body">
            <div className="tl-date">{h.date} · {h.company}</div>
            <div className="tl-desc">{h.content}</div>
            <div className="ai-quote" style={{ marginTop: 6 }}>后续建议：{h.advice}</div>
            <div className="pf-ov-sub" style={{ fontSize: 11, color: 'var(--t-aux)', marginTop: 4 }}>来源：同步自大气监督帮扶平台</div>
          </div>
        </div>
      ))}
    </div>
  );
}
