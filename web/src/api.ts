/**
 * api.ts — eco-server REST/SSE 客户端
 */

const BASE = import.meta.env.VITE_ECO_API ?? '/api/v1';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export interface ChatResp {
  reply: string;
  model: string;
  usage: Record<string, number>;
  duration_ms?: number;
  ttft_ms?: number;
  trace?: TraceEvent[];
}

/** 会话级 token 计量（后端循环累加） */
export interface ChatUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface TraceEvent {
  type: 'think' | 'think_delta' | 'tool_start' | 'tool' | 'answer' | 'correction' | 'document' | 'card' | 'artifact' | 'approval' | 'narration';
  round?: number;
  name?: string;
  category?: 'read' | 'write' | 'exec';
  args?: Record<string, unknown>;
  result_preview?: string;
  cost_ms?: number;
  chars?: number;
  tools?: string[];
  thought?: string;
  note?: string;
  /** think_delta 事件：推理流分片，前端按 round 累积实时渲染（DSH Think 流） */
  text?: string;
  /** document 事件：docs.qq.com 链接，Web 界面右侧「预览」面板内嵌打开 */
  url?: string;
  source?: string;
  /** card 事件：ECharts 图表卡片（沙箱 iframe 渲染） */
  html?: string;
  title?: string;
  /** answer 事件：本回答被要点版截断（前端显示「详细版」按钮） */
  truncated?: boolean;
  /** artifact 事件：完整稿落盘为 MD 产物（点击拉取原文查看） */
  path?: string;
  size?: number;
  /** artifact 事件：对话提到 DOCX/Word 时额外生成的 .docx（WorkBuddy 文档路由对标） */
  docx_path?: string;
  docx_name?: string;
  /** approval 事件：L4 工具触发审批栈，前端渲染「批准/拒绝」授权卡片 */
  request_id?: string;
  status?: string;
}

export interface Skill {
  name: string;
  manifest?: { description?: string; tags?: string[]; version?: string; trust?: string };
  installed_at?: string;
  [key: string]: unknown;
}

export interface MemoryNode {
  id: string;
  type: string;
  title: string;
  score: number;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ToolEntry {
  source: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  approval_required: boolean;
}

/** 子代理摘要/详情（对标 DSH subagent） */
export interface SubagentInfo {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'idle' | 'done' | 'failed' | 'killed';
  parent_id?: string | null;
  created_at: number;
  duration_ms?: number;
  turns?: number;
  usage?: ChatUsage;
  result?: string | null;
  error?: string | null;
  output_seq?: number;
}

export interface GoalInfo {
  id: string;
  objective: string;
  context?: string;
  max_goal_rounds?: number;
  status: string;
  rounds?: number;
  created_at?: number;
  updated_at?: number;
  last_result?: string;
  history?: { time?: number; round?: number; result?: string }[];
  armed?: boolean;
  blocked_reason?: string;
}

export interface SessionOut {
  session_id: string;
  platform: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  /** 会话显示名（重命名后设置，空则用 user_id） */
  name?: string;
}

/** 轨迹 span 树摘要（GET /traces） */
export interface TraceSummary {
  session_id: string;
  trace_id: string;
  meta: Record<string, unknown>;
  span_count: number;
  llm_calls: number;
  tool_calls: number;
  start: number;
  start_iso: string;
  duration_ms?: number | null;
  prompt_tokens: number;
  completion_tokens: number;
}

/** 轨迹 span（GET /traces/{id}，attrs 字符串已被服务端截断到 2000 字符） */
export interface TraceSpan {
  span_id: string;
  parent_id: string | null;
  name: string;
  kind: string; // session | llm_call | tool_call | dag_step ...
  start: number;
  start_iso: string;
  end?: number | null;
  duration_ms?: number | null;
  attrs: Record<string, unknown>;
}

export interface TraceTree {
  session_id: string;
  trace_id: string;
  meta: Record<string, unknown>;
  spans: TraceSpan[];
}

/** LLM 决策时间线条目（decisions.jsonl） */
export interface DecisionItem {
  ts: string;
  hash: string;
  candidate_tools: number;
  selected_tools: string[];
  finish_reason: string;
  prompt_phase: string;
  model: string;
  provider: string;
  round: number;
  trace_id: string;
}

/** 会话检查点摘要 */
export interface CheckpointItem {
  id: number;
  session: string;
  ts: string;
  history_len: number;
  decisions_count: number;
  workspace_slug: string;
  workspace_files: string[];
}

/** LLM 统计聚合（/stats/summary） */
export interface StatsSummary {
  total: { calls: number; errors: number; prompt_tokens: number; completion_tokens: number; total_tokens: number; avg_latency_ms: number; cost_yuan: number };
  by_provider: Record<string, unknown>;
  by_model: { model: string; provider: string; price_per_m: { input: number; output: number; rule: string }; calls: number; errors: number; total_tokens: number; avg_latency_ms: number; cost_yuan: number }[];
  by_date: { date: string; calls: number; errors: number; total_tokens: number; cost_yuan: number }[];
  pricing: { unit: string; default: { input: number; output: number }; models: Record<string, { input: number; output: number }> };
}

/** 定时任务（cron 调度） */
export interface AutomationJob {
  job_id: string;
  cron_expr: string;
  task_desc: string;
  handler_name: string;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
  fail_count: number;
}

/** MCP 连接器 */
export interface ConnectorInfo {
  name: string;
  transport: string;
  url: string;
  has_headers: boolean;
  timeout: number;
  connected: boolean;
  last_error: string;
  tool_count: number;
  tools: string[];
}

export const api = {
  health: () => fetch('/healthz').then((r) => r.json()),
  version: () => get<{ version: string; rev?: string }>('/version'),
  sessions: () => get<SessionOut[]>('/sessions'),
  workspaces: () => get<{ workspaces: { id: string; name: string }[] }>('/workspaces'),
  createWorkspace: (name: string) => post<{ ok: boolean; id: string; name: string }>('/workspaces', { name }),
  createSession: (userName?: string) => post<SessionOut>('/sessions', { user_name: userName ?? '' }),
  renameSession: (sessionId: string, name: string) => patch<SessionOut>(`/sessions/${sessionId}`, { name }),
  deleteSession: (sessionId: string) => del<{ ok: boolean; session_id: string }>(`/sessions/${sessionId}`),
  exportSession: (sessionId: string) =>
    get<{ ok: boolean; path: string; content: string; count: number }>(`/sessions/${sessionId}/export`),
  chat: (message: string, history: { role: string; content: string }[]) =>
    post<ChatResp>('/chat', { message, history }),
  chatStream: (message: string, history: { role: string; content: string }[]) =>
    post<ChatResp>('/chat', { message, history }),
  memoryNodes: (limit = 50) => get<{ nodes: MemoryNode[] }>(`/memory/nodes?limit=${limit}`),
  memoryHot: (limit = 20) => get<{ nodes: MemoryNode[] }>(`/memory/hot?limit=${limit}`),
  memorySearch: (q: string) => get<{ nodes: MemoryNode[] }>(`/memory/search?q=${encodeURIComponent(q)}`),
  memoryStats: () => get<Record<string, unknown>>('/memory/stats'),
  skills: () => get<{ skills: Skill[] }>('/skills'),
  skillsSearch: (q: string) => get<{ skills: Skill[] }>(`/skills/search?q=${encodeURIComponent(q)}`),
  tools: () => get<{ tools: ToolEntry[]; categories: Record<string, number> }>('/tools'),
  system: () => get<Record<string, unknown>>('/system'),
  permissionGate: (enabled: boolean) => post<{ enabled: boolean; note: string }>('/system/permission-gate', { enabled }),
  presets: () => get<{ presets: { id: string; role: string; name: string; files: string[] }[]; count: number }>('/system/presets'),
  metrics: () => get<Record<string, unknown>>('/metrics'),
  documents: () => get<{ count: number; files: { name: string; path: string; size_kb: number; modified: number }[]; artifacts?: { name: string; path: string; size_kb: number; modified: number }[] }>('/documents'),
  documentTools: () => get<{ count: number; tools: { name: string; desc: string }[] }>('/documents/tools'),
  artifact: (name: string) => get<{ name: string; path: string; content: string; size: number }>(`/documents/artifact/${encodeURIComponent(name)}`),
  approvalPending: () => get<{ pending: { id: string; scope: string; detail: unknown; created_ts: string }[]; count: number }>('/approvals/pending'),
  approvalDecide: (id: string, allow: boolean, reason?: string) =>
    post<{ id: string; status: string; allow: boolean }>(`/approvals/${encodeURIComponent(id)}/decide`, { allow, reason: reason ?? '', answerer: 'admin' }),
  subagentSpawn: (body: { message: string; history?: { role: string; content: string }[]; background?: boolean; label?: string }) =>
    post<SubagentInfo>('/subagents', body),
  subagentList: () => get<{ agents: SubagentInfo[]; stats: Record<string, number> }>('/subagents'),
  subagentGet: (id: string, sinceSeq = 0) =>
    get<{ agent: SubagentInfo; output: { seq: number; kind: string; status?: string; result?: string; event?: TraceEvent }[]; seq: number }>(`/subagents/${id}?since_seq=${sinceSeq}`),
  subagentMessage: (id: string, message: string) => post<{ id: string; status: string }>(`/subagents/${id}/message`, { message }),
  subagentInterrupt: (id: string) => post<{ id: string; interrupted: boolean }>(`/subagents/${id}/interrupt`, {}),
  /** 会话消息重放（刷新恢复）：assistant 消息附带轮次级 trace/usage/耗时（server/api/sessions.py） */
  sessionMessages: (sessionId = 'default') =>
    get<{
      session_id: string;
      messages: {
        role: string; content: string;
        trace?: TraceEvent[]; usage?: ChatUsage; duration_ms?: number; ttft_ms?: number;
      }[];
      count: number;
    }>(`/sessions/${sessionId}/messages`),
  /** 观测数据：轨迹 / 决策 / 统计 / 检查点（server/api/traces.py） */
  traces: () => get<{ count: number; items: TraceSummary[] }>('/traces'),
  trace: (sessionId: string) => get<TraceTree>(`/traces/${encodeURIComponent(sessionId)}`),
  decisions: (limit = 50, offset = 0, traceId = '') =>
    get<{ total: number; offset: number; limit: number; items: DecisionItem[] }>(
      `/decisions?limit=${limit}&offset=${offset}${traceId ? `&trace_id=${encodeURIComponent(traceId)}` : ''}`),
  statsSummary: () => get<StatsSummary>('/stats/summary'),
  checkpoints: (session: string) => get<{ session: string; count: number; items: CheckpointItem[] }>(`/checkpoints/${encodeURIComponent(session)}`),
  rewindCheckpoint: (session: string, n: number) =>
    post<{ ok: boolean; checkpoint: CheckpointItem; restored_files: string[]; history: { role: string; content: string }[]; note: string }>(
      `/checkpoints/${encodeURIComponent(session)}/rewind`, { n }),
  slots: () => get<{ slots: { slot: string; id: string; title: string; description: string }[]; stats: Record<string, number> }>('/slots'),
  slotData: (id: string) => get<Record<string, unknown>>(`/slots/${id}/data`),
  goals: () => get<{ goals: GoalInfo[]; stats: Record<string, number> }>('/goals'),
  goalCreate: (body: { objective: string; max_goal_rounds?: number; auto_run?: boolean; context?: string }) =>
    post<GoalInfo>('/goals', body),
  goalAction: (id: string, action: string, body?: { note?: string; reason?: string }) =>
    post<{ ok: boolean; goal?: GoalInfo }>(`/goals/${id}/${action}`, body ?? {}),
  plugins: () => get<{ count: number; plugins: { name: string; status?: string; description?: string; tools?: string[] }[] }>('/plugins'),
  pluginAction: (name: string, action: 'load' | 'unload' | 'reload') =>
    post<Record<string, unknown>>(`/plugins/${name}/${action}`, {}),
  /** 自动任务（cron 定时调度） */
  automationJobs: () => get<{ running: boolean; count: number; jobs: AutomationJob[]; stats: Record<string, unknown> }>('/automation/jobs'),
  /** 任务日志（WorkBuddy memory 面板对标）：近 N 天任务段记忆 */
  taskLog: (days = 7) => get<{ stats: { days: number; files: string[] }; days: number; content: string }>(`/task-log?days=${days}`),
  automationAdd: (body: { description?: string; cron_expr?: string; task_desc?: string }) =>
    post<{ ok: boolean; job_id?: string; error?: string }>('/automation/jobs', body),
  automationRemove: (id: string) => del<{ ok: boolean }>(`/automation/jobs/${encodeURIComponent(id)}`),
  automationRun: (id: string) => post<Record<string, unknown>>(`/automation/jobs/${encodeURIComponent(id)}/run`, {}),
  /** 连接器（MCP） */
  connectors: () => get<{ count: number; connected: number; tool_total: number; connectors: ConnectorInfo[] }>('/connectors'),
  connectorsRefresh: () => post<{ ok: boolean; mcp_count: number; connected: number; connectors: ConnectorInfo[] }>('/connectors/refresh', {}),
  dynplugins: () => get<{ plugins: { plugin_id: string; running: boolean; size_bytes: number; defined_at: number }[]; stats: Record<string, number> }>('/dynplugins'),
  dynpluginDefine: (body: { code: string; name?: string; plugin_id?: string | null }) =>
    post<{ ok: boolean; plugin_id?: string; name?: string; precheck?: { error?: string } }>('/dynplugins/define', body),
  dynpluginRun: (id: string, config?: Record<string, unknown>) =>
    post<Record<string, unknown>>(`/dynplugins/${id}/run`, { config: config ?? {} }),
  dynpluginStop: (id: string) => post<Record<string, unknown>>(`/dynplugins/${id}/stop`, {}),
  dynpluginUndefine: (id: string) => del<{ ok: boolean }>(`/dynplugins/${id}`),
  dynpluginSource: (id: string) => get<{ ok: boolean; source?: string; name?: string; error?: string }>(`/dynplugins/${id}`),
  workflowRun: (script: string, args?: Record<string, unknown>, timeout?: number) =>
    post<{ ok: boolean; result?: unknown; log?: { type: string; title?: string; message?: string; label?: string; chars?: number; error?: string }[]; duration_ms?: number; error?: string }>('/workflow', { script, args: args ?? {}, timeout: timeout ?? 600 }),

  /** 附件上传（multipart）→ 工作区 uploads/，返回模型可读的服务器路径 */
  uploadFile: async (f: File) => {
    const fd = new FormData();
    fd.append('file', f, f.name);
    const res = await fetch(`${BASE}/files`, { method: 'POST', body: fd });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((body as { detail?: string }).detail || `HTTP ${res.status}`);
    return body as { ok: boolean; name: string; path: string; size_kb: number };
  },

  /** 语音转写（multipart 音频 → 飞书妙记逐字稿），可耗时 20–60s */
  transcribeVoice: async (blob: Blob, name: string) => {
    const fd = new FormData();
    fd.append('file', blob, name);
    const res = await fetch(`${BASE}/voice/transcribe`, { method: 'POST', body: fd });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((body as { detail?: string }).detail || `HTTP ${res.status}`);
    return body as { ok: boolean; text?: string; error?: string; audio_path?: string };
  },
};

/** POST /api/v1/chat/stream 的 SSE 流式读取，逐块回调（DSH 式实时事件流）。
 * onDelta(text, meta) — meta 首块携带 {ttft_ms}；reset 时以该 delta 替换已追加内容；
 * onEvent(ev) — think/tool/correction 轨迹事件边跑边推（实时过程块）；
 * 结束事件 onDone({duration_ms, usage, ttft_ms, trace})。 */
export async function streamChat(
  message: string,
  history: { role: string; content: string }[],
  sessionId: string,
  model: string,
  workspace = '',
  onDelta: (text: string, meta?: { ttft_ms?: number; reset?: boolean }) => void,
  onEvent?: (ev: TraceEvent) => void,
  onDone?: (meta: { duration_ms?: number; trace?: TraceEvent[]; usage?: ChatUsage; ttft_ms?: number }) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-ECO-CLIENT': 'web' },
    body: JSON.stringify({ message, history, session_id: sessionId, model, workspace }),
  });
  // HTTP 错误（服务端 500 等）给出明确信息，而非被误读成"连接失败"
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`服务端 HTTP ${res.status}${detail ? `：${detail.slice(0, 200)}` : ''}`);
  }
  if (!res.body) throw new Error('stream body unavailable');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let traceAcc: TraceEvent[] | undefined;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === '[DONE]') return;
      try {
        const obj = JSON.parse(payload) as {
          delta?: string;
          reset?: boolean;
          error?: string;
          done?: boolean;
          trace?: TraceEvent[];
          trace_event?: TraceEvent;
          ttft_ms?: number;
          duration_ms?: number;
          usage?: ChatUsage;
        };
        if (obj.error) throw new Error(obj.error);
        if (obj.done) {
          onDone?.({
            duration_ms: obj.duration_ms,
            trace: obj.trace ?? traceAcc,
            usage: obj.usage,
            ttft_ms: obj.ttft_ms,
          });
          continue;
        }
        if (obj.trace_event) {
          // 实时轨迹事件：缓存 + 即时回调（过程块边跑边渲染）
          traceAcc = [...(traceAcc ?? []), obj.trace_event];
          onEvent?.(obj.trace_event);
          continue;
        }
        if (obj.trace) {
          traceAcc = obj.trace;
          continue;
        }
        // 注意判空方式：撤销草稿的事件是 {"delta": "", "reset": true}，
        // 空字符串是 falsy，写成 if (obj.delta) 会把整个 reset 分支跳过 ——
        // 实测后果是工具间旁白全部堆进最终答案气泡（刷新页面才恢复正常，
        // 因为存储的内容是对的，只有实时渲染没吃掉撤销）。
        if (typeof obj.delta === 'string') {
          onDelta(obj.delta, {
            ttft_ms: obj.ttft_ms,
            reset: obj.reset,
          });
        }
      } catch (e) {
        if ((e as Error).message && payload.startsWith('{')) {
          const obj = JSON.parse(payload) as { error?: string };
          if (obj.error) throw new Error(obj.error);
        }
      }
    }
  }
}
