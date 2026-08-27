import { useState, useCallback, useEffect, useRef, useMemo, type ReactNode } from 'react';
import { greeting, quickCommands, type ChatMsg, todos, experts, weekSummary } from '../data/assistant';
import { cases } from '../data/enforcement';
import { platforms } from '../data/platforms';
import { useChatStream } from '../hooks/useBridgeData';
import { IconShield } from './icons';
import { IconPaperclip, IconMic, IconSend } from './icons-extra';

const BRIDGE = import.meta.env.VITE_ECO_BRIDGE ?? 'http://localhost:8787';

interface Props {
  onNavigate: (id: string) => void;
  activeTab: string;
}

type SubTab = 'welcome' | 'tasks' | 'dashboard' | 'expert';

const MODELS = [
  { id: 'deepseek-v4', label: 'DeepSeek-V4', desc: '通用能力最强' },
  { id: 'deepseek-r1', label: 'DeepSeek-R1', desc: '深度推理' },
  { id: 'qwen-max', label: 'Qwen-Max', desc: '中文优化' },
];

const ACTIVE_EXPERTS = experts.filter((e) => e.active).length;

// 数据看板派生指标（统一从数据层取数，避免硬编码漂移）
const PENDING_REVIEW_DOCS = cases.reduce(
  (n, c) => n + Object.values(c.docs).flat().filter((d) => d.status === 'AI草稿待确认').length,
  0,
);
const PLATFORMS_OK = platforms.length - platforms.filter((p) => p.status === 'error').length;

const TAB_WELCOME_TEXTS: Record<SubTab, string> = {
  welcome: `${greeting.hello}，${greeting.name}。${greeting.stats}`,
  tasks: `今日待办事项：${greeting.stats.split('今日待办')[1] || greeting.stats}`,
  dashboard: `数据看板已就绪。${greeting.date}`,
  expert: `AI 专家工作台已激活。${experts.length} 位专家 · ${ACTIVE_EXPERTS} 位正在执行。`,
};

// ==================================================================
// 轻量 Markdown 渲染 — 支持加粗、表格、无序列表、代码块
// ==================================================================

function renderMarkdown(text: string): string {
  // 转义 HTML 防止 XSS
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // 代码块 ```...```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    return `<pre class="md-code"><code>${code.trim()}</code></pre>`;
  });

  // 行内代码 `...`
  html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');

  // 表格（连续 | 分隔的行）
  html = html.replace(/((?:^\|.+\|\s*$[\n\r]*)+)/gm, (block) => {
    const rows = block.trim().split(/\n\r?/).filter((r) => r.includes('|'));
    if (rows.length < 2) return block;
    // 跳过纯分隔行（|---|---|）
    const dataRows = rows.filter((r) => !/^\|[\s\-:|]+\|$/.test(r));
    if (dataRows.length === 0) return block;
    const thead = `<thead><tr>${dataRows[0].split('|').filter(Boolean).map((c) => `<th>${c.trim()}</th>`).join('')}</tr></thead>`;
    const tbody = dataRows.length > 1
      ? `<tbody>${dataRows.slice(1).map((r) => `<tr>${r.split('|').filter(Boolean).map((c) => `<td>${c.trim()}</td>`).join('')}</tr>`).join('')}</tbody>`
      : '';
    return `<table class="md-table">${thead}${tbody}</table>`;
  });

  // 加粗 **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // 无序列表（- / * 开头行）
  html = html.replace(/(?:^|\n)[-*]\s+(.+)/g, '<li>$1</li>');
  html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, '<ul class="md-ul">$1</ul>');

  // 有序列表（1. 2. 开头行）
  html = html.replace(/(?:^|\n)(\d+)\.\s+(.+)/g, '<li>$2</li>');
  // 只包裹连续的 <li>（避免重复包裹）
  html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, (match) => {
    if (match.includes('<ul')) return match;
    return `<ol class="md-ol">${match}</ol>`;
  });

  // 段落：连续双换行 → </p><p>
  html = `<p>${html.replace(/\n{2,}/g, '</p><p>').replace(/\n/g, '<br/>')}</p>`;

  // 清理空段落
  html = html.replace(/<p><\/p>/g, '');

  return html;
}

/** 扁平大拇指图标 */
function IconThumbUp({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3m0 0h11a2 2 0 0 1 2 2v1a1 1 0 0 1-1 1h-2.5M7 11l3-7a2 2 0 0 1 2 2v4" />
    </svg>
  );
}

function IconThumbDown({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3m0 0H6a2 2 0 0 1-2-2v-1a1 1 0 0 1 1-1h2.5M17 13l-3 7a2 2 0 0 1-2-2v-4" />
    </svg>
  );
}

/** 消息内容组件 — 负责 Markdown 渲染 */
function MessageBody({ text }: { text: string }) {
  const html = useMemo(() => renderMarkdown(text), [text]);
  return (
    <div
      className="msg-body"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default function Assistant({ onNavigate, activeTab }: Props): ReactNode {
  const tab = (activeTab as SubTab) || 'welcome';
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState('');
  const [model, setModel] = useState(MODELS[0].id);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatFlowRef = useRef<HTMLDivElement>(null);
  const streamMsgIdRef = useRef<string | null>(null);
  const messagesRef = useRef<ChatMsg[]>([]);
  // 同步 messages 到 ref，供 send 回调读取
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // ── 真实 AI 对话流 ──
  const {
    streamingText,
    isStreaming,
    completedReply,
    model: chatModel,
    tokens,
    error: chatError,
    sendMessage,
  } = useChatStream();

  // 流式文本实时更新最后一条 AI 消息
  useEffect(() => {
    const streamId = streamMsgIdRef.current;
    if (!streamId) return;

    if (chatError) {
      // 连接/流式失败：替换占位气泡，避免永久卡在「AI 分析中...」
      setMessages((m) => m.map((msg) =>
        msg.id === streamId
          ? { ...msg, text: '连接失败，请检查 AI 服务后重试。', cite: `错误：${chatError}` }
          : msg,
      ));
      streamMsgIdRef.current = null;
      return;
    }

    if (isStreaming) {
      setMessages((m) => m.map((msg) =>
        msg.id === streamId
          ? { ...msg, text: streamingText || '思考中...' }
          : msg,
      ));
    } else if (completedReply) {
      const modelLabel = MODELS.find((m) => m.id === model)?.label ?? model;
      setMessages((m) => m.map((msg) =>
        msg.id === streamId
          ? { ...msg, text: completedReply, cite: `模型：${chatModel ?? modelLabel} · ${tokens} tokens` }
          : msg,
      ));
      streamMsgIdRef.current = null;
    }
  }, [streamingText, isStreaming, completedReply, chatError, chatModel, tokens, model]);

  const send = useCallback(() => {
    const text = draft.trim();
    if (!text || isStreaming) return;

    const now = new Date().toISOString();
    const modelLabel = MODELS.find((m) => m.id === model)?.label ?? model;
    const userMsg: ChatMsg = { id: 'u' + Date.now(), who: 'user', text, timestamp: now };
    const streamId = 'a' + Date.now();
    streamMsgIdRef.current = streamId;

    const history = messagesRef.current
      .filter((m) => m.text && m.text.length > 0)
      .slice(-8)
      .map((m) => ({ role: m.who === 'user' ? 'user' : 'assistant', content: m.text }));

    const aiMsg: ChatMsg = {
      id: streamId,
      who: 'ai',
      text: '',
      cite: `模型：${modelLabel} · 连接中...`,
      timestamp: now,
    };

    setMessages((m) => [...m, userMsg, aiMsg]);
    setDraft('');
    setUploadedFile(null);

    sendMessage(text, model, history);
  }, [draft, isStreaming, model, sendMessage]);

  const runQuick = useCallback((cmd: string) => {
    const text = `帮我${cmd}`;
    if (isStreaming) return;
    const now = new Date().toISOString();
    const modelLabel = MODELS.find((m) => m.id === model)?.label ?? model;
    const userMsg: ChatMsg = { id: 'u' + Date.now(), who: 'user', text, timestamp: now };
    const streamId = 'a' + Date.now();
    streamMsgIdRef.current = streamId;
    const history = messagesRef.current
      .filter((m) => m.text && m.text.length > 0)
      .slice(-8)
      .map((m) => ({ role: m.who === 'user' ? 'user' : 'assistant', content: m.text }));
    setMessages((m) => [...m, userMsg, { id: streamId, who: 'ai', text: '', cite: `模型：${modelLabel} · 连接中...`, timestamp: now }]);
    sendMessage(text, model, history);
  }, [isStreaming, model, sendMessage]);

  // 反馈切换 + 后端埋点上报
  const toggleFeedback = useCallback((msgId: string, type: 'like' | 'dislike') => {
    setMessages((m) => {
      const msg = m.find((x) => x.id === msgId);
      if (!msg) return m;
      const newFeedback = msg.feedback === type ? null : type;
      // 异步上报埋点（fire-and-forget，不阻塞 UI）
      fetch(`${BRIDGE}/api/chat/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ msgId, type: newFeedback, msgText: msg.text }),
      }).catch(() => { /* 埋点失败不影响交互 */ });
      return m.map((x) =>
        x.id === msgId ? { ...x, feedback: newFeedback } : x,
      );
    });
  }, []);

  // 复制文本
  const copyText = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
  }, []);

  // 格式化时间
  const fmtTime = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedFile(file.name);
    }
  };

  const handleVoice = () => {
    setIsRecording((v) => !v);
    if (!isRecording) {
      // 模拟语音识别
      setTimeout(() => {
        setIsRecording(false);
        setDraft((prev) => prev + '（语音输入内容）');
      }, 2000);
    }
  };

  const hasMessages = messages.length > 0;

  // ── 欢迎页（仅 welcome 标签 + 无消息时） ──
  if (tab === 'welcome') {
    return (
      <div className="assistant-dialog">
        {!hasMessages && (
          <section className="welcome-hero compact">
            <div className="welcome-shield"><IconShield /></div>
            <h1 className="welcome-greet">{TAB_WELCOME_TEXTS.welcome}</h1>
            <div className="welcome-actions">
              <button className="btn btn-primary" onClick={() => onNavigate('enforcement')}>查看今日待办</button>
              <button className="btn btn-ghost" onClick={() => onNavigate('review')}>打开案卷评查</button>
            </div>
          </section>
        )}
        <section className={`welcome-chat${hasMessages ? ' has-messages' : ''}`}>
          {hasMessages && <div className="welcome-chat-head">与执法助理对话</div>}
          <div className="welcome-chat-flow" ref={chatFlowRef}>
            {messages.map((m) => (
              <div key={m.id} className={`chat-msg ${m.who}`}>
                <div className="msg-bubble-wrap">
                  <div className="bubble">
                    {m.who === 'ai' && m.text ? (
                      <MessageBody text={m.text} />
                    ) : m.text ? (
                      <span>{m.text}</span>
                    ) : (
                      <span className="chat-typing"><span className="spinner" /> AI 分析中...</span>
                    )}
                    {m.text && streamMsgIdRef.current === m.id && <span className="chat-cursor" />}
                    {m.cite && <div className="cite">{m.cite}</div>}
                  </div>
                  {m.who === 'ai' && m.text && (
                    <div className="chat-actions">
                      <span className="chat-time">{fmtTime(m.timestamp)}</span>
                      <button className={`chat-act-btn${m.feedback === 'like' ? ' active' : ''}`} onClick={() => toggleFeedback(m.id, 'like')} title="有用"><IconThumbUp filled={m.feedback === 'like'} /></button>
                      <button className={`chat-act-btn${m.feedback === 'dislike' ? ' active' : ''}`} onClick={() => toggleFeedback(m.id, 'dislike')} title="没用"><IconThumbDown filled={m.feedback === 'dislike'} /></button>
                      <button className="chat-act-btn" onClick={() => copyText(m.text)} title="复制">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="quick-row">
            {quickCommands.map((c) => (
              <button key={c} className="quick-chip" onClick={() => runQuick(c)}>{c}</button>
            ))}
          </div>
        </section>
        {/* 底部输入框 */}
        <div className="welcome-input-bar">
          <div className="model-selector">
            <button className="model-selector-btn" onClick={() => setShowModelMenu((v) => !v)} title="切换大模型">
              {MODELS.find((m) => m.id === model)?.label ?? model}
              <svg width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M1 1l4 4 4-4"/></svg>
            </button>
            {showModelMenu && (
              <div className="model-dropdown">
                {MODELS.map((m) => (
                  <button key={m.id} className={`model-option${model === m.id ? ' selected' : ''}`} onClick={() => { setModel(m.id); setShowModelMenu(false); }}>
                    <span className="model-option-name">{m.label}</span><span className="model-option-desc">{m.desc}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <input ref={fileInputRef} type="file" onChange={handleFileChange} style={{ display: 'none' }} accept=".txt,.doc,.docx,.pdf,.xlsx,.csv,.json" />
          <button className={`input-tool-btn${uploadedFile ? ' has-file' : ''}`} onClick={() => fileInputRef.current?.click()} title="上传文件"><IconPaperclip /></button>
          <button className={`input-tool-btn${isRecording ? ' recording' : ''}`} onClick={handleVoice} title="语音输入"><IconMic /></button>
          <input type="text" value={draft} placeholder={uploadedFile ? `已附加：${uploadedFile}` : '问我：这个案子该怎么走流程 / 帮我起草一份现场检查笔录...'} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} className="welcome-input" />
          <button className="btn btn-primary welcome-send" onClick={send} disabled={!draft.trim() || isStreaming}><IconSend /></button>
        </div>
      </div>
    );
  }

  // ── 今日待办标签 ──
  if (tab === 'tasks') {
    return (
      <div className="assistant-dialog">
        <div className="todo-tab-view">
          <div className="todo-tab-head">
            <h2>今日待办</h2>
            <span className="todo-tab-count">{todos.length} 项</span>
          </div>
          <div className="todo-tab-body">
            {todos.map((t) => (
              <div key={t.id} className="todo-tab-item">
                <span className={`todo-level-dot ${t.level}`} />
                <div className="todo-tab-info">
                  <div className="todo-tab-title">{t.title}</div>
                  <div className="todo-tab-meta">
                    <span className="todo-tab-source">{t.source}</span>
                    <span className={`todo-tab-deadline ${t.level}`}>{t.deadline}</span>
                  </div>
                </div>
                <button className="btn btn-primary btn-sm" onClick={() => onNavigate(t.target)}>去处理</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── 数据看板标签 ──
  if (tab === 'dashboard') {
    return (
      <div className="assistant-dialog">
        <div className="dash-tab-view">
          <h2 className="dash-tab-title">本周数据概览</h2>
          <div className="dash-grid">
            <div className="dash-card">
              <div className="dash-card-v terra">{weekSummary.cases}</div>
              <div className="dash-card-l">本周立案</div>
            </div>
            <div className="dash-card">
              <div className="dash-card-v olive">{weekSummary.passed}</div>
              <div className="dash-card-l">评查通过</div>
            </div>
            <div className="dash-card">
              <div className="dash-card-v red">{weekSummary.veto}</div>
              <div className="dash-card-l">否决拦截</div>
            </div>
            <div className="dash-card">
              <div className="dash-card-v blue">{weekSummary.docs}</div>
              <div className="dash-card-l">文书生成</div>
            </div>
          </div>
          <div className="dash-detail">
            <div className="dash-detail-row">
              <span>案件总数</span>
              <strong>{cases.length}</strong>
            </div>
            <div className="dash-detail-row">
              <span>待审核</span>
              <strong className="amber">{PENDING_REVIEW_DOCS}</strong>
            </div>
            <div className="dash-detail-row">
              <span>平台状态</span>
              <strong className="olive">{PLATFORMS_OK}/{platforms.length} 正常</strong>
            </div>
            <div className="dash-detail-row">
              <span>今日待办完成率</span>
              <strong className="terra">2/6</strong>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── AI 专家标签 ──
  if (tab === 'expert') {
    return (
      <div className="assistant-dialog">
        <div className="expert-tab-view">
          <h2 className="expert-tab-title">AI 专家工作台</h2>
          <p className="expert-tab-sub">{experts.length} 位专家 · {ACTIVE_EXPERTS} 位正在执行</p>
          <div className="expert-tab-grid">
            {experts.map((ex) => (
              <div key={ex.id} className={`expert-tab-card${ex.active ? ' active' : ''}`}>
                <div className="expert-tab-name">{ex.name}</div>
                <div className="expert-tab-role">{ex.role}</div>
                <div className="expert-tab-status">
                  <span className={`expert-dot${ex.active ? ' on' : ''}`} />
                  {ex.status}
                </div>
                <div className="expert-tab-metric">{ex.metric}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
