/**
 * web/src/components/DocDrawer.tsx — 产物抽屉（WorkBuddy 对标）
 *
 * 形态取自 WorkBuddy 源码 .colleague-chat-artifact-drawer 及其原始注释：
 *   - absolute 定位在对话容器内（不走 portal），top/right/bottom 贴边
 *   - 宽度由 inline px 控制，CSS 只做 transition —— 因此放大/缩小可插值成动画
 *     （translateX 滑入是另一回事，WorkBuddy 用的是 width 过渡）
 *   - .is-wide 全屏态在 CSS 上不控制宽度，仅作状态钩子
 *   - transition: width .24s cubic-bezier(.4,0,.2,1)
 *   - box-shadow: -8px 0 24px rgba(0,0,0,.06)
 *
 * 右上角按钮组对标 WorkBuddy preview-modal__header-actions：
 *   全屏切换（Maximize2/Minimize2，14px）+ 关闭（X，16px）
 * 左边缘可拖拽调宽（MIN_WIDTH_PX 下限 + 容器宽度上限），与 WorkBuddy 一致。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import DocViewer, { type DocSource } from './DocViewer';

const MIN_WIDTH_PX = 320;
const DEFAULT_WIDTH_PX = 480;
const STORAGE_KEY = 'eco-doc-drawer-w';

export default function DocDrawer({
  source,
  title,
  onClose,
}: {
  source: DocSource | null;
  title?: string;
  onClose: () => void;
}) {
  const [width, setWidth] = useState<number>(() => {
    const saved = Number(window.localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(saved) && saved >= MIN_WIDTH_PX ? saved : DEFAULT_WIDTH_PX;
  });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  const toggleFullscreen = useCallback(() => setIsFullscreen((v) => !v), []);

  // Esc 关闭；全屏态下先退出全屏（与 WorkBuddy 的分层退出一致）
  useEffect(() => {
    if (!source) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (isFullscreen) setIsFullscreen(false);
      else onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [source, isFullscreen, onClose]);

  // 左边缘拖拽调宽
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      const st = dragRef.current;
      if (!st) return;
      const parent = rootRef.current?.parentElement;
      const maxW = parent ? Math.max(MIN_WIDTH_PX, parent.clientWidth - 160) : 1200;
      const next = Math.max(MIN_WIDTH_PX, Math.min(maxW, st.startW + (st.startX - e.clientX)));
      setWidth(next);
    };
    const onUp = () => {
      setDragging(false);
      dragRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      setWidth((w) => { window.localStorage.setItem(STORAGE_KEY, String(w)); return w; });
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [dragging]);

  if (!source) return null;

  const startDrag = (e: React.MouseEvent) => {
    if (isFullscreen) return;
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startW: width };
    setDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const label = title
    ?? (source.kind === 'local' ? source.name
      : source.kind === 'url' ? source.url
      : source.title || '图表');

  return (
    <aside
      ref={rootRef}
      className={`doc-drawer${isFullscreen ? ' is-wide' : ''}${dragging ? ' is-dragging' : ''}`}
      style={{ width: isFullscreen ? '100%' : width }}
    >
      {!isFullscreen && (
        <div className="doc-drawer-sash" onMouseDown={startDrag} title="拖拽调整宽度" />
      )}
      <div className="doc-drawer-head">
        <span className="doc-drawer-title" title={label}>{label}</span>
        <button
          className="doc-drawer-btn"
          onClick={toggleFullscreen}
          title={isFullscreen ? '退出全屏' : '全屏'}
          aria-label={isFullscreen ? '退出全屏' : '全屏'}
        >
          {isFullscreen ? <Minimize2 /> : <Maximize2 />}
        </button>
        <button className="doc-drawer-btn" onClick={onClose} title="关闭" aria-label="关闭">
          <CloseIcon />
        </button>
      </div>
      <div className="doc-drawer-body">
        <DocViewer source={source} />
      </div>
    </aside>
  );
}

/* 图标尺寸对齐 WorkBuddy：全屏 14px，关闭 16px */
const Maximize2 = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" />
    <line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
  </svg>
);
const Minimize2 = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" />
    <line x1="14" y1="10" x2="21" y2="3" /><line x1="3" y1="21" x2="10" y2="14" />
  </svg>
);
const CloseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
