/**
 * web/src/components/ProductPanel.tsx — 常驻右栏产物面板（WorkBuddy ProductPanel 对标）
 *
 * 之前右栏产物面板被整体移除，只留下「点击单个产物弹 DocDrawer」的临时抽屉。
 * 用户反馈「页面一点变化没有」，根因就在这里：产物是对话里散落的 ArtifactCard，
 * 没有一个常驻的右侧面板把它们聚合起来。
 *
 * 本组件恢复常驻右栏，按 WorkBuddy 三分区组织（RENDER_SPEC §6.5.2）：
 *   1. 制品（artifactSlot.title「任务产生制品」）——HTML 类产物点击在面板内 iframe 实时预览
 *   2. 文件变更（filesTitle）——暂从产物名推断，后端未单独上报 diff
 *   3. 引用来源（sourcesTitle）——暂无独立数据源，有则显示
 *
 * 行为对齐：
 *   - HTML/URL 产物在面板内打开实时预览（DocViewer 的 iframe 沙箱 + CSP 白名单）
 *   - 非 HTML 产物点击预览/下载
 *   - 左边缘可拖拽调宽（沿用 DocDrawer 的 sash 交互）
 *   - 空态文案「请选择一个产物查看详情」对齐 detailPanel.selectArtifact
 */

import React, { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import TaskPanel from './TaskPanel';
import DocViewer, { type DocSource, rendererFor } from './DocViewer';

export interface ProductItem {
  name: string;
  title: string;
  size?: number;
  path?: string;
  /** 产物 MIME（后端据扩展名给出，右栏据此路由预览器/图标） */
  mimeType?: string;
  /** document | media（对标 WorkBuddy artifact.contentType） */
  contentType?: string;
  /** 产生时间 ms（按此降序，对标 WorkBuddy updatedAt） */
  createdAt?: number;
  /** 主动产出凭证：SaveDocument | PresentFiles（对标 _meta.sourceTool） */
  sourceTool?: string;
}

/** 右栏最多展示卡片数（对标 WorkBuddy artifact-slot-panel MAX_DISPLAY_ITEMS） */
export const MAX_PRODUCT_ITEMS = 6;

/** 不进产物栏的内部路径黑名单（对标 HIDDEN_PATHS：.workbuddy / .memory） */
export const HIDDEN_PRODUCT_PATH_RE = /(\.eco[\\/]|memory-tree|\.workbuddy|\.memory|decisions\.jsonl|session_log)/i;

const MIN_WIDTH_PX = 280;
const DEFAULT_WIDTH_PX = 400;
const STORAGE_KEY = 'eco-product-panel-w';

function fileIcon(name: string): string {
  const r = rendererFor(name);
  if (r === 'html') return 'link';
  if (r === 'image') return 'image';
  if (r === 'slides') return 'slides';
  if (r === 'audio' || r === 'video') return 'mic';
  if (r === 'pdf' || r === 'docx') return 'file-text';
  if (r === 'sheet') return 'chart';
  if (r === 'text') return 'file-text';
  return 'paperclip';
}

export default function ProductPanel({
  products,
  sources,
  open,
  onClose,
}: {
  products: ProductItem[];
  /** web 搜索来源聚合（对标 WorkBuddy DetailPanel sources 视图） */
  sources?: { title: string; url: string; engine?: string; query?: string }[];
  open: boolean;
  onClose: () => void;
}) {
  const [width, setWidth] = useState<number>(() => {
    const saved = Number(window.localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(saved) && saved >= MIN_WIDTH_PX ? saved : DEFAULT_WIDTH_PX;
  });
  const [selected, setSelected] = useState<ProductItem | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // 防御性过滤：即便上游传入未收敛的列表，右栏也只显示安全区主动产物、最多 6 条
  const visibleProducts = products
    .filter((p) => !HIDDEN_PRODUCT_PATH_RE.test(p.path || p.name))
    .slice(0, MAX_PRODUCT_ITEMS);

  // 产物列表变化时，若当前选中的产物已不在列表，回到列表态
  useEffect(() => {
    if (selected && !visibleProducts.some((p) => p.name === selected.name)) {
      setSelected(null);
    }
  }, [visibleProducts, selected]);

  // Esc 关闭（先退出详情，再关面板，与 WorkBuddy 分层退出一致）
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (selected) setSelected(null);
      else onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, selected, onClose]);

  // 左边缘拖拽调宽
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      const st = dragRef.current;
      if (!st) return;
      const parent = rootRef.current?.parentElement;
      const maxW = parent ? Math.max(MIN_WIDTH_PX, parent.clientWidth - 260) : 1400;
      setWidth(Math.max(MIN_WIDTH_PX, Math.min(maxW, st.startW + (st.startX - e.clientX))));
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

  if (!open) return null;

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startW: width };
    setDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const src: DocSource | null = selected
    ? { kind: 'local', name: selected.name }
    : null;

  const previewable = (p: ProductItem) => rendererFor(p.name) !== 'none';

  return (
    <aside
      ref={rootRef}
      className={`product-panel${dragging ? ' is-dragging' : ''}`}
      style={{ width }}
    >
      <div className="product-panel-sash" onMouseDown={startDrag} title="拖拽调整宽度" />

      <div className="product-panel-head">
        <span className="product-panel-title">产物</span>
        <span className="product-panel-count">{visibleProducts.length}</span>
        <button
          className="product-panel-btn"
          title="收起右栏"
          aria-label="收起右栏"
          onClick={onClose}
        >
          <CloseIcon />
        </button>
      </div>

      {selected ? (
        <div className="product-panel-detail">
          <div className="product-panel-detail-head">
            <button
              className="product-panel-back"
              onClick={() => setSelected(null)}
              title="返回产物列表"
            >
              ← 返回列表
            </button>
            <span className="product-panel-detail-name" title={selected.title}>{selected.title}</span>
            <a
              className="product-panel-btn"
              title="在浏览器中打开"
              href={`/api/v1/documents/artifact/${encodeURIComponent(selected.name)}/download`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalIcon />
            </a>
          </div>
          <div className="product-panel-detail-body">
            {src ? <DocViewer source={src} /> : (
              <div className="product-panel-empty">该产物不支持内嵌预览，请下载查看</div>
            )}
          </div>
        </div>
      ) : visibleProducts.length === 0 ? (
        <div className="product-panel-empty">
          <div className="product-panel-empty-icon"><Icon name="folder" size={22} /></div>
          <div className="product-panel-empty-title">请选择一个产物查看详情</div>
          <div className="product-panel-empty-sub">对话中生成的文档、图表、报告会出现在这里</div>
        </div>
      ) : (
        <div className="product-panel-list">
          {visibleProducts.map((p) => (
            <button
              key={p.name}
              className="product-item"
              onClick={() => previewable(p) && setSelected(p)}
              title={previewable(p) ? `预览 ${p.title}` : `${p.title}（点击下载）`}
            >
              <span className="product-item-icon"><Icon name={fileIcon(p.name) as never} size={15} /></span>
              <span className="product-item-body">
                <span className="product-item-title">{p.title}</span>
                {p.path && <span className="product-item-path">{p.path}</span>}
              </span>
              {p.size !== undefined && (
                <span className="product-item-size">{(p.size / 1024).toFixed(1)} KB</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* 来源聚合（对标 WorkBuddy DetailPanel sources）：列表态下常驻产物下方 */}
      {!selected && (sources || []).length > 0 && (
        <div className="product-sources">
          <div className="product-sources-title">引用来源 · {sources!.length}</div>
          {sources!.map((s) => {
            let host = s.url;
            try { host = new URL(s.url).hostname.replace(/^www\./, ''); } catch { /* keep */ }
            return (
              <a key={s.url} className="product-source-item" href={s.url}
                 target="_blank" rel="noreferrer" title={s.url}>
                <span className="product-source-icon"><Icon name="link" size={13} /></span>
                <span className="product-source-body">
                  <span className="product-source-title">{s.title}</span>
                  <span className="product-source-host">{host}</span>
                </span>
              </a>
            );
          })}
        </div>
      )}

      {/* 持久化任务（对标 WorkBuddy TaskList）：列表态下常驻右栏 */}
      {!selected && <TaskPanel compact />}
    </aside>
  );
}

const CloseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const ExternalIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);
