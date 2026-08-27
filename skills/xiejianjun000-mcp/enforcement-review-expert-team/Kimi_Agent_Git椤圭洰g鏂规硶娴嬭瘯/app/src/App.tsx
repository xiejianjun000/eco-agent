import { useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import LeftNav from './components/LeftNav';
import RightPanel from './components/RightPanel';
import { computeResize, logResize, NAV_DEFAULT, RP_DEFAULT } from './utils/resize';
import Platforms from './components/Platforms';
import Assistant from './components/Assistant';
import Calendar from './components/Calendar';
import Enterprises from './components/Enterprises';
import Map from './components/Map';
import Enforcement from './components/Enforcement';
import Inspection from './components/Inspection';
import Review from './components/Review';
import Archive from './components/Archive';
import Knowledge from './components/Knowledge';
import Mcp from './components/Mcp';
import Settings from './components/Settings';
import { connections as mcpConnections } from './data/mcp';
import './App.css';

const TITLES: Record<string, string> = {
  assistant: '执法助理', calendar: '工作日历', map: '辖区地图', enterprises: '企业管理',
  platforms: '平台管理', enforcement: '执法办案', inspection: '督察管理', review: '案卷评查',
  archive: '档案管理', knowledge: '知识库', mcp: 'MCP 连接', settings: '设置',
};

type SubTab = 'welcome' | 'tasks' | 'dashboard' | 'expert';
const SUB_TABS: { id: SubTab; label: string }[] = [
  { id: 'welcome', label: '执法助理' },
  { id: 'tasks', label: '今日待办' },
  { id: 'dashboard', label: '数据看板' },
  { id: 'expert', label: 'AI 专家' },
];

function renderModule(id: string, navigate: (id: string) => void, subTab: SubTab, onOpenBrowser: (url: string) => void): ReactNode {
  switch (id) {
    case 'assistant':
      return <Assistant onNavigate={navigate} activeTab={subTab} />;
    case 'calendar':
      return <Calendar />;
    case 'enterprises':
      return <Enterprises onNavigate={navigate} />;
    case 'map':
      return <Map onNavigate={navigate} />;
    case 'enforcement':
      return <Enforcement onNavigate={navigate} />;
    case 'inspection':
      return <Inspection onNavigate={navigate} />;
    case 'review':
      return <Review onNavigate={navigate} />;
    case 'archive':
      return <Archive onNavigate={navigate} />;
    case 'knowledge':
      return <Knowledge />;
    case 'mcp':
      return <Mcp />;
    case 'settings':
      return <Settings />;
    case 'platforms':
      return <Platforms onNavigate={navigate} onOpenBrowser={onOpenBrowser} />;
    default:
      return (
        <div
          className="card"
          style={{ maxWidth: 760, margin: '0 auto', textAlign: 'center', color: 'var(--t-aux)' }}
        >
          模块「{TITLES[id] ?? id}」建设中，本版聚焦「执法助理」与「平台管理」。
        </div>
      );
  }
}

export default function App(): ReactNode {
  const [activeNav, setActiveNav] = useState<string>('assistant');
  const [subTab, setSubTab] = useState<SubTab>('welcome');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [browserUrl, setBrowserUrl] = useState<string>('');  // 无头浏览器 URL
  const navigate = useCallback((id: string) => { setActiveNav(id); setDrawerOpen(false); }, []);

  // ── 面板拖拽拉扯（左侧导航 + 右侧协作栏）──

  const RP_MIN = 260, RP_MAX = 560;
  const LN_MIN = 180, LN_MAX = 360;

  /** 右侧栏：默认 320，范围 260~560，左边缘手柄 */
  const [rightWidth, setRightWidth] = useState(RP_DEFAULT);
  const rpDragging = useRef(false);
  const rpStartX = useRef(0);
  const rpStartW = useRef(RP_DEFAULT);

  /** 左侧导航：默认 232，范围 180~360，右边缘手柄 */
  const [leftWidth, setLeftWidth] = useState(NAV_DEFAULT);
  const lnDragging = useRef(false);
  const lnStartX = useRef(0);
  const lnStartW = useRef(NAV_DEFAULT);

  // 右侧栏 — 左边缘手柄（鼠标左移 → 面板变宽）
  const rpMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    rpDragging.current = true;
    rpStartX.current = e.clientX;
    rpStartW.current = rightWidth;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  }, [rightWidth]);

  // 左侧导航 — 右边缘手柄（鼠标右移 → 面板变宽）
  const lnMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    lnDragging.current = true;
    lnStartX.current = e.clientX;
    lnStartW.current = leftWidth;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  }, [leftWidth]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      // 右侧栏
      if (rpDragging.current) {
        const next = computeResize(rpStartX.current, e.clientX, rpStartW.current, -1, RP_MIN, RP_MAX);
        setRightWidth(next);
        logResize('right', next, 'drag');
      }
      // 左侧导航
      if (lnDragging.current) {
        const next = computeResize(lnStartX.current, e.clientX, lnStartW.current, 1, LN_MIN, LN_MAX);
        setLeftWidth(next);
        logResize('left', next, 'drag');
      }
    };
    const onUp = () => {
      if (rpDragging.current) {
        rpDragging.current = false;
        logResize('right', rpStartW.current, 'end'); // 拖拽结束上报
      }
      if (lnDragging.current) {
        lnDragging.current = false;
        logResize('left', lnStartW.current, 'end');
      }
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, []);

  const mcpError = mcpConnections.filter((c) => c.status === 'error').length;
  const navBadges: Record<string, { text: string; color?: 'blue' | 'red' | 'amber' }> =
    mcpError > 0 ? { mcp: { text: String(mcpError), color: 'red' } } : {};

  const isAssistant = activeNav === 'assistant';

  return (
    <div className="app-container">
      {/* 左侧导航 + 拖拽手柄 */}
      <div
        className="ln-resize-wrapper"
        style={{ width: leftWidth, flex: `0 0 ${leftWidth}px` }}
      >
        <LeftNav activeNav={activeNav} onNavigate={navigate} badges={navBadges} navWidth={leftWidth} />
        <div className="ln-resize-handle" onMouseDown={lnMouseDown} />
      </div>

      <main className="middle">
        <div className={`title-bar${isAssistant ? ' has-tabs' : ''}`}>
          {!isAssistant && <span className="page-title">{TITLES[activeNav]}</span>}
          {isAssistant && (
            <nav className="title-tabs">
              {SUB_TABS.map((t) => (
                <button
                  key={t.id}
                  className={`title-tab${subTab === t.id ? ' active' : ''}`}
                  onClick={() => setSubTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </nav>
          )}
          {activeNav === 'platforms' && (
            <span className="crumb">新增业务平台 · 首次人工登录后由 AI 日常代管</span>
          )}
        </div>
        <div className="work-scroll">
          {renderModule(activeNav, navigate, subTab, setBrowserUrl)}
        </div>
      </main>

      {/* 右侧栏 + 拖拽手柄 */}
      <div
        className="rp-resize-wrapper"
        style={{ width: rightWidth, flex: `0 0 ${rightWidth}px` }}
      >
        <div className="rp-resize-handle" onMouseDown={rpMouseDown} />
        <RightPanel activeNav={activeNav} drawerOpen={drawerOpen} onClose={() => setDrawerOpen(false)} panelWidth={rightWidth} browserUrl={browserUrl} onBrowserClose={() => setBrowserUrl('')} />
      </div>

      {/* 窄屏右侧栏抽屉触发按钮 */}
      <button
        className="rp-drawer-trigger"
        onClick={() => setDrawerOpen((v) => !v)}
        aria-label="打开侧栏"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
    </div>
  );
}
