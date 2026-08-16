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
  type: 'think' | 'tool' | 'answer' | 'correction';
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

export const api = {
  health: () => fetch('/healthz').then((r) => r.json()),
  version: () => get<{ version: string }>('/version'),
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
  metrics: () => get<Record<string, unknown>>('/metrics'),
  documents: () => get<{ count: number; files: { name: string; path: string; size_kb: number; modified: number }[] }>('/documents'),
  documentTools: () => get<{ count: number; tools: { name: string; desc: string }[] }>('/documents/tools'),
};

/** POST /api/v1/chat/stream 的 SSE 流式读取，逐块回调（DSH 式实时事件流）。
 * onDelta(text, meta) — meta 首块携带 {ttft_ms}；reset 时以该 delta 替换已追加内容；
 * onEvent(ev) — think/tool/correction 轨迹事件边跑边推（实时过程块）；
 * 结束事件 onDone({duration_ms, usage, ttft_ms, trace})。 */
export async function streamChat(
  message: string,
  history: { role: string; content: string }[],
  onDelta: (text: string, meta?: { ttft_ms?: number; reset?: boolean }) => void,
  onEvent?: (ev: TraceEvent) => void,
  onDone?: (meta: { duration_ms?: number; trace?: TraceEvent[]; usage?: ChatUsage; ttft_ms?: number }) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  });
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
        if (obj.delta) {
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
