/** `settings.ecoMemory` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': '记忆',
  'title': '记忆',
  'desc': '长期记忆：跨会话保留的项目事实与偏好。',
  'loading': '读取中…',
  'unavailable': '当前部署没有接入记忆服务。',
  'unavailableHint': '开源自部署版默认不带记忆后端。没有后端就不摆开关——接入之后这里才会出现可管理的条目。',
  'reset': '清空记忆',
  'import': '导入记忆',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'Memory',
  'title': 'Memory',
  'desc': 'Long-term memory: project facts and preferences kept across sessions.',
  'loading': 'Reading…',
  'unavailable': 'This deployment has no memory service attached.',
  'unavailableHint': 'The self-hosted open-source build ships no memory backend by default. No backend means no switch to fake; entries appear here once one is attached.',
  'reset': 'Clear memory',
  'import': 'Import memory',
}

/** The ecoMemory namespace key union. */
export type MemoryKey = keyof typeof zh
