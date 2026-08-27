// 平台白名单模板（MVP 仅收「账号+密码+图形验证码」型平台）
// 后端 AI 基座为 Hermes agent：真实接入时由 Hermes 完成地址识别与字段推断，
// 这里先用前端匹配做 0-1 演示（见 PlatformAdd 的 requestHermes 桩）。

export interface LoginFieldLabels {
  username: string;
  password: string;
  captcha: string;
}

export interface WhitelistPlatform {
  id: string;
  name: string;
  url?: string; // 平台地址
  /** 从粘贴地址中识别平台的关键字 */
  keywords: string[];
  /** 人话用途 */
  purpose: string;
  /** 登录壳字段标签（贴合原站语义，EcoAegis 风格渲染） */
  fields: LoginFieldLabels;
  /** 验证码是否由 AI 自动识别：true=AI 已识别态，false=需人工输入态 */
  captchaAuto: boolean;
}

export const WHITELIST: WhitelistPlatform[] = [
  {
    id: 'water',
    name: '水环境非现场执法平台',
    keywords: ['水环境', 'water', 'shui', '非现场'],
    purpose: '查在线监测数据、看企业超标预警',
    fields: { username: '执法账号', password: '登录密码', captcha: '图形验证码' },
    captchaAuto: true,
  },
  {
    id: 'air',
    name: '大气监督帮扶平台',
    keywords: ['大气', 'air', '帮扶', 'daqi'],
    purpose: '看帮扶任务、跟踪整改情况',
    fields: { username: '帮扶账号', password: '登录密码', captcha: '图形验证码' },
    captchaAuto: true,
  },
  {
    id: 'enforce',
    name: '湖南生态环境智慧执法办案系统',
    url: 'https://pwq.sthjt.hunan.gov.cn:8507/zfyth',
    keywords: ['sthjt', 'pwq', 'zfyth', '执法办案', '生态环境', 'hunan'],
    purpose: '查案卷台账、管理执法文书、案件填报',
    fields: { username: '执法账号', password: '登录密码', captcha: '图形验证码' },
    captchaAuto: false,
  },
  {
    id: 'permit',
    name: '排污许可证管理端',
    keywords: ['排污', 'paiwu', 'permit', '许可证'],
    purpose: '管排污许可、企业证照',
    fields: { username: '管理账号', password: '登录密码', captcha: '图形验证码' },
    captchaAuto: true,
  },
  {
    id: 'monitor',
    name: '在线监测系统管理端',
    keywords: ['在线监测', '监测', 'monitor', 'jiance'],
    purpose: '看在线监测数据、排口状态',
    fields: { username: '监测账号', password: '登录密码', captcha: '图形验证码' },
    captchaAuto: true,
  },
  {
    id: 'electricity',
    name: '用电监控系统管理端',
    keywords: ['用电', 'electric', 'dian', '监控'],
    purpose: '看企业用电负荷、异常停产',
    fields: { username: '监控账号', password: '登录密码', captcha: '图形验证码' },
    captchaAuto: false,
  },
];

/** 从粘贴的地址中匹配白名单平台（模拟 Hermes 的地址识别能力）。 */
export function matchPlatform(address: string): WhitelistPlatform | null {
  const a = address.trim().toLowerCase();
  if (!a) return null;
  for (const p of WHITELIST) {
    if (p.keywords.some((k) => a.includes(k.toLowerCase()))) return p;
  }
  return null;
}
