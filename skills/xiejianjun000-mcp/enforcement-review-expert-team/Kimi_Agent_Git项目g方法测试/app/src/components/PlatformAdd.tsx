import { useState, type ReactNode } from 'react';
import { IconShield } from './icons';
import {
  matchPlatformRemote,
  fetchCaptchaRemote,
  submitLoginRemote,
  addPlatformRemote,
  newSessionToken,
} from '../lib/hermesClient';
import type { WhitelistPlatform } from '../data/whitelist';

type Stage = 'input' | 'matching' | 'hit' | 'miss' | 'done';

// 后端 AI 基座 = Hermes agent，经 eco-bridge 薄桥接(http://localhost:8787) 接入。
// 本组件只负责向导交互；地址识别/字段推断/验证码/登录接管全部走 hermesClient。
// 见 lib/hermesClient.ts 与 EcoAegis/eco-bridge/README.md。
export default function PlatformAdd({ onAdded, onBack, onOpenBrowser }: {
  onAdded?: (p: WhitelistPlatform) => void;
  onBack?: () => void;
  onOpenBrowser?: (url: string) => void;
}): ReactNode {
  const [stage, setStage] = useState<Stage>('input');
  const [address, setAddress] = useState('');
  const [platform, setPlatform] = useState<WhitelistPlatform | null>(null);
  const [sessionToken, setSessionToken] = useState('');
  const [manualCaptcha, setManualCaptcha] = useState(false);
  const [capValue, setCapValue] = useState('');
  const [aiCaptcha, setAiCaptcha] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');  // base64 验证码图片
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  // miss 阶段的子视图：show=显示提示，manual=手动录入表单
  const [missView, setMissView] = useState<'show' | 'manual'>('show');
  // 手动录入表单字段
  const [manualName, setManualName] = useState('');
  const [manualPurpose, setManualPurpose] = useState('');
  const [manualKeywords, setManualKeywords] = useState('');

  const stepNo = stage === 'input' ? 1 : stage === 'matching' || stage === 'hit' ? 2 : 3;

  /** 刷新验证码（重新获取） */
  const refreshCaptcha = async (): Promise<void> => {
    if (!platform || busy) return;
    setBusy(true);
    try {
      const token = newSessionToken();
      const cap = await fetchCaptchaRemote(platform.id, token);
      setSessionToken(token);
      if (cap.mode === 'manual') {
        setManualCaptcha(true);
        setAiCaptcha('');
        setCaptchaImage(cap.imageB64 ?? '');
      } else {
        setManualCaptcha(false);
        setAiCaptcha(cap.value ?? '');
        setCaptchaImage(cap.imageB64 ?? '');
      }
    } finally {
      setBusy(false);
    }
  };

  const start = async (): Promise<void> => {
    if (!address.trim() || busy) return;
    setBusy(true);
    setStage('matching');
    try {
      const p = await matchPlatformRemote(address);
      if (!p) {
        setStage('miss');
        return;
      }
      // 步骤2：取该平台验证码（由 Hermes agent 抓取并 AI 识别，复杂则回落人工）
      const token = newSessionToken();
      const cap = await fetchCaptchaRemote(p.id, token);
      setPlatform(p);
      setSessionToken(token);
      if (cap.mode === 'manual') {
        setManualCaptcha(true);
        setAiCaptcha('');
        setCaptchaImage(cap.imageB64 ?? '');
      } else {
        setManualCaptcha(false);
        setAiCaptcha(cap.value ?? '');
        setCaptchaImage(cap.imageB64 ?? '');
      }
      setStage('hit');
    } catch (err) {
      console.error('[PlatformAdd] 匹配/接入失败:', err);
      setStage('miss');
    } finally {
      setBusy(false);
    }
  };

  const takeOver = async (): Promise<void> => {
    if (!platform || busy) return;
    setBusy(true);
    try {
      // 步骤3：提交凭据并完成登录接管（凭据加密保存由 Hermes agent 负责）
      const res = await submitLoginRemote({
        platformId: platform.id,
        username,
        password,
        captcha: manualCaptcha ? capValue : aiCaptcha,
        remember,
        sessionToken,
      });
      setStage(res.ok ? 'done' : 'miss');
      if (res.ok && platform) {
        onAdded?.({ ...platform, url: address });
        onOpenBrowser?.(address);
      }
    } finally {
      setBusy(false);
    }
  };

  const reset = (): void => {
    setStage('input');
    setAddress('');
    setPlatform(null);
    setSessionToken('');
    setManualCaptcha(false);
    setCapValue('');
    setAiCaptcha('');
    setCaptchaImage('');
    setUsername('');
    setPassword('');
    setRemember(false);
    setMissView('show');
    setManualName('');
    setManualPurpose('');
    setManualKeywords('');
  };

  /** 不在白名单时，用户手动录入平台信息并持久化 */
  const handleManualAdd = async (): Promise<void> => {
    const name = manualName.trim();
    const purpose = manualPurpose.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      const kws = manualKeywords
        .split(/[,，\s]+/)
        .map((k) => k.trim())
        .filter(Boolean);
      const p: WhitelistPlatform = {
        id: '',
        name,
        purpose: purpose || name,
        keywords: kws.length > 0 ? kws : [name],
        fields: { username: '账号', password: '密码', captcha: '图形验证码' },
        captchaAuto: false,
      };
      // 持久化
      const res = await addPlatformRemote({
        name,
        purpose: purpose || name,
        keywords: kws.length > 0 ? kws : undefined,
        captchaAuto: false,
      });
      if (res.ok && res.platform) {
        p.id = res.platform.id;
      }
      onAdded?.(p);
    } catch {
      // 即使后端失败，仍然添加到前端列表
      onAdded?.({
        id: `p-${Date.now().toString(36)}`,
        name,
        purpose: purpose || name,
        keywords: manualKeywords ? manualKeywords.split(/[,，\s]+/).filter(Boolean) : [name],
        fields: { username: '账号', password: '密码', captcha: '图形验证码' },
        captchaAuto: false,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="add-wrap">
      <p className="add-intro">
        粘贴平台的 IP 地址或访问地址，AI 会自动识别平台并为你生成 EcoAegis 风格的登录界面，
        验证码也会自动推送到这个入口。首次人工登录一次后，后续日常操作由 AI 代管。
      </p>

      <div className="steps">
        {['粘贴地址', 'AI 识别匹配', '生成登录壳并接通'].map((t, i) => (
          <div
            key={t}
            className={`step${stepNo > i ? ' done' : ''}${stepNo === i + 1 ? ' active' : ''}`}
          >
            <span className="num">{stepNo > i ? '✓' : i + 1}</span>
            <span>{t}</span>
          </div>
        ))}
      </div>

      {stage === 'input' && (
        <div className="card">
          <div className="addr-box">
            <input
              className="addr-input"
              placeholder="例如：http://10.12.34.56:8080 或 水环境非现场执法平台"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void start(); }}
            />
            <button className="btn btn-primary" onClick={() => void start()} disabled={busy}>开始接入</button>
          </div>
          <p className="hint">支持 IP、域名或平台名称关键字；仅支持「账号 + 密码 + 图形验证码」型白名单平台。</p>
        </div>
      )}

      {stage === 'matching' && (
        <div className="card">
          <div className="matching">
            <span className="spinner" />
            AI 正在识别平台、分析登录方式…
          </div>
        </div>
      )}

      {stage === 'hit' && platform && (
        <div className="card match-card">
          <div className="login-shell">
            <div className="ls-head">
              <IconShield />
              <div>
                <div className="ls-title">{platform.name}</div>
                <div className="ls-sub">{platform.purpose}</div>
              </div>
            </div>

            <div className="field">
              <label>{platform.fields.username}</label>
              <input
                type="text"
                placeholder={`请输入${platform.fields.username}`}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="field">
              <label>{platform.fields.password}</label>
              <input
                type="password"
                placeholder={`请输入${platform.fields.password}`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {/* 验证码双态：AI 已识别 / 人工输入 */}
            <div className={`field captcha-zone${manualCaptcha ? '' : ' ai'}`}>
              {manualCaptcha ? (
                <>
                  {captchaImage && (
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                      <img
                        className="cap-image"
                        src={captchaImage}
                        alt="验证码"
                        style={{ width: 140, height: 44, borderRadius: 6, border: '1px solid var(--line)', objectFit: 'contain', background: '#fff' }}
                      />
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => void refreshCaptcha()}
                        disabled={busy}
                        style={{ fontSize: 12, padding: '4px 8px', lineHeight: '20px' }}
                      >
                        ↻ 换一张
                      </button>
                    </div>
                  )}
                  <input
                    className="cap-input"
                    placeholder={`请输入${platform.fields.captcha}`}
                    value={capValue}
                    onChange={(e) => setCapValue(e.target.value)}
                  />
                </>
              ) : (
                <>
                  {captchaImage && (
                    <img
                      className="cap-image"
                      src={captchaImage}
                      alt="验证码"
                      style={{ width: '100%', maxWidth: 200, borderRadius: 6, border: '1px solid var(--line)', marginBottom: 8 }}
                    />
                  )}
                  <div className="cap-img">{aiCaptcha}</div>
                  <div className="cap-meta">
                    <span className="badge blue"><span className="bdot" />AI 已识别</span>
                  </div>
                </>
              )}
            </div>
            {!manualCaptcha && (
              <p className="hint">
                <a onClick={() => setManualCaptcha(true)} style={{ color: 'var(--c-terra)', cursor: 'pointer' }}>
                  验证码看不清？改为人工输入
                </a>
              </p>
            )}

            <label className="remember" onClick={() => setRemember((v) => !v)}>
              <span className={`toggle${remember ? ' on' : ''}`} />
              记住账号（本地加密保存，下次免输）
            </label>

            <div className="ls-actions">
              <button className="btn btn-primary" onClick={() => void takeOver()} disabled={busy}>登录并接管</button>
              <button className="btn btn-ghost" onClick={reset}>取消</button>
            </div>
          </div>
          <p className="hint">登录一次并完成验证码后，AI 将自动接管该平台的日常操作与巡检，你可随时收回权限。</p>
        </div>
      )}

      {stage === 'miss' && missView === 'show' && (
        <div className="card miss-box">
          <div className="mt">该平台暂不在白名单内</div>
          <p className="hint">
            为保证安全与稳定，MVP 仅支持「账号 + 密码 + 图形验证码」型政务 / 环保业务平台。
            UKEY、数字证书、人脸或扫码类（MFA）平台暂不自动接入。
          </p>
          <p className="hint" style={{ marginTop: 8 }}>
            你也可以手动录入该平台的基本信息，加入白名单后即可体验接管流程。
          </p>
          <div className="ls-actions" style={{ gap: 8, marginTop: 12 }}>
            <button className="btn btn-ghost" onClick={reset}>重新输入地址</button>
            <button className="btn btn-primary" onClick={() => setMissView('manual')}>
              手动添加此平台
            </button>
          </div>
        </div>
      )}

      {stage === 'miss' && missView === 'manual' && (
        <div className="card match-card">
          <div className="login-shell">
            <div className="ls-head">
              <IconShield />
              <div>
                <div className="ls-title">手动添加平台</div>
                <div className="ls-sub">录入后加入白名单，后续可体验接管流程</div>
              </div>
            </div>

            <div className="field">
              <label>平台名称 *</label>
              <input
                type="text"
                placeholder="例如：环境应急管理系统"
                value={manualName}
                onChange={(e) => setManualName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void handleManualAdd(); }}
              />
            </div>
            <div className="field">
              <label>用途说明</label>
              <input
                type="text"
                placeholder="人话描述：查什么、管什么"
                value={manualPurpose}
                onChange={(e) => setManualPurpose(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void handleManualAdd(); }}
              />
            </div>
            <div className="field">
              <label>搜索关键词（逗号分隔）</label>
              <input
                type="text"
                placeholder="例如：应急管理, 环境应急, yj"
                value={manualKeywords}
                onChange={(e) => setManualKeywords(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void handleManualAdd(); }}
              />
            </div>

            <p className="hint">填好后点击「加入白名单」，平台将以「待登录」状态进入平台管理列表，后续可体验完整接管流程。</p>

            <div className="ls-actions" style={{ marginTop: 16, gap: 8 }}>
              <button className="btn btn-ghost" onClick={() => setMissView('show')}>返回</button>
              <button className="btn btn-primary" onClick={() => void handleManualAdd()} disabled={busy || !manualName.trim()}>
                {busy ? '添加中…' : '加入白名单'}
              </button>
            </div>
          </div>
        </div>
      )}

      {stage === 'done' && (
        <div className="card success-box">
          <div className="check">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div className="st-title">已接管，后续由 AI 日常代管</div>
          <div className="st-sub">{platform?.name} · 你已随时可在此页收回权限</div>
          <div className="ls-actions" style={{ justifyContent: 'center', marginTop: 16 }}>
            {onBack && (
              <button className="btn btn-ghost" onClick={onBack}>返回平台管理</button>
            )}
            <button className="btn btn-primary" onClick={reset}>再添加一个平台</button>
          </div>
        </div>
      )}
    </div>
  );
}
