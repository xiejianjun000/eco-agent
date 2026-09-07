/**
 * useAiReviewStream 单元测试
 * 场景：SSE 连接断开 → 自动重试 → 验证重试次数/错误状态/日志
 *
 * 使用 vi.useFakeTimers() 消除指数退避的真实延迟（2s/4s/8s），
 * 使所有测试在毫秒级完成。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ── mock fetch ──
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// ── mock console（保留真实 error 输出便于调试） ──
const mockLog = vi.fn();
const mockWarn = vi.fn();
const mockError = vi.fn();

// ── SSE 数据构造器 ──
function sseProgress(pct: number, msg: string) {
  return `event: progress\ndata: {"percent":${pct},"message":"${msg}"}\n\n`;
}
function sseUpdate(paraId: string, text: string, author = '文书成') {
  return `event: update\ndata: {"paragraphId":"${paraId}","text":"${text}","aiAuthor":"${author}"}\n\n`;
}
function sseDone(total: number) {
  return `event: done\ndata: {"status":"completed","taskId":"test-task-001","totalSuggestions":${total}}\n\n`;
}
function sseError(msg: string) {
  return `event: error\ndata: {"message":"${msg}"}\n\n`;
}

// ── 创建可手动控制的 SSE Response mock ──
function createSSEResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  const encodedChunks = chunks.map((c) => encoder.encode(c));
  let chunkIndex = 0;
  let cancelled = false;

  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'text/event-stream' }),
    body: {
      getReader() {
        return {
          read: async () => {
            if (cancelled) return { done: true, value: undefined };
            if (chunkIndex < encodedChunks.length) {
              return { done: false, value: encodedChunks[chunkIndex++] };
            }
            return { done: true, value: undefined };
          },
          cancel: () => { cancelled = true; },
          releaseLock: () => {},
        };
      },
    },
  } as unknown as Response;
}

// ═══════════════════════════════════════════════════════════
describe('useAiReviewStream — 重试机制', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetch.mockReset();
    mockLog.mockReset();
    mockWarn.mockReset();
    mockError.mockReset();

    // 替换 console 方法以便验证日志
    vi.stubGlobal('console', {
      ...console,
      log: mockLog,
      warn: mockWarn,
      error: mockError,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  // ═══════ 场景 1：正常 SSE 流式完成 ═══════
  it('正常 SSE 流式完成，status 变为 done，收到所有事件', async () => {
    mockFetch.mockResolvedValueOnce(createSSEResponse([
      sseProgress(10, '加载中'),
      sseProgress(50, '分析中'),
      sseUpdate('p-001', '建议补充完整描述'),
      sseUpdate('p-003', '法律条文引用格式建议调整'),
      sseDone(2),
    ]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'test-doc' });
      // 将所有 pending 的微任务推进完成（mock ReadableStream 的 read() 全部 resolve）
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('done');
    expect(result.current.events.length).toBe(5);
    expect(result.current.progress).toBe(50);

    const updateEvents = result.current.events.filter((e) => e.event === 'update');
    expect(updateEvents.length).toBe(2);
    expect(updateEvents[0].data.paragraphId).toBe('p-001');
  });

  // ═══════ 场景 2：首次连接断开 → 自动重试成功 ═══════
  it('第一次连接抛出 NetworkError 后自动重试第二次成功', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    mockFetch.mockResolvedValueOnce(createSSEResponse([sseDone(1)]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'retry-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    // 第一次尝试失败，状态仍为 streaming
    expect(result.current.status).toBe('streaming');

    // 快进 2s（指数退避第 1 次重试延迟）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // 重试应该已完成
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('done');
    expect(result.current.retryCount).toBe(1);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  // ═══════ 场景 3：HTTP 500 不重试 ═══════
  it('HTTP 500 错误不自动重试，直接置为 error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: new Headers(),
    } as Response);

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'http500-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.retryCount).toBe(0);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  // ═══════ 场景 4：SSE 流返回 error 事件 ═══════
  it('SSE 流返回 error 事件 → lastError 设置正确', async () => {
    mockFetch.mockResolvedValueOnce(createSSEResponse([
      sseProgress(10, '加载中'),
      sseError('AI 引擎超时，请稍后重试'),
    ]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'sse-error-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.lastError).toBe('AI 引擎超时，请稍后重试');
  });

  // ═══════ 场景 5：用户取消 ═══════
  it('用户调用 cancelReview 后停止，status 回到 idle', async () => {
    // 永不 resolve 的 fetch（模拟挂起的连接）
    mockFetch.mockImplementation(() => new Promise<Response>(() => {}));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'cancel-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('streaming');

    await act(async () => {
      result.current.cancelReview();
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('idle');
  });

  // ═══════ 场景 6：ECONNREFUSED 触发重试 ═══════
  it('ECONNREFUSED 错误触发网络重试', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('ECONNREFUSED ::1:8787'));
    mockFetch.mockResolvedValueOnce(createSSEResponse([sseDone(0)]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'econn-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('streaming');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('done');
    expect(result.current.retryCount).toBe(1);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  // ═══════ 场景 7：ERR_CONNECTION 触发重试 ═══════
  it('ERR_CONNECTION_REFUSED 错误触发网络重试', async () => {
    mockFetch.mockRejectedValueOnce(new Error('ERR_CONNECTION_REFUSED'));
    mockFetch.mockResolvedValueOnce(createSSEResponse([sseDone(0)]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'err-conn-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('streaming');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('done');
    expect(result.current.retryCount).toBe(1);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  // ═══════ 场景 8：连续失败重试耗尽 ═══════
  it('连续 4 次连接失败后停止重试，status 为 error', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'exhaust-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    // 初始尝试失败 → 状态 streaming
    expect(result.current.status).toBe('streaming');

    // 第 1 次重试（延迟 2s）→ fetch 失败后立即进入第 2 次
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe('streaming');
    expect(result.current.retryCount).toBeGreaterThanOrEqual(1);

    // 第 2 次重试（延迟 4s）→ 再次失败进入第 3 次
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe('streaming');
    expect(result.current.retryCount).toBeGreaterThanOrEqual(2);

    // 第 3 次重试（延迟 8s）→ 耗尽
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.retryCount).toBe(3);
    expect(result.current.lastError).toContain('Failed to fetch');
    expect(mockFetch).toHaveBeenCalledTimes(4); // 初始 1 + 重试 3
  });

  // ═══════ 场景 9：详细日志打印验证 ═══════
  it('重试时详细日志包含时间戳/错误类型/重试策略', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('NetworkError: connection lost'));
    mockFetch.mockResolvedValueOnce(createSSEResponse([sseDone(0)]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'log-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('done');

    const allLogs = [...mockLog.mock.calls, ...mockWarn.mock.calls, ...mockError.mock.calls].flat();
    const logStr = allLogs.join(' ');

    expect(logStr).toContain('[useAiReviewStream]');
    expect(logStr).toContain('开始 AI 审阅');
    expect(logStr).toContain('NetworkError');
    expect(logStr).toContain('重试');
    expect(logStr).toContain('指数退避');
    // 验证时间戳格式 ISO 8601
    expect(logStr).toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  // ═══════ 场景 10：progress 状态正确更新 ═══════
  it('progress 值随 SSE progress 事件逐步更新到最终值', async () => {
    mockFetch.mockResolvedValueOnce(createSSEResponse([
      sseProgress(10, '加载'),
      sseProgress(40, '分析'),
      sseProgress(85, '整理'),
      sseDone(0),
    ]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'progress-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('done');
    expect(result.current.progress).toBe(85);
  });

  // ═══════ 场景 11：流意外中断（无 done/error 事件）═══
  it('SSE 流未发送 done/error 即关闭 → 标记为流意外结束', async () => {
    mockFetch.mockResolvedValueOnce(createSSEResponse([
      sseProgress(10, '加载中'),
      sseProgress(25, '分析中'),
    ]));

    const mod = await import('./useBridgeData');
    const { result } = renderHook(() => mod.useAiReviewStream());

    await act(async () => {
      result.current.startReview({ docId: 'incomplete-test' });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.lastError).toBe('流意外结束');
  });
});
