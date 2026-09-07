export type AiTier = 'full' | 'key' | 'query';

export interface AiTierDef {
  id: AiTier;
  name: string;
  desc: string;
}

export const aiTiers: AiTierDef[] = [
  { id: 'full', name: '全面协助', desc: 'AI 自动起草、自动巡检、自动评查初评，我只做确认' },
  { id: 'key', name: '关键协助', desc: 'AI 只做评查初评与法规核验，文书我来自写' },
  { id: 'query', name: '仅查询', desc: 'AI 只回答问题和检索，不动我的文书' },
];

// 细项开关随档位联动：返回各档位下默认开启的细项
export const tierDetails: Record<AiTier, Record<string, boolean>> = {
  full: { draft: true, hosting: true, prereview: true, schedule: true },
  key: { draft: false, hosting: false, prereview: true, schedule: false },
  query: { draft: false, hosting: false, prereview: false, schedule: false },
};

export const detailLabels: { id: string; label: string }[] = [
  { id: 'draft', label: '文书自动起草' },
  { id: 'hosting', label: '平台自动代管' },
  { id: 'prereview', label: '评查自动初评' },
  { id: 'schedule', label: '日历自动排期' },
];

export interface LoginRec {
  time: string;
  ip: string;
  device: string;
}

export const loginRecords: LoginRec[] = [
  { time: '2026-08-08 07:01', ip: '113.88.x.x', device: 'MacBook · Chrome' },
  { time: '2026-08-07 21:43', ip: '113.88.x.x', device: 'iPhone · 飞书' },
  { time: '2026-08-06 09:12', ip: '10.20.x.x', device: '内网终端 · Edge' },
];
