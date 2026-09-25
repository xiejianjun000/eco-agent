/** `settings.ecoAbout` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': '帮助与关于',
  'title': '关于 eco Agent',
  'desc': '最懂生态环境领域各个要素的 AI agent —— 水、大气、土壤、固废与化学品、核与辐射、环评、排污许可、监测、自然生态、海洋、气候变化、督察。',
  'edition': '开源自部署版',
  'editionDesc': '当前是自部署的开源版本，没有账号体系；所有数据留在本机。',
  'links': '资源',
  'repo': '代码仓库（GitHub）',
  'repoDesc': '源码、构建与二次开发说明。',
  'issues': '反馈与问题',
  'issuesDesc': '提 bug、提需求都在这里。',
  'docs': '使用文档',
  'docsDesc': '安装、配置与能力说明。',
  'versionHint': '版本号见仓库 Releases —— 页面不猜版本，猜错不如不写。',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'Help & About',
  'title': 'About eco Agent',
  'desc': 'The AI agent that knows every element of the ecological environment domain — water, air, soil, solid waste & chemicals, nuclear & radiation, EIA, discharge permits, monitoring, natural ecology, oceans, climate, inspection.',
  'edition': 'Self-hosted open-source edition',
  'editionDesc': 'This is the self-hosted open-source build: no account system, all data stays on this machine.',
  'links': 'Resources',
  'repo': 'Repository (GitHub)',
  'repoDesc': 'Source, build, and customization notes.',
  'issues': 'Feedback & issues',
  'issuesDesc': 'Report bugs and request features here.',
  'docs': 'Documentation',
  'docsDesc': 'Installation, configuration, and capabilities.',
  'versionHint': 'Find the version in the repository Releases — the page does not guess it; a wrong guess is worse than none.',
}

/** The ecoAbout namespace key union. */
export type AboutKey = keyof typeof zh
