import { useEffect, useState, type ReactNode } from 'react';
import {
  enterprises, overview, riskMeta, industries, levels, riskFilters, type Enterprise,
} from '../data/enterprises';

function useCountUp(target: number, dur = 600): number {
  const [val, setVal] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      setVal(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, dur]);
  return val;
}

function CemsChart({ data }: { data: Enterprise['cems'] }): ReactNode {
  if (!data.length) return <div className="chart-empty">暂无排放监测数据</div>;
  const w = 320, h = 120, pad = 16;
  const max = Math.max(...data.map((d) => d.v)) * 1.1;
  const pts = data.map((d, i) => {
    const x = pad + (i * (w - pad * 2)) / (data.length - 1);
    const y = h - pad - (d.v / max) * (h - pad * 2);
    return { x, y, d };
  });
  const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="line-chart">
      <polyline points={line} fill="none" stroke="#6E8299" strokeWidth="2" />
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={p.d.over ? 4 : 2.5} fill={p.d.over ? '#B0574A' : '#6E8299'} />
      ))}
      {data.map((d, i) => (
        <text key={i} x={pts[i].x} y={h - 3} fontSize="8" fill="#9A9184" textAnchor="middle">{d.d}</text>
      ))}
    </svg>
  );
}

function Detail({ e, onBack, onNavigate }: { e: Enterprise; onBack: () => void; onNavigate: (id: string) => void }): ReactNode {
  const [tab, setTab] = useState('license');
  const from = new Date(e.licenseFrom).getTime();
  const to = new Date(e.licenseTo).getTime();
  const now = new Date('2026-08-03').getTime();
  const pct = Math.max(0, Math.min(100, ((now - from) / (to - from)) * 100));
  const remaining = (to - now) / (1000 * 86400 * 30);
  const nearExpiry = remaining < 3;

  return (
    <div className="ent-detail">
      <button className="back-btn" onClick={onBack}>‹ 返回企业列表</button>
      <div className="ent-head">
        <div>
          <div className="ent-name">{e.name}</div>
          <div className="ent-badges">
            <span className={`badge ${riskMeta[e.risk].cls}`}>{riskMeta[e.risk].label}</span>
            <span className="ent-permit">许可证 {e.permitNo}</span>
          </div>
        </div>
        <div className="ent-actions">
          <button className="btn btn-ghost">发起检查</button>
          <button className="btn btn-ghost">立案</button>
          <button className="btn btn-primary" onClick={() => onNavigate('map')}>生成帮扶建议</button>
        </div>
      </div>

      <div className="license-bar">
        <div className="lb-top">
          <span>排污许可证有效期</span>
          <span className={nearExpiry ? 'lb-near' : ''}>{e.licenseFrom} ~ {e.licenseTo}（剩 {Math.max(0, Math.round(remaining))} 个月）</span>
        </div>
        <div className="lb-track"><div className="lb-fill" style={{ width: `${pct}%`, background: nearExpiry ? 'var(--c-amber)' : 'var(--c-olive)' }} /></div>
      </div>

      <div className="ent-tabs">
        {['license', 'cems', 'electric', 'cases', 'help'].map((t) => (
          <button key={t} className={`ent-tab${tab === t ? ' on' : ''}`} onClick={() => setTab(t)}>
            {{ license: '证照信息', cems: '排放画像', electric: '用电画像', cases: '案件记录', help: '帮扶与信用' }[t]}
          </button>
        ))}
      </div>

      <div className="ent-tab-body">
        {tab === 'license' && (
          <div className="kv">
            <div><span>许可证号</span><b>{e.permitNo}</b></div>
            <div><span>有效期</span><b>{e.licenseFrom} ~ {e.licenseTo}</b></div>
            <div><span>行业类别</span><b>{e.industry}</b></div>
            <div><span>主要排放因子</span><b>{e.factors}</b></div>
            <div className="kv-src">读取自排污许可证管理端 · 2026-07-28 同步</div>
          </div>
        )}
        {tab === 'cems' && (
          <div>
            <CemsChart data={e.cems} />
            <div className="chart-cap">近 90 天 CEMS 排放趋势，红点为超标记录{e.risk === 'over' ? `（${e.name} 近 30 天多次超标）` : ''}</div>
          </div>
        )}
        {tab === 'electric' && (
          <div className="elec">
            {e.electricity.length === 0 ? <div className="chart-empty">暂无用电监测数据</div> : e.electricity.map((m) => (
              <div key={m.d} className="elec-row">
                <span className="elec-m">{m.d}</span>
                <div className="elec-bars">
                  <div className="eb use" style={{ height: `${m.use / 12}px` }} title={`用电 ${m.use}`} />
                  <div className="eb prod" style={{ height: `${m.produce / 12}px` }} title={`产量 ${m.produce}`} />
                </div>
                <span className="elec-diff">{m.use - m.produce > 40 ? '⚠ 用电偏高' : '匹配'}</span>
              </div>
            ))}
            <div className="elec-legend"><span><i className="eb use" />用电</span><span><i className="eb prod" />产量折算</span></div>
          </div>
        )}
        {tab === 'cases' && (
          <div className="timeline">
            {e.cases.length === 0 ? <div className="chart-empty">暂无案件记录</div> : e.cases.map((c, i) => (
              <div key={i} className="tl-row">
                <span className="tl-dot" />
                <div className="tl-body">
                  <div className="tl-date">{c.date} · {c.type}</div>
                  <div className="tl-desc">{c.desc}</div>
                  <div className="tl-status">{c.status}</div>
                </div>
              </div>
            ))}
          </div>
        )}
        {tab === 'help' && (
          <div>
            <div className="kv"><div><span>信用等级</span><b>{e.credit}</b></div></div>
            <div className="help-list">
              {e.help.length === 0 ? <div className="chart-empty">暂无帮扶记录</div> : e.help.map((h, i) => <div key={i} className="help-item">{h}</div>)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Enterprises({ onNavigate }: { onNavigate: (id: string) => void }): ReactNode {
  const [detail, setDetail] = useState<Enterprise | null>(null);
  const [search, setSearch] = useState('');
  const [ind, setInd] = useState('全部');
  const [lvl, setLvl] = useState('全部');
  const [risks, setRisks] = useState<Set<string>>(new Set());

  const cReg = useCountUp(overview.registered);
  const cKey = useCountUp(overview.key);
  const cOver = useCountUp(overview.over30);
  const cDue = useCountUp(overview.permitDue);

  const toggleRisk = (k: string) =>
    setRisks((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const filtered = enterprises.filter((e) => {
    if (search && !e.name.includes(search) && !e.permitNo.includes(search)) return false;
    if (ind !== '全部' && !e.industry.includes(ind)) return false;
    if (risks.has('over') && e.risk !== 'over') return false;
    if (risks.has('due') && e.risk !== 'due') return false;
    if (risks.has('hasCase') && e.openCases === 0) return false;
    return true;
  });

  if (detail) return <Detail e={detail} onBack={() => setDetail(null)} onNavigate={onNavigate} />;

  return (
    <div className="ents">
      <div className="ov-bar">
        {[
          { v: cReg, l: '在册企业', c: 'var(--c-terra)' },
          { v: cKey, l: '重点监管', c: 'var(--c-red)' },
          { v: cOver, l: '近30天有超标', c: 'var(--c-amber)' },
          { v: cDue, l: '证照临期(90天)', c: 'var(--c-blue)' },
        ].map((o, i) => (
          <div key={i} className="ov-card" style={{ animationDelay: `${i * 50}ms` }}>
            <div className="ov-num" style={{ color: o.c }}>{o.v}</div>
            <div className="ov-label">{o.l}</div>
          </div>
        ))}
      </div>

      <div className="ent-toolbar">
        <input className="addr-input" style={{ maxWidth: 240 }} placeholder="搜企业名称 / 许可证号" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="mini-sel" value={ind} onChange={(e) => setInd(e.target.value)}>
          {industries.map((x) => <option key={x}>{x}</option>)}
        </select>
        <select className="mini-sel" value={lvl} onChange={(e) => setLvl(e.target.value)}>
          {levels.map((x) => <option key={x}>{x}</option>)}
        </select>
        {riskFilters.map((r) => (
          <button key={r.key} className={`fchip${risks.has(r.key) ? ' on' : ''}`} onClick={() => toggleRisk(r.key)}>{r.label}</button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn btn-primary">读取排污许可证</button>
          <button className="btn btn-ghost">导出名单</button>
        </div>
      </div>

      <div className="ent-grid">
        {filtered.map((e, i) => (
          <div key={e.id} className="ent-card" style={{ animationDelay: `${i * 40}ms` }}>
            <div className="ent-card-top">
              <span className="ent-card-name">{e.name}</span>
              <span className={`badge ${riskMeta[e.risk].cls}`}>{riskMeta[e.risk].label}</span>
            </div>
            <div className="ent-lines">
              <div><span>许可证号</span>{e.permitNo}</div>
              <div><span>行业类别</span>{e.industry}</div>
              <div><span>主要因子</span>{e.factors}</div>
              <div><span>未结案件</span>{e.openCases} 件</div>
            </div>
            <blockquote className="ai-quote">{e.aiNote}</blockquote>
            <div className="ent-card-foot">
              <button className="todo-go" onClick={() => setDetail(e)}>查看画像 →</button>
              <button className="todo-go" onClick={() => onNavigate('enforcement')}>发起检查</button>
              <button className="todo-go" onClick={() => onNavigate('map')}>在地图查看</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
