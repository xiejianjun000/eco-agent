/**
 * 上下文用量共享 store —— 让右栏（SidePanel）能读取当前会话的 context_usage 环数据。
 * ChatView 在收到后端 context_usage 事件时写入；SidePanel 订阅并渲染环形进度。
 * 与 WorkBuddy 的 ContextUsageDisplay 同构（used/max + conv/tool/sp/mcp/skill 五类）。
 */

export interface ContextUsageData {
  used: number;
  max: number;
  percent: number;
  conv: number;
  tool: number;
  sp: number;
  mcp: number;
  skill: number;
}

type Listener = (d: ContextUsageData | null) => void;

let current: ContextUsageData | null = null;
const listeners = new Set<Listener>();

/** ChatView 收到 context_usage 事件时调用 */
export function setContextUsage(d: ContextUsageData | null): void {
  current = d;
  listeners.forEach((l) => l(d));
}

export function getContextUsage(): ContextUsageData | null {
  return current;
}

/** SidePanel 订阅实时更新；返回取消订阅函数 */
export function subscribeContextUsage(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
