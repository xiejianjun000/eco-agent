// 工作日历 mock 数据 —— 锚定 design/calendar.md

export type CalType = 'enforce' | 'review' | 'supervise' | 'inspect' | 'deliver' | 'law';

export interface CalTypeMeta {
  key: CalType;
  label: string;
  color: string; // 浅底
  text: string; // 深字
  dot: string; // 圆点/标识色
}

export const calTypes: Record<CalType, CalTypeMeta> = {
  enforce: { key: 'enforce', label: '执法检查', color: '#F6E7D8', text: '#9A5A2C', dot: '#C97C3E' },
  review: { key: 'review', label: '案卷评查', color: '#E7ECF1', text: '#4E6378', dot: '#6E8299' },
  supervise: { key: 'supervise', label: '督察复查', color: '#EDF0E6', text: '#5C6B43', dot: '#7C8B5F' },
  inspect: { key: 'inspect', label: '平台巡检', color: '#EFEAF2', text: '#6A5B77', dot: '#8A7A9B' },
  deliver: { key: 'deliver', label: '送达节点', color: '#F6EFD9', text: '#9A7A2E', dot: '#C9A24B' },
  law: { key: 'law', label: '法典施行', color: '#EFEAF2', text: '#6A5B77', dot: '#8A7A9B' },
};

// 顶部筛选片（design：执法检查/案卷评查/督察复查/平台巡检/送达节点）
export const filterTypes: CalType[] = ['enforce', 'review', 'supervise', 'inspect', 'deliver'];

export interface CalEvent {
  id: string;
  day: number; // 8 月内的日期
  title: string;
  type: CalType;
  time?: string;
  urgent?: boolean;
  note?: string; // 全站性提示（如法典施行日）
}

export const calEvents: CalEvent[] = [
  { id: 'e1', day: 3, title: '金竹山矿业法制审核确认', type: 'enforce', urgent: true },
  { id: 'e2', day: 3, title: '百卷精评第74卷复核', type: 'review', time: '14:00' },
  { id: 'e3', day: 3, title: '每日平台巡检', type: 'inspect', time: '09:00' },
  { id: 'e4', day: 6, title: '赢湖矿产品现场复查', type: 'supervise' },
  { id: 'e5', day: 8, title: '禾青镇页岩砖厂 决定书送达截止', type: 'deliver', urgent: true },
  { id: 'e6', day: 12, title: '鑫顺建材案 集体讨论会', type: 'enforce', time: '15:00' },
  { id: 'e7', day: 15, title: '生态环境法典施行日', type: 'law', note: '今日起引用法典条款，旧法停用' },
  { id: 'e8', day: 20, title: '瑞龙木艺厂 整改期限到期', type: 'supervise' },
  { id: 'e9', day: 26, title: '每日巡检连续满月提醒', type: 'inspect' },
];

// 周视图 / 日程视图示例
export interface WeekEvent {
  id: string;
  day: number;
  start: string; // HH:MM
  end: string;
  title: string;
  type: CalType;
  place: string;
  related: string;
  collab?: string[]; // 协同人
}
export const weekEvents: WeekEvent[] = [
  { id: 'w1', day: 3, start: '09:00', end: '09:30', title: '每日平台巡检', type: 'inspect', place: '线上', related: '大气监督帮扶平台' },
  { id: 'w2', day: 3, start: '14:00', end: '15:30', title: '第74卷复核', type: 'review', place: '评查室', related: '鑫顺建材案', collab: ['卷查清'] },
  { id: 'w3', day: 6, start: '10:00', end: '12:00', title: '赢湖矿产品现场复查', type: 'supervise', place: '赢湖矿区', related: '督察整改', collab: ['督察精'] },
  { id: 'w4', day: 12, start: '15:00', end: '16:30', title: '鑫顺建材案 集体讨论会', type: 'enforce', place: '会议室2', related: '鑫顺建材案', collab: ['执法准', '法条通'] },
];

export const aiSuggestion = '数据芯建议：8/7 上午安排禾青镇复查，避开周五送达高峰。';

export const dueSoon = [
  { id: 'd1', title: '金竹山矿业法制审核确认', left: 0, unit: '今天 17:00 前', urgent: true },
  { id: 'd2', title: '娄环罚(冷)〔2026〕2号 送达回证归档', left: 1, unit: '明天到期' },
  { id: 'd3', title: '禾青镇页岩砖厂 决定书送达', left: 5, unit: '还剩 5 天' },
];

export const aiScheduled = [
  { id: 's1', text: '已为您排定 8/3 14:00 第74卷复核（关联卷查清）', canUndo: true },
  { id: 's2', text: '已合并 8/6 赢湖复查与当日巡检路线', canUndo: true },
];

export const TODAY = 3; // 2026-08-03
export const MONTH = '2026年8月';
