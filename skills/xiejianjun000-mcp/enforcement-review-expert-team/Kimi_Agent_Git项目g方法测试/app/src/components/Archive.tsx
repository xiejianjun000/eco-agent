import { useMemo, useState, type ReactNode } from 'react';
import { archives, CONCL_CLS, docTree, type Archive, type Conclusion } from '../data/archive';
import { currentUser } from '../data/currentUser';

export default function Archive(_props: { onNavigate: (id: string) => void }): ReactNode {
  const [viewId, setViewId] = useState<string | null>(null);
  const view = archives.find((a) => a.id === viewId) ?? null;
  if (view) return <Viewer item={view} onBack={() => setViewId(null)} />;
  return <ArchiveList onView={setViewId} />;
}

function ArchiveList({ onView }: { onView: (id: string) => void }): ReactNode {
  const [q, setQ] = useState('');
  const [year, setYear] = useState('全部');
  const [concl, setConcl] = useState<'全部' | Conclusion>('全部');
  // 档案行本地副本：借阅登记会更新借阅状态/借阅人
  const [rows, setRows] = useState<Archive[]>(archives);
  const [toast, setToast] = useState<string | null>(null);

  const notify = (msg: string): void => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 1600);
  };

  const filtered = useMemo(
    () => rows.filter(
      (a) => (q === '' || (a.no + a.name + a.party).includes(q)) &&
        (year === '全部' || a.date.startsWith(year)) &&
        (concl === '全部' || a.conclusion === concl),
    ),
    [rows, q, year, concl],
  );

  const [borrow, setBorrow] = useState<Archive | null>(null);
  const [borrowerName, setBorrowerName] = useState('');

  const openBorrow = (a: Archive): void => {
    setBorrow(a);
    setBorrowerName('');
  };

  const confirmBorrow = (): void => {
    if (!borrow) return;
    const name = borrowerName.trim() || currentUser.name;
    setRows((rs) => rs.map((r) => (r.id === borrow.id ? { ...r, borrow: '借阅中', borrower: name } : r)));
    setBorrow(null);
    notify(`已登记借阅：${borrow.name}（借阅人：${name}）`);
  };

  return (
    <div className="ar">
      <div className="ov-bar">
        <div className="ov-card"><div className="ov-num">157</div><div className="ov-label">已归档案卷</div></div>
        <div className="ov-card"><div className="ov-num">6</div><div className="ov-label">本月归档</div></div>
        <div className="ov-card"><div className="ov-num">{rows.filter((a) => a.borrow === '借阅中').length}</div><div className="ov-label">借阅中</div></div>
        <div className="ov-card"><div className="ov-num" style={{ color: 'var(--c-amber)' }}>2</div><div className="ov-label">临期未归档</div></div>
      </div>

      <div className="card ar-search">
        <input className="ar-search-input" placeholder="搜案号、当事人、案件类型、文书名…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="ar-filters">
          <select className="mini-sel" value={year} onChange={(e) => setYear(e.target.value)}>
            <option>全部</option><option>2026</option><option>2025</option>
          </select>
          <select className="mini-sel" value={concl} onChange={(e) => setConcl(e.target.value as '全部' | Conclusion)}>
            <option>全部</option><option>合格</option><option>整改</option><option>否决</option><option>待评</option>
          </select>
          <span className="ar-ai-hint">也可以直接问：「去年矿区超标被否决的那个案子」</span>
        </div>
      </div>

      <div className="card ar-table">
        <div className="ar-thead">
          <span>案号</span><span>案件名</span><span>归档日期</span><span>卷内文书</span><span>评查结论</span><span>借阅状态</span><span>操作</span>
        </div>
        {filtered.length === 0 ? (
          <div className="ar-empty">没有找到对应卷宗，试试换个说法或放宽筛选。</div>
        ) : (
          filtered.map((a, i) => (
            <div className="ar-row" key={a.id} style={{ animationDelay: `${i * 30}ms` }}>
              <span className="ar-no">{a.no}</span>
              <span className="ar-name">{a.name}<small>{a.party}</small></span>
              <span>{a.date}</span>
              <span>{a.docs} 份</span>
              <span><span className={`badge ${CONCL_CLS[a.conclusion]}`}>{a.conclusion}</span></span>
              <span className={a.borrow === '借阅中' ? 'ar-borrow out' : 'ar-borrow'}>{a.borrow}{a.borrower ? `（${a.borrower}）` : ''}</span>
              <span className="ar-ops">
                <button className="side-btn ghost" onClick={() => onView(a.id)}>查阅</button>
                <button className="side-btn ghost" onClick={() => openBorrow(a)}>借阅</button>
                <button className="side-btn ghost" onClick={() => notify(`已导出 ${a.no} 卷宗（${a.docs} 份文书）`)}>导出</button>
              </span>
            </div>
          ))
        )}
      </div>

      {borrow && (
        <div className="modal-mask" onClick={() => setBorrow(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">借阅登记 · {borrow.name}</div>
            <div className="field"><label>借阅人</label><input type="text" placeholder={`请输入借阅人（默认 ${currentUser.name}）`} value={borrowerName} onChange={(e) => setBorrowerName(e.target.value)} /></div>
            <div className="field"><label>借阅事由</label><input type="text" placeholder="如：复议审查 / 上级调阅" /></div>
            <div className="field"><label>借阅期限</label><input type="text" defaultValue="7 天" /></div>
            <div className="modal-text">到期前 1 天将发送琥珀色提醒。</div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setBorrow(null)}>取消</button>
              <button className="btn btn-primary" onClick={confirmBorrow}>确认借阅</button>
            </div>
          </div>
        </div>
      )}

      {toast && <div className="toast ok">{toast}</div>}
    </div>
  );
}

function Viewer({ item, onBack }: { item: Archive; onBack: () => void }): ReactNode {
  const [mode, setMode] = useState<'read' | 'annot'>('read');
  const [zoom, setZoom] = useState<number>(100);
  const [activeCat, setActiveCat] = useState<number>(0);
  const [activeDoc, setActiveDoc] = useState<number>(0);

  return (
    <div className="ar-viewer">
      <button className="back-btn" onClick={onBack}>← 返回卷宗列表</button>
      <div className="ar-v-head">
        <div>
          <div className="ent-name">{item.name}</div>
          <div className="pf-ov-sub">{item.no} · 归档 {item.date} · {item.docs} 份文书</div>
        </div>
        <div className="ar-mode-switch">
          <button className={`seg-btn${mode === 'read' ? ' on' : ''}`} onClick={() => setMode('read')}>阅读</button>
          <button className={`seg-btn${mode === 'annot' ? ' on' : ''}`} onClick={() => setMode('annot')}>批注</button>
        </div>
      </div>

      <div className="ar-v-body">
        <aside className="ar-tree">
          {docTree.map((c, ci) => (
            <div className="ar-tree-cat" key={c.cat}>
              <button className="ar-tree-head" onClick={() => setActiveCat(ci)}>
                <span className={`chev${activeCat === ci ? '' : ' collapsed'}`}>▾</span>{c.cat}
              </button>
              {activeCat === ci && (
                <div className="ar-tree-docs">
                  {c.docs.map((d, di) => (
                    <div key={d.name} className={`ar-tree-doc${d.missing ? ' missing' : ''}${activeDoc === di ? ' on' : ''}`} onClick={() => setActiveDoc(di)}>
                      {d.name}{d.pages ? `（${d.pages}页）` : d.missing ? '（该卷未含此文书）' : ''}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </aside>

        <div className="ar-reader">
          <div className="ar-reader-bar">
            <button className="side-btn ghost" onClick={() => setZoom((z) => Math.max(60, z - 10))}>－</button>
            <span className="ar-zoom">{zoom}%</span>
            <button className="side-btn ghost" onClick={() => setZoom((z) => Math.min(160, z + 10))}>＋</button>
            <span className="ar-page">第 {activeDoc + 1} / {docTree[activeCat].docs.length} 页</span>
          </div>
          <div className="ar-pdf" style={{ transform: `scale(${zoom / 100})` }}>
            <div className="ar-pdf-title">{docTree[activeCat].docs[activeDoc]?.name ?? '文档'}</div>
            <div className="ar-pdf-lines">
              {Array.from({ length: 9 }).map((_, k) => <span key={k} style={{ width: `${70 + ((k * 13) % 28)}%` }} />)}
            </div>
            <div className="ar-pdf-watermark">{mode === 'annot' ? '批注模式' : '阅读模式'}</div>
          </div>
        </div>

        <aside className="ar-ai">
          <div className="card ar-ai-card">
            <div className="sec-title" style={{ marginBottom: 8 }}>AI 卷宗摘要</div>
            <div className="ar-ai-text">
              本案因「听证期限不足」被否决（命中一票否决第 9 项）。整改要点：① 补正听证期限 ② 重新计算决定时限 ③ 复核文书送达回证。
            </div>
            <button className="side-btn terra" style={{ marginTop: 8 }}>生成阅卷笔记</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
