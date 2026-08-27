import { useRef, useState, type ReactNode } from 'react';
import PlatformAdd from './PlatformAdd';
import { IconShield } from './icons';
import { platforms as seed, STATUS_META, type Platform, type PlatformStatus } from '../data/platforms';
import type { WhitelistPlatform } from '../data/whitelist';
import { addPlatformRemote } from '../lib/hermesClient';

interface ReportDay {
  date: string;
  ok: boolean;
  note: string;
}

const REPORT_DAYS: ReportDay[] = [
  { date: '7/26', ok: true, note: '全部正常' },
  { date: '7/27', ok: true, note: '全部正常' },
  { date: '7/28', ok: true, note: '全部正常' },
  { date: '7/29', ok: true, note: '全部正常' },
  { date: '7/30', ok: true, note: '全部正常' },
  { date: '7/31', ok: true, note: '全部正常' },
  { date: '8/1', ok: true, note: '全部正常' },
  { date: '8/2', ok: true, note: '全部正常' },
  { date: '8/3', ok: true, note: '全部正常' },
];

type View = 'overview' | 'add';

export default function Platforms({ onNavigate, onOpenBrowser }: { onNavigate: (id: string) => void; onOpenBrowser?: (url: string) => void }): ReactNode {
  const [view, setView] = useState<View>('overview');
  const [list, setList] = useState<Platform[]>(seed);
  const [loginTarget, setLoginTarget] = useState<Platform | null>(null);
  const [pauseTarget, setPauseTarget] = useState<Platform | null>(null);
  const [paused, setPaused] = useState<Set<string>>(new Set());
  const reportRef = useRef<HTMLDivElement | null>(null);

  const managed = list.filter((p) => p.status === 'managed' && !paused.has(p.id)).length;
  const connecting = list.filter((p) => p.status === 'pending' || p.status === 'configuring').length;

  const statusBadge = (s: PlatformStatus): ReactNode => {
    const m = STATUS_META[s];
    return (
      <span className={`badge ${m.cls}`}>
        {s === 'managed' && <span className="bdot breathe" />}
        {m.label}
      </span>
    );
  };

  const onAdded = async (p: WhitelistPlatform): Promise<void> => {
    // 持久化到后端白名单
    try {
      const res = await addPlatformRemote({
        name: p.name,
        purpose: p.purpose,
        keywords: p.keywords,
        fields: p.fields,
        captchaAuto: p.captchaAuto,
        id: p.id,
      });
      if (!res.ok) {
        console.warn('[Platforms] 后端新增平台返回非 ok:', res);
      }
    } catch (err) {
      console.warn('[Platforms] 后端新增平台失败（将在前端临时展示）:', err);
    }
    // 前端列表追加
    setList((prev) => [
      ...prev,
      {
        id: p.id,
        name: p.name,
        purpose: p.purpose,
        url: p.url,
        status: 'pending' as PlatformStatus,
        rows: [
          { label: '最近同步', value: '—' },
          { label: '状态', value: '待登录' },
        ],
      },
    ]);
    setView('overview');
  };

  const confirmPause = (): void => {
    if (!pauseTarget) return;
    setPaused((prev) => new Set(prev).add(pauseTarget.id));
    setPauseTarget(null);
  };

  const resume = (id: string): void => {
    setPaused((prev) => {
      const n = new Set(prev);
      n.delete(id);
      return n;
    });
  };

  if (view === 'add') {
    return (
      <div className="add-wrap">
        <button className="back-btn" onClick={() => setView('overview')}>← 返回平台管理</button>
        <PlatformAdd onAdded={onAdded} onBack={() => setView('overview')} onOpenBrowser={onOpenBrowser} />
      </div>
    );
  }

  return (
    <div className="pf">
      {/* 1. 概览条 */}
      <div className="card pf-overview">
        <div className="pf-ov-stats">
          <div className="pf-ov-item"><b>{managed}</b><span>已接通</span></div>
          <div className="pf-ov-sep" />
          <div className="pf-ov-item"><b>{connecting}</b><span>接入中</span></div>
          <div className="pf-ov-sep" />
          <div className="pf-ov-item pf-ov-ok">
            <span className="badge olive"><span className="bdot breathe" />今日巡检全部正常</span>
          </div>
          <div className="pf-ov-item pf-ov-ok"><span className="pf-ov-sub">连续巡检 9 天 · 自 2026-07-26</span></div>
        </div>
        <div className="pf-ov-actions">
          <button className="btn btn-ghost" onClick={() => reportRef.current?.scrollIntoView({ behavior: 'smooth' })}>
            生成今日巡检说明
          </button>
          <button className="btn btn-primary" onClick={() => setView('add')}>+ 新增平台</button>
        </div>
      </div>

      {/* 2. 平台卡片列表 */}
      <div className="pf-grid">
        {list.map((p, i) => {
          const isPaused = paused.has(p.id);
          return (
            <div
              key={p.id}
              className="card pf-card"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              {p.notice && (
                <div className="pf-notice">{p.notice}</div>
              )}
              <div className="pf-card-top">
                <div className="pf-card-name">{p.name}</div>
                {statusBadge(isPaused ? 'pending' : p.status)}
              </div>
              <div className="pf-card-purpose">{p.purpose}</div>
              <div className="pf-rows">
                {p.rows.map((r) => (
                  <div className="pf-row" key={r.label}>
                    <span className="pf-row-l">{r.label}</span>
                    <span className={`pf-row-v${r.alert ? ' alert' : ''}`}>{r.value}</span>
                  </div>
                ))}
                {p.status === 'configuring' && p.progress != null && (
                  <div className="pf-prog">
                    <div className="pf-prog-track"><div className="pf-prog-fill" style={{ width: `${p.progress}%` }} /></div>
                    <span>{p.progress}%</span>
                  </div>
                )}
              </div>
              <div className="pf-actions">
                {isPaused ? (
                  <button className="btn btn-ghost" onClick={() => resume(p.id)}>恢复代管</button>
                ) : p.status === 'managed' ? (
                  <>
                    <button className="btn btn-ghost" onClick={() => reportRef.current?.scrollIntoView({ behavior: 'smooth' })}>查看巡检报告</button>
                    <button className="btn btn-ghost" onClick={() => setPauseTarget(p)}>暂停代管</button>
                    {p.url && (
                      <button className="btn btn-primary" onClick={() => onOpenBrowser?.(p.url!)} title="在右侧面板打开平台">打开</button>
                    )}
                  </>
                ) : p.status === 'pending' ? (
                  <>
                    <button className="btn btn-primary" onClick={() => setLoginTarget(p)}>人工登录一次</button>
                    {p.url && (
                      <button className="btn btn-ghost" onClick={() => onOpenBrowser?.(p.url!)} title="在右侧面板打开平台">打开</button>
                    )}
                  </>
                ) : (
                  <button className="btn btn-ghost" disabled>配置中…</button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. 每日巡检报告区 */}
      <div className="card pf-report" ref={reportRef}>
        <div className="sec-head">
          <span className="sec-title">每日巡检报告</span>
          <span className="sec-count">2026-08-03 · 周一</span>
        </div>
        <div className="pf-expert-chip">
          <span className="exp-avatar" style={{ background: 'rgba(124,139,95,.18)', color: 'var(--c-olive)' }}>巡</span>
          <span className="pf-expert-text">巡检员 已完成今日 6 平台巡检，用时 4 分钟</span>
        </div>
        <div className="pf-concl">
          <div className="pf-ok-list">
            <div className="pf-ok"><span className="bdot olive" />大气监督帮扶平台 · 正常</div>
            <div className="pf-ok"><span className="bdot olive" />行政执法系统 · 配置待续</div>
            <div className="pf-ok"><span className="bdot olive" />排污许可证管理端 · 配置中</div>
            <div className="pf-ok"><span className="bdot olive" />在线监测系统管理端 · 待登录</div>
            <div className="pf-ok"><span className="bdot olive" />用电监控系统管理端 · 配置中</div>
          </div>
          <div className="pf-abn-card">
            <div className="pf-abn-head"><span className="bdot red" />异常 1 项</div>
            <div className="pf-abn-body">水环境平台发现 2 家企业排口数据中断 &gt;6 小时，已生成核查建议。</div>
            <button className="btn btn-ghost pf-abn-btn" onClick={() => onNavigate('enforcement')}>异常处理 → 执法办案</button>
          </div>
        </div>
        <div className="pf-streak">
          <span className="pf-streak-label">连续记录</span>
          <div className="pf-streak-dots">
            {REPORT_DAYS.map((d) => (
              <div className="pf-dot-wrap" key={d.date} title={`${d.date}：${d.note}`}>
                <span className={`pf-dot${d.ok ? ' ok' : ' bad'}`} />
                <span className="pf-dot-date">{d.date}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 人工登录引导弹窗 */}
      {loginTarget && <LoginGuide platform={loginTarget} onClose={() => setLoginTarget(null)} />}

      {/* 暂停代管确认 */}
      {pauseTarget && (
        <div className="modal-mask" onClick={() => setPauseTarget(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">确认暂停 AI 代管？</div>
            <div className="modal-text">
              暂停「{pauseTarget.name}」期间，该平台的预警将<b>不会自动抓取</b>，
              巡检报告也不再包含它。你可随时在本页恢复代管。
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setPauseTarget(null)}>取消</button>
              <button className="btn btn-primary" onClick={confirmPause}>确认暂停</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LoginGuide({ platform, onClose }: { platform: Platform; onClose: () => void }): ReactNode {
  const [step, setStep] = useState<number>(1);
  const [manual, setManual] = useState<boolean>(false);
  const [cap, setCap] = useState<string>('');

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal-box login-guide" onClick={(e) => e.stopPropagation()}>
        <div className="lg-head">
          <IconShield />
          <div>
            <div className="lg-title">{platform.name}</div>
            <div className="lg-sub">人工登录一次 · 之后 AI 自动接管</div>
          </div>
        </div>

        <div className="steps">
          {['登录说明', '验证码协助', '完成接管'].map((t, i) => (
            <div key={t} className={`step${step > i ? ' done' : ''}${step === i + 1 ? ' active' : ''}`}>
              <span className="num">{step > i ? '✓' : i + 1}</span>
              <span>{t}</span>
            </div>
          ))}
        </div>

        {step === 1 && (
          <div className="lg-body">
            <p className="lg-p">请在本页面完成一次人工登录（输入账号、密码与验证码）。</p>
            <ul className="lg-list">
              <li>登录一次后，AI 将自动接管该平台的日常操作与巡检。</li>
              <li>验证码识别由平台自动完成；遇复杂验证码会请您协助输入。</li>
              <li>凭据采用本地加密保存，你可随时在此页收回权限。</li>
            </ul>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={onClose}>稍后登录</button>
              <button className="btn btn-primary" onClick={() => setStep(2)}>开始登录</button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="lg-body">
            <div className="captcha-zone ai" style={{ maxWidth: '100%' }}>
              <div className="cap-img">{manual ? '????' : 'K7P9'}</div>
              <div className="cap-meta">
                {manual
                  ? <span className="badge amber"><span className="bdot" />请人工输入</span>
                  : <span className="badge blue"><span className="bdot" />AI 已识别</span>}
              </div>
            </div>
            {manual ? (
              <input className="cap-input" placeholder="请输入验证码" value={cap} onChange={(e) => setCap(e.target.value)} />
            ) : (
              <p className="hint">
                <a onClick={() => setManual(true)} style={{ color: 'var(--c-terra)', cursor: 'pointer' }}>
                  验证码看不清？改为人工输入
                </a>
              </p>
            )}
            <p className="hint">为什么要人工？平台安全要求关键操作必须由本人完成，AI 无法替代登录动作。</p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setStep(1)}>上一步</button>
              <button className="btn btn-primary" onClick={() => setStep(3)}>完成</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="success-box" style={{ animation: 'fadeUp .3s ease-out' }}>
            <div className="check">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div className="st-title">已接管</div>
            <div className="st-sub">后续日常操作由 AI 完成，您可随时在本页收回权限</div>
            <div className="ls-actions" style={{ justifyContent: 'center', marginTop: 16 }}>
              <button className="btn btn-primary" onClick={onClose}>完成</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
