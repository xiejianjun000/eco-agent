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

/** 上下文用量五类（对标 WorkBuddy cr-context-usage 五分色环） */
const CTX_CATS: { key: keyof ContextUsageData; label: string; color: string }[] = [
  { key: 'conv', label: '对话', color: 'var(--cat-conv)' },
  { key: 'tool', label: '工具', color: 'var(--cat-tool)' },
  { key: 'sp', label: '系统', color: 'var(--cat-sp)' },
  { key: 'mcp', label: 'MCP', color: 'var(--cat-mcp)' },
  { key: 'skill', label: '技能', color: 'var(--cat-skill)' },
];

/** SVG 用量环（对标 WorkBuddy RingProgress：五类分段、rotate(-90) 起顶、顺时针堆叠） */
function RingProgress({ data, size = 44, strokeWidth = 4 }: { data: ContextUsageData; size?: number; strokeWidth?: number }) {
  const radius = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * radius;
  const max = Math.max(1, data.max);
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="ctx-ring-svg" aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke="var(--ring-track, rgba(128,128,128,0.2))" strokeWidth={strokeWidth} />
      {CTX_CATS.map((seg) => {
        const val = (data[seg.key] as number) || 0;
        const frac = Math.min(1, Math.max(0, val / max));
        const len = frac * c;
        const node = (
          <circle key={seg.key} cx={size / 2} cy={size / 2} r={radius} fill="none"
            stroke={seg.color} strokeWidth={strokeWidth} strokeLinecap="butt"
            strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-acc}
            transform={`rotate(-90 ${size / 2} ${size / 2})`} className="ctx-ring-seg">
            <title>{`${seg.label}：${val} token`}</title>
          </circle>
        );
        acc += len;
        return node;
      })}
    </svg>
  );
}

/** 上下文用量摘要段（对标 WorkBuddy cr-context-usage-popover 的 byCategory 信息） */
function UsageSummary({ data }: { data: ContextUsageData }) {
  const total = CTX_CATS.reduce((a, s) => a + ((data[s.key] as number) || 0), 0) || 1;
  return (
    <div className="ctx-usage-card">
      <div className="ctx-usage-head">
        <div className="ctx-ring-wrap" tabIndex={0} role="button" aria-label="上下文用量明细">
          <RingProgress data={data} />
          <div className="ctx-ring-pop" role="tooltip">
            <div className="ctx-ring-pop__title">上下文用量明细</div>
            {CTX_CATS.map((s) => {
              const v = (data[s.key] as number) || 0;
              return (
                <div className="ctx-ring-pop__row" key={s.key}>
                  <span className="ctx-cat-dot" style={{ background: s.color }} />
                  <span className="ctx-ring-pop__k">{s.label}</span>
                  <span className="ctx-ring-pop__v">{v} · {Math.round((v / total) * 100)}%</span>
                </div>
              );
            })}
            <div className="ctx-ring-pop__foot">{data.used} / {data.max} token · {data.percent}%</div>
          </div>
        </div>
        <div className="ctx-usage-meta">
          <div className="ctx-usage-pct">{data.percent}%</div>
          <div className="ctx-usage-sub">{data.used} / {data.max} token</div>
        </div>
      </div>
      <div className="ctx-usage-cats">
        {CTX_CATS.map((s) => {
          const v = (data[s.key] as number) || 0;
          return (
            <div className="ctx-cat" key={s.key}>
              <span className="ctx-cat-dot" style={{ background: s.color }} />
              <span className="ctx-cat-k">{s.label}</span>
              <span className="ctx-cat-v">{v} · {Math.round((v / total) * 100)}%</span>
            </div>
          );
        })}
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
