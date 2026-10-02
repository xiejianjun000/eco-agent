/** `settings.ecoPermission` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': '权限与审批',
  'title': '权限与审批',
  'desc': '新会话创建时采用的默认权限预设。',
  'hint': '这里只影响之后新建的会话；当前会话的权限仍在输入框旁切换。',
  'unavailable': '当前部署没有暴露权限配置，默认权限请在会话输入框旁切换。',
  'loading': '读取中…',
  'readonly': '只读',
  // 描述不重复选项名：选项名已经占了一行，描述只写"它到底允许什么"。
  'preset.readOnly': '不写文件、不执行命令',
  'preset.workspaceWrite': '可在工作区内写文件、执行命令',
  'preset.fullAccess': '不做拦截（风险自负）',
  'preset.auto': '每条高风险操作都问一次（实验性）',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'Permissions & Approval',
  'title': 'Permissions & Approval',
  'desc': 'The default permission preset applied when a new session is created.',
  'hint': 'This only affects sessions created later; the current session still switches permissions beside the composer.',
  'unavailable': 'This deployment exposes no permission configuration; switch permissions beside the composer instead.',
  'loading': 'Reading…',
  'readonly': 'Read-only',
  'preset.readOnly': 'No file writes, no command execution',
  'preset.workspaceWrite': 'Write files and run commands inside the workspace',
  'preset.fullAccess': 'No gating (at your own risk)',
  'preset.auto': 'Ask before every high-risk action (experimental)',
}

/** The ecoPermission namespace key union. */
export type PermissionKey = keyof typeof zh
