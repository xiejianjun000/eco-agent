import { useState, useMemo, useCallback, useEffect, memo, type ReactNode } from 'react';
import SectionOffice from './SectionOffice';
import { IconShield } from './icons';
import { IconMapPin, IconRefreshCw, IconTrendingUp } from './icons-extra';
import { platforms, type PlatformStatus } from '../data/platforms';
import { cases, openCases } from '../data/enforcement';
import { queue, VETO_GROUPS } from '../data/review';
import { todos, experts } from '../data/assistant';
import { calEvents, dueSoon } from '../data/calendar';
import { mapPoints } from '../data/map';
import { tasks, fixes } from '../data/inspection';
import { connections as mcpConnections } from '../data/mcp';
import {
  useOfficeState,
  useReviewStats,
  useHermesMemory,
  useGisOperations,
  useAiReviewStream,
} from '../hooks/useBridgeData';
import type { AiStreamEvent } from '../hooks/useBridgeData';
import type { Annotation } from '../data/rightpanel';

/* ── 旧的上下文统计逻辑（保留头部显示）── */

interface CtxStat {
  label: string; value: string; tone?: 'terra' | 'olive' | 'red' | 'amber' | 'blue';
}

function buildBrief(nav: string): { stats: CtxStat[]; badge: string } {
  switch (nav) {
    case 'platforms': {
      const by = (s: PlatformStatus) => platforms.filter((p) => p.status === s).length;
      return { stats: [
        { label: '代管', value: String(by('managed')), tone: 'olive' },
        { label: '待接入', value: String(by('pending')), tone: 'amber' },
        { label: '异常', value: String(by('error')), tone: 'red' },
      ], badge: `${by('error')}异常` };
    }
    case 'enforcement': {
      const open = openCases.length;
      const overdue = cases.filter((c) => c.warning).length;
      return { stats: [
        { label: '在办', value: String(open), tone: 'terra' },
        { label: '临期', value: String(overdue), tone: overdue ? 'red' : 'olive' },
        { label: '结案', value: String(cases.length - open), tone: 'olive' },
      ], badge: `${open}在办` };
    }
    case 'review': {
      const done = queue.filter((q) => q.status === '已完成').length;
      const pending = queue.length - done;
      const vetoTotal = VETO_GROUPS.reduce((n, g) => n + g.items.length, 0);
      return { stats: [
        { label: '已评', value: `${done}/${queue.length}`, tone: 'olive' },
        { label: '待评', value: String(pending), tone: 'amber' },
        { label: '否决项', value: String(vetoTotal), tone: 'terra' },
      ], badge: `${pending}待评` };
    }
    case 'map': {
      const over = mapPoints.filter((p) => p.status === 'over').length;
      return { stats: [
        { label: '企业', value: String(mapPoints.length), tone: 'blue' },
        { label: '超标', value: String(over), tone: over ? 'red' : 'olive' },
      ], badge: over ? `${over}超标` : '正常' };
    }
    case 'calendar': {
      return { stats: [
        { label: '今日', value: String(calEvents.length), tone: 'terra' },
        { label: '临期', value: String(dueSoon.length), tone: dueSoon.length ? 'amber' : 'olive' },
      ], badge: `${calEvents.length}事项` };
    }
    case 'inspection': {
      const todo = tasks.filter((t) => t.col === 'todo').length;
      const doing = tasks.filter((t) => t.col === 'doing').length;
      const fixPending = fixes.filter((f) => f.state === '待复核').length;
      return { stats: [
        { label: '在办', value: String(todo + doing), tone: 'terra' },
        { label: '待销号', value: String(fixPending), tone: fixPending ? 'red' : 'olive' },
      ], badge: fixPending ? `${fixPending}待销` : '' };
    }
    case 'mcp': {
      const err = mcpConnections.filter((c) => c.status === 'error').length;
      const on = mcpConnections.filter((c) => c.status === 'connected').length;
      return { stats: [
        { label: '接通', value: String(on), tone: 'olive' },
        { label: '异常', value: String(err), tone: err ? 'red' : 'olive' },
      ], badge: err ? `${err}异常` : '正常' };
    }
    default: {
      const urgent = todos.filter((t) => t.level === 'urgent').length;
      return { stats: [
        { label: '待办', value: String(todos.length), tone: 'terra' },
        { label: '紧急', value: String(urgent), tone: urgent ? 'red' : 'olive' },
        { label: '活跃专家', value: String(experts.filter((e) => e.active).length), tone: 'blue' },
      ], badge: `${todos.length}待办` };
    }
  }
}

const TONE_CLS: Record<string, string> = {
  terra: 'terra', olive: 'olive', red: 'red', amber: 'amber', blue: 'blue',
};

/* ═══════════════════════════════════════════════
   容器组件 — 接入真实 eco-bridge 数据
   ═══════════════════════════════════════════════ */

/** Hermes 记忆卡片 — memo 化，避免父组件频繁重渲染时子组件无谓更新 */
const HermesCard = memo(function HermesCard({ card }: {
  card: { id: string; title: string; category: string; summary?: string; usageCount?: number };
}): ReactNode {
  return (
    <div className="rp-hermes-card">
      <div className="rp-hermes-title">{card.title}</div>
      <div className="rp-hermes-meta">
        <span className="rp-hermes-cat">{card.category}</span>
        {card.usageCount && <span>复用 {card.usageCount} 次</span>}
      </div>
      {card.summary && <div className="rp-hermes-sum">{card.summary.slice(0, 60)}...</div>}
    </div>
  );
});

export default function RightPanel({ activeNav, drawerOpen, onClose, panelWidth: _panelWidth, browserUrl, onBrowserClose }: {
  activeNav: string;
  drawerOpen: boolean;
  onClose: () => void;
  panelWidth?: number;
  browserUrl?: string;
  onBrowserClose?: () => void;
}) {
  const brief = useMemo(() => buildBrief(activeNav), [activeNav]);

  // 依赖 activeNav，只在 assistant/enforcement/review 模块展示 Office 区
  const showOffice = activeNav === 'assistant' || activeNav === 'enforcement' || activeNav === 'review';

  // ── 标签页状态（替代原来的折叠状态）──
  const [activeTab, setActiveTab] = useState<'office' | 'gis' | 'hermes' | 'review' | 'browser'>(
    showOffice ? 'office' : 'gis'
  );

  // 切到非 office 模块时，若仍停留在 office 标签则回退到 GIS，避免面板空白
  useEffect(() => {
    if (!showOffice && activeTab === 'office') setActiveTab('gis');
  }, [showOffice, activeTab]);

  // 自动切换到浏览器标签页
  useEffect(() => {
    if (browserUrl) setActiveTab('browser');
  }, [browserUrl]);

  // ── 真实数据桥接 ──
  const defaultDocId = 'case-JZS-0038';
  const { data: officeData, loading: officeLoading } = useOfficeState(showOffice ? defaultDocId : '');
  const { data: reviewStats } = useReviewStats();
  const { data: hermesMemory } = useHermesMemory();
  const { data: gisOps } = useGisOperations();

  // ── GIS 本地可撤销列表 ──
  const [localGisOps, setLocalGisOps] = useState<typeof gisOps>([]);
  useEffect(() => {
    if (gisOps.length > 0) setLocalGisOps(gisOps);
  }, [gisOps]);

  const undoGisOp = useCallback((id: string) => {
    setLocalGisOps((prev) => prev.filter((op) => op.id !== id));
  }, []);

  // ── AI 审阅流 ──
  const {
    events: reviewEvents,
    status: reviewStatus,
    progress: reviewProgress,
    retryCount,
    lastError: reviewError,
    startReview,
  } = useAiReviewStream();

  // 将 SSE update 事件转换为 Annotation[]
  const liveAnnotations: Annotation[] = useMemo(() => {
    return reviewEvents
      .filter((ev): ev is AiStreamEvent & { event: 'update' } => ev.event === 'update')
      .map((ev, i) => ({
        id: ev.data.paragraphId ?? `ai-live-${i}`,
        author: ev.data.aiAuthor ?? '文书成',
        role: 'ai' as const,
        content: ev.data.text ?? '',
        time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        resolved: false,
        replies: [],
      }));
  }, [reviewEvents]);

  // 开始 AI 审阅
  const handleStartReview = useCallback(() => {
    startReview({ docId: defaultDocId, reviewType: 'full' });
  }, [startReview, defaultDocId]);

  // ── Hermes 卡片列表缓存（避免每次渲染重新 slice）──
  const hermesCards = useMemo(
    () => hermesMemory?.cards.slice(0, 50) ?? [],
    [hermesMemory?.cards],
  );

  return (
    <>
      {/* 抽屉遮罩（窄屏） */}
      {drawerOpen && <div className="rp-drawer-overlay" onClick={onClose} />}

      <aside className={`right-panel${drawerOpen ? ' drawer-open' : ''}`} style={{ width: '100%', flex: 'none' }}>
      {/* 头部 */}
      <div className="rp-top">
        <div className="rp-avatar"><IconShield /></div>
        <div className="rp-top-txt">
          <div className="rp-top-name">执法助理</div>
          <div className="rp-top-sub"><span className="live-dot" /> AI 在线 · 随时可问</div>
        </div>
      </div>

      {/* 模块概览 */}
      <section className="rp-ctx">
        <div className="rp-ctx-title">{brief.badge || '概览'}</div>
        <div className="rp-stat-grid">
          {brief.stats.map((s) => (
            <div key={s.label} className="rp-stat">
              <div className={`rp-stat-v ${TONE_CLS[s.tone ?? 'terra']}`}>{s.value}</div>
              <div className="rp-stat-l">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 标签栏 ── */}
      <div className="rp-tabs">
        {showOffice && (
          <button
            className={`rp-tab${activeTab === 'office' ? ' active' : ''}`}
            onClick={() => setActiveTab('office')}
          >
            <IconShield /> 文书协同
          </button>
        )}
        <button
          className={`rp-tab${activeTab === 'gis' ? ' active' : ''}`}
          onClick={() => setActiveTab('gis')}
        >
          <IconMapPin /> GIS 辅助
          {localGisOps.length > 0 && <span className="rp-tab-badge">{localGisOps.length}</span>}
        </button>
        <button
          className={`rp-tab${activeTab === 'hermes' ? ' active' : ''}`}
          onClick={() => setActiveTab('hermes')}
        >
          <IconRefreshCw /> 记忆进化
        </button>
        <button
          className={`rp-tab${activeTab === 'review' ? ' active' : ''}`}
          onClick={() => setActiveTab('review')}
        >
          <IconTrendingUp /> 评查看板
        </button>
        {browserUrl && (
          <button
            className={`rp-tab${activeTab === 'browser' ? ' active' : ''}`}
            onClick={() => setActiveTab('browser')}
          >
            <IconMapPin /> 浏览器
          </button>
        )}
      </div>

      {/* ── 标签页内容 ── */}
      <div className="rp-tab-panel">
        {/* Office 文书协同 */}
        {showOffice && activeTab === 'office' && (
          <SectionOffice
            activeDoc={officeData}
            loading={officeLoading}
            liveAnnotations={liveAnnotations}
            reviewProgress={reviewProgress}
            reviewStatus={reviewStatus}
            onStartReview={handleStartReview}
            retryCount={retryCount}
            reviewError={reviewError}
          />
        )}

        {/* GIS 地图辅助 */}
        {activeTab === 'gis' && (
          localGisOps.length > 0 ? (
            <div className="rp-gis-list">
              {localGisOps.map((op) => (
                <div key={op.id} className="rp-gis-item">
                  <span className="rp-gis-time">{op.time}</span>
                  <span className="rp-gis-expert">{op.expert}</span>
                  <span className="rp-gis-desc">{op.description}</span>
                  {op.canUndo && (
                    <button className="rp-gis-undo" onClick={() => undoGisOp(op.id)}>撤销</button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="rp-placeholder">地图操作记录将在展开时展示。从辖区地图模块触发 AI 标注、圈选、路径规划等操作。</div>
          )
        )}

        {/* Hermes 记忆进化 */}
        {activeTab === 'hermes' && (
          hermesMemory ? (
            <div className="rp-hermes-list">
              <div className="rp-hermes-summary">
                学会 {hermesMemory.totalLearned} · 修正 {hermesMemory.totalRevised} · 复用 {hermesMemory.totalReused}
              </div>
              {hermesCards.map((card) => <HermesCard key={card.id} card={card} />)}
            </div>
          ) : (
            <div className="rp-placeholder">经验积累 → 实践验证 → 规则沉淀 → 下次复用。本周新学会 3 条经验，复用 56 次。</div>
          )
        )}

        {/* 评查看板趋势 */}
        {activeTab === 'review' && (
          reviewStats ? (
            <div className="rp-review-data">
              <div className="rp-review-row"><span>已评</span><strong>{reviewStats.totalReviewed}/{reviewStats.totalTarget}</strong></div>
              <div className="rp-review-row"><span>合格率</span><strong className="olive">{reviewStats.passRate}%</strong></div>
              <div className="rp-review-row"><span>否决</span><strong className="red">{reviewStats.deniedCount} 卷</strong></div>
              <div className="rp-review-row">
                <span>待评</span><strong className="amber">{reviewStats.alerts?.pendingReview ?? '?'}</strong>
                <span className="rp-review-sub">临期 {reviewStats.alerts?.nearDeadline ?? '?'}</span>
              </div>
            </div>
          ) : (
            <div className="rp-placeholder">百卷精评 73/100 · 合格率 93.2% · 否决 1 卷</div>
          )
        )}

        {/* 无头浏览器 */}
        {activeTab === 'browser' && browserUrl && (() => {
          const proxyUrl = `http://localhost:8787/api/proxy?url=${encodeURIComponent(browserUrl)}`;
          return (
          <div className="rp-browser">
            <div className="rp-browser-bar">
              <div className="rp-browser-dots">
                <span className="rp-browser-dot red" onClick={onBrowserClose} title="关闭浏览器" />
                <span className="rp-browser-dot amber" />
                <span className="rp-browser-dot olive" />
              </div>
              <div className="rp-browser-url">{browserUrl}</div>
              <button className="rp-browser-reload" onClick={() => {
                const iframe = document.getElementById('rp-browser-iframe') as HTMLIFrameElement | null;
                if (iframe) iframe.src = proxyUrl;
              }} title="刷新">↻</button>
            </div>
            <iframe
              id="rp-browser-iframe"
              className="rp-browser-frame"
              src={proxyUrl}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-top-navigation"
              title="无头浏览器"
            />
          </div>
          );
        })()}
      </div>
    </aside>
    </>
  );
}
