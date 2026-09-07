import { useRef, type ReactNode } from 'react';
import { IconChevron } from './icons';

interface SectionHeaderProps {
  id: string;
  icon: ReactNode;
  title: string;
  statusDot?: 'olive' | 'amber' | 'red' | 'blue' | null;
  badge?: string;
  collapsed: boolean;
  pinned?: boolean;
  onToggle: () => void;
}

export default function SectionHeader({
  icon, title, statusDot, badge, collapsed, pinned, onToggle,
}: SectionHeaderProps): ReactNode {
  const bodyRef = useRef<HTMLDivElement>(null);

  const handleToggle = () => {
    // Collapse animation: set explicit maxHeight before toggling
    const body = bodyRef.current?.parentElement?.querySelector('.rp-sec-body') as HTMLElement | null;
    if (body) {
      if (collapsed) {
        // Expanding: set to scrollHeight then remove limit
        body.style.maxHeight = body.scrollHeight + 'px';
        body.style.opacity = '1';
        const tid = setTimeout(() => { body.style.maxHeight = 'none'; }, 240);
        body.dataset.tid = String(tid);
      } else {
        // Collapsing: lock current height then go to 0
        const tid = Number(body.dataset.tid);
        if (tid) clearTimeout(tid);
        body.style.maxHeight = body.scrollHeight + 'px';
        requestAnimationFrame(() => {
          body.style.maxHeight = '0';
          body.style.opacity = '0';
        });
      }
    }
    onToggle();
  };

  return (
    <div className="rp-sec-head" onClick={handleToggle} role="button" aria-expanded={!collapsed} tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleToggle(); } }}
    >
      <span className="rp-sec-icon">{icon}</span>
      <span className="rp-sec-title">{title}</span>
      {statusDot && !collapsed && <span className={`rp-sec-dot ${statusDot}`} />}
      {badge && collapsed && <span className="rp-sec-badge">{badge}</span>}
      {pinned && <span className="rp-sec-pin" title="已钉住" />}
      <span className={`rp-sec-chev ${collapsed ? '' : 'open'}`}>
        <IconChevron />
      </span>
    </div>
  );
}
