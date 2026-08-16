import React, { useState } from 'react';
import ChatView from './views/ChatView';
import MemoryView from './views/MemoryView';
import SkillsView from './views/SkillsView';
import SystemView from './views/SystemView';

type PageId = 'chat' | 'memory' | 'skills' | 'system';

const NAV: { id: PageId; label: string; desc: string }[] = [
  { id: 'chat', label: '会话', desc: '与 ECO AGENT 对话' },
  { id: 'memory', label: '记忆树', desc: '长期记忆浏览与检索' },
  { id: 'skills', label: '技能', desc: '技能库与孵化' },
  { id: 'system', label: '系统', desc: '组件状态与指标' },
];

const TITLES: Record<PageId, string> = {
  chat: '会话',
  memory: '记忆树',
  skills: '技能库',
  system: '系统状态',
};

export default function App(): React.ReactElement {
  const [page, setPage] = useState<PageId>('chat');
  const [version, setVersion] = useState<string>('');

  React.useEffect(() => {
    import('./api').then(({ api }) => {
      api.version().then((v) => setVersion(v.version)).catch(() => setVersion(''));
    });
  }, []);

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">
          ECO AGENT<span className="sub">生态环境执法 AI 智能体</span>
        </div>
        {NAV.map((n) => (
          <div
            key={n.id}
            className={`item${page === n.id ? ' active' : ''}`}
            onClick={() => setPage(n.id)}
          >
            {n.label}
          </div>
        ))}
        <div className="foot">v{version || '…'}</div>
      </aside>
      <div className="main">
        <div className="topbar">
          <h1>{TITLES[page]}</h1>
          <span className="meta">{NAV.find((n) => n.id === page)?.desc}</span>
        </div>
        <div className="content">
          {page === 'chat' && <ChatView />}
          {page === 'memory' && <MemoryView />}
          {page === 'skills' && <SkillsView />}
          {page === 'system' && <SystemView />}
        </div>
      </div>
    </div>
  );
}
