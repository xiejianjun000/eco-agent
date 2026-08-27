import React, { useEffect, useRef, useState } from 'react';
import { streamChat, api, type ChatUsage, type TraceEvent, type SubagentInfo } from '../api';
import { renderMarkdown, escapeHtml } from '../utils/markdown';
import { renderToolResult } from '../utils/toolResult';

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
  suggestions?: string[]; // 后续提问建议（DSH suggest-prompt 对标，点击填入输入框）
  attachments?: { name: string; path: string; size_kb: number }[]; // 用户消息附件（DSH 式 chips）
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

/** 新建会话欢迎主页的快捷提问（DSH hero 对标，点击填入输入框） */
const HERO_SUGGESTIONS = [
  '查冷水江市 2026 年执法数据',
  '解读一条生态环境法规',
  '起草一份现场检查笔录',
];

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
/** 交互图表卡片（DSH visualize 对标）：沙箱 iframe 渲染 ECharts HTML。
 *  sandbox="allow-scripts"（不带 allow-same-origin）：卡片脚本可运行但不具备同源权限，
 *  无法访问父页面/localStorage——模型生成的 HTML 在隔离沙箱内执行。 */
function renderCards(trace: TraceEvent[]): React.ReactElement | null {
  const cards = (trace ?? []).filter((t) => t.type === 'card' && t.html);
  if (cards.length === 0) return null;
  return (
    <div className="card-stack">
      {cards.map((c, i) => (
        <details key={i} className="card-item" open>
          <summary className="card-summary">
            <span className="card-title">📊 {c.title || '图表'}</span>
            <span className="card-hint">可交互 · 沙箱隔离渲染</span>
          </summary>
          <iframe
            className="card-frame"
            sandbox="allow-scripts"
            srcDoc={c.html}
            title={c.title || '图表卡片'}
          />
        </details>
      ))}
    </div>
  );
}

function renderProcessBlock(trace: TraceEvent[]): React.ReactElement | null {
  if (!trace || trace.length === 0) return null;
  const turns = groupTraceByRound(trace);
  const hasProc = trace.some((t) => t.type === 'think' || t.type === 'think_delta' || t.type === 'tool' || t.type === 'tool_start');
  if (!hasProc) return null;
  return (
    <div className="process-block">
      {turns.map((turn) => {
        // 实时思考流（DSH Think 流）：think_delta 分片按序累积；
        // think 事件（服务端清洗后的权威版）覆盖累积值
        const rounds: number[] = [];
        const seen = new Set<number>();
        const live: Record<number, string> = {};
        const thinkEv: Record<number, TraceEvent | undefined> = {};
        for (const ev of turn.events) {
          const r = ev.round ?? turn.round;
          if (!seen.has(r)) { seen.add(r); rounds.push(r); }
          if (ev.type === 'think_delta' && ev.text) live[r] = (live[r] ?? '') + ev.text;
          if (ev.type === 'think') { thinkEv[r] = ev; if (ev.thought) live[r] = ev.thought; }
        }
        return (
          <div key={turn.round} className="process-turn">
            {rounds.map((r) => {
              const te = thinkEv[r];
              const toolStarts = turn.events.filter(
                (t) => t.type === 'tool_start' && (t.round ?? turn.round) === r);
              const toolEvts = turn.events.filter(
                (t) => t.type === 'tool' && (t.round ?? turn.round) === r);
              return (
                <div key={`r${r}`} className="pt-round">
                  {(live[r] || te) && (
                    <details className={`think-item${!te ? ' running' : ''}`} open={!te}>
                      <summary className="think-summary">
                        <span className="pt-caret">▸</span>
                        <span className="think-label">思考 · R{r}</span>
                        {!te && <span className="live-dot" title="正在实时思考" />}
                        {te && te.tools && te.tools.length > 0 && (
                          <span className="think-tools">· {te.tools.join('、')}</span>
                        )}
                        {te && <span className="trace-cost">{fmtMs(te.cost_ms)}</span>}
                      </summary>
                      <div className="think-body">
                        {live[r] ? escapeHtml(live[r]) : '（思考内容未返回）'}
                      </div>
                    </details>
                  )}
                  {toolStarts.map((ts, ti) => {
                    const done = toolEvts.find((t) => t.name === ts.name);
                    const running = !done;
                    return (
                      <details key={ti} className={`call-item${running ? ' running' : ''}`}>
                        <summary className="call-summary">
                          <span className="pt-caret">▸</span>
                          <span className="call-name">{ts.name}</span>
                          <span className="call-args">{fmtArgs(ts.args)}</span>
                          {running && <span className="live-dot" title="执行中" />}
                          {done && <span className="trace-cost">{fmtMs(done.cost_ms)}</span>}
                        </summary>
                        {done && done.result_preview && (
                          <pre className="call-result"
                               dangerouslySetInnerHTML={{ __html: renderToolResult(done.result_preview) }} />
                        )}
                      </details>
                    );
                  })}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

export default function ChatView({ sessionId = 'default', onActivity }: { sessionId?: string; onActivity?: () => void }): React.ReactElement {
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: 'assistant',
      content: '你好，我是 eco Agent——生态环境系统全要素 AI 同事。大气/水/土壤/固废/噪声/辐射/生态/碳全要素，法规、监测、环评、排污许可、执法、督察、应急都能帮上忙。',
      time: fmtClock(),
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState('');
  const [branchTag, setBranchTag] = useState<string | null>(null);
  const [sideTab, setSideTab] = useState<'trace' | 'artifact' | 'doc' | 'task' | 'slot' | 'preview'>('trace');
  const [docFiles, setDocFiles] = useState<{ name: string; path: string; size_kb: number }[]>([]);
  const [docTools, setDocTools] = useState<{ name: string; desc: string }[]>([]);
  // 右侧预览面板：文档生成/上传后自动内嵌打开 docs.qq.com（不弹系统浏览器）
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewTitle, setPreviewTitle] = useState<string>('');
  const sawDocEventRef = useRef(false);
  const contentRef = useRef('');
  // 子代理任务面板（对标 DSH subagent/jobs）
  const [taskAgents, setTaskAgents] = useState<SubagentInfo[]>([]);
  const [taskInput, setTaskInput] = useState('');
  const [taskSpawnBusy, setTaskSpawnBusy] = useState(false);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [taskDetail, setTaskDetail] = useState<{ agent: SubagentInfo; output: { seq: number; kind: string; status?: string; result?: string }[] } | null>(null);
  const [taskFollowup, setTaskFollowup] = useState('');
  // Slot 动态面板（插件注册）
  const [slotPanels, setSlotPanels] = useState<{ id: string; title: string; description: string }[]>([]);
  const [activeSlot, setActiveSlot] = useState<string | null>(null);
  const [slotData, setSlotData] = useState<Record<string, unknown> | null>(null);

  // ── DSH 式右栏：输出产物可收缩 + 左右拖拽调宽 ────────────
  const [panelOpen, setPanelOpen] = useState<boolean>(() => window.localStorage.getItem('eco-panel-open') !== '0');
  const [panelW, setPanelW] = useState<number>(() => {
    const saved = Number(window.localStorage.getItem('eco-panel-w'));
    return Number.isFinite(saved) && saved >= 260 && saved <= 900 ? saved : 340;
  });

  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panelW;
    let w = startW;
    const onMove = (ev: PointerEvent) => {
      // 拖拽条向左 → 面板变宽（面板在右侧，宽度 = 起始 + 左移距离）
      w = Math.min(900, Math.max(260, startW + (startX - ev.clientX)));
      setPanelW(w);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    };
    const onUp = () => {
      window.localStorage.setItem('eco-panel-w', String(w));
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  // ── 输入栏附件 / 语音（DSH 式）────────────────────────────
  const [attachments, setAttachments] = useState<{ name: string; path: string; size_kb: number }[]>([]);
  const [voice, setVoice] = useState<'idle' | 'recording' | 'transcribing'>('idle');
  const [voiceSec, setVoiceSec] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const voiceChunksRef = useRef<Blob[]>([]);
  const voiceTimerRef = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    for (const f of list) {
      try {
        const data = await api.uploadFile(f);
        if (!data.ok || !data.path) throw new Error(data.ok === false ? '上传失败' : '上传失败');
        setAttachments((prev) => [...prev, { name: f.name, path: data.path, size_kb: data.size_kb ?? 0 }]);
      } catch (err) {
        window.alert(`文件上传失败: ${(err as Error).message}`);
      }
    }
  };

  const toggleVoice = async () => {
    if (voice === 'recording') {
      stopRecording();
      return;
    }
    if (voice === 'transcribing') return;
    if (!navigator.mediaDevices?.getUserMedia) {
      window.alert('当前浏览器不支持麦克风录音（需 localhost/HTTPS 环境）');
      return;
    }
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorderRef.current = rec;
      voiceChunksRef.current = [];
      rec.ondataavailable = (ev) => { if (ev.data.size > 0) voiceChunksRef.current.push(ev.data); };
      rec.onstop = () => { stream.getTracks().forEach((t) => t.stop()); void finishVoice(); };
      rec.start();
      setVoice('recording');
      setVoiceSec(0);
      voiceTimerRef.current = window.setInterval(() => setVoiceSec((s) => s + 1), 1000);
    } catch (err) {
      window.alert(`无法访问麦克风: ${(err as Error).message}`);
    }
  };

  const stopRecording = () => {
    if (voiceTimerRef.current !== null) {
      window.clearInterval(voiceTimerRef.current);
      voiceTimerRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop();
  };

  const finishVoice = async () => {
    const chunks = voiceChunksRef.current;
    voiceChunksRef.current = [];
    if (chunks.length === 0) {
      setVoice('idle');
      return;
    }
    const blob = new Blob(chunks, { type: chunks[0].type || 'audio/webm' });
    setVoice('transcribing');
    try {
      const data = await api.transcribeVoice(blob, `voice-${Date.now()}.webm`);
      if (data.ok && data.text) {
        setInput((prev) => (prev ? `${prev}\n${data.text!}` : data.text!));
      } else {
        setVoiceError(data.error || '转写失败（音频已保留在工作区 uploads/）');
      }
    } catch (err) {
      setVoiceError((err as Error).message);
    } finally {
      setVoice('idle');
    }
  };

  React.useEffect(() => {
    import('../api').then(({ api }) => {
      api.documents().then((r) => setDocFiles(r.files)).catch(() => {});
      api.documentTools().then((r) => setDocTools(r.tools)).catch(() => {});
      // 会话恢复：按当前会话（工作区点击的真实 session_id）重放历史
      api.sessionMessages(sessionId).then((r) => {
        if (r.count > 0) {
          const restored = r.messages.map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content, time: fmtClock() }));
          setMessages((prev) => [...prev, ...restored]);
        }
      }).catch(() => {});
      // Slot 面板动态加载
      api.slots().then((r) => setSlotPanels(r.slots)).catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
  const [selectedTrace, setSelectedTrace] = useState<number | null>(null);
  const [turnsOpen, setTurnsOpen] = useState(false);
  const [callsOpen, setCallsOpen] = useState(false);
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

  /** 新会话欢迎态：还没有任何用户消息时显示居中的 hero 主页（DSH 对标） */
  const fresh = messages.length === 1;

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

  const send = async (preset?: string) => {
    const attach = attachments;
    let text = (preset ?? input).trim();
    if (busy) return;
    if (!text && attach.length > 0) text = '请阅读并分析这些附件';
    if (!text) return;
    setInput('');
    setAttachments([]);
    // 附件信息以工作指令形式一并交给模型：模型用 file_read 读取服务器路径分析
    const withAttach =
      attach.length > 0
        ? `${text}\n\n【附件】以下文件已上传到本机服务器（工作区 uploads/ 目录）：\n${attach
            .map((a) => `- ${a.name} → ${a.path}`)
            .join('\n')}\n请先用 file_read 读取附件内容，再结合我的问题分析回答。`
        : text;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const sentAt = fmtClock();
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, time: sentAt, attachments: attach },
      { role: 'assistant', content: '', time: sentAt },
    ]);
    setBusy(true);
    // 新一轮对话：重置文档事件标记与流式内容累积
    sawDocEventRef.current = false;
    contentRef.current = '';
    try {
      await streamChat(withAttach, history, sessionId, model, (delta, meta) => {
        contentRef.current = meta?.reset ? delta : contentRef.current + delta;
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
        // document 事件：文档生成/上传完成 → 自动在右侧预览面板打开
        if (ev.type === 'document' && ev.url) {
          sawDocEventRef.current = true;
          setPreviewUrl(ev.url);
          setPreviewTitle(ev.source && ev.source !== 'final_answer'
            ? `由 ${ev.source} 生成` : '在线文档预览');
          setPanelOpen(true);
          setSideTab('preview');
        }
      }, (meta) => {
        // 兜底：链接只出现在最终回答文本时，从内容里提取 docs.qq.com 链接自动打开
        if (!sawDocEventRef.current) {
          const m = contentRef.current.match(/https:\/\/docs\.qq\.com\/[^\s"'<>()[\]]+/);
          if (m) {
            sawDocEventRef.current = true;
            setPreviewUrl(m[0]);
            setPreviewTitle('在线文档预览');
            setPanelOpen(true);
            setSideTab('preview');
          }
        }
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            durationMs: meta.duration_ms,
            trace: meta.trace ?? last.trace,
            usage: meta.usage ?? last.usage,
            ttftMs: meta.ttft_ms ?? last.ttftMs,
            suggestions: meta.suggestions ?? last.suggestions,
            time: fmtClock(),
          };
          return next;
        });
        // 一轮对话完成 → 通知侧栏刷新会话列表（计数/时间/排序）
        onActivity?.();
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

  /** 消息日志区点击委托：代码块横幅「复制」按钮 + 选项提问按钮（DSH user-questions 行为） */
  const onLogClick = (e: React.MouseEvent) => {
    const opt = (e.target as HTMLElement).closest('.md-option') as HTMLButtonElement | null;
    if (opt) {
      const v = opt.getAttribute('data-opt');
      if (v) setInput(v);
      return;
    }
    const btn = (e.target as HTMLElement).closest('.md-code-copy') as HTMLButtonElement | null;
    if (!btn) return;
    const code = btn.closest('.md-codeblock')?.querySelector('code')?.textContent ?? '';
    void navigator.clipboard
      .writeText(code)
      .then(() => {
        btn.textContent = '已复制';
        window.setTimeout(() => { btn.textContent = '复制'; }, 1200);
      })
      .catch(() => {});
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
        <div className={`chat-log${fresh ? ' hero-mode' : ''}`} ref={logRef} onClick={onLogClick}>
          {fresh ? (
            /* 新建会话欢迎主页（DSH hero 对标）：矢量 logo + Agent 横向居中，下面欢迎语 */
            <div className="hero">
              <div className="hero-head">
                <img className="hero-logo" src="/eco-logo.svg" alt="eco Agent" />
                <span className="hero-title">Agent</span>
              </div>
              <div className="hero-sub">
                最懂生态环境垂直领域的<span className="sub-accent">AI Agent</span>
              </div>
              <div className="hero-chips">
                {HERO_SUGGESTIONS.map((s, i) => (
                  <button key={i} className="suggest-chip" onClick={() => setInput(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-meta">
                <span className="msg-role">{m.role === 'user' ? '你' : 'eco Agent'}</span>
                {m.role === 'user' && m.time && <span className="msg-time">{m.time}</span>}
                {m.role === 'assistant' && m.durationMs !== undefined && (
                  <span className="msg-stat">{fmtStatRow(m)}</span>
                )}
              </div>
              {m.role === 'assistant' && (m.trace?.length ?? 0) > 0 && renderProcessBlock(m.trace!)}
              {m.role === 'assistant' && (m.trace?.length ?? 0) > 0 && renderCards(m.trace!)}
              {m.role === 'assistant' && (m.trace ?? []).some((t) => t.type === 'answer' && t.truncated) && !busy && (
                <button
                  className="tb-btn detail-btn"
                  title="此回答为要点版，点击取完整版（原稿兑现，不重新生成）"
                  onClick={() => void send('详细版')}
                >📄 详细版</button>
              )}
              <div
                className={`bubble${m.role === 'assistant' && !m.content ? ' streaming' : ''}`}
                dangerouslySetInnerHTML={{
                  __html: m.content
                    ? m.role === 'assistant'
                      ? renderMarkdown(m.content)
                      : escapeHtml(m.content).replace(/\n/g, '<br/>')
                    : (busy ? '<span class="thinking">正在思考<span class="dots">…</span></span>' : ''),
                }}
              />
              {m.role === 'user' && (m.attachments?.length ?? 0) > 0 && (
                <div className="attach-chips">
                  {m.attachments!.map((a, ai) => (
                    <span key={ai} className="attach-chip" title={a.path}>
                      📎 {a.name}
                      {a.size_kb > 0 ? ` · ${a.size_kb}KB` : ''}
                    </span>
                  ))}
                </div>
              )}
              {m.role === 'assistant' && !busy && (m.suggestions?.length ?? 0) > 0 && (
                <div className="suggest-row">
                  {m.suggestions!.map((s, si) => (
                    <button
                      key={si}
                      className="suggest-chip"
                      title="点击填入输入框"
                      onClick={() => { setInput(s); }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
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
              {m.role === 'user' && m.content && (
                <div className="msg-toolbar">
                  <button className="tb-btn" title="复制" onClick={() => copyMsg(m)}>⧉ 复制</button>
                </div>
              )}
            </div>
            ))
          )}
        </div>
        {attachments.length > 0 && (
          <div className="attach-row">
            {attachments.map((a, ai) => (
              <span key={ai} className="attach-chip" title={a.path}>
                📎 {a.name}
                <button
                  className="attach-x"
                  title="移除附件"
                  onClick={() => setAttachments((prev) => prev.filter((_, i) => i !== ai))}
                >✕</button>
              </span>
            ))}
          </div>
        )}
        <div className="chat-input-row">
          <div className="input-tools">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files) void uploadFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <button
              className="input-tool-btn"
              title="上传文件——保存到工作区 uploads/，模型会用 file_read 读取分析"
              onClick={() => fileInputRef.current?.click()}
            >📎</button>
            <button
              className={`input-tool-btn${voice === 'recording' ? ' recording' : ''}`}
              title={voice === 'recording' ? '停止录音并转写' : '语音输入——录音后经飞书妙记转写成文字'}
              onClick={() => void toggleVoice()}
            >
              {voice === 'recording' ? '⏹' : '🎤'}
            </button>
          </div>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            rows={2}
          />
          <select
            className="model-select"
            title="选择模型（DSH ui-model-selection）"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="">默认（deepseek-v4-pro）</option>
            <option value="deepseek-chat">deepseek-chat</option>
            <option value="deepseek-v4-pro">deepseek-v4-pro（含Think流·推荐）</option>
            <option value="deepseek-reasoner">deepseek-reasoner（含Think流）</option>
            <option value="deepseek-v4-flash">deepseek-v4-flash</option>
            <option value="doubao-plan">doubao-plan（豆包 Agent Plan·火山方舟）</option>
            <option value="qwen-max">qwen-max</option>
            <option value="claude-sonnet-4-20260514">claude-sonnet-4</option>
          </select>
          <button
            className="btn"
            onClick={() => void send()}
            disabled={busy || (!input.trim() && attachments.length === 0)}
          >
            {busy ? '生成中' : '发送'}
          </button>
        </div>
        {voice === 'recording' && (
          <div className="voice-status">🔴 录音中 {voiceSec}s——再点 🎤 停止并转写</div>
        )}
        {voice === 'transcribing' && (
          <div className="voice-status">⏳ 转写中——飞书妙记正在生成逐字稿（约 20–60 秒）…</div>
        )}
        {voiceError && <div className="voice-status error">{voiceError}</div>}
      </div>

      {/* 右侧「输出产物」面板（DSH Details 栏对标）：可收缩 + 拖拽调宽 */}
      {!panelOpen ? (
        <div className="side-collapsed" title="展开输出产物栏">
          <button className="side-collapsed-btn" onClick={() => setPanelOpen(true)}>◀</button>
          <span className="side-collapsed-label">产物</span>
        </div>
      ) : (
        <>
          <div className="side-resizer" onPointerDown={startResize} title="按住左右拖拽调整宽度" />
          <aside
            className={`side-panel${sideTab === 'preview' ? ' preview-wide' : ''}`}
            style={sideTab === 'preview' ? undefined : { width: panelW }}
          >
            <div className="side-head">
              <span className="side-head-title">输出产物</span>
              <span className="side-head-spacer" />
              <button
                className="side-collapse"
                title="收起输出产物栏"
                onClick={() => setPanelOpen(false)}
              >✕</button>
            </div>
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
            className={`side-tab${sideTab === 'preview' ? ' active' : ''}${previewUrl ? ' has-dot' : ''}`}
            title="文档生成后自动在此内嵌打开（docs.qq.com）"
            onClick={() => setSideTab('preview')}
          >
            预览
          </button>
          <button
            className={`side-tab${sideTab === 'task' ? ' active' : ''}`}
            onClick={() => { setSideTab('task'); refreshTaskList(); }}
          >
            任务{taskAgents.length > 0 ? ` (${taskAgents.length})` : ''}
          </button>
          {slotPanels.map((p) => (
            <button
              key={p.id}
              className={`side-tab${activeSlot === p.id ? ' active' : ''}`}
              title={p.description}
              onClick={() => {
                setSideTab('slot');
                setActiveSlot(p.id);
                setSlotData(null);
                void api.slotData(p.id).then((d) => setSlotData(d)).catch(() => setSlotData({ error: '加载失败' }));
              }}
            >
              {p.title}
            </button>
          ))}
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
                                          <svg className="call-icon" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 3.3a3.8 3.8 0 0 1-4.8 4.8l-5.1 5.1a1.6 1.6 0 1 1-2.3-2.3l5.1-5.1A3.8 3.8 0 0 1 11.7 1l-2.3 2.3 2.3 2.3L14 3.3Z" /></svg>
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

        {sideTab === 'preview' && (
          <div className="preview-panel">
            {previewUrl ? (
              <>
                <div className="preview-toolbar">
                  <span className="preview-title" title={previewUrl}>{previewTitle || '在线文档'}</span>
                  <span className="preview-spacer" />
                  <a className="tb-btn" href={previewUrl} target="_blank" rel="noreferrer"
                     title="若面板内无法显示，在新标签页打开">↗ 新标签页</a>
                  <button className="tb-btn" title="关闭预览"
                          onClick={() => setPreviewUrl(null)}>✕ 关闭</button>
                </div>
                <iframe
                  className="preview-frame"
                  src={previewUrl}
                  title="在线文档预览"
                  allow="clipboard-read; clipboard-write"
                />
                <div className="preview-hint">
                  面板内无法正常显示时点「↗ 新标签页」；文档链接已保留在左侧回复中。
                </div>
              </>
            ) : (
              <div className="empty" style={{ padding: 24 }}>
                暂无预览——让模型「生成分析报告并上传腾讯文档」，
                或对已有文档说「打开 XXX」，完成后会自动在此内嵌打开。
              </div>
            )}
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

        {sideTab === 'slot' && activeSlot && (
          <div className="side-artifacts slot-panel">
            <div className="side-doc-section">{slotPanels.find((p) => p.id === activeSlot)?.title ?? activeSlot}</div>
            {slotData === null ? (
              <div className="empty" style={{ padding: 16 }}>加载中…</div>
            ) : (slotData as { chain?: Record<string, unknown> })?.chain ? (
              /* 审计链面板（govmcp SM3）：结构化渲染（DSH provider 视图语义） */
              <div className="audit-card">
                <div className="row">
                  <span className="title">链完整性</span>
                  <span className={`badge ${(slotData as any).chain.ok ? 'olive' : 'red'}`}>
                    {(slotData as any).chain.ok ? '✅ 完整' : '❌ 断裂'}
                  </span>
                </div>
                <div className="row">
                  <span className="title">链条目</span>
                  <span className="mono">{(slotData as any).chain.entries ?? 0}</span>
                </div>
                <div className="row">
                  <span className="title">尾哈希</span>
                  <span className="mono audit-hash">{String((slotData as any).chain.last_hash ?? '').slice(0, 16)}…</span>
                </div>
                {(slotData as any).stats?.by_operation && (
                  <div className="audit-ops">
                    {Object.entries((slotData as any).stats.by_operation).map(([op, n]) => (
                      <div key={op} className="row">
                        <span className="title">{op}</span>
                        <span className="mono">{String(n)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {(slotData as any).stats?.size_bytes !== undefined && (
                  <div className="muted">
                    体积 {Math.round((slotData as any).stats.size_bytes / 1024)} KB
                  </div>
                )}
              </div>
            ) : (
              <pre className="artifact-code" style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(slotData, null, 2)}
              </pre>
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
        </>
      )}
    </div>
  );
}
