import type { ReactNode } from 'react';
import {
  IconAssistant, IconCalendar, IconMap, IconEnterprises, IconPlatforms,
  IconEnforcement, IconInspection, IconReview, IconArchive, IconKnowledge,
  IconMcp, IconSettings, IconShield,
} from './icons';
import { currentUser } from '../data/currentUser';

interface NavDef {
  id: string;
  label: string;
  icon: () => ReactNode;
  badge?: { text: string; color?: 'blue' | 'red' | 'amber' };
}

// 顺序严格固定（design.md §6）
const NAV: NavDef[] = [
  { id: 'assistant', label: '执法助理', icon: IconAssistant, badge: { text: '3', color: 'blue' } },
  { id: 'calendar', label: '工作日历', icon: IconCalendar, badge: { text: '2', color: 'amber' } },
  { id: 'map', label: '辖区地图', icon: IconMap },
  { id: 'enterprises', label: '企业管理', icon: IconEnterprises },
  { id: 'platforms', label: '平台管理', icon: IconPlatforms, badge: { text: '0', color: 'red' } },
  { id: 'enforcement', label: '执法办案', icon: IconEnforcement },
  { id: 'inspection', label: '督察管理', icon: IconInspection },
  { id: 'review', label: '案卷评查', icon: IconReview, badge: { text: '2' } },
  { id: 'archive', label: '档案管理', icon: IconArchive },
  { id: 'knowledge', label: '知识库', icon: IconKnowledge },
  { id: 'mcp', label: 'MCP 连接', icon: IconMcp },
  { id: 'settings', label: '设置', icon: IconSettings },
];

interface Props {
  activeNav: string;
  onNavigate: (id: string) => void;
  badges?: Record<string, { text: string; color?: 'blue' | 'red' | 'amber' }>;
  navWidth?: number;
}

export default function LeftNav({ activeNav, onNavigate, badges, navWidth: _navWidth }: Props): ReactNode {
  const badgeOf = (id: string) => badges?.[id] || NAV.find((n) => n.id === id)?.badge;
  return (
    <nav className="left-nav" style={{ width: '100%', flex: 'none' }}>
      <div className="brand">
        <IconShield />
        <div className="brand-text">
          生态环境执法办案评查
          <small>一体化平台</small>
        </div>
      </div>

      <div className="nav-list">
        {NAV.map((n) => {
          const b = badgeOf(n.id);
          return (
            <div
              key={n.id}
              className={`nav-item${activeNav === n.id ? ' active' : ''}`}
              onClick={() => onNavigate(n.id)}
            >
              <span className="ico">{n.icon()}</span>
              <span className="label">{n.label}</span>
              {b && (
                <span className={`nav-badge${b.color ? ' ' + b.color : ''}`}>
                  {b.text}
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="user-zone">
        <div className="avatar">军</div>
        <div className="u-info">
          <div className="u-name">{currentUser.name}</div>
          <div className="u-org">广通众创 · 生态环境执法</div>
        </div>
      </div>
    </nav>
  );
}
