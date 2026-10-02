/** `settings.ecoMcp` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': 'MCP 服务',
  'title': 'MCP 服务',
  'desc': 'MCP 服务的真实运行状态，读自运行时的插件清单。',
  'hint': '状态取自运行时的 Fiber 阶段，不做探测也不做推测；服务接在哪（本机进程还是远程端点）由部署配置决定，本页按提供它的包标注，不猜地址。',
  'loading': '读取中…',
  'empty': '当前部署没有配置 MCP 服务。',
  'error': '读取失败',
  'retry': '重新读取',
  'refresh': '刷新',
  'state.active': '已连接',
  'state.failed': '连接失败',
  'state.pending': '等待中',
  'state.loading': '连接中',
  'state.unloading': '断开中',
  'state.idle': '未加载',
  'state.disabled': '已禁用',
  // 行的"出身"：dsh-mcp-client 连的是外部服务（stdio 子进程或远程 HTTP），
  // dsh-mcp-resources 是本机自带的资源服务。按包名判定，不猜端点。
  'kind.external': '外部服务',
  'kind.local': '本机服务',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'MCP Services',
  'title': 'MCP Services',
  'desc': 'Live status of MCP services, read from the runtime plugin inventory.',
  'hint': 'Status comes from the runtime Fiber phase: no probing, no guessing. Where a service lives (a local process or a remote endpoint) is deployment config this page does not read; the badge follows the package that provides it.',
  'loading': 'Reading…',
  'empty': 'No MCP service is configured in this deployment.',
  'error': 'Read failed',
  'retry': 'Retry',
  'refresh': 'Refresh',
  'state.active': 'Connected',
  'state.failed': 'Failed',
  'state.pending': 'Pending',
  'state.loading': 'Connecting',
  'state.unloading': 'Disconnecting',
  'state.idle': 'Not loaded',
  'state.disabled': 'Disabled',
  'kind.external': 'External',
  'kind.local': 'Local',
}

/** The ecoMcp namespace key union. */
export type McpKey = keyof typeof zh
