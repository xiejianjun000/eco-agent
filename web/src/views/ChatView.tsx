import React, { useEffect, useRef, useState } from 'react';
import { streamChat, type TraceEvent } from '../api';
import { renderMarkdown, escapeHtml } from '../utils/markdown';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  time?: string;        // 发送/完成时间
  durationMs?: number;  // 总耗时
  ttftMs?: number;      // 首 token 耗时
  rating?: 'up' | 'down' | null;
  branchId?: string;    // 该消息所属分支（分支新对话后标记）
  trace?: TraceEvent[]; // 执行轨迹（DSH 式折叠展示）
}

/** 从 Markdown 回复里提取代码块作为产物（artifact） */
function extractArtifacts(text: string): { lang: string; code: string }[] {
  const out: { lang: string; code: string }[] = [];
  const re = /```(\w*)\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push({ lang: m[1] || 'text', code: m[2].trim() });
  }
  return out;
}

function fmtClock(): string {
  const d = new Date();
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function fmtMs(ms?: number): string {
  if (ms === undefined) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function ChatView(): React.ReactElement {
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: 'assistant',
      content: '你好，我是 ECO AGENT。生态环境执法领域的 AI 同事——可以问我法规、案卷、裁量、督察相关的问题。',
      time: fmtClock(),
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [branchTag, setBranchTag] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const artifacts = messages
    .filter((m) => m.role === 'assistant')
    .flatMap((m) => extractArtifacts(m.content));

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const sentAt = fmtClock();
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, time: sentAt },
      { role: 'assistant', content: '', time: sentAt },
    ]);
    setBusy(true);
    try {
      await streamChat(text, history, (delta, meta) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            content: last.content + delta,
            ttftMs: meta?.ttft_ms ?? last.ttftMs,
          };
          return next;
        });
      }, (meta) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            durationMs: meta.duration_ms,
            trace: meta.trace ?? last.trace,
            time: fmtClock(),
          };
          return next;
        });
      });
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          ...next[next.length - 1],
          content: `[连接失败] ${(e as Error).message}\n请确认已启动: eco server`,
          time: fmtClock(),
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const copyMsg = (m: Msg) => {
    void navigator.clipboard.writeText(m.content);
  };

  const rateMsg = (index: number, rating: 'up' | 'down') => {
    setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, rating: m.rating === rating ? null : rating } : m)));
  };

  const branchFrom = (index: number) => {
    // 分支新对话：把该消息及之前的上下文复制为新会话
    const prefix = messages.slice(0, index + 1).filter((m) => m.content);
    setMessages([
      {
        role: 'assistant',
        content: `已从对话中分支（保留前 ${prefix.length} 条上下文）。继续提问即可。`,
        time: fmtClock(),
        branchId: `branch-${Date.now()}`,
      },
    ]);
    setBranchTag(`分支 · ${prefix.length} 条上下文`);
  };

  return (
    <div className="chat-wrap">
      {/* 左侧产物栏（有产物时显示） */}
      {artifacts.length > 0 && (
        <aside className="artifact-panel">
          <div className="artifact-title">产物 ({artifacts.length})</div>
          {artifacts.map((a, i) => (
            <details key={i} className="artifact-item">
              <summary className="artifact-summary">
                <span className="artifact-lang">{a.lang}</span>
                <span className="artifact-len">{a.code.length} 字符</span>
                <button
                  className="btn ghost artifact-copy"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    void navigator.clipboard.writeText(a.code);
                  }}
                >
                  复制
                </button>
              </summary>
              <pre className="artifact-code">{escapeHtml(a.code)}</pre>
            </details>
          ))}
        </aside>
      )}

      <div className="chat-box" style={{ height: 'calc(100vh - 120px)' }}>
        {branchTag && <div className="branch-tag">{branchTag}</div>}
        <div className="chat-log" ref={logRef}>
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-meta">
                <span className="msg-role">{m.role === 'user' ? '你' : 'ECO AGENT'}</span>
                {m.time && <span className="msg-time">{m.time}</span>}
                {m.role === 'assistant' && m.ttftMs !== undefined && (
                  <span className="msg-stat">首token {fmtMs(m.ttftMs)}</span>
                )}
                {m.role === 'assistant' && m.durationMs !== undefined && (
                  <span className="msg-stat">用时 {fmtMs(m.durationMs)}</span>
                )}
              </div>
              {m.role === 'assistant' && m.trace && m.trace.length > 0 && (
                <details className="trace-block">
                  <summary className="trace-summary">
                    <span className="trace-icon">⚙</span>
                    执行轨迹 · {m.trace.length} 步
                    <span className="trace-hint">（点击展开）</span>
                  </summary>
                  <div className="trace-list">
                    {m.trace.map((t, ti) => (
                      <div key={ti} className={`trace-row trace-${t.type}`}>
                        <span className="trace-step">{ti + 1}</span>
                        {t.type === 'think' && (
                          <span className="trace-body">
                            <span className="trace-badge badge-think">思考</span>
                            {(t.tools?.length ?? 0) > 0 && (
                              <span className="trace-detail">决定调用 {t.tools?.join(', ')}</span>
                            )}
                            {t.thought && <span className="trace-thought">{t.thought}</span>}
                            <span className="trace-cost">{t.cost_ms}ms</span>
                          </span>
                        )}
                        {t.type === 'tool' && (
                          <span className="trace-body">
                            <span className={`trace-badge badge-${t.category ?? 'exec'}`}>
                              {t.category === 'read' ? '读' : t.category === 'write' ? '写' : '执行'}
                            </span>
                            <span className="trace-detail">{t.name}({JSON.stringify(t.args ?? {}).slice(0, 80)})</span>
                            <span className="trace-cost">{t.cost_ms}ms</span>
                            {t.result_preview && (
                              <span className="trace-result">{t.result_preview.slice(0, 120)}</span>
                            )}
                          </span>
                        )}
                        {t.type === 'answer' && (
                          <span className="trace-body">
                            <span className="trace-badge badge-answer">综合</span>
                            <span className="trace-detail">基于检索结果生成回答（{t.chars}字）</span>
                            <span className="trace-cost">{t.cost_ms ?? ''}ms</span>
                          </span>
                        )}
                        {t.type === 'correction' && (
                          <span className="trace-body">
                            <span className="trace-badge badge-correction">纠偏</span>
                            <span className="trace-detail">{t.note}</span>
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}
              <div
                className="bubble"
                dangerouslySetInnerHTML={{
                  __html: m.content
                    ? m.role === 'assistant'
                      ? renderMarkdown(m.content)
                      : escapeHtml(m.content).replace(/\n/g, '<br/>')
                    : (busy ? '<span class="thinking">正在思考<span class="dots">…</span></span>' : ''),
                }}
              />
              {m.role === 'assistant' && !busy && m.content && (
                <div className="msg-toolbar">
                  <button className="tb-btn" title="复制" onClick={() => copyMsg(m)}>⧉ 复制</button>
                  <button
                    className={`tb-btn${m.rating === 'up' ? ' active' : ''}`}
                    title="点赞"
                    onClick={() => rateMsg(i, 'up')}
                  >👍</button>
                  <button
                    className={`tb-btn${m.rating === 'down' ? ' active' : ''}`}
                    title="踩"
                    onClick={() => rateMsg(i, 'down')}
                  >👎</button>
                  <button className="tb-btn" title="在此处分支新对话" onClick={() => branchFrom(i)}>⑂ 分支</button>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="chat-input-row">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            rows={2}
          />
          <button className="btn" onClick={() => void send()} disabled={busy || !input.trim()}>
            {busy ? '生成中' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
