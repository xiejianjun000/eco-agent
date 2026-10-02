/** `settings.ecoDiagnostics` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': '数据与诊断',
  'title': '运行时健康',
  'desc': '宿主插件与浏览器侧模块的真实统计，不做估算。',
  'loading': '读取中…',
  'error': '读取失败',
  'retry': '重新读取',
  'refresh': '刷新',
  'total': '插件总数',
  'enabled': '已启用',
  'active': '活跃',
  'failed': '失败',
  'failedList': '失败条目',
  'clientTitle': '浏览器模块',
  'clientDesc': '浏览器侧插件包的加载结果；失败的包会列出包名与原因。',
  'clientSyncing': '同步中…',
  'clientOk': '全部加载正常',
  'resync': '重新同步',
  'exportTitle': '会话日志',
  'exportDesc': '在会话里输入 /export 导出当前会话日志（含工具调用与产物）。',
  'archiveTitle': '归档会话',
  'archiveDesc': '归档会话的恢复在「归档会话」分区，这里不重复入口。',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'Data & Diagnostics',
  'title': 'Runtime Health',
  'desc': 'Honest counts of host plugins and browser modules; nothing estimated.',
  'loading': 'Reading…',
  'error': 'Read failed',
  'retry': 'Retry',
  'refresh': 'Refresh',
  'total': 'Total plugins',
  'enabled': 'Enabled',
  'active': 'Active',
  'failed': 'Failed',
  'failedList': 'Failed entries',
  'clientTitle': 'Browser modules',
  'clientDesc': 'Load results of the browser-side plugin bundles; failures list the package and the reason.',
  'clientSyncing': 'Syncing…',
  'clientOk': 'All loaded',
  'resync': 'Resync',
  'exportTitle': 'Session log',
  'exportDesc': 'Run /export in a session to export its log (tool calls and deliverables included).',
  'archiveTitle': 'Archived sessions',
  'archiveDesc': 'Restoring archived sessions lives in the Archived sessions section; no duplicate entry here.',
}

/** The ecoDiagnostics namespace key union. */
export type DiagnosticsKey = keyof typeof zh
