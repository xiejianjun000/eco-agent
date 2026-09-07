import { useMemo, useState, type ReactNode } from 'react';
import {
  cases, STAGES, DOC_COUNTS, STAGE_STATUS_CLS, openCases, type CaseItem, type Stage, type CaseDoc,
} from '../data/enforcement';

const stageIndex = (s: Stage): number => STAGES.indexOf(s);

export default function Enforcement({ onNavigate }: { onNavigate: (id: string) => void }): ReactNode {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = cases.find((c) => c.id === openId) ?? null;

  if (open) return <CaseWorkbench item={open} onBack={() => setOpenId(null)} onNavigate={onNavigate} />;

  return <CaseList onOpen={setOpenId} />;
}

function CaseList({ onOpen }: { onOpen: (id: string) => void }): ReactNode {
  const [stageFilter, setStageFilter] = useState<Stage | 'all'>('all');
  const [riskOnly, setRiskOnly] = useState<boolean>(false);

  const filtered = useMemo(
    () => cases.filter((c) => (stageFilter === 'all' || c.stage === stageFilter) && (!riskOnly || !!c.warning)),
    [stageFilter, riskOnly],
  );

  const inOffice = openCases.length;
  const thisMonth = 3;
  const nearDeadline = cases.filter((c) => c.deadline.includes('天') && !c.deadline.includes('已结案')).length;
  const vetoWarn = cases.filter((c) => !!c.warning).length;

  return (
    <div className="ef">
      <div className="ov-bar">
        <div className="ov-card"><div className="ov-num">{inOffice}</div><div className="ov-label">在办案件</div></div>
        <div className="ov-card"><div className="ov-num">{thisMonth}</div><div className="ov-label">本月立案</div></div>
        <div className="ov-card"><div className="ov-num">{nearDeadline}</div><div className="ov-label">临近期限</div></div>
        <div className="ov-card"><div className="ov-num" style={{ color: 'var(--c-red)' }}>{vetoWarn}</div><div className="ov-label">否决预警中</div></div>
      </div>

      <div className="ef-toolbar">
        <div className="seg">
          <button className={`seg-btn${stageFilter === 'all' ? ' on' : ''}`} onClick={() => setStageFilter('all')}>全部</button>
          {STAGES.map((s) => (
            <button key={s} className={`seg-btn${stageFilter === s ? ' on' : ''}`} onClick={() => setStageFilter(s)}>{s}</button>
          ))}
        </div>
        <label className="ef-risk">
          <input type="checkbox" checked={riskOnly} onChange={(e) => setRiskOnly(e.target.checked)} /> 仅看否决预警
        </label>
        <span className="ef-count">共 {filtered.length} 件</span>
      </div>

      <div className="ef-list">
        {filtered.map((c, i) => (
          <div key={c.id} className="card ef-card" style={{ animationDelay: `${i * 40}ms` }}>
            <div className="ef-card-top">
              <div className="ef-card-name">{c.name}</div>
              <span className={`badge blue`}>{c.stage}</span>
            </div>
            <div className="ef-card-no">{c.no} · 当事人 {c.party} · 承办 {c.handler}</div>
            <div className="ef-mini-bar">
              {STAGES.map((s, idx) => (
                <span key={s} className={`ef-mini-dot${idx <= stageIndex(c.stage) ? ' on' : ''}`} title={s} />
              ))}
            </div>
            {c.warning && <div className="ef-warn">{c.warning}</div>}
            {c.suggest && <div className="ef-suggest">建议：{c.suggest}</div>}
            <div className="ef-card-foot">
              <span className="ef-deadline">⏱ {c.deadline}</span>
              <button className="btn btn-primary ef-enter" onClick={() => onOpen(c.id)}>进入办案</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CaseWorkbench({ item, onBack, onNavigate }: { item: CaseItem; onBack: () => void; onNavigate: (id: string) => void }): ReactNode {
  const [tab, setTab] = useState<Stage>(item.stage);
  const [toast, setToast] = useState<string | null>(null);
  const curIdx = stageIndex(item.stage);

  const notify = (msg: string): void => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 1600);
  };

  const stageCounts = STAGES.map((s) => {
    const docs = item.docs[s] ?? [];
    const done = docs.filter((d) => d.status !== '未起草').length;
    return { stage: s, done, todo: DOC_COUNTS[s] - done };
  });

  const docsForTab: CaseDoc[] = item.docs[tab] ?? [];
  const remaining = DOC_COUNTS[tab] - docsForTab.length;

  return (
    <div className="ef-detail">
      <button className="back-btn" onClick={onBack}>← 返回案件列表</button>

      <div className="card ef-head">
        <div className="ent-name">{item.name}</div>
        <div className="ef-head-meta">{item.no} · {item.party} · 承办 {item.handler}</div>
        <div className="ef-head-foot">
          <span className={`badge blue`}>{item.stage}</span>
          <span className="ef-deadline" style={{ color: 'var(--c-amber)' }}>⏱ {item.deadline}</span>
        </div>
      </div>

      {/* SOP 阶段条 */}
      <div className="card ef-sop">
        {STAGES.map((s, idx) => {
          const c = stageCounts[idx];
          return (
            <button key={s} className={`ef-sop-node${idx === curIdx ? ' active' : ''}${idx < curIdx ? ' past' : ''}`} onClick={() => setTab(s)}>
              <span className="ef-sop-dot" />
              <span className="ef-sop-name">{s}</span>
              <span className="ef-sop-count">{c.done}/{DOC_COUNTS[s]}</span>
            </button>
          );
        })}
      </div>

      <div className="ef-split">
        {/* 左 60% 阶段内容 */}
        <div className="card ef-left">
          <div className="sec-head"><span className="sec-title">{tab} · 文书清单</span><span className="sec-count">{DOC_COUNTS[tab]} 类模板</span></div>
          <div className="ef-doc-list">
            {docsForTab.map((d) => (
              <div className="ef-doc-row" key={d.name}>
                <span className="ef-doc-name">{d.name}</span>
                <span className={`badge ${STAGE_STATUS_CLS[d.status]}`}>{d.status}</span>
                <div className="ef-doc-actions">
                  <button className="side-btn ghost">AI 起草</button>
                  <button className="side-btn ghost" onClick={() => notify(`「${d.name}」已在右侧「文书协同」面板打开`)}>打开协同</button>
                  <button className="side-btn ghost">上传</button>
                </div>
              </div>
            ))}
            {remaining > 0 && <div className="ef-doc-rest">其余 {remaining} 份文书待生成（共 {DOC_COUNTS[tab]} 类模板）</div>}
          </div>

          {tab === '调查' && item.evidence && (
            <div className="ef-evidence">
              <div className="sec-head"><span className="sec-title">证据清单</span></div>
              {item.evidence.map((e) => (
                <div className={`ef-evi-row${e.state === 'missing' ? ' miss' : ''}`} key={e.name}>
                  <span>{e.state === 'missing' ? '⚠' : '✓'}</span>
                  <span>{e.name}</span>
                  {e.note && <span className="ef-evi-note">{e.note}</span>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 右 40% 智能辅助 */}
        <div className="ef-right">
          {item.vetoScan && (
            <div className="card ef-veto">
              <div className="ef-veto-head">25 项一票否决扫描</div>
              <div className="ef-veto-sum">已扫 {item.vetoScan.scanned} 项：<b style={{ color: 'var(--c-olive)' }}>{item.vetoScan.pass} 通过</b> · <b style={{ color: 'var(--c-red)' }}>{item.vetoScan.risk} 风险</b></div>
              {item.vetoScan.risks.map((r) => (
                <div className="ef-veto-risk" key={r.name}>
                  <div className="ef-veto-risk-name">{r.name}</div>
                  <div className="ef-veto-risk-law">{r.law}</div>
                  <div className="ef-veto-risk-fix">{r.fix}</div>
                </div>
              ))}
            </div>
          )}
          {item.sentencing && (
            <div className="card ef-sent">
              <div className="ef-sent-head">裁量辅助</div>
              <div className="ef-sent-basis">{item.sentencing.basis}</div>
              <div className="ef-sent-range">{item.sentencing.range}</div>
              <div className="ef-sent-slider"><div className="ef-sent-fill" /></div>
              <div className="ef-sent-note">{item.sentencing.note}</div>
              <button className="side-btn ghost" style={{ marginTop: 8 }}>供您参考</button>
            </div>
          )}
          {item.codeLink && (
            <div className="card ef-code">
              <div className="ef-code-head">法典衔接提示</div>
              <div className="ef-code-text">{item.codeLink}</div>
            </div>
          )}
          {item.transfer && (
            <div className="card ef-transfer">
              <div className="ef-transfer-head">移送研判</div>
              <div className={`ef-transfer-detail${item.transfer.reached ? ' reach' : ''}`}>{item.transfer.detail}</div>
            </div>
          )}
        </div>
      </div>

      {/* 底部 AI 活动流 */}
      <div className="card ef-ai-flow">
        <div className="sec-head"><span className="sec-title">AI 活动流</span></div>
        <div className="timeline">
          {[
            { d: '09:12', t: '法条通 完成法条核验', s: '已核对 14 条法条适用性' },
            { d: '09:20', t: '文书成 生成决定书草稿', s: '待您确认后送签' },
            { d: '09:35', t: '卷查清 否决扫描完成', s: '发现 1 项风险：听证期限不足' },
            { d: '10:02', t: '督察精 推送地图落图', s: '金竹山矿区点位已标注' },
          ].map((a) => (
            <div className="tl-row" key={a.d}>
              <span className="tl-dot" />
              <div className="tl-body">
                <div className="tl-date">{a.d} · {a.t}</div>
                <div className="tl-desc">{a.s}</div>
              </div>
            </div>
          ))}
        </div>
        <button className="side-btn ghost" style={{ marginTop: 8 }} onClick={() => onNavigate('review')}>发起随办随评 → 案卷评查</button>
      </div>

      {toast && <div className="toast ok">{toast}</div>}
    </div>
  );
}
