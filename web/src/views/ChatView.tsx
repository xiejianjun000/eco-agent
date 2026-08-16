import React, { useEffect, useRef, useState } from 'react';
import { streamChat, api, type ChatUsage, type TraceEvent, type SubagentInfo } from '../api';
import { renderMarkdown, escapeHtml } from '../utils/markdown';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  time?: string;        // 发送/完成时间
  durationMs?: number;  // 总耗时
  ttftMs?: number;      // 首个 LLM 响应耗时
  usage?: ChatUsage;    // 会话级 token 计量
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

/** 按轮次分组轨迹事件（DSH 式 Turns/Calls 结构） */
function groupTraceByRound(trace: TraceEvent[]): { round: number; events: TraceEvent[]; totalMs: number }[] {
  const map = new Map<number, TraceEvent[]>();
  for (const t of trace) {
    const r = t.round ?? 1;
    if (!map.has(r)) map.set(r, []);
    map.get(r)!.push(t);
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([round, events]) => ({
      round,
      events,
      totalMs: events.reduce((s, e) => s + (e.cost_ms ?? 0), 0),
    }));
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

/** 统计行：时间 · 用时 · 首响应 · token 速率（DSH 式计量） */
function fmtStatRow(m: Msg): string {
  const parts: string[] = [];
  if (m.time) parts.push(m.time);
  if (m.durationMs !== undefined) parts.push(`用时 ${fmtMs(m.durationMs)}`);
  if (m.ttftMs !== undefined) parts.push(`首响应 ${fmtMs(m.ttftMs)}`);
  const total = m.usage?.total_tokens;
  const durS = (m.durationMs ?? 0) / 1000;
  if (total && durS > 0) parts.push(`${total} tok · ${Math.round(total / durS)} tok/s`);
  return parts.join(' · ');
}

/** 工具结果 JSON 摘要（截断显示 + 可展开） */
function fmtArgs(args?: Record<string, unknown>): string {
  try {
    const s = JSON.stringify(args ?? {});
    return s.length > 80 ? `${s.slice(0, 80)}…` : s;
  } catch {
    return '';
  }
}

/** DSH 式过程块：按轮次渲染思考（完整 thought）+ 工具调用卡 */
function renderProcessBlock(trace: TraceEvent[]): React.ReactElement | null {
  if (!trace || trace.length === 0) return null;
  const turns = groupTraceByRound(trace);
  const hasProc = trace.some((t) => t.type === 'think' || t.type === 'tool');
  if (!hasProc) return null;
  return (
    <div className="process-block">
      {turns.map((turn) => (
        <div key={turn.round} className="process-turn">
          {turn.events.map((t, ti) => {
            if (t.type === 'think' && t.thought) {
              return (
                <details key={ti} className="think-item" open={turn.round === 1}>
                  <summary className="think-summary">
                    <span className="think-badge">思考 · R{turn.round}</span>
                    <span className="think-tools">拟调用 {t.tools?.join(', ') || '—'}</span>
                    <span className="trace-cost">{fmtMs(t.cost_ms)}</span>
                  </summary>
                  <div className="think-body">{escapeHtml(t.thought)}</div>
                </details>
              );
            }
            if (t.type === 'tool') {
              return (
                <details key={ti} className="call-item">
                  <summary className="call-summary">
                    <span className={`trace-badge badge-${t.category ?? 'exec'}`}>
                      {t.category === 'read' ? '读' : t.category === 'write' ? '写' : '执行'}
                    </span>
                    <span className="call-name">{t.name}</span>
                    <span className="call-args">{fmtArgs(t.args)}</span>
                    <span className="trace-cost">{fmtMs(t.cost_ms)}</span>
                  </summary>
                  {t.result_preview && (
                    <pre className="call-result">{escapeHtml(t.result_preview)}</pre>
                  )}
                </details>
              );
            }
            return null;
          })}
        </div>
      ))}
    </div>
  );
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
  const [sideTab, setSideTab] = useState<'trace' | 'artifact' | 'doc' | 'task'>('trace');
  const [docFiles, setDocFiles] = useState<{ name: string; path: string; size_kb: number }[]>([]);
  const [docTools, setDocTools] = useState<{ name: string; desc: string }[]>([]);
  // 子代理任务面板（对标 DSH subagent/jobs）
  const [taskAgents, setTaskAgents] = useState<SubagentInfo[]>([]);
  const [taskInput, setTaskInput] = useState('');
  const [taskSpawnBusy, setTaskSpawnBusy] = useState(false);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [taskDetail, setTaskDetail] = useState<{ agent: SubagentInfo; output: { seq: number; kind: string; status?: string; result?: string }[] } | null>(null);
  const [taskFollowup, setTaskFollowup] = useState('');

  React.useEffect(() => {
    import('../api').then(({ api }) => {
      api.documents().then((r) => setDocFiles(r.files)).catch(() => {});
      api.documentTools().then((r) => setDocTools(r.tools)).catch(() => {});
    });
  }, [messages]);
  const [selectedTrace, setSelectedTrace] = useState<number | null>(null);
  const [turnsOpen, setTurnsOpen] = useState(true);
  const [callsOpen, setCallsOpen] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  // 最新一条带轨迹的 assistant 消息自动选中
  const lastTraceIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'assistant' && (messages[i].trace?.length ?? 0) > 0) return i;
    }
    return null;
  })();
  const activeTraceMsg = selectedTrace !== null ? messages[selectedTrace] : null;
  const activeTrace = activeTraceMsg?.trace ?? messages[lastTraceIndex ?? -1]?.trace ?? [];

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const artifacts = messages
    .filter((m) => m.role === 'assistant')
    .flatMap((m) => extractArtifacts(m.content));

  // ── 子代理任务面板逻辑 ─────────────────────────────
  // 选中任务轮询（running/pending 时每 2.5s 刷新，done 后停止）
  useEffect(() => {
    if (!selectedTask) return;
    let alive = true;
    const poll = async () => {
      try {
        const d = await api.subagentGet(selectedTask);
        if (!alive) return;
        setTaskDetail({ agent: d.agent, output: d.output });
        void api.subagentList().then((l) => { if (alive) setTaskAgents(l.agents); }).catch(() => {});
        if (d.agent.status === 'running' || d.agent.status === 'pending') {
          window.setTimeout(() => void poll(), 2500);
        }
      } catch { /* 任务已移除 */ }
    };
    void poll();
    return () => { alive = false; };
  }, [selectedTask]);

  const spawnTask = async () => {
    const text = taskInput.trim();
    if (!text || taskSpawnBusy) return;
    setTaskSpawnBusy(true);
    setTaskInput('');
    try {
      const snap = await api.subagentSpawn({ message: text, background: true, label: text.slice(0, 24) });
      setSelectedTask(snap.id);
      setSideTab('task');
      const list = await api.subagentList();
      setTaskAgents(list.agents);
    } catch (e) {
      setTaskInput(text);
      window.alert(`任务发起失败: ${(e as Error).message}`);
    } finally {
      setTaskSpawnBusy(false);
    }
  };

  const followupTask = async (id: string) => {
    const text = taskFollowup.trim();
    if (!text) return;
    setTaskFollowup('');
    try {
      await api.subagentMessage(id, text);
      const d = await api.subagentGet(id);
      setTaskDetail({ agent: d.agent, output: d.output });
    } catch (e) {
      window.alert(`续聊失败: ${(e as Error).message}`);
    }
  };

  const refreshTaskList = () => {
    void api.subagentList().then((l) => setTaskAgents(l.agents)).catch(() => {});
  };

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
            content: meta?.reset ? delta : last.content + delta,
            ttftMs: meta?.ttft_ms ?? last.ttftMs,
          };
          return next;
        });
      }, (ev) => {
        // 实时轨迹事件：过程块边跑边渲染（DSH 式）
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, trace: [...(last.trace ?? []), ev] };
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
            usage: meta.usage ?? last.usage,
            ttftMs: meta.ttft_ms ?? last.ttftMs,
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
      <div className="chat-box" style={{ height: 'calc(100vh - 120px)' }}>
        {branchTag && <div className="branch-tag">{branchTag}</div>}
        <div className="chat-log" ref={logRef}>
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-meta">
                <span className="msg-role">{m.role === 'user' ? '你' : 'ECO AGENT'}</span>
                {m.role === 'user' && m.time && <span className="msg-time">{m.time}</span>}
                {m.role === 'assistant' && m.durationMs !== undefined && (
                  <span className="msg-stat">{fmtStatRow(m)}</span>
                )}
              </div>
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
              {m.role === 'assistant' && (m.trace?.length ?? 0) > 0 && renderProcessBlock(m.trace!)}
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
                  <button
                    className={`tb-btn${selectedTrace === i ? ' active' : ''}`}
                    title="查看执行轨迹"
                    onClick={() => {
                      setSelectedTrace(i);
                      setSideTab('trace');
                    }}
                  >⚙ 轨迹</button>
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

      {/* 右侧标签页面板：轨迹 / 产物 */}
      <aside className="side-panel">
        <div className="side-tabs">
          <button
            className={`side-tab${sideTab === 'trace' ? ' active' : ''}`}
            onClick={() => setSideTab('trace')}
          >
            轨迹{activeTrace.length > 0 ? ` (${activeTrace.length})` : ''}
          </button>
          <button
            className={`side-tab${sideTab === 'artifact' ? ' active' : ''}`}
            onClick={() => setSideTab('artifact')}
          >
            产物{artifacts.length > 0 ? ` (${artifacts.length})` : ''}
          </button>
          <button
            className={`side-tab${sideTab === 'doc' ? ' active' : ''}`}
            onClick={() => setSideTab('doc')}
          >
            文档{docFiles.length > 0 ? ` (${docFiles.length})` : ''}
          </button>
          <button
            className={`side-tab${sideTab === 'task' ? ' active' : ''}`}
            onClick={() => { setSideTab('task'); refreshTaskList(); }}
          >
            任务{taskAgents.length > 0 ? ` (${taskAgents.length})` : ''}
          </button>
        </div>

        {sideTab === 'trace' && (
          <div className="side-trace">
            {activeTrace.length === 0 ? (
              <div className="empty" style={{ padding: 24 }}>
                暂无轨迹——问一个需要查法条/知识库的问题，
                或点击消息下方「⚙ 轨迹」查看对应执行过程。
              </div>
            ) : (
              <>
                <div className="trace-toolbar">
                  <span className="trace-stat">
                    <b>{fmtMs(activeTraceMsg?.durationMs ?? activeTrace.reduce((s, t) => s + (t.cost_ms ?? 0), 0))}</b>
                    <span>Duration</span>
                  </span>
                  <span className="trace-stat">
                    <b>{groupTraceByRound(activeTrace).length}</b>
                    <span>Turns</span>
                  </span>
                  <span className="trace-stat">
                    <b>{activeTrace.filter((t) => t.type === 'tool').length}</b>
                    <span>Calls</span>
                  </span>
                  <span className="trace-spacer" />
                  <button className="tb-btn" onClick={() => setTurnsOpen((v) => !v)}>
                    {turnsOpen ? '收起轮次' : '展开轮次'}
                  </button>
                  <button className="tb-btn" onClick={() => setCallsOpen((v) => !v)}>
                    {callsOpen ? '收起调用' : '展开调用'}
                  </button>
                </div>
                <div className="trace-selector">
                  选择消息查看轨迹：
                  {messages.map((m, i) =>
                    m.role === 'assistant' && (m.trace?.length ?? 0) > 0 ? (
                      <button
                        key={i}
                        className={`trace-chip${selectedTrace === i ? ' active' : ''}`}
                        onClick={() => setSelectedTrace(i)}
                      >
                        第 {i + 1} 条 · {m.trace!.length} 步
                      </button>
                    ) : null,
                  )}
                </div>
                <div className="trace-tree">
                  <details className="trace-node trace-root" open>
                    <summary className="trace-node-summary">
                      <span className="trace-caret">▼</span>
                      <span className="trace-label">Duration</span>
                      <span className="trace-cost">
                        {fmtMs(activeTraceMsg?.durationMs ?? activeTrace.reduce((s, t) => s + (t.cost_ms ?? 0), 0))}
                      </span>
                    </summary>
                    <div className="trace-group">
                      <div className="trace-group-label">Turns · {groupTraceByRound(activeTrace).length}</div>
                      {groupTraceByRound(activeTrace).map((turn) => {
                        const callEvts = turn.events.filter((t) => t.type === 'tool');
                        const thinkEvts = turn.events.filter((t) => t.type !== 'tool');
                        return (
                          <details key={turn.round} className="trace-node trace-turn" open={turnsOpen}>
                            <summary className="trace-node-summary">
                              <span className="trace-caret">▼</span>
                              <span className="trace-label">Turn {turn.round}</span>
                              <span className="trace-cost">{fmtMs(turn.totalMs)}</span>
                            </summary>
                            <div className="trace-node-body">
                              {thinkEvts.map((t, ti) => {
                                if (t.type === 'think') {
                                  return (
                                    <div key={ti} className="trace-event">
                                      <span className="trace-badge badge-think">思考</span>
                                      {(t.tools?.length ?? 0) > 0 && (
                                        <span className="trace-detail">决定调用 {t.tools?.join(', ')}</span>
                                      )}
                                      <span className="trace-cost">{t.cost_ms}ms</span>
                                    </div>
                                  );
                                }
                                if (t.type === 'answer') {
                                  return (
                                    <div key={ti} className="trace-event">
                                      <span className="trace-badge badge-answer">综合</span>
                                      <span className="trace-detail">生成回答（{t.chars}字）</span>
                                      <span className="trace-cost">{t.cost_ms ?? ''}ms</span>
                                    </div>
                                  );
                                }
                                if (t.type === 'correction') {
                                  return (
                                    <div key={ti} className="trace-event">
                                      <span className="trace-badge badge-correction">纠偏</span>
                                      <span className="trace-detail">{t.note}</span>
                                    </div>
                                  );
                                }
                                return null;
                              })}
                              {callEvts.length > 0 && (
                                <details className="trace-node trace-calls" open={callsOpen}>
                                  <summary className="trace-node-summary">
                                    <span className="trace-caret">▼</span>
                                    <span className="trace-label">Calls · {callEvts.length}</span>
                                    <span className="trace-cost">
                                      {fmtMs(callEvts.reduce((s, t) => s + (t.cost_ms ?? 0), 0))}
                                    </span>
                                  </summary>
                                  <div className="trace-node-body">
                                    {callEvts.map((t, ti) => (
                                      <div key={ti} className="trace-call">
                                        <div className="trace-event">
                                          <span className={`trace-badge badge-${t.category ?? 'exec'}`}>
                                            {t.category === 'read' ? '读' : t.category === 'write' ? '写' : '执行'}
                                          </span>
                                          <span className="trace-detail">{t.name}({JSON.stringify(t.args ?? {}).slice(0, 70)})</span>
                                          <span className="trace-cost">{t.cost_ms}ms</span>
                                        </div>
                                        {t.result_preview && (
                                          <details className="trace-result-wrap">
                                            <summary className="trace-result">
                                              {t.result_preview.slice(0, 150)}
                                              {t.result_preview.length > 150 ? ' …(展开全文)' : ''}
                                            </summary>
                                            <pre className="trace-result-full">{escapeHtml(t.result_preview)}</pre>
                                          </details>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </details>
                              )}
                            </div>
                          </details>
                        );
                      })}
                    </div>
                  </details>
                </div>
              </>
            )}
          </div>
        )}

        {sideTab === 'doc' && (
          <div className="side-artifacts">
            <div className="side-doc-section">已生成文件（output/）</div>
            {docFiles.length === 0 ? (
              <div className="empty" style={{ padding: 16 }}>暂无文档——对话中让模型生成 Word/PPT 后会出现在这里。</div>
            ) : (
              docFiles.map((f) => (
                <div key={f.path} className="doc-file-row">
                  <div className="doc-file-name">{f.name}</div>
                  <div className="doc-file-meta">{f.size_kb} KB</div>
                  <div className="doc-file-actions">
                    <button className="tb-btn" onClick={() => void navigator.clipboard.writeText(f.path)}>复制路径</button>
                    <button className="tb-btn" onClick={() => window.open(`file://${f.path}`, '_blank')}>打开</button>
                  </div>
                </div>
              ))
            )}
            <div className="side-doc-section">腾讯 MCP-Doc 工具（{docTools.length}）</div>
            {docTools.map((t) => (
              <div key={t.name} className="doc-tool-row">
                <span className="trace-badge badge-read">{t.name}</span>
                <span className="doc-tool-desc">{t.desc}</span>
              </div>
            ))}
            <div className="empty" style={{ padding: 10, fontSize: 11 }}>
              用法：对话中说"创建一份 Word 文档，标题…"，模型会调用 MCP-Doc 工具生成真实 .docx。
            </div>
          </div>
        )}

        {sideTab === 'artifact' && (
          <div className="side-artifacts">
            {artifacts.length === 0 ? (
              <div className="empty" style={{ padding: 24 }}>
                暂无产物——回复中的代码块会自动提取到这里。
              </div>
            ) : (
              artifacts.map((a, i) => (
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
              ))
            )}
          </div>
        )}

        {sideTab === 'task' && (
          <div className="side-tasks">
            <div className="task-spawn">
              <textarea
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                placeholder="派发后台子代理任务（如：查六个督察局子站最新动态）"
                rows={2}
              />
              <button className="btn" onClick={() => void spawnTask()} disabled={taskSpawnBusy || !taskInput.trim()}>
                {taskSpawnBusy ? '派发中' : '派发'}
              </button>
            </div>
            <div className="task-list">
              {taskAgents.length === 0 ? (
                <div className="empty" style={{ padding: 16 }}>暂无子代理任务——派发一个后台任务，主对话继续提问，完成后自动归档。</div>
              ) : (
                taskAgents.map((a) => (
                  <div
                    key={a.id}
                    className={`task-row${selectedTask === a.id ? ' active' : ''}`}
                    onClick={() => { setSelectedTask(a.id); setTaskDetail(null); }}
                  >
                    <span className={`task-status st-${a.status}`}>{a.status}</span>
                    <span className="task-label">{a.label}</span>
                    <span className="task-dur">{a.duration_ms ? `${(a.duration_ms / 1000).toFixed(0)}s` : ''}</span>
                  </div>
                ))
              )}
            </div>
            {selectedTask && taskDetail && (
              <div className="task-detail">
                <div className="task-detail-head">
                  <span className={`task-status st-${taskDetail.agent.status}`}>{taskDetail.agent.status}</span>
                  <span className="task-label">{taskDetail.agent.label}</span>
                  {(taskDetail.agent.status === 'running' || taskDetail.agent.status === 'pending') && (
                    <button className="tb-btn" onClick={() => { void api.subagentInterrupt(selectedTask); }}>⏹ 中断</button>
                  )}
                </div>
                <div className="task-output">
                  {taskDetail.output.map((o) => (
                    <div key={o.seq} className="task-output-line">
                      {o.kind === 'trace' ? (
                        <span className="task-output-trace">[工具]</span>
                      ) : o.kind === 'done' ? (
                        <div className="task-result" dangerouslySetInnerHTML={{ __html: renderMarkdown(o.result ?? '') }} />
                      ) : (
                        <span className="task-output-status">状态: {o.status ?? o.kind}</span>
                      )}
                    </div>
                  ))}
                  {taskDetail.agent.status === 'failed' && taskDetail.agent.error && (
                    <div className="task-error">失败: {taskDetail.agent.error}</div>
                  )}
                </div>
                {(taskDetail.agent.status === 'done' || taskDetail.agent.status === 'idle') && (
                  <div className="task-followup">
                    <input
                      value={taskFollowup}
                      onChange={(e) => setTaskFollowup(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') void followupTask(selectedTask); }}
                      placeholder="追问这个子代理（续聊）…"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
