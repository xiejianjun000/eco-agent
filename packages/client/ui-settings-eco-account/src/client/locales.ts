/** `settings.ecoAccount` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': '账号与身份',
  'title': '账号与身份',
  'desc': '账号、订阅与用量属于正式应用版的能力。',
  'reserved': '开源自部署版不提供账号体系：没有登录，也没有远端用量。这个分区默认关闭 —— 正式应用版要启用时，把 cordis 配置里这一行的 disabled 去掉即可，其余代码不用改。',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'Account & Identity',
  'title': 'Account & Identity',
  'desc': 'Accounts, subscriptions, and usage belong to the hosted application edition.',
  'reserved': 'The self-hosted open-source edition has no account system: no sign-in, no remote usage. This section ships disabled — enable it for the hosted edition by removing `disabled` from its cordis row; no other code changes.',
}

/** The ecoAccount namespace key union. */
export type AccountKey = keyof typeof zh
