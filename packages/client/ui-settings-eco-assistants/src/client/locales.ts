/** `settings.assistants` namespace dictionaries. */

/** Simplified Chinese dictionary (the key-set source of truth). */
export const zh = {
  'nav': '渠道接入',
  'wechat.title': '微信助手',
  'wechat.desc': '扫码登录个人微信，在手机上跟 eco Agent 聊天。支持白名单、流式回复、定时任务。',
  'wechat.enabled': '启用微信助手',
  'wechat.enabledHint': '开启后由后端自动弹出二维码，用手机微信扫码即可连接。',
  // 运行状态：与 MCP 服务页同一口径 —— 取宿主插件清单的 Fiber 阶段，不猜。
  'wechat.state.running': '运行中',
  'wechat.state.starting': '启动中',
  'wechat.state.failed': '启动失败',
  'wechat.state.stopped': '已关闭',
  'wechat.state.idle': '未加载',
  'wechat.state.absent': '未安装',
  'wechat.state.reading': '读取中…',
  'wechat.state.error': '状态读取失败',
  'feishu.title': '飞书助手',
  'feishu.desc': '连接飞书，在飞书里跟 eco Agent 聊天。',
  'feishu.todo': '飞书助手正在适配中，敬请期待。',
} as const

/** English dictionary, checked complete against the zh key set. */
export const en: Record<keyof typeof zh, string> = {
  'nav': 'Channels',
  'wechat.title': 'WeChat Assistant',
  'wechat.desc': 'Scan to sign in your personal WeChat and chat with eco Agent on your phone. Whitelist, streaming replies, and scheduled tasks included.',
  'wechat.enabled': 'Enable WeChat Assistant',
  'wechat.enabledHint': 'Once enabled, the backend opens a QR code for you to scan with your phone.',
  'wechat.state.running': 'Running',
  'wechat.state.starting': 'Starting',
  'wechat.state.failed': 'Failed to start',
  'wechat.state.stopped': 'Stopped',
  'wechat.state.idle': 'Not loaded',
  'wechat.state.absent': 'Not installed',
  'wechat.state.reading': 'Reading…',
  'wechat.state.error': 'Status read failed',
  'feishu.title': 'Feishu Assistant',
  'feishu.desc': 'Connect Feishu and chat with eco Agent there.',
  'feishu.todo': 'The Feishu assistant is being adapted. Stay tuned.',
}

/** The assistants namespace key union. */
export type AssistantsKey = keyof typeof zh
