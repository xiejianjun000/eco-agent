// 平台管理模块数据 —— 锚定 design/platforms.md
export type PlatformStatus = 'managed' | 'pending' | 'configuring' | 'error';

export interface KeyRow {
  label: string;
  value: string;
  alert?: boolean;
}

export interface Platform {
  id: string;
  name: string;
  purpose: string; // 人话用途
  url?: string; // 平台地址（新入驻时保存）
  status: PlatformStatus;
  rows: KeyRow[];
  progress?: number; // 接入配置中
  notice?: string; // 置顶提示条
}

export const platforms: Platform[] = [
  {
    id: 'water',
    name: '水环境非现场执法平台',
    purpose: '查在线监测数据、看企业超标',
    status: 'managed',
    rows: [
      { label: '最近同步', value: '08:40' },
      { label: '今日抓取预警', value: '14 条' },
      { label: '异常数', value: '0' },
    ],
  },
  {
    id: 'air',
    name: '大气监督帮扶平台',
    purpose: '帮扶任务下发、夏季大气监督',
    status: 'managed',
    rows: [
      { label: '首次登录', value: '已完成' },
      { label: '本周帮扶任务', value: '3 项' },
      { label: '异常数', value: '0' },
    ],
  },
  {
    id: 'enforce',
    name: '湖南生态环境智慧执法办案系统',
    purpose: '案卷台账、文书管理、案件填报',
    url: 'https://pwq.sthjt.hunan.gov.cn:8507/zfyth',
    status: 'managed',
    rows: [
      { label: '案卷总数', value: '69 卷' },
      { label: '文书总数', value: '74 份' },
      { label: '最近同步', value: '刚刚' },
      { label: '异常数', value: '0' },
    ],
  },
  {
    id: 'permit',
    name: '排污许可证管理端',
    purpose: '企业排污许可证照管理',
    status: 'configuring',
    progress: 60,
    notice: '接通后企业证照自动更新到企业画像库',
    rows: [
      { label: '配置进度', value: '60%' },
      { label: '接通后', value: '证照自动更新' },
    ],
  },
  {
    id: 'monitor',
    name: '在线监测系统管理端',
    purpose: '污染源在线监测数据管理',
    status: 'pending',
    rows: [
      { label: '最近同步', value: '—' },
      { label: '状态', value: '待登录' },
    ],
  },
  {
    id: 'electricity',
    name: '用电监控系统管理端',
    purpose: '企业用电工况监控',
    status: 'configuring',
    progress: 35,
    rows: [
      { label: '配置进度', value: '35%' },
      { label: '接通后', value: '用电数据入画像' },
    ],
  },
];

export const STATUS_META: Record<PlatformStatus, { label: string; cls: string }> = {
  managed: { label: 'AI 代管中', cls: 'olive' },
  pending: { label: '待人工首次登录', cls: 'amber' },
  configuring: { label: '接入配置中', cls: 'blue' },
  error: { label: '异常', cls: 'red' },
};
