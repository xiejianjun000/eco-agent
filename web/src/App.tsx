import React, { useState } from 'react';
import RightPanel from './components/RightPanel';
import ChatView from './views/ChatView';
import MemoryView from './views/MemoryView';
import SkillsView from './views/SkillsView';
import SystemView from './views/SystemView';
import AgentsView from './views/AgentsView';
import GoalsView from './views/GoalsView';
import PluginsView from './views/PluginsView';
import WelcomeView from './views/WelcomeView';
import WorkflowView from './views/WorkflowView';
import { api, type SessionOut } from './api';

type PageId = 'welcome' | 'chat' | 'memory' | 'skills' | 'agents' | 'goals' | 'workflow' | 'plugins' | 'system';

const NAV: { id: PageId; label: string; desc: string }[] = [
  { id: 'memory', label: '生态空间', desc: '生态环境空间数据与长期记忆检索' },
  { id: 'skills', label: '生态技能', desc: '生态环境技能库与智能体孵化' },
  { id: 'agents', label: '生态助手', desc: '后台生态助手目录与任务输出' },
  { id: 'goals', label: '生态目标', desc: '跨轮生态目标与自动推进' },
  { id: 'workflow', label: '生态编排', desc: '生态环境工作流编排与计划' },
  { id: 'plugins', label: '生态插件', desc: '生态环境插件清单与MCP连接器' },
  { id: 'system', label: '系统', desc: '组件状态与生态指标' },
];

const TITLES: Record<PageId, string> = {
  welcome: '欢迎',
  chat: '生态助手',
  memory: '生态空间',
  skills: '生态技能库',
  agents: '生态助手',
  goals: '生态目标',
  workflow: '生态编排',
  plugins: '生态插件',
  system: '系统状态',
};

/** 会话展示名：去掉 web_ 平台前缀 */
function sessionLabel(s: SessionOut): string {
  if (s.name) return s.name;
  const uid = (s.user_id || s.session_id || '').replace(/^web_/, '');
  return uid || s.session_id;
}

function relTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

export default function App(): React.ReactElement {
  const [page, setPage] = useState<PageId>('welcome');
  const [version, setVersion] = useState<string>('');
  const [collapsed, setCollapsed] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [query, setQuery] = useState('');
  const [activeSessionId, setActiveSessionId] = useState('default');
  /** 删除当前会话等场景强制 ChatView 重挂载（key 相同 React 不会自动换新） */
  const [chatNonce, setChatNonce] = useState(0);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = window.localStorage.getItem('eco-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('eco-theme', theme);
  }, [theme]);

  // 设置页三态切换（light/dark/system）同步回侧栏按钮
  React.useEffect(() => {
    const onThemeChanged = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === 'light' || detail === 'dark') setTheme(detail);
    };
    window.addEventListener('eco-theme-changed', onThemeChanged);
    return () => window.removeEventListener('eco-theme-changed', onThemeChanged);
  }, []);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  React.useEffect(() => {
    import('./api').then(({ api }) => {
      api.version().then((v) => setVersion(v.version)).catch(() => setVersion(''));
      // 刷新后显示最新的那条会话（列表已按最近活跃排序）
      api.sessions().then((list) => {
        setSessions(list);
        if (list.length > 0) setActiveSessionId(list[0].session_id);
      }).catch(() => {});
    });
  }, []);

  const refreshSessions = () => {
    api.sessions().then(setSessions).catch(() => {});
  };

  const newSession = async () => {
    try {
      const s = await api.createSession('');
      setSessions((prev) => [s, ...prev.filter((x) => x.session_id !== s.session_id)]);
      setActiveSessionId(s.session_id);
      setPage('chat');
    } catch {
      // 创建失败保持现状，不打断使用
    }
  };

  const openSession = (id: string) => {
    setActiveSessionId(id);
    setPage('chat');
  };

  // ── 会话行操作：重命名（内联编辑）/ 删除 / 分享导出 ──
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const renameRef = React.useRef<string | null>(null);

  const startRename = (s: SessionOut) => {
    setEditingId(s.session_id);
    setEditName(sessionLabel(s));
    renameRef.current = s.session_id;
  };

  const saveRename = async (id: string) => {
    if (renameRef.current !== id) return; // 防 Enter+blur 双触发
    renameRef.current = null;
    setEditingId(null);
    const name = editName.trim();
    if (!name) return;
    try {
      const updated = await api.renameSession(id, name);
      setSessions((prev) => prev.map((x) => (x.session_id === id ? updated : x)));
    } catch (e) {
      window.alert(`重命名失败: ${(e as Error).message}`);
    }
  };

  const deleteSession = async (s: SessionOut) => {
    if (!window.confirm(`删除会话「${sessionLabel(s)}」？聊天记录一并删除，不可恢复。`)) return;
    try {
      await api.deleteSession(s.session_id);
      const rest = sessions.filter((x) => x.session_id !== s.session_id);
      setSessions(rest);
      if (activeSessionId === s.session_id) {
        if (rest.length === 0) {
          // 全部删光：清掉 default 通道残留日志 → 回到品牌欢迎页
          try {
            await api.deleteSession('default');
          } catch {
            // default 无残留，忽略
          }
          setActiveSessionId('default');
        } else {
          setActiveSessionId(rest[0].session_id);
        }
        // 强制 ChatView 重挂载：即使新 id 与旧 id 相同（删的就是当前会话），也要回到初始态
        setChatNonce((n) => n + 1);
        setPage('chat');
      }
    } catch (e) {
      window.alert(`删除失败: ${(e as Error).message}`);
    }
  };

  const shareSession = async (s: SessionOut) => {
    if ((s.message_count ?? 0) === 0) {
      window.alert('该会话还没有聊天内容，先聊几句再分享');
      return;
    }
    try {
      const r = await api.exportSession(s.session_id);
      await navigator.clipboard.writeText(r.content);
      window.alert(`已导出并复制全文（${r.count} 条消息）\n文件: ${r.path}`);
    } catch (e) {
      window.alert(`导出失败: ${(e as Error).message}`);
    }
  };

  const filtered = sessions.filter(
    (s) =>
      !query.trim() ||
      s.user_id.includes(query.trim()) ||
      s.session_id.includes(query.trim()),
  );

  // DSH 式折叠图标（侧栏面板收起/展开）
  const panelIcon = (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M6 2.5v11" />
    </svg>
  );

  return (
    <div className="app">
      <aside className={`nav${collapsed ? ' collapsed' : ''}`}>
        <div className="brand" title="回到会话" onClick={() => setPage('chat')}>
          <div className="brand-row">
            {collapsed ? (
              <img className="brand-icon" src="/favicon.svg" alt="eco Agent" />
            ) : (
              <img className="brand-logo" src="/eco-logo.svg" alt="eco Agent" />
            )}
            <button
              className="collapse-btn"
              title={collapsed ? '展开侧边栏' : '收起侧边栏'}
              aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
              onClick={(e) => {
                e.stopPropagation();
                setCollapsed((v) => !v);
              }}
            >
              {panelIcon}
            </button>
          </div>
          {!collapsed && (
            <span className="sub">
              最懂生态环境的<span className="sub-accent">AI 伙伴</span>
            </span>
          )}
        </div>

        <button
          className={`new-session-btn${collapsed ? ' icon-only' : ''}`}
          title="新建生态任务"
          onClick={() => void newSession()}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
               strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
            <path d="M8 3v10M3 8h10" />
          </svg>
          {!collapsed && <span>新建生态任务</span>}
        </button>

        {/* WorkBuddy 风格主导航 — 直接展示，不折叠 */}
        <nav className="nav-menu">
          {NAV.map((n) => (
            <div
              key={n.id}
              className={`nav-item${page === n.id ? ' active' : ''}`}
              title={n.desc}
              onClick={() => setPage(n.id)}
            >
              <span className="nav-icon">{n.id === 'chat' ? '🌿' : n.id === 'memory' ? '🗺️' : n.id === 'skills' ? '🛠️' : n.id === 'agents' ? '🤖' : n.id === 'goals' ? '🎯' : n.id === 'workflow' ? '⚡' : n.id === 'plugins' ? '🔌' : '⚙️'}</span>
              {!collapsed && <span className="nav-label">{n.label}</span>}
            </div>
          ))}
        </nav>

        {/* 底部区域 — WorkBuddy 风格 */}
        {!collapsed && (
          <div className="nav-bottom">
            <div className="nb-section">
              <span className="nb-item">📝 生态任务 ({sessions.length})</span>
              <span className="nb-item">🗺️ 生态空间 (14)</span>
            </div>
            <div className="nb-section">
              <span className="nb-item">🟢 社区互动</span>
              <span className="nb-item">🔔 通知</span>
            </div>
            <div className="nb-foot">
              <span className="foot-btn" title="切换主题" onClick={toggleTheme}>
                {theme === 'dark' ? '☀' : '🌙'}
              </span>
              <span>v{version || '…'}</span>
            </div>
          </div>
        )}
      </aside>
      <div className="main">
        <div className="topbar">
          <h1>{TITLES[page]}</h1>
          <span className="meta">{NAV.find((n) => n.id === page)?.desc ?? '与 eco Agent 对话'}</span>
        </div>
        <div className="content-area">
          <div className="content">
            {page === 'welcome' && <WelcomeView onStartChat={() => setPage('chat')} />}
            {page === 'chat' && (
              <ChatView
                key={`${activeSessionId}:${chatNonce}`}
                sessionId={activeSessionId}
                onActivity={refreshSessions}
              />
            )}
            {page === 'memory' && <MemoryView />}
            {page === 'skills' && <SkillsView />}
            {page === 'agents' && <AgentsView />}
            {page === 'goals' && <GoalsView />}
            {page === 'workflow' && <WorkflowView />}
            {page === 'plugins' && <PluginsView />}
            {page === 'system' && <SystemView />}
          </div>
          <RightPanel
            open={rightPanelOpen}
            onToggle={() => setRightPanelOpen((v) => !v)}
            sessionName={activeSession?.name}
            tags={["大气", "信访", "数据"]}
          />
        </div>
      </div>
    </div>
  );
}
