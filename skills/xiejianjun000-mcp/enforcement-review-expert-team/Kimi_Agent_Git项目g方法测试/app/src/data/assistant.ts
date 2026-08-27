// 执法助理（首页）mock 数据 —— 锚定 design/assistant.md 精确内容
import { currentUser } from './currentUser';

export interface TodoItem {
  id: string;
  level: 'urgent' | 'due' | 'normal'; // 紧急 / 临期 / 普通
  title: string;
  source: string; // 来源模块小字
  deadline: string; // 截止时间
  target: string; // 「去处理」跳转的模块 id
}

export interface Expert {
  id: string;
  name: string;
  role: string; // 职责一句
  status: string; // 正在做什么
  metric: string; // 累计完成数
  active: boolean; // 是否正在执行（状态点）
}

export interface ChatMsg {
  id: string;
  who: 'user' | 'ai';
  text: string;
  cite?: string;
  timestamp: string;
  feedback?: 'like' | 'dislike' | null;
}

export interface WeekSummary {
  cases: number; // 立案
  passed: number; // 评查通过
  veto: number; // 否决拦截
  docs: number; // 文书生成
}

export const greeting = {
  hello: '早上好',
  name: currentUser.name,
  date: '今天是 2026年8月3日 星期一',
  stats: '今日待办 6 项 · 评查进行中 2 卷 · 平台巡检正常',
};

export const todos: TodoItem[] = [
  {
    id: 't1',
    level: 'urgent',
    title: '金竹山矿业 CEMS 超标案：法制审核意见待确认',
    source: '执法办案',
    deadline: '今日 17:00 前',
    target: 'enforcement',
  },
  {
    id: 't2',
    level: 'due',
    title: '娄环罚(冷)〔2026〕2号：决定书送达回证待归档',
    source: '档案管理',
    deadline: '明日到期',
    target: 'archive',
  },
  {
    id: 't3',
    level: 'normal',
    title: '百卷精评第 74 卷已就绪，待您复核 AI 初评结果',
    source: '案卷评查',
    deadline: '今日',
    target: 'review',
  },
  {
    id: 't4',
    level: 'normal',
    title: '大气监督帮扶平台：本周巡检报告已生成',
    source: '平台管理',
    deadline: '今日',
    target: 'platforms',
  },
  {
    id: 't5',
    level: 'normal',
    title: '赢湖矿产品现场检查复查安排',
    source: '督察管理',
    deadline: '8月6日',
    target: 'inspection',
  },
  {
    id: 't6',
    level: 'normal',
    title: '冷水江市 3 家企业排污许可执行报告待审核',
    source: '企业管理',
    deadline: '本周内',
    target: 'enterprises',
  },
];

export const experts: Expert[] = [
  {
    id: 'e1',
    name: '法眼通',
    role: '调度官 · 统筹任务分派',
    status: '正在分派第 74 卷评查任务',
    metric: '累计调度 312 次',
    active: true,
  },
  {
    id: 'e2',
    name: '卷查清',
    role: '案卷评查 · 逐卷比对 25 项否决',
    status: '正在核查鑫顺建材案证据链',
    metric: '已评 73 卷',
    active: true,
  },
  {
    id: 'e3',
    name: '执法准',
    role: '现场执法 · 检查要点提示',
    status: '待命',
    metric: '辅助检查 58 次',
    active: false,
  },
  {
    id: 'e4',
    name: '督察精',
    role: '督察实战 · 整改跟踪',
    status: '正在整理帮扶记录',
    metric: '跟踪整改 21 项',
    active: true,
  },
  {
    id: 'e5',
    name: '法条通',
    role: '法律合规 · 法典衔接 · 新旧法比对',
    status: '待命',
    metric: '法典衔接核验 96 次',
    active: false,
  },
  {
    id: 'e6',
    name: '文书成',
    role: '文书生成 · 74 类文书起草',
    status: '正在起草处罚决定书',
    metric: '已起草 143 份',
    active: true,
  },
  {
    id: 'e7',
    name: '数据芯',
    role: '数据分析 · 超标数据研判',
    status: '已标记金竹山 24 次超标',
    metric: '分析 402 条',
    active: true,
  },
  {
    id: 'e8',
    name: '知识库',
    role: '知识管理 · 法规检索问答',
    status: '待命',
    metric: '收录法规 1242 条（法典）',
    active: false,
  },
  {
    id: 'e9',
    name: '巡检员',
    role: '平台巡检 · 6 平台每日巡检',
    status: '今日巡检完成（连续第 9 天）',
    metric: '报告 9 份',
    active: true,
  },
];

export const quickCommands: string[] = [
  '起草文书',
  '核对否决项',
  '查法条',
  '安排复查',
  '生成巡检说明',
];

export const weekSummary: WeekSummary = {
  cases: 3,
  passed: 11,
  veto: 2,
  docs: 18,
};
