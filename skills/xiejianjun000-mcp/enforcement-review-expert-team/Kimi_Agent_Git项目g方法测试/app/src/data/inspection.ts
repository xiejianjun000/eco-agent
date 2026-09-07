// 督察管理模块数据 —— 锚定 design/inspection.md
export type TaskType = '专项督察' | '日常督察' | '帮扶';
export type TaskCol = 'todo' | 'doing' | 'done';

export interface InspectTask {
  id: string;
  name: string;
  type: TaskType;
  enterprises: string[];
  deadline: string;
  progress: number;
  col: TaskCol;
}

export type FixState = '未开始' | '整改中' | '待复核' | '已销号';

export interface FixItem {
  id: string;
  problem: string;
  company: string;
  deadline: string;
  remainDays: number; // 负 = 逾期
  state: FixState;
  note?: string;
  beforeAfter?: { before: string; after: string };
}

export interface HelpRecord {
  date: string;
  company: string;
  content: string;
  advice: string;
}

export const tasks: InspectTask[] = [
  { id: 't1', name: '禾青镇砖瓦行业专项督察', type: '专项督察', enterprises: ['禾青镇页岩砖厂'], deadline: '2026-08-20', progress: 60, col: 'doing' },
  { id: 't2', name: '矿区生态修复"回头看"', type: '专项督察', enterprises: ['金竹山矿业', '赢湖矿产品'], deadline: '2026-08-25', progress: 0, col: 'todo' },
  { id: 't3', name: '大气帮扶夏季行动', type: '帮扶', enterprises: [], deadline: '2026-08-31', progress: 45, col: 'doing' },
  { id: 't4', name: '饮用水源地日常督察', type: '日常督察', enterprises: [], deadline: '2026-07-30', progress: 100, col: 'done' },
];

export const fixes: FixItem[] = [
  { id: 'f1', problem: '粉尘收集设施改造', company: '瑞龙木艺厂', deadline: '2026-08-24', remainDays: 17, state: '整改中' },
  { id: 'f2', problem: '堆场覆盖不到位', company: '鑫顺建材', deadline: '2026-08-05', remainDays: -2, state: '整改中', note: '督察精 已生成催办函草稿', beforeAfter: { before: '物料露天堆放', after: '待复核' } },
  { id: 'f3', problem: '排口数据中断修复', company: '金竹山矿业', deadline: '2026-08-12', remainDays: 5, state: '待复核' },
  { id: 'f4', problem: '脱硫设施运行异常', company: '禾青镇页岩砖厂', deadline: '2026-08-10', remainDays: 3, state: '整改中' },
  { id: 'f5', problem: '危废暂存间不规范', company: '赢湖矿产品', deadline: '2026-08-17', remainDays: 10, state: '未开始' },
];

export const helps: HelpRecord[] = [
  { date: '2026-08-05', company: '鑫顺建材', content: '堆场覆盖技术指导，现场演示防尘网铺设', advice: '一周内完成全覆盖，逾期将催办' },
  { date: '2026-08-03', company: '瑞龙木艺厂', content: '粉尘治理工艺帮扶，推荐布袋除尘方案', advice: '升级收集设施，纳入整改跟踪' },
  { date: '2026-07-30', company: '金竹山矿业', content: '废气治理设施检修帮扶', advice: '修复监测排口，确保数据连续' },
];

export const TASK_TYPE_CLS: Record<TaskType, string> = {
  专项督察: 'red', 日常督察: 'blue', 帮扶: 'olive',
};

export const FIX_STATE_CLS: Record<FixState, string> = {
  未开始: 'aux', 整改中: 'amber', 待复核: 'blue', 已销号: 'olive',
};
