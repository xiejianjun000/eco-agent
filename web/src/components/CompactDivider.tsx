/**
 * web/src/components/CompactDivider.tsx — 记忆压缩分隔线（WorkBuddy 对标）
 *
 * 对标 WorkBuddy renderer/assets/compact-divider-utils-DSX5v5DJ.js
 * （packages/agent-ui/src/utils/compact-divider-utils.ts）。
 *
 * 三种触发时机（源码 CompactType 枚举原样）：
 *   PRE_MESSAGE_AUTO: "pre-message-auto"  发消息前自动压缩
 *   USER_COMMAND:     "user-command"      用户手动触发
 *   EMERGENCY_AUTO:   "emergency-auto"    上下文超限的紧急压缩
 *
 * 压缩产物由 <conversation_history_summary> 等标签包裹，前端识别后渲染成
 * 一条分隔线而非普通消息 —— 这正是 WorkBuddy 的做法。
 */

import { useState } from 'react';

/** 对标源码 CompactType 枚举，值一字不改 */
export const CompactType = {
  PRE_MESSAGE_AUTO: 'pre-message-auto',
  USER_COMMAND: 'user-command',
  EMERGENCY_AUTO: 'emergency-auto',
} as const;
export type CompactTypeValue = (typeof CompactType)[keyof typeof CompactType];

/** 对标 compact-divider-utils.ts 里的同名正则（逐条照抄） */
export const COMPACT_REQUEST_AT_START_RE = /^\s*<compact-request\b/i;
export const CONVERSATION_HISTORY_SUMMARY_AT_START_RE = /^\s*<conversation_history_summary\b/i;
export const CB_SUMMARY_AT_START_RE = /^\s*<cb_summary\b/i;
export const CONTINUE_PROMPT_AT_START_RE = /^\s*Please continue with the conversation based on the summarized context above\b/i;
export const PLEASE_SUMMARIZE_PROMPT_AT_START_RE = /^\s*Please\s+summarize\s+the\s+conversation\s+above/i;
export const PROMPT_TOO_LONG_META_RE =
  /prompt[_-]?too[_-]?long|input[_-]?length|context[_-]?length|payload[_-]?too[_-]?large|maximum[_-]?context/i;

/** 对标 isCompactUserPromptContent：判断一段文本是否为压缩提示/摘要产物 */
export function isCompactContent(text: string): boolean {
  if (!text) return false;
  return (
    COMPACT_REQUEST_AT_START_RE.test(text) ||
    CONVERSATION_HISTORY_SUMMARY_AT_START_RE.test(text) ||
    CB_SUMMARY_AT_START_RE.test(text) ||
    CONTINUE_PROMPT_AT_START_RE.test(text) ||
    PLEASE_SUMMARIZE_PROMPT_AT_START_RE.test(text)
  );
}

/** 对标 isPromptTooLongErrorContent：命中即应触发 EMERGENCY_AUTO */
export const isPromptTooLongError = (text: string): boolean =>
  !!text && PROMPT_TOO_LONG_META_RE.test(text);

/** 从压缩内容推断 CompactType */
export function inferCompactType(text: string): CompactTypeValue {
  if (isPromptTooLongError(text)) return CompactType.EMERGENCY_AUTO;
  if (COMPACT_REQUEST_AT_START_RE.test(text)) return CompactType.USER_COMMAND;
  return CompactType.PRE_MESSAGE_AUTO;
}

const LABEL: Record<CompactTypeValue, string> = {
  [CompactType.PRE_MESSAGE_AUTO]: '已自动压缩上文记忆',
  [CompactType.USER_COMMAND]: '已按指令压缩记忆',
  [CompactType.EMERGENCY_AUTO]: '上下文超限，已紧急压缩',
};

/** 剥掉包裹标签，取出摘要正文 */
export function extractSummaryBody(text: string): string {
  const m = text.match(/<(?:conversation_history_summary|cb_summary)\b[^>]*>([\s\S]*?)<\/(?:conversation_history_summary|cb_summary)>/i);
  return (m ? m[1] : text).trim();
}

export default function CompactDivider({
  type, summary,
}: {
  type: CompactTypeValue;
  summary?: string;
}) {
  const [open, setOpen] = useState(false);
  const body = summary ? extractSummaryBody(summary) : '';
  const emergency = type === CompactType.EMERGENCY_AUTO;

  return (
    <div className={`compact-divider${emergency ? ' emergency' : ''}`}>
      <div className="compact-divider-line">
        <span className="compact-divider-rule" />
        <button
          className="compact-divider-label"
          onClick={() => body && setOpen((v) => !v)}
          title={body ? '点击查看压缩摘要' : undefined}
          disabled={!body}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" />
          </svg>
          {LABEL[type]}
          {body && <span className="compact-divider-caret">{open ? '收起' : '展开'}</span>}
        </button>
        <span className="compact-divider-rule" />
      </div>
      {open && body && <pre className="compact-divider-body">{body}</pre>}
    </div>
  );
}
