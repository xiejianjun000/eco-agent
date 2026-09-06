import React from 'react';
import Icon, { type IconName } from '../components/Icon';

/** 功能模块卡片（与 App.tsx ADMIN_NAV 同序，带扁平图标） */
const MODULE_CARDS: { id: string; icon: IconName; label: string; desc: string }[] = [
  { id: 'memory', icon: 'branch', label: '记忆树', desc: '长期记忆浏览与检索' },
  { id: 'skills', icon: 'sparkles', label: '技能', desc: '技能库与孵化' },
  { id: 'agents', icon: 'package', label: '子代理', desc: '后台子代理目录与任务输出' },
  { id: 'goals', icon: 'check', label: '目标', desc: '跨轮目标与自动推进' },
  { id: 'workflow', icon: 'gear', label: '编排', desc: 'Workflow 编排与执法计划' },
  { id: 'traces', icon: 'chart', label: '轨迹', desc: '会话 span 瀑布与决策时间线' },
  { id: 'system', icon: 'terminal', label: '系统状态', desc: '组件状态与指标' },
];

/** 独立设置页：外观（主题三态）+ 功能模块入口 + 关于 */
export default function SettingsView({
  theme,
  onThemeChange,
  onNavigate,
  version,
  rev,
}: {
  theme: 'light' | 'dark';
  onThemeChange: (t: 'light' | 'dark') => void;
  onNavigate: (page: string) => void;
  version: string;
  rev: string;
}): React.ReactElement {
  // 主题三态：followSystem=true 时高亮「跟随系统」，实际 light/dark 由 matchMedia 解析
  const [followSystem, setFollowSystem] = React.useState(false);

  const pickSystem = () => {
    setFollowSystem(true);
    onThemeChange(window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  };
  const pick = (t: 'light' | 'dark') => {
    setFollowSystem(false);
    onThemeChange(t);
  };

  const themeOpts: { key: 'system' | 'light' | 'dark'; label: string; icon: IconName; onClick: () => void; active: boolean }[] = [
    { key: 'system', label: '跟随系统', icon: 'gear', onClick: pickSystem, active: followSystem },
    { key: 'light', label: '浅色', icon: 'sun', onClick: () => pick('light'), active: !followSystem && theme === 'light' },
    { key: 'dark', label: '深色', icon: 'moon', onClick: () => pick('dark'), active: !followSystem && theme === 'dark' },
  ];

  return (
    <div className="settings-page">
      <div className="settings-group">
        <div className="settings-group-title">外观</div>
        <div className="settings-theme-row">
          {themeOpts.map((o) => (
            <button
              key={o.key}
              className={`settings-theme-btn${o.active ? ' active' : ''}`}
              onClick={o.onClick}
            >
              <Icon name={o.icon} size={14} /> {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="settings-group">
        <div className="settings-group-title">功能模块</div>
        <div className="settings-cards">
          {MODULE_CARDS.map((m) => (
            <button key={m.id} className="settings-card" onClick={() => onNavigate(m.id)}>
              <span className="settings-card-icon"><Icon name={m.icon} size={18} /></span>
              <span className="settings-card-name">{m.label}</span>
              <span className="settings-card-desc">{m.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="settings-group">
        <div className="settings-group-title">关于</div>
        <div className="settings-about">
          <div className="settings-about-name">eco Agent</div>
          <div className="settings-about-meta">
            v{version || '…'}{rev ? ` · git ${rev}` : ''}
          </div>
        </div>
      </div>
    </div>
  );
}
