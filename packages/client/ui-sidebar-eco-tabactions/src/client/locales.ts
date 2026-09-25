/** Locale bundles for the eco right-Sidebar tab content actions. */

/** Locale keys this menu contributes. */
export type TabActionsKey =
  | 'menu.copyPath'
  | 'menu.copyName'
  | 'menu.reveal'
  | 'notice.copied'
  | 'notice.copyFailed'
  | 'notice.revealFailed'
  | 'notice.notAFile'

/** Namespace the dictionaries register under. */
export const NS = 'sidebarEcoTabActions'

/** English copy. */
export const en: Record<TabActionsKey, string> = {
  'menu.copyPath': 'Copy file path',
  'menu.copyName': 'Copy file name',
  'menu.reveal': 'Show in file manager',
  'notice.copied': 'Copied',
  'notice.copyFailed': 'Copy failed',
  'notice.revealFailed': 'Could not open the file manager',
  'notice.notAFile': 'This tab is not a workspace file',
}

/** Simplified Chinese copy. */
export const zh: Record<TabActionsKey, string> = {
  'menu.copyPath': '复制文件路径',
  'menu.copyName': '复制文件名',
  'menu.reveal': '在文件管理器中显示',
  'notice.copied': '已复制',
  'notice.copyFailed': '复制失败',
  'notice.revealFailed': '无法打开文件管理器',
  'notice.notAFile': '这个标签页不是工作区文件',
}
