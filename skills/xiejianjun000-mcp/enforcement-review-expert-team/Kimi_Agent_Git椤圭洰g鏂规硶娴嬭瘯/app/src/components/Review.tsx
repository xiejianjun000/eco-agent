import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  VETO_GROUPS, SOP_STAGES, SOP_CURRENT, queue, RESULT_CLS, RESULT_LABEL,
  type ReviewCase, type VetoResult,
} from '../data/review';

const TOTAL = VETO_GROUPS.reduce((n, g) => n + g.items.length, 0);
const HIT = VETO_GROUPS.flatMap((g) => g.items).find((i) => i.result === 'hit');

export default function Review({ onNavigate }: { onNavigate: (id: string) => void }): ReactNode {
  const [sel, setSel] = useState<number>(74);
  const [scanStep, setScanStep] = useState<number>(0);
  const [scanning, setScanning] = useState<boolean>(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set(VETO_GROUPS.map((g) => g.cat)));
  // 队列本地副本：人工复核结论会更新卷状态
  const [queueState, setQueueState] = useState<ReviewCase[]>(queue);
  const [decisions, setDecisions] = useState<Record<number, string>>({});
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!scanning) return;
    timer.current = setInterval(() => {
      setScanStep((s) => {
        const next = s + 1;
        if (next >= TOTAL) {
          // 最后一项扫完的同一个 tick 收尾，避免 done=true && scanning=true 僵尸态
          if (timer.current) clearInterval(timer.current);
          setScanning(false);
          return TOTAL;
        }
        return next;
      });
    }, 110);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [scanning]);

  const startScan = (): void => {
    if (scanning) return;
    setScanStep(0);
    setScanning(true);
  };

  const current = queueState.find((q) => q.vol === sel) ?? queueState[0];
  const done = scanStep >= TOTAL;
  const hit = done && HIT;

  // 人工复核结论：更新当前卷状态并给出徽标反馈
  const decide = (action: '确认通过' | '退回补正' | '提出异议'): void => {
    setDecisions((p) => ({ ...p, [sel]: action }));
    setQueueState((qs) => qs.map((q) => {
      if (q.vol !== sel) return q;
      if (action === '确认通过') return { ...q, status: '已完成', progress: undefined };
      if (action === '退回补正') return { ...q, status: '待评', progress: undefined };
      return { ...q, status: '待人工复核', progress: undefined };
    }));
  };

  const statusCls: Record<ReviewCase['status'], string> = {
    待评: 'aux', 'AI初评中': 'amber', 待人工复核: 'blue', 已完成: 'olive',
  };

  return (
    <div className="rv">
      {/* 百卷精评横幅 */}
      <div className="card rv-banner">
        <div className="rv-big">
          <div className="rv-num"><span className="rv-cur">73</span><span className="rv-tot">/100</span></div>
          <div className="rv-banner-sub">百卷精评行动 · 第 74 卷 AI 初评完成，待您复核</div>
        </div>
        <div className="rv-prog-wrap">
          <div className="rv-prog"><div className="rv-prog-fill" style={{ width: '73%' }} /></div>
        </div>
        <div className="rv-mini">
          <span className="badge olive">通过 68</span>
          <span className="badge amber">整改 4</span>
          <span className="badge red">否决 1</span>
        </div>
      </div>

      {/* SOP 五阶段 */}
      <div className="card rv-sop">
        {SOP_STAGES.map((s, idx) => (
          <div key={s.name} className={`rv-sop-node${idx === SOP_CURRENT ? ' active' : ''}${idx < SOP_CURRENT ? ' past' : ''}`}>
            <span className="rv-sop-dot" />
            <span className="rv-sop-name">{s.name}</span>
            <span className="rv-sop-expert">{s.expert}</span>
          </div>
        ))}
      </div>

      <div className="rv-body">
        {/* 左：评查队列 */}
        <div className="card rv-queue">
          <div className="sec-head"><span className="sec-title">评查队列</span></div>
          {queueState.map((q) => (
            <div key={q.vol} className={`rv-q-row${q.vol === sel ? ' sel' : ''}`} onClick={() => { setSel(q.vol); setScanStep(0); setScanning(false); }}>
              <div className="rv-q-top">
                <span className="rv-q-name">第 {q.vol} 卷 · {q.name}</span>
                <span className={`badge ${statusCls[q.status]}`}>{q.status}</span>
              </div>
              <div className="rv-q-no">{q.no}</div>
              {q.status === 'AI初评中' && q.progress != null && (
                <div className="rv-q-prog"><div className="rv-q-fill" style={{ width: `${q.progress}%` }} /><span>{q.progress}%</span></div>
              )}
              {q.status === '已完成' && (
                <div className={`rv-q-score${q.denied ? ' denied' : ''}`}>{q.denied ? '否决 · 0 分' : `得分 ${q.score ?? '—'}`}</div>
              )}
            </div>
          ))}
        </div>

        {/* 右：25 项否决扫描 */}
        <div className="card rv-panel">
          <div className="rv-panel-note">
            当前案卷：第 {current.vol} 卷 · {current.name}（{current.no}）。以下 25 项任中一项，本案卷即为不合格（0 分）。
            <span className="rv-tooltip" title="指触及法定底线的严重问题，案卷直接判不合格">一票否决?</span>
          </div>

          <div className="rv-scan-bar">
            <span className="rv-scan-count">{scanStep}/{TOTAL} 已扫描</span>
            <button className="btn btn-primary" onClick={startScan} disabled={scanning}>
              {scanning ? '扫描中…' : done ? '重新扫描' : '开始扫描'}
            </button>
          </div>

          <div className="rv-groups">
            {VETO_GROUPS.map((g) => {
              const open = openGroups.has(g.cat);
              return (
                <div className="rv-group" key={g.cat}>
                  <button className="rv-group-head" onClick={() => setOpenGroups((p) => { const n = new Set(p); n.has(g.cat) ? n.delete(g.cat) : n.add(g.cat); return n; })}>
                    <span className={`chev${open ? '' : ' collapsed'}`}>▾</span>
                    {g.cat}
                  </button>
                  {open && (
                    <div className="rv-group-body">
                      {g.items.map((it) => {
                        const idx = globalIndex(it.no);
                        const scanned = idx < scanStep;
                        const scanningRow = scanning && idx === scanStep - 1;
                        return (
                          <div key={it.no} className={`rv-item${scanned && it.result === 'hit' ? ' hit' : ''}${scanningRow ? ' scanning' : ''}`}>
                            <span className="rv-item-no">{it.no}</span>
                            <span className="rv-item-name">{it.name}</span>
                            <span className="rv-item-kw">{it.keyword}</span>
                            {scanned ? (
                              <span className={`badge ${RESULT_CLS[it.result as VetoResult]}`}>{RESULT_LABEL[it.result as VetoResult]}</span>
                            ) : (
                              <span className="rv-item-wait">待扫描</span>
                            )}
                            {scanned && it.result !== 'na' && (
                              <span className="rv-item-law">{it.law}</span>
                            )}
                            {scanned && it.extract && (
                              <div className="rv-item-extract">{it.extract}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 汇总卡 */}
          {done && (
            <div className={`rv-summary${hit ? ' denied' : ' pass'}`}>
              {hit ? (
                <>
                  <div className="rv-sum-title">命中第 {hit.no} 项：{hit.name} — 本案卷评查不合格</div>
                  <ul className="rv-sum-list">
                    <li>听证告知距决定不足 3 日，违反法定时限。</li>
                    <li>整改建议：补正后重新计算听证期限，再作决定。</li>
                  </ul>
                </>
              ) : (
                <div className="rv-sum-title">本案卷通过 25 项否决扫描，建议得分 92 分</div>
              )}
              <button className="btn btn-ghost rv-sum-btn" onClick={() => onNavigate('archive')}>生成评查报告 → 归档</button>
            </div>
          )}
        </div>
      </div>

      {/* 人工复核确认条 */}
      <div className="rv-confirm">
        <span className="rv-confirm-note">
          AI 初评结果仅供参考，请复核后确认。
          {decisions[sel] && <span className="badge olive" style={{ marginLeft: 8 }}>已{decisions[sel]}</span>}
        </span>
        <div className="rv-confirm-btns">
          <button className="btn btn-primary" onClick={() => decide('确认通过')}>确认通过</button>
          <button className="btn btn-ghost" onClick={() => decide('退回补正')}>退回补正</button>
          <button className="btn btn-ghost" onClick={() => decide('提出异议')}>提出异议</button>
        </div>
      </div>
    </div>
  );
}

// 项编号(1-based) → 全局 0-based 索引
function globalIndex(no: number): number {
  let acc = 0;
  for (const g of VETO_GROUPS) {
    const f = g.items.find((i) => i.no === no);
    if (f) return acc + g.items.indexOf(f);
    acc += g.items.length;
  }
  return no - 1;
}
