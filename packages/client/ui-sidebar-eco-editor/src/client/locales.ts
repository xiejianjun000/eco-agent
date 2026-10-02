/** Editor dictionaries: the save affordance, its honest states, and the read-only reason. */
export const NS = 'sidebarEcoEditor' as const

/** Every editor string key. */
export type EditorKey =
  | 'viewer.title'
  | 'action.save'
  | 'action.reload'
  | 'state.clean'
  | 'state.dirty'
  | 'state.saving'
  | 'state.saved'
  | 'state.conflict'
  | 'state.readonly'
  | 'state.unsupported'
  | 'state.loading'
  | 'error.read'
  | 'error.save'
  | 'hint.shortcut'

export const zh: Record<EditorKey, string> = {
  'viewer.title': '编辑',
  'action.save': '保存',
  'action.reload': '重新加载',
  'state.clean': '已同步',
  'state.dirty': '未保存',
  'state.saving': '保存中…',
  'state.saved': '已保存',
  'state.conflict': '文件已被改动，请重新加载后再保存',
  'state.readonly': '未接入写通道，当前只读',
  'state.unsupported': '这个文件不是工作区文件，无法保存',
  'state.loading': '正在读取…',
  'error.read': '读取失败',
  'error.save': '保存失败',
  'hint.shortcut': '⌘/Ctrl + S 保存',
}

export const en: Record<EditorKey, string> = {
  'viewer.title': 'Edit',
  'action.save': 'Save',
  'action.reload': 'Reload',
  'state.clean': 'In sync',
  'state.dirty': 'Unsaved',
  'state.saving': 'Saving…',
  'state.saved': 'Saved',
  'state.conflict': 'The file changed underneath you — reload before saving',
  'state.readonly': 'No write channel: read-only',
  'state.unsupported': 'Not a workspace file, so it cannot be saved',
  'state.loading': 'Reading…',
  'error.read': 'Read failed',
  'error.save': 'Save failed',
  'hint.shortcut': '⌘/Ctrl + S to save',
}

export const dictionaries = { zh, en }
