/**
 * useBridgeData — EcoAegis 前端 ↔ eco-bridge 数据桥接
 *
 * 对接 eco-bridge 的 REST API 和 SSE 流式端点。
 * 替换原有 mock 数据，实现真实 AI 数据接入。
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { ActiveDoc, Annotation } from '../data/rightpanel';

const BRIDGE = import.meta.env.VITE_ECO_BRIDGE ?? import.meta.env.VITE_BRIDGE_BASE ?? 'http://localhost:8787';

// ── 类型 ──

export interface ReviewStats {
  totalReviewed: number;
  totalTarget: number;
  passRate: number;
  deniedCount: number;
  alerts: { pendingReview: number; nearDeadline: number };
  trend: { weeks: string[]; rates: number[] };
  vetoDist: { category: string; total: number; hit: number }[];
}

export interface GisOperation {
  id: string;
  time: string;
  expert: string;
  description: string;
  canUndo: boolean;
}

export interface HermesMemory {
  totalLearned: number;
  totalRevised: number;
  totalReused: number;
  cards: {
    id: string;
    title: string;
    category: string;
    status?: string;
    summary?: string;
    usageCount?: number;
  }[];
}

export interface AiStreamEvent {
  event: 'progress' | 'update' | 'done' | 'error';
  data: {
    percent?: number;
    message?: string;
    paragraphId?: string;
    text?: string;
    aiMarked?: boolean;
    aiAuthor?: string;
    index?: number;
    total?: number;
    status?: string;
    totalSuggestions?: number;
    taskId?: string;
  };
}

// ── API 函数 ──

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BRIDGE}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${BRIDGE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

// ── 适配器：将 eco-bridge 响应转为前端类型 ──

function _toNum(v: string | number): number {
  if (typeof v === 'number') return v;
  const m = v.match(/\d+/);
  return m ? Number(m[0]) : 0;
}

function adaptOfficeState(raw: Record<string, unknown>): ActiveDoc {
  const ds = (raw.docState ?? raw) as Record<string, unknown>;
  const paragraphs = ((ds.paragraphs as Array<Record<string, unknown>>) ?? []).map((p, i) => ({
    id: _toNum((p.id as string) ?? `p-${i + 1}`),
    text: (p.text as string) ?? '',
    aiModified: (p.aiMarked as boolean) ?? false,
    aiRevision: (p.aiRevision as string) ?? undefined,
    aiExpert: (p.aiAuthor as string) ?? undefined,
  }));

  const annotations: Annotation[] = ((ds.annotations as Array<Record<string, unknown>>) ?? []).map((a) => ({
    id: (a.id as string) ?? '',
    author: ((a.author as Record<string, unknown>)?.displayName as string) ?? (a.author as string) ?? '未知',
    role: ((a.author as Record<string, unknown>)?.role as 'ai' | 'human') ?? ((a.role as 'ai' | 'human') ?? 'ai'),
    content: (a.content as string) ?? '',
    time: (a.createdAt as string)?.slice(11, 16) ?? '',
    resolved: (a.resolved as boolean) ?? false,
    replies: ((a.replies as Array<Record<string, unknown>>) ?? []).map((r) => ({
      author: ((r.author as Record<string, unknown>)?.displayName as string) ?? (r.author as string) ?? '',
      role: ((r.author as Record<string, unknown>)?.role as 'ai' | 'human') ?? 'ai',
      content: (r.content as string) ?? '',
      time: (r.createdAt as string)?.slice(11, 16) ?? '',
    })),
  }));

  return {
    id: (ds.docId as string) ?? '',
    name: (ds.fileName as string) ?? '未命名.docx',
    format: (ds.format as ActiveDoc['format']) ?? 'docx',
    status: ((ds.status as string) ?? 'editing') as ActiveDoc['status'],
    templateId: (ds.templateId as number) ?? 38,
    paragraphs,
    annotations,
    synced: (ds.aiSync as Record<string, unknown>)?.status === 'idle',
  };
}

// ── Hooks ──

/** 获取文书协同状态 */
export function useOfficeState(docId: string) {
  const [data, setData] = useState<ActiveDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchState = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const raw = await getJSON<Record<string, unknown>>(
        `/api/office/state?docId=${encodeURIComponent(docId)}`,
      );
      setData(adaptOfficeState(raw));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => { fetchState(); }, [fetchState]);

  return { data, loading, error, refetch: fetchState };
}

/** 获取评查看板数据 */
export function useReviewStats() {
  const [data, setData] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getJSON<ReviewStats>('/api/office/review-stats')
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { data, loading };
}

/** 获取 Hermes 记忆进化数据 */
export function useHermesMemory() {
  const [data, setData] = useState<HermesMemory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getJSON<HermesMemory>('/api/hermes/memory')
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { data, loading };
}

/** 获取 GIS 最近操作 */
export function useGisOperations() {
  const [data, setData] = useState<GisOperation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getJSON<{ operations: GisOperation[] }>('/api/gis/latest?limit=10')
      .then((d) => setData(d.operations ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { data, loading };
}

/** 提交协同编辑同步 */
export function useOfficeSync() {
  const [syncing, setSyncing] = useState(false);

  const sync = useCallback(async (params: {
    docId: string;
    expectedVersion: number;
    action?: string;
    paragraphId?: string;
    text?: string;
  }) => {
    setSyncing(true);
    try {
      const res = await postJSON<{ ok: boolean; version: number }>('/api/office/sync', params);
      setSyncing(false);
      return res;
    } catch (e) {
      setSyncing(false);
      throw e;
    }
  }, []);

  return { sync, syncing };
}

/** SSE 流式 AI 审阅 — 含自动重试机制和详细日志 */
const MAX_RETRIES = 3;
const RETRY_BASE_MS = 2000;

const LOG_PREFIX = '[useAiReviewStream]';

function log(level: 'info' | 'warn' | 'error', msg: string, detail?: unknown) {
  const ts = new Date().toISOString();
  const parts = [`${LOG_PREFIX} [${ts}] [${level.toUpperCase()}] ${msg}`];
  if (detail !== undefined) parts.push(JSON.stringify(detail, null, 2));
  const line = parts.join('\n');
  switch (level) {
    case 'error': console.error(line); break;
    case 'warn': console.warn(line); break;
    default: console.log(line); break;
  }
}

export function useAiReviewStream() {
  const [events, setEvents] = useState<AiStreamEvent[]>([]);
  const [status, setStatus] = useState<'idle' | 'streaming' | 'done' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [retryCount, setRetryCount] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const paramsRef = useRef<{ docId: string; reviewType?: string } | null>(null);
  const streamStartRef = useRef<string | null>(null);

  /** 核心 SSE 读取循环 — 详细日志版 */
  const readSSEStream = useCallback(async (
    res: Response,
    onEvent: (ev: AiStreamEvent) => void,
  ): Promise<void> => {
    const reader = res.body?.getReader();
    if (!reader) throw new Error('No readable stream');

    const decoder = new TextDecoder();
    let buffer = '';
    let eventCount = 0;
    const streamStart = performance.now();
    let lastEventTime = streamStart;

    log('info', 'SSE 流开始读取', {
      contentType: res.headers.get('content-type'),
      status: res.status,
      contentLength: res.headers.get('content-length') ?? 'chunked',
    });

    while (true) {
      const readStart = performance.now();
      const { done, value } = await reader.read();
      const readCost = (performance.now() - readStart).toFixed(1);

      if (done) {
        const totalCost = (performance.now() - streamStart).toFixed(1);
        log('info', `SSE 流结束`, {
          totalEvents: eventCount,
          totalDuration: `${totalCost}ms`,
          avgPerEvent: eventCount > 0 ? `${(parseFloat(totalCost) / eventCount).toFixed(1)}ms` : 'N/A',
        });
        break;
      }

      const decodeStart = performance.now();
      buffer += decoder.decode(value, { stream: true });
      const decodeCost = (performance.now() - decodeStart).toFixed(1);

      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      let currentEvent = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            eventCount++;

            const now = performance.now();
            const elapsed = (now - streamStart).toFixed(1);
            const sincePrev = (now - lastEventTime).toFixed(1);
            lastEventTime = now;

            // 按事件类型抽取关键字段做摘要
            const summary: Record<string, unknown> = {};
            switch (currentEvent) {
              case 'progress':
                summary.percent = data.percent;
                summary.message = data.message;
                break;
              case 'update':
                summary.paragraphId = data.paragraphId;
                summary.author = data.aiAuthor;
                summary.textLen = data.text?.length ?? 0;
                summary.textPreview = typeof data.text === 'string'
                  ? data.text.slice(0, 40) + (data.text.length > 40 ? '…' : '')
                  : undefined;
                break;
              case 'done':
                summary.totalSuggestions = data.totalSuggestions;
                summary.taskId = data.taskId;
                break;
              case 'error':
                summary.message = data.message;
                break;
              default:
                summary.keys = Object.keys(data);
            }

            log('info', `SSE 事件 #${eventCount} [${currentEvent}]`, {
              seq: eventCount,
              event: currentEvent,
              elapsedMs: `${elapsed}ms`,
              sincePrevMs: `${sincePrev}ms`,
              chunkReadMs: `${readCost}ms`,
              chunkDecodeMs: `${decodeCost}ms`,
              content: summary,
            });

            onEvent({
              event: currentEvent as AiStreamEvent['event'],
              data,
            });
          } catch {
            log('warn', `SSE 解析失败`, { line: line.slice(0, 100) });
          }
        }
      }
    }
  }, []);

  /** 发起或重试 SSE 流 */
  const startReview = useCallback(async (params: { docId: string; reviewType?: string }) => {
    paramsRef.current = params;
    setStatus('streaming');
    setEvents([]);
    setProgress(0);
    setRetryCount(0);
    setLastError(null);
    streamStartRef.current = new Date().toISOString();

    log('info', '开始 AI 审阅', { ...params, bridge: BRIDGE });

    const controller = new AbortController();
    abortRef.current = controller;

    const attemptConnect = async (attempt: number): Promise<void> => {
      const attemptStart = new Date().toISOString();

      if (attempt > 0) {
        // 重试前等待（指数退避）
        const delay = RETRY_BASE_MS * Math.pow(2, attempt - 1);
        log('warn', `第 ${attempt}/${MAX_RETRIES} 次重试`, {
          retryDelay: `${delay}ms (${delay / 1000}s)`,
          strategy: '指数退避',
          docId: params.docId,
          previousAttemptStart: attemptStart,
        });
        setRetryCount(attempt);
        setLastError(`连接断开，${delay / 1000}s 后重试 (${attempt}/${MAX_RETRIES})...`);
        await new Promise((r) => setTimeout(r, delay));

        if (controller.signal.aborted) {
          log('info', '重试被用户取消', { attempt });
          return;
        }
      }

      try {
        log('info', `尝试连接 (第 ${attempt + 1} 次)`, { attemptStart, url: `${BRIDGE}/api/stream/ai-review` });
        const res = await fetch(`${BRIDGE}/api/stream/ai-review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
          signal: controller.signal,
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        await readSSEStream(res, (ev) => {
          if (controller.signal.aborted) return;

          setEvents((prev) => [...prev, ev]);
          if (ev.event === 'progress' && ev.data.percent) {
            setProgress(ev.data.percent);
            log('info', `审阅进度 ${ev.data.percent}%`, { message: ev.data.message });
          }
          if (ev.event === 'update') {
            log('info', '收到 AI 建议', { paragraphId: ev.data.paragraphId, author: ev.data.aiAuthor });
          }
          if (ev.event === 'done') {
            const elapsed = streamStartRef.current
              ? `${((Date.now() - new Date(streamStartRef.current).getTime()) / 1000).toFixed(1)}s`
              : '?';
            log('info', `AI 审阅完成`, {
              totalSuggestions: ev.data.totalSuggestions,
              taskId: ev.data.taskId,
              totalElapsed: elapsed,
            });
            setStatus('done');
            setLastError(null);
          }
          if (ev.event === 'error') {
            log('error', 'AI 审阅服务端错误', { message: ev.data.message, taskId: ev.data.taskId });
            setLastError(ev.data.message ?? '未知错误');
            setStatus('error');
          }
        });

        // 流自然结束但没收到 done 事件 — 可能是不完整
        setStatus((prev) => {
          if (prev !== 'done' && prev !== 'error') {
            log('warn', '流意外结束（未收到 done/error 事件）');
            setLastError('流意外结束');
            return 'error';
          }
          return prev;
        });

      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          log('info', '连接被用户中止');
          return;
        }

        const errMsg = (e as Error).message;
        const errType = (e as Error).name || 'UnknownError';

        const isNetworkError = (e as TypeError).message?.includes('fetch') ||
          errMsg.includes('Failed') ||
          errMsg.includes('NetworkError') ||
          errMsg.includes('ECONNREFUSED') ||
          errMsg.includes('ERR_CONNECTION');

        log(isNetworkError ? 'error' : 'error', `连接失败: ${errType}`, {
          errorMessage: errMsg,
          isNetworkError,
          attempt,
          maxRetries: MAX_RETRIES,
          timestamp: new Date().toISOString(),
        });

        if (isNetworkError && attempt < MAX_RETRIES && !controller.signal.aborted) {
          // 网络错误 — 自动重试
          return attemptConnect(attempt + 1);
        }

        setLastError(errMsg);
        setStatus('error');
      }
    };

    attemptConnect(0);
  }, [readSSEStream]);

  const cancelReview = useCallback(() => {
    log('info', '用户取消审阅');
    abortRef.current?.abort();
    setStatus('idle');
  }, []);

  return { events, status, progress, retryCount, lastError, startReview, cancelReview };
}

/* ═══════════════════════════════════════════════
   useChatStream — AI 对话流式 Hook
   ═══════════════════════════════════════════════ */

export interface ChatStreamState {
  /** 流式接收中的文本（逐字累积） */
  streamingText: string;
  /** 是否正在接收 */
  isStreaming: boolean;
  /** 完成后的完整回复 */
  completedReply: string | null;
  /** 使用的模型 */
  model: string | null;
  /** 估算 token 数 */
  tokens: number;
  /** 错误信息 */
  error: string | null;
}

export function useChatStream() {
  const [state, setState] = useState<ChatStreamState>({
    streamingText: '',
    isStreaming: false,
    completedReply: null,
    model: null,
    tokens: 0,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (message: string, modelId: string, history: { role: string; content: string }[]) => {
    // 取消上一个请求
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({
      streamingText: '',
      isStreaming: true,
      completedReply: null,
      model: modelId,
      tokens: 0,
      error: null,
    });

    try {
      const res = await fetch(`${BRIDGE}/api/stream/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, model: modelId, history }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`Chat API 返回 ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No readable stream');

      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';
      let doneModel: string | null = null;
      let doneTokens = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (currentEvent === 'chunk') {
                fullText += data.text ?? '';
                setState((s) => ({ ...s, streamingText: fullText }));
              } else if (currentEvent === 'done') {
                doneModel = data.model;
                doneTokens = data.tokens;
              }
            } catch { /* skip */ }
          }
        }
      }

      setState({
        streamingText: fullText,
        isStreaming: false,
        completedReply: fullText,
        model: doneModel ?? modelId,
        tokens: doneTokens,
        error: null,
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setState({
          streamingText: '',
          isStreaming: false,
          completedReply: null,
          model: null,
          tokens: 0,
          error: null,
        });
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      setState((s) => ({ ...s, isStreaming: false, error: msg }));
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => ({ ...s, isStreaming: false }));
  }, []);

  return { ...state, sendMessage, cancel };
}
