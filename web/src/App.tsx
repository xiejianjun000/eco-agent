import React, { useState } from 'react';
import ChatView from './views/ChatView';
import MemoryView from './views/MemoryView';
import SkillsView from './views/SkillsView';
import SystemView from './views/SystemView';
import AgentsView from './views/AgentsView';
import GoalsView from './views/GoalsView';
import PluginsView from './views/PluginsView';
import WorkflowView from './views/WorkflowView';
import AutomationView from './views/AutomationView';
import ConnectorsView from './views/ConnectorsView';
import SettingsView from './views/SettingsView';
import TracesView from './views/TracesView';
import { api, type SessionOut } from './api';
import Icon from './components/Icon';

/** 主导航（生态环境专业 Agent 面向用户的 5 项） */
type PageId = 'chat' | 'plugins' | 'automation' | 'connectors' | 'settings';
/** 设置/管理区保留的功能页（本会话已建成的 DSH 对标能力） */
type AdminId = 'memory' | 'skills' | 'agents' | 'goals' | 'workflow' | 'system' | 'traces';

type AnyPage = PageId | AdminId;

/** 生态监测工作空间——决定可用工具集、记忆上下文、权限等级（文件夹驱动，来自 /workspaces API） */
export interface Workspace {
  id: string;
  name: string;
}

export const ADMIN_NAV: { id: AdminId; label: string; desc: string }[] = [
  { id: 'memory', label: '记忆树', desc: '长期记忆浏览与检索' },
  { id: 'skills', label: '技能', desc: '技能库与孵化' },
  { id: 'agents', label: '子代理', desc: '后台子代理目录与任务输出（DSH subagent/jobs）' },
  { id: 'goals', label: '目标', desc: '跨轮目标与自动推进（DSH goal）' },
  { id: 'workflow', label: '编排', desc: 'Workflow 编排与执法计划（DSH workflow/plan）' },
  { id: 'traces', label: '轨迹', desc: '会话 span 瀑布与决策时间线（落盘持久化）' },
  { id: 'system', label: '系统', desc: '组件状态与指标' },
];

const TITLES: Record<AnyPage, string> = {
  chat: '会话',
  plugins: '插件',
  automation: '自动任务',
  connectors: '连接器',
  settings: '设置',
  memory: '记忆树',
  skills: '技能库',
  agents: '子代理',
  goals: '目标',
  workflow: '编排',
  system: '系统状态',
  traces: '轨迹',
};

const DESCS: Record<AnyPage, string> = {
  chat: '与 eco Agent 对话',
  plugins: 'MCP 插件安装 / 配置',
  automation: '定时巡查 / 报告生成（cron）',
  connectors: 'MCP 服务连接器配置',
  settings: '外观、功能模块与系统信息',
  memory: '长期记忆浏览与检索',
  skills: '技能库与孵化',
  agents: '后台子代理目录与任务输出',
  goals: '跨轮目标与自动推进',
  workflow: 'Workflow 编排与执法计划',
  system: '组件状态与指标',
  traces: '会话 span 瀑布与决策时间线（刷新不丢）',
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

const NavIcon = ({ d }: { d: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
);

export default function App(): React.ReactElement {
  const [page, setPage] = useState<AnyPage>('chat');
  const [version, setVersion] = useState<string>('');
  const [rev, setRev] = useState<string>('');
  const [collapsed, setCollapsed] = useState(false);
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [query, setQuery] = useState('');
  const [activeSessionId, setActiveSessionId] = useState('default');
  /** 删除当前会话等场景强制 ChatView 重挂载 */
  const [chatNonce, setChatNonce] = useState(0);
  /** 工作空间列表（文件夹驱动真源，/workspaces API） */
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  /** 侧边栏工作空间组收缩态 */
  const [wsOpen, setWsOpen] = useState(true);
  /** 当前生态工作空间（与 ChatView 输入栏联动） */
  const [activeWorkspace, setActiveWorkspace] = useState<string>('');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = window.localStorage.getItem('eco-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('eco-theme', theme);
  }, [theme]);

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
      api.version().then((v) => { setVersion(v.version); setRev(v.rev ?? ''); }).catch(() => setVersion(''));
      api.sessions().then((list) => {
        setSessions(list);
        if (list.length > 0) setActiveSessionId(list[0].session_id);
      }).catch(() => {});
      refreshWorkspaces();
    });
  }, []);

  const refreshWorkspaces = () => {
    api.workspaces().then((r) => {
      setWorkspaces(r.workspaces);
      setActiveWorkspace((cur) => (cur === '' && r.workspaces.length > 0 ? r.workspaces[0].id : cur));
    }).catch(() => {});
  };

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

  // ── 会话行操作：重命名 / 删除 / 分享导出 ──
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const renameRef = React.useRef<string | null>(null);

  const startRename = (s: SessionOut) => {
    setEditingId(s.session_id);
    setEditName(sessionLabel(s));
    renameRef.current = s.session_id;
  };

  const saveRename = async (id: string) => {
    if (renameRef.current !== id) return;
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
          try { await api.deleteSession('default'); } catch { /* ignore */ }
          setActiveSessionId('default');
        } else {
          setActiveSessionId(rest[0].session_id);
        }
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
        {/* 品牌：字标 + 定位语（收缩按钮独立贴侧栏右缘，见下） */}
        <div className="brand" title="回到会话" onClick={() => setPage('chat')}>
          <div className="brand-row">
            {collapsed ? (
              <img className="brand-icon" src="/favicon.svg" alt="eco Agent" />
            ) : (
              <img className="brand-logo" src="/eco-logo.svg" alt="eco Agent" />
            )}
          </div>
          {!collapsed && (
            <span className="sub">
              最懂生态环境领域<span className="sub-accent">AI Agent</span>
            </span>
          )}
        </div>

        {/* 收缩按钮：绝对定位贴侧栏右缘（与中间栏相邻），不再跟在 logo 后面 */}
        <button
          className="collapse-btn"
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          onClick={(e) => { e.stopPropagation(); setCollapsed((v) => !v); }}
        >
          {panelIcon}
        </button>

        {/* 主导航：新建任务 + 会话/插件/自动任务/连接器 */}
        <div className="nav-main">
          <button className="nav-item nav-new" title="新建任务" onClick={() => void newSession()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            {!collapsed && <span>新建任务</span>}
          </button>

          <button className={`nav-item${page === 'chat' ? ' active' : ''}`} onClick={() => setPage('chat')}>
            <NavIcon d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            {!collapsed && <span>会话</span>}
          </button>

          <button className={`nav-item${page === 'plugins' ? ' active' : ''}`} onClick={() => setPage('plugins')}>
            <NavIcon d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
            {!collapsed && <span>插件</span>}
          </button>

          <button className={`nav-item${page === 'automation' ? ' active' : ''}`} onClick={() => setPage('automation')}>
            <NavIcon d="M12 2a10 10 0 1 0 10 10M12 6v6l4 2" />
            {!collapsed && <span>自动任务</span>}
          </button>

          <button className={`nav-item${page === 'connectors' ? ' active' : ''}`} onClick={() => setPage('connectors')}>
            <NavIcon d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            {!collapsed && <span>连接器</span>}
          </button>
        </div>

        {/* 工作空间分组（文件夹驱动真源，与输入栏联动） */}
        {!collapsed && (
          <div className="nav-group">
            <div className="nav-group-title" style={{ cursor: 'pointer' }} onClick={() => setWsOpen((v) => !v)}>
              <span className="nav-group-caret">{wsOpen ? '▼' : '▶'}</span> 工作空间 ({workspaces.length})
            </div>
            {wsOpen && (
              <div className="nav-group-body">
                {workspaces.length === 0 ? (
                  <div className="nav-empty" style={{ padding: '4px 10px' }}>
                    暂无工作空间——在输入栏 📁 选择器里新建
                  </div>
                ) : (
                  workspaces.map((ws) => (
                    <button
                      key={ws.id}
                      className={`nav-item nav-workspace-item${activeWorkspace === ws.id ? ' active' : ''}`}
                      title={`${ws.name}——决定可用工具集、记忆上下文、权限等级`}
                      onClick={() => { setActiveWorkspace(ws.id); setPage('chat'); }}
                    >
                      {ws.name}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {/* 会话记录（保留既有会话管理：切换/重命名/删除/分享） */}
        {!collapsed && (
          <div className="nav-workspace">
            <div className="nav-section-title">
              会话记录{sessions.length > 0 ? ` · ${sessions.length}` : ''}
            </div>
            <div className="nav-search">
              <input placeholder="搜索会话…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div className="session-list">
              {filtered.length === 0 ? (
                <div className="nav-empty">
                  {sessions.length === 0 ? '暂无会话——点「新建任务」开始' : '无匹配会话'}
                </div>
              ) : (
                filtered.map((s) => (
                  <div
                    key={s.session_id}
                    className={`session-row${s.session_id === activeSessionId ? ' active' : ''}`}
                    title={s.session_id}
                    onClick={() => openSession(s.session_id)}
                  >
                    {editingId === s.session_id ? (
                      <input
                        className="session-rename-input"
                        value={editName}
                        autoFocus
                        maxLength={60}
                        onChange={(e) => setEditName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void saveRename(s.session_id);
                          if (e.key === 'Escape') { renameRef.current = null; setEditingId(null); }
                        }}
                        onBlur={() => void saveRename(s.session_id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <span className="session-name">{sessionLabel(s)}</span>
                    )}
                    <span className="session-meta">
                      {s.message_count} 条 · {relTime(s.updated_at)}
                    </span>
                    <div className="session-actions" onClick={(e) => e.stopPropagation()}>
                      <button title="重命名" onClick={() => startRename(s)}>✎</button>
                      <button title="分享会话内容（导出 Markdown 并复制）" onClick={() => void shareSession(s)}>⤴</button>
                      <button className="danger" title="删除会话" onClick={() => void deleteSession(s)}>✕</button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 底部：设置（独立设置页）+ 用户区 */}
        <div className="nav-footer">
          <div className="nav-settings">
            <button
              className={`settings-trigger${page === 'settings' ? ' open' : ''}`}
              title="设置：外观、功能模块与系统信息"
              onClick={() => {
                if (collapsed) setCollapsed(false);
                setPage('settings');
              }}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
                   strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="8" cy="8" r="2.4" />
                <path d="M8 1.8v1.8M8 12.4v1.8M1.8 8h1.8M12.4 8h1.8M3.6 3.6l1.3 1.3M11.1 11.1l1.3 1.3M12.4 3.6l-1.3 1.3M4.9 11.1l-1.3 1.3" />
              </svg>
              {!collapsed && <span className="settings-label">设置</span>}
            </button>
          </div>

          <div className="user-bar">
            <img className="user-avatar" src="/favicon.svg" alt="user" />
            {!collapsed && <span className="user-name">生态管理员</span>}
            <button className="user-btn" title="通知">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="badge">1</span>
            </button>
            <span className="foot-btn" title="切换主题" onClick={toggleTheme}>
              {theme === 'dark' ? <Icon name="sun" size={15} /> : <Icon name="moon" size={15} />}
            </span>
          </div>
          {!collapsed && (
            <div className="foot">
              <span>eco Agent</span>
              <span title={`git ${rev}`}>v{version || '…'}{rev ? ` (${rev})` : ''}</span>
            </div>
          )}
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <h1>{TITLES[page]}</h1>
          <span className="meta">{DESCS[page]}</span>
        </div>
        <div className="content">
          {page === 'chat' && (
            <ChatView
              key={`${activeSessionId}:${chatNonce}`}
              sessionId={activeSessionId}
              onActivity={refreshSessions}
              workspaces={workspaces}
              activeWorkspace={activeWorkspace}
              onWorkspaceChange={setActiveWorkspace}
              onWorkspacesChange={refreshWorkspaces}
            />
          )}
          {page === 'plugins' && <PluginsView />}
          {page === 'automation' && <AutomationView />}
          {page === 'connectors' && <ConnectorsView />}
          {page === 'memory' && <MemoryView />}
          {page === 'skills' && <SkillsView />}
          {page === 'agents' && <AgentsView />}
          {page === 'goals' && <GoalsView />}
          {page === 'workflow' && <WorkflowView />}
          {page === 'system' && <SystemView />}
          {page === 'traces' && <TracesView />}
          {page === 'settings' && (
            <SettingsView
              theme={theme}
              onThemeChange={setTheme}
              onNavigate={(p) => setPage(p as AnyPage)}
              version={version}
              rev={rev}
            />
          )}
        </div>
      </div>
    </div>
  );
}
