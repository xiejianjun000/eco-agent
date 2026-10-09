/** `skill` namespace dictionaries for the dedicated tool row. */

/** Dictionary namespace owned by this plugin. */
export const NS = 'skill'

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'row.title': '加载技能',
  'row.running': '正在加载 skill',
  'row.preparing': '准备加载技能',
  'row.failed': 'skill 加载失败',
  'row.stopped': 'skill 加载已中止',
  'row.instructions': '说明',
  'row.inspect': '查看',
  'menu.userOnly': '仅用户',
  'shortcut.label': '技能',
  'shortcut.aria': '打开技能中心面板',
  'panel.title': '技能中心',
  'panel.count': '{count} 个可用技能',
  'panel.listAria': '可用技能清单',
  'panel.noSession': '进入会话后查看当前组合可用的技能',
  'panel.loading': '正在加载技能清单…',
  'panel.empty': '当前组合没有可调用的技能',
  'panel.error': '技能清单加载失败：{message}',
  'card.model': '模型可调用',
  'card.userOnly': '仅用户',
  'card.copy': '复制调用命令',
  'card.copied': '已复制',
  'card.copyAria': '复制 /{name} 调用命令',
  'card.whenToUse': '适用：{whenToUse}',
} satisfies Record<string, string>

/** The skill namespace key union. */
export type SkillKey = keyof typeof zh

/** English dictionary, checked complete against the zh key set. */
export const en = {
  'row.title': 'Skill',
  'row.running': 'Loading skill',
  'row.preparing': 'Preparing to load a skill',
  'row.failed': 'Skill load failed',
  'row.stopped': 'Skill load stopped',
  'row.instructions': 'Instructions',
  'row.inspect': 'Inspect',
  'menu.userOnly': 'user-only',
  'shortcut.label': 'Skills',
  'shortcut.aria': 'Open the skills center panel',
  'panel.title': 'Skills',
  'panel.count': '{count} available skills',
  'panel.listAria': 'Available skills',
  'panel.noSession': 'Enter a session to browse the skills of its composition',
  'panel.loading': 'Loading the skill catalog…',
  'panel.empty': 'No invocable skills in this composition',
  'panel.error': 'Skill catalog failed to load: {message}',
  'card.model': 'model-invocable',
  'card.userOnly': 'user-only',
  'card.copy': 'Copy invoke command',
  'card.copied': 'Copied',
  'card.copyAria': 'Copy the /{name} invoke command',
  'card.whenToUse': 'Use when: {whenToUse}',
} satisfies Record<SkillKey, string>
