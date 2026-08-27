import { useState } from 'react';
import type { ReactNode } from 'react';
import {
  aiTiers, tierDetails, detailLabels, loginRecords,
  type AiTier,
} from '../data/settings';
import { currentUser } from '../data/currentUser';

const TABS = ['个人与单位', '通知提醒', 'AI 协助程度', '界面偏好', '账号与安全'];

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }): ReactNode {
  return (
    <button className={`mcp-switch${on ? ' on' : ''}`} onClick={() => onChange(!on)} aria-label="切换">
      <span className="knob" />
    </button>
  );
}

export default function Settings(): ReactNode {
  const [tab, setTab] = useState(0);
  const [toast, setToast] = useState<string | null>(null);

  // 个人
  const [name, setName] = useState<string>(currentUser.name);
  const [unit, setUnit] = useState('广通众创 · 生态环境执法支队');
  const [cert, setCert] = useState('湘环执 0437');
  const [phone, setPhone] = useState('138****6620');

  // 通知
  const [leadMode, setLeadMode] = useState<'3' | '1'>('3');
  const [notify, setNotify] = useState({ veto: true, patrol: true, daily: true, sms: false });

  // AI 协助
  const [tier, setTier] = useState<AiTier>('full');
  const [details, setDetails] = useState<Record<string, boolean>>(tierDetails.full);
  const [confirmTier, setConfirmTier] = useState<AiTier | null>(null);

  // 界面
  const [fontSize, setFontSize] = useState<'std' | 'big'>('std');
  const [rightOpen, setRightOpen] = useState(true);
  const [mapLayers, setMapLayers] = useState({ water: true, enterprise: true, road: false });

  const saved = (m = '已保存') => {
    setToast(m);
    window.setTimeout(() => setToast(null), 1600);
  };

  const pickTier = (t: AiTier) => {
    if (t === tier) return;
    setConfirmTier(t);
  };
  const confirmTierSwitch = () => {
    if (!confirmTier) return;
    setTier(confirmTier);
    setTimeout(() => setDetails(tierDetails[confirmTier]), 60);
    setConfirmTier(null);
    saved('AI 协助档位已切换');
  };

  return (
    <div className="mod">
      <div className="mod-head"><div><h2 className="mod-title">设置</h2><p className="mod-sub">个人偏好与 AI 协助程度。所有修改即时保存。</p></div></div>

      <div className="set-layout">
        <div className="set-tabs">
          {TABS.map((t, i) => (
            <div key={t} className={`set-tab${tab === i ? ' active' : ''}`} onClick={() => setTab(i)}>{t}</div>
          ))}
        </div>

        <div className="set-content">
          {tab === 0 && (
            <div className="set-block">
              <div className="profile-row">
                <div className="profile-avatar">军</div>
                <div className="profile-fields">
                  <label className="set-field"><span>姓名</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
                  <label className="set-field"><span>单位</span><input className="input" value={unit} onChange={(e) => setUnit(e.target.value)} /></label>
                  <label className="set-field"><span>执法证号</span><input className="input" value={cert} onChange={(e) => setCert(e.target.value)} /></label>
                  <label className="set-field"><span>联系方式</span><input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
                </div>
              </div>
              <button className="btn btn-primary" onClick={() => saved()}>保存</button>
            </div>
          )}

          {tab === 1 && (
            <div className="set-block">
              <div className="set-line"><span>临期提醒</span>
                <div className="seg">
                  <button className={`seg-btn${leadMode === '3' ? ' on' : ''}`} onClick={() => { setLeadMode('3'); saved(); }}>提前 3 天</button>
                  <button className={`seg-btn${leadMode === '1' ? ' on' : ''}`} onClick={() => { setLeadMode('1'); saved(); }}>提前 1 天</button>
                </div>
              </div>
              <div className="set-line"><span>否决预警即时提醒</span><Toggle on={notify.veto} onChange={(v) => { setNotify({ ...notify, veto: v }); saved(); }} /></div>
              <div className="set-line"><span>平台巡检异常提醒</span><Toggle on={notify.patrol} onChange={(v) => { setNotify({ ...notify, patrol: v }); saved(); }} /></div>
              <div className="set-line"><span>每日工作小结（下班前推送）</span><Toggle on={notify.daily} onChange={(v) => { setNotify({ ...notify, daily: v }); saved(); }} /></div>
              <div className="set-line"><span>提醒方式 · 短信</span><Toggle on={notify.sms} onChange={(v) => { setNotify({ ...notify, sms: v }); saved(); }} /></div>
            </div>
          )}

          {tab === 2 && (
            <div className="set-block">
              <div className="ai-tier-grid">
                {aiTiers.map((t) => (
                  <div key={t.id} className={`ai-tier${tier === t.id ? ' cur' : ''}`} onClick={() => pickTier(t.id)}>
                    <div className="ai-tier-name">{t.name}</div>
                    <div className="ai-tier-desc">{t.desc}</div>
                  </div>
                ))}
              </div>
              <div className="ai-detail-list">
                {detailLabels.map((d, i) => (
                  <div key={d.id} className="set-line" style={{ animationDelay: `${i * 60}ms` }}>
                    <span>{d.label}</span>
                    <Toggle on={details[d.id] ?? false} onChange={(v) => setDetails({ ...details, [d.id]: v })} />
                  </div>
                ))}
              </div>
              <div className="declare-bar">无论哪一档，处罚决定、销号、归档确认等关键动作始终由您本人完成。</div>
            </div>
          )}

          {tab === 3 && (
            <div className="set-block">
              <div className="set-line"><span>字号</span>
                <div className="seg">
                  <button className={`seg-btn${fontSize === 'std' ? ' on' : ''}`} onClick={() => { setFontSize('std'); saved(); }}>标准</button>
                  <button className={`seg-btn${fontSize === 'big' ? ' on' : ''}`} onClick={() => { setFontSize('big'); saved(); }}>大</button>
                </div>
              </div>
              <div className="set-line"><span>右侧栏默认展开</span><Toggle on={rightOpen} onChange={(v) => { setRightOpen(v); saved(); }} /></div>
              <div className="set-line"><span>地图默认图层 · 水域</span><Toggle on={mapLayers.water} onChange={(v) => setMapLayers({ ...mapLayers, water: v })} /></div>
              <div className="set-line"><span>地图默认图层 · 企业点位</span><Toggle on={mapLayers.enterprise} onChange={(v) => setMapLayers({ ...mapLayers, enterprise: v })} /></div>
              <div className="set-line"><span>地图默认图层 · 道路</span><Toggle on={mapLayers.road} onChange={(v) => { setMapLayers({ ...mapLayers, road: v }); saved(); }} /></div>
            </div>
          )}

          {tab === 4 && (
            <div className="set-block">
              <label className="set-field"><span>修改密码</span><input className="input" type="password" placeholder="新密码" /></label>
              <button className="btn btn-primary" onClick={() => saved('密码已更新')}>更新密码</button>
              <div className="login-rec card">
                <div className="card-h">登录记录</div>
                {loginRecords.map((r, i) => (
                  <div key={i} className="login-row">
                    <span>{r.time}</span><span className="mono">{r.ip}</span><span>{r.device}</span>
                  </div>
                ))}
              </div>
              <button className="btn btn-warn" onClick={() => saved('已退出全部设备')}>退出全部设备</button>
            </div>
          )}
        </div>
      </div>

      {toast && <div className="toast ok">{toast}</div>}

      {confirmTier && (
        <div className="modal-mask" onClick={() => setConfirmTier(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-h">切换 AI 协助档位</div>
            <p className="modal-p">切换到「{aiTiers.find((t) => t.id === confirmTier)?.name}」将调整 AI 自动执行范围，部分自动动作（如文书起草、平台代管）将发生变化。确认切换？</p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmTier(null)}>取消</button>
              <button className="btn btn-primary" onClick={confirmTierSwitch}>确认切换</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
