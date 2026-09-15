import React, { useEffect, useState } from 'react';
import { getSideCards, type SideCardContribution } from '../plugins/registry';
import {
  getContextUsage, subscribeContextUsage, type ContextUsageData,
} from '../plugins/contextUsageStore';
import { IconChevronRight, IconChevronLeft, IconPlus } from '../plugins/icons';

/**
 * 右侧 ContextPanel —— 严格对标 WorkBuddy 的 context-panel（packages/agent-ui/.../context-panel）。
 *
 * 结构（源码级还原）：
 *   <aside class="context-panel">
 *     <header class="context-panel__header">  标题 + 折叠键 </header>
 *     <usage summary>                          上下文用量环（CR 环，五类分段）
 *     <div class="context-panel__cards">        垂直配置卡片栈（wb-config-card）
 *
 * 卡片双态（对标 WorkBuddy）：
 *   - filled：有 body（图标列 / 任务列表 / 团队 chips）
 *   - empty ：仅标题 + 描述 + 右上角 PlusIcon
 */

/** SVG 用量环（对标 WorkBuddy RingProgress：双 circle、round 端点、rotate(-90) 起顶） */
function RingProgress({ percent, size = 44, strokeWidth = 4 }: { percent: number; size?: number; strokeWidth?: number }) {
  const radius = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * radius;
  const offset = c - (Math.min(100, Math.max(0, percent)) / 100) * c;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="ctx-ring-svg" aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke="var(--ring-track, rgba(128,128,128,0.2))" strokeWidth={strokeWidth} />
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke="var(--ring-progress, var(--ds-brand))" strokeWidth={strokeWidth}
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} className="ctx-ring-progress" />
    </svg>
  );
}

/** 上下文用量摘要段（对标 WorkBuddy cr-context-usage-popover 的 byCategory 信息） */
function UsageSummary({ data }: { data: ContextUsageData }) {
  const cats: [string, number][] = [
    ['对话', data.conv], ['工具', data.tool], ['系统', data.sp],
    ['MCP', data.mcp], ['技能', data.skill],
  ];
  return (
    <div className="ctx-usage-card">
      <div className="ctx-usage-head">
        <RingProgress percent={data.percent} />
        <div className="ctx-usage-meta">
          <div className="ctx-usage-pct">{data.percent}%</div>
          <div className="ctx-usage-sub">{data.used} / {data.max} token</div>
        </div>
      </div>
      <div className="ctx-usage-cats">
        {cats.map(([k, v]) => (
          <div className="ctx-cat" key={k}>
            <span className="ctx-cat-k">{k}</span>
            <span className="ctx-cat-v">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 单张配置卡片（wb-config-card 同构） */
function SideCard({ card }: { card: SideCardContribution }) {
  const filled = Boolean(card.body);
  return (
    <div
      className={`wb-config-card${filled ? ' wb-config-card--filled' : ' wb-config-card--empty'}`}
      onClick={card.onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.onOpen?.(); } }}
    >
      <div className="wb-config-card__content">
        <div className="wb-config-card__title">
          <span className="wb-config-card__icon">{card.icon}</span>
          <span>{card.title}</span>
        </div>
        {filled ? (
          <div className="wb-config-card__body">{card.body}</div>
        ) : (
          <div className="wb-config-card__desc">{card.desc}</div>
        )}
      </div>
      <button
        className="wb-config-card__plus"
        title={`配置${card.title}`}
        aria-label={`配置${card.title}`}
        onClick={(e) => { e.stopPropagation(); card.onOpen?.(); }}
      >
        <IconPlus size={16} />
      </button>
    </div>
  );
}

interface SidePanelProps {
  open: boolean;
  onToggle: () => void;
  /** 折叠态时显示的折叠轨道按钮（贴在中栏右侧） */
}

export default function SidePanel({ open, onToggle }: SidePanelProps) {
  const cards = getSideCards();
  const [usage, setUsage] = useState<ContextUsageData | null>(getContextUsage());

  useEffect(() => subscribeContextUsage(setUsage), []);

  if (!open) {
    return (
      <button
        className="side-rail-btn"
        title="展开生态上下文"
        aria-label="展开生态上下文"
        onClick={onToggle}
      >
        <IconChevronLeft size={16} />
      </button>
    );
  }

  return (
    <aside className="context-panel">
      <div className="context-panel__header">
        <h2 className="context-panel__title">生态上下文</h2>
        <button
          className="context-panel__collapse"
          title="收起面板"
          aria-label="收起面板"
          onClick={onToggle}
        >
          <IconChevronRight size={16} />
        </button>
      </div>
      {usage && <UsageSummary data={usage} />}
      <div className="context-panel__cards">
        {cards.map((c) => (
          <SideCard key={c.id} card={c} />
        ))}
      </div>
    </aside>
  );
}
