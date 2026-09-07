/**
 * web/src/components/ChatTopbar.tsx — 对话顶栏右上角功能（WorkBuddy 对标）
 *
 * 对标 WorkBuddy packages/agent-ui/src/components/workbuddy-topbar/ 下的两个子模块
 * （在 hooks-B12UGIqg.js 中，不在主 bundle）：
 *
 *  1) chat-search-button/ — 对话内搜索
 *     chat-search-navigation.ts 的 findLocalMarkInContainers 说明其实现是：
 *     在容器内用 `mark.${CHAT_SEARCH_HIT_CLASS}` 标注命中，再按全局序号跨容器定位，
 *     即「DOM 内插入 mark 高亮 + 全局索引上下跳转」，不是简单的滚动。本实现照此。
 *
 *  2) user-prompt-list-button.tsx — 用户提问快速跳转
 *     源码注释原话：「对话内用户提问快速跳转按钮，抽离以降低 WorkBuddyTopBar
 *     主文件大小。」筛选 messageType === "user" 列出，点击跳转到该条。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/** 对标 WorkBuddy CHAT_SEARCH_HIT_CLASS */
export const CHAT_SEARCH_HIT_CLASS = 'chat-search-hit';
const ACTIVE_CLASS = 'chat-search-hit-active';

/** 清除既有高亮：把 mark 还原为纯文本并合并相邻文本节点 */
function clearHighlights(root: HTMLElement) {
  root.querySelectorAll(`mark.${CHAT_SEARCH_HIT_CLASS}`).forEach((m) => {
    const parent = m.parentNode;
    if (!parent) return;
    parent.replaceChild(document.createTextNode(m.textContent || ''), m);
    parent.normalize();
  });
}

/**
 * 在容器内对 query 做文本高亮，返回命中数。
 * 只走文本节点，跳过 script/style 与已有 mark，避免破坏结构或重复包裹。
 */
function highlight(root: HTMLElement, query: string): HTMLElement[] {
  clearHighlights(root);
  const q = query.trim();
  if (!q) return [];
  const lower = q.toLowerCase();

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentElement;
      if (!p) return NodeFilter.FILTER_REJECT;
      if (/^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(p.tagName)) return NodeFilter.FILTER_REJECT;
      if (p.closest(`mark.${CHAT_SEARCH_HIT_CLASS}`)) return NodeFilter.FILTER_REJECT;
      if (!node.nodeValue || !node.nodeValue.toLowerCase().includes(lower)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const targets: Text[] = [];
  let n: Node | null;
  while ((n = walker.nextNode())) targets.push(n as Text);

  const marks: HTMLElement[] = [];
  for (const textNode of targets) {
    const text = textNode.nodeValue || '';
    const frag = document.createDocumentFragment();
    let idx = 0;
    let hit = text.toLowerCase().indexOf(lower, idx);
    while (hit >= 0) {
      if (hit > idx) frag.appendChild(document.createTextNode(text.slice(idx, hit)));
      const mk = document.createElement('mark');
      mk.className = CHAT_SEARCH_HIT_CLASS;
      mk.textContent = text.slice(hit, hit + q.length);
      frag.appendChild(mk);
      marks.push(mk);
      idx = hit + q.length;
      hit = text.toLowerCase().indexOf(lower, idx);
    }
    if (idx < text.length) frag.appendChild(document.createTextNode(text.slice(idx)));
    textNode.parentNode?.replaceChild(frag, textNode);
  }
  return marks;
}

/** 对话内搜索按钮（WorkBuddy chat-search-button 对标） */
export function ChatSearchButton({ containerRef }: { containerRef: React.RefObject<HTMLElement | null> }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState(0);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const marksRef = useRef<HTMLElement[]>([]);

  const run = useCallback((q: string) => {
    const root = containerRef.current;
    if (!root) return;
    const marks = highlight(root, q);
    marksRef.current = marks;
    setHits(marks.length);
    setCursor(marks.length ? 0 : -1);
    if (marks.length) {
      marks[0].classList.add(ACTIVE_CLASS);
      marks[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [containerRef]);

  const jump = useCallback((delta: number) => {
    const marks = marksRef.current;
    if (!marks.length) return;
    setCursor((prev) => {
      marks[prev]?.classList.remove(ACTIVE_CLASS);
      const next = (prev + delta + marks.length) % marks.length;
      marks[next]?.classList.add(ACTIVE_CLASS);
      marks[next]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      return next;
    });
  }, []);

  const close = useCallback(() => {
    const root = containerRef.current;
    if (root) clearHighlights(root);
    marksRef.current = [];
    setOpen(false); setQuery(''); setHits(0); setCursor(0);
  }, [containerRef]);

  // Cmd/Ctrl+F 打开（mac 上是 Cmd）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        setOpen(true);
        setTimeout(() => inputRef.current?.focus(), 0);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => () => { const r = containerRef.current; if (r) clearHighlights(r); }, [containerRef]);

  return (
    <div className="topbar-item">
      <button
        className={`topbar-btn${open ? ' active' : ''}`}
        onClick={() => {
          if (open) close();
          else { setOpen(true); setTimeout(() => inputRef.current?.focus(), 0); }
        }}
        title="对话内搜索 (⌘F)"
        aria-label="对话内搜索"
      >
        <SearchIcon />
      </button>
      {open && (
        <div className="chat-search-pop">
          <input
            ref={inputRef}
            className="chat-search-input"
            value={query}
            placeholder="在对话中搜索…"
            onChange={(e) => { setQuery(e.target.value); run(e.target.value); }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); jump(e.shiftKey ? -1 : 1); }
              if (e.key === 'Escape') { e.preventDefault(); close(); }
            }}
          />
          <span className="chat-search-count">
            {hits ? `${cursor + 1}/${hits}` : query ? '无结果' : ''}
          </span>
          <button className="chat-search-nav" onClick={() => jump(-1)} disabled={!hits} title="上一个 (⇧⏎)">↑</button>
          <button className="chat-search-nav" onClick={() => jump(1)} disabled={!hits} title="下一个 (⏎)">↓</button>
          <button className="chat-search-nav" onClick={close} title="关闭 (Esc)">✕</button>
        </div>
      )}
    </div>
  );
}

/** 用户提问列表快速跳转（WorkBuddy user-prompt-list-button 对标） */
export function UserPromptListButton({
  messages, onJump,
}: {
  messages: { role: string; content: string }[];
  onJump: (index: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // 对标源码：filter(msg => msg.messageType === "user")
  const prompts = useMemo(
    () => messages
      .map((m, i) => ({ ...m, index: i }))
      .filter((m) => m.role === 'user' && m.content.trim()),
    [messages],
  );

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="topbar-item" ref={rootRef}>
      <button
        className={`topbar-btn${open ? ' active' : ''}`}
        onClick={() => setOpen((v) => !v)}
        title={`提问列表（${prompts.length}）`}
        aria-label="提问列表"
        disabled={prompts.length === 0}
      >
        <ListIcon />
      </button>
      {open && (
        <div className="prompt-list-pop">
          <div className="prompt-list-head">本次对话提问 · {prompts.length}</div>
          <div className="prompt-list-body">
            {prompts.map((p, i) => (
              <button
                key={p.index}
                className="prompt-list-item"
                onClick={() => { onJump(p.index); setOpen(false); }}
                title={p.content}
              >
                <span className="prompt-list-no">{i + 1}</span>
                <span className="prompt-list-text">{p.content.replace(/\s+/g, ' ').slice(0, 60)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);
const ListIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
    <circle cx="3.5" cy="6" r="1.2" fill="currentColor" /><circle cx="3.5" cy="12" r="1.2" fill="currentColor" /><circle cx="3.5" cy="18" r="1.2" fill="currentColor" />
  </svg>
);
