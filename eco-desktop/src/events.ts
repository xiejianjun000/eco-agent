// events.ts — ECO AGENT 事件总线（G8 可追溯）
// 所有跨模块通信走统一事件中心

export interface EcoEvent {
  type: string        // 'navigate' | 'open-doc' | 'map-locate' | 'generate' | ...
  source: string      // 来源模块
  payload: any        // 数据
  traceId: string     // 可追溯 ID
  timestamp: number
}

type Handler = (event: EcoEvent) => void

class EventBus {
  private handlers: Map<string, Handler[]> = new Map()
  private log: EcoEvent[] = []

  on(type: string, handler: Handler): () => void {
    if (!this.handlers.has(type)) this.handlers.set(type, [])
    this.handlers.get(type)!.push(handler)
    return () => {
      const hs = this.handlers.get(type) || []
      this.handlers.set(type, hs.filter(h => h !== handler))
    }
  }

  emit(type: string, payload: any = {}, source: string = 'unknown'): EcoEvent {
    const event: EcoEvent = {
      type, payload, source,
      traceId: `trace_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now()
    }
    this.log.push(event)
    if (this.log.length > 200) this.log.shift()

    // 全局分发
    this.handlers.get('*')?.forEach(h => h(event))
    this.handlers.get(type)?.forEach(h => h(event))
    return event
  }

  /** 查询某类型的最近事件（供新模块获取上下文） */
  recent(type?: string): EcoEvent[] {
    if (!type) return [...this.log]
    return this.log.filter(e => e.type === type)
  }
}

export const bus = new EventBus()

// ─── 常用事件类型 ─────────────────────────
export const EVENTS = {
  NAVIGATE: 'navigate',
  OPEN_DOC: 'open-doc',
  MAP_LOCATE: 'map-locate',
  MAP_DRAW: 'map-draw',
  BROWSER_OPEN: 'browser-open',
  GENERATE: 'generate',
  AGENT_STATUS: 'agent-status',
  ARTIFACT_READY: 'artifact-ready',
  EVOLUTION: 'evolution',
  COMMAND: 'command',
} as const
