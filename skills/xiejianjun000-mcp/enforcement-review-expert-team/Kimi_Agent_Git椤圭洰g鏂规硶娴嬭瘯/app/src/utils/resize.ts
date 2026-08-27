/**
 * 面板拖拽拉扯工具 — clamp + shared hook
 * 方向约定：direction = 1 表示鼠标右移增大面板（右侧手柄），direction = -1 表示鼠标左移增大面板（左侧手柄）
 */

export const PANEL_MIN = 180;
export const PANEL_MAX = 560;

export const NAV_DEFAULT = 232;
export const RP_DEFAULT = 320;

/** 无副作用的宽度截断函数 —— 可单独单元测试 */
export function clampPanelWidth(value: number, min = PANEL_MIN, max = PANEL_MAX): number {
  return Math.min(max, Math.max(min, value));
}

/** 计算拖拽后的新宽度 */
export function computeResize(
  startX: number,
  currentX: number,
  startW: number,
  direction: 1 | -1,
  min = PANEL_MIN,
  max = PANEL_MAX,
): number {
  const delta = (currentX - startX) * direction;
  return clampPanelWidth(startW + delta, min, max);
}

/** 后端埋点日志 — fire-and-forget */
const BRIDGE = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_ECO_BRIDGE)
  || 'http://localhost:8787';

let _logTimer: ReturnType<typeof setTimeout> | null = null;
let _lastLogWidth = 0;

export function logResize(panel: 'left' | 'right', width: number, phase: 'drag' | 'end'): void {
  // 拖拽中节流 300ms
  if (phase === 'drag') {
    if (_logTimer) return;
    _logTimer = setTimeout(() => { _logTimer = null; }, 300);
  }
  // 宽度未变化则跳过（仅 drag 阶段）
  if (phase === 'drag' && width === _lastLogWidth) return;
  _lastLogWidth = width;

  const ts = new Date().toISOString();
  console.info(`[resize] panel=${panel} phase=${phase} width=${width}px ts=${ts}`);

  // 后端上报
  try {
    fetch(`${BRIDGE}/api/resize/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ panel, width, phase, ts }),
    }).catch(() => { /* 静默 */ });
  } catch { /* 静默 */ }
}
