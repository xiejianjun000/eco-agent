// 执法办案模块数据 —— 锚定 design/enforcement.md
import { currentUser } from './currentUser';

export type Stage = '立案' | '调查' | '裁量' | '告知' | '决定' | '执行' | '归档';

export const STAGES: Stage[] = ['立案', '调查', '裁量', '告知', '决定', '执行', '归档'];

// 74 类文书按阶段分布（见 design/enforcement.md）
export const DOC_COUNTS: Record<Stage, number> = {
  立案: 5, 调查: 20, 裁量: 5, 告知: 12, 决定: 9, 执行: 18, 归档: 4,
};

export type DocStatus = '未起草' | 'AI草稿待确认' | '已签署' | '已送达';

export interface CaseDoc {
  name: string;
  status: DocStatus;
}

export interface Evidence {
  name: string;
  state: 'ok' | 'missing';
  note?: string;
}

export interface CaseItem {
  id: string;
  name: string;
  no: string;
  party: string;
  handler: string;
  stage: Stage;
  deadline: string;
  warning?: string;
  suggest?: string;
  docs: Partial<Record<Stage, CaseDoc[]>>;
  evidence?: Evidence[];
  // 右栏辅助（金竹山详例）
  vetoScan?: { scanned: number; pass: number; risk: number; risks: { name: string; law: string; fix: string }[] };
  sentencing?: { basis: string; range: string; note: string };
  codeLink?: string;
  transfer?: { reached: boolean; detail: string };
}

const KINZHUSHAN_DOCS: Partial<Record<Stage, CaseDoc[]>> = {
  立案: [
    { name: '01_指定管辖通知书', status: '已送达' },
    { name: '02_立案审批表', status: '已签署' },
    { name: '03_立案决定书', status: '已送达' },
  ],
  调查: [
    { name: '08_现场检查勘察笔录', status: '已签署' },
    { name: '09_调查询问笔录', status: '已签署' },
    { name: '14_监测报告（废气）', status: '已送达' },
    { name: '17_现场照片证据', status: '已签署' },
  ],
  裁量: [
    { name: '21_裁量权基准适用表', status: 'AI草稿待确认' },
  ],
  告知: [
    { name: '26_行政处罚事先告知书', status: 'AI草稿待确认' },
    { name: '27_听证告知书', status: '未起草' },
  ],
  决定: [
    { name: '33_行政处罚决定书', status: '未起草' },
  ],
  执行: [],
  归档: [],
};

const KINZHUSHAN_EVIDENCE: Evidence[] = [
  { name: '现场照片', state: 'ok' },
  { name: '监测报告', state: 'ok' },
  { name: '笔录签字', state: 'missing', note: '笔录缺当事人签字' },
];

export const cases: CaseItem[] = [
  {
    id: 'jzs',
    name: '金竹山矿业废气超标案',
    no: '娄环罚(冷)〔2026〕2号',
    party: '金竹山矿业有限公司',
    handler: currentUser.name,
    stage: '归档',
    deadline: '已结案',
    warning: '卷查清 发现 1 项否决风险：听证期限不足',
    suggest: '文书成 建议：今日起草《行政处罚决定书》',
    docs: KINZHUSHAN_DOCS,
    evidence: KINZHUSHAN_EVIDENCE,
    vetoScan: {
      scanned: 18, pass: 17, risk: 1,
      risks: [
        { name: '听证期限不足', law: '《生态环境法典》第 112 条', fix: '听证告知距决定不足 3 日，建议补正后重新计算期限' },
      ],
    },
    sentencing: {
      basis: '湖南省生态环境行政处罚裁量权基准（2021 版）表 12',
      range: '罚款 20 万 – 45 万元',
      note: '超标 2.1 倍，属较重情节；禁自动生成最终决定，仅供您参考',
    },
    codeLink: '本案若在 2026-08-15 后作出决定，应引用生态环境法典条款 → 查看对照',
    transfer: { reached: false, detail: '未达移送标准（超标 2.1 倍 < 3 倍）' },
  },
  {
    id: 'xsbj', name: '鑫顺建材堆场扬尘案', no: '娄环罚(冷)〔2026〕7号',
    party: '鑫顺建材有限公司', handler: '王海', stage: '调查',
    deadline: '距调查终结 12 天',
    docs: {
      立案: [{ name: '02_立案审批表', status: '已签署' }],
      调查: [{ name: '08_现场检查勘察笔录', status: 'AI草稿待确认' }],
    },
  },
  {
    id: 'rlmy', name: '瑞龙木艺厂粉尘案', no: '娄环罚(冷)〔2026〕9号',
    party: '瑞龙木艺厂', handler: '陈敏', stage: '告知',
    deadline: '距送达 3 天',
    docs: {
      立案: [{ name: '03_立案决定书', status: '已送达' }],
      调查: [{ name: '14_监测报告', status: '已送达' }],
      告知: [{ name: '26_行政处罚事先告知书', status: '已签署' }],
    },
  },
  {
    id: 'hqzs', name: '禾青镇页岩砖厂废气案', no: '娄环罚(冷)〔2026〕5号',
    party: '禾青镇页岩砖厂', handler: currentUser.name, stage: '执行',
    deadline: '距缴款期满 21 天',
    docs: {
      决定: [{ name: '33_行政处罚决定书', status: '已送达' }],
      执行: [{ name: '41_催告书', status: '未起草' }],
    },
  },
  {
    id: 'yhkc', name: '赢湖矿产品无证排污案', no: '娄环罚(冷)〔2026〕3号',
    party: '赢湖矿产品有限公司', handler: '王海', stage: '裁量',
    deadline: '距裁量完成 6 天',
    docs: { 立案: [{ name: '02_立案审批表', status: '已签署' }], 裁量: [] },
  },
  {
    id: 'c6', name: '冷江塑业异味扰民案', no: '娄环罚(冷)〔2026〕11号',
    party: '冷江塑业有限公司', handler: '陈敏', stage: '立案',
    deadline: '距立案 2 天',
    docs: { 立案: [] },
  },
  {
    id: 'c7', name: '新化砖厂噪声案', no: '娄环罚(冷)〔2026〕12号',
    party: '新化新型砖厂', handler: currentUser.name, stage: '调查',
    deadline: '距调查终结 9 天',
    docs: { 立案: [{ name: '03_立案决定书', status: '已送达' }] },
  },
  {
    id: 'c8', name: '渣土运输抛洒案', no: '娄环罚(冷)〔2026〕13号',
    party: '顺通渣土运输公司', handler: '王海', stage: '归档',
    deadline: '已结案',
    docs: { 归档: [{ name: '72_卷宗目录', status: '已签署' }] },
  },
  {
    id: 'c9', name: '矿山生态修复滞后案', no: '娄环罚(冷)〔2026〕14号',
    party: '禾青矿区修复项目部', handler: '陈敏', stage: '决定',
    deadline: '距决定作出 8 天',
    docs: { 决定: [{ name: '33_行政处罚决定书', status: '未起草' }] },
  },
];

// 「在办案件」统一口径：执行 / 归档阶段视为已办结，其余为在办（执法办案列表与右侧栏共用）
export const CLOSED_STAGES: readonly Stage[] = ['执行', '归档'];
export const isOpenCase = (c: CaseItem): boolean => !CLOSED_STAGES.includes(c.stage);
export const openCases: CaseItem[] = cases.filter(isOpenCase);

export const STAGE_STATUS_CLS: Record<DocStatus, string> = {
  未起草: 'aux',
  'AI草稿待确认': 'amber',
  已签署: 'blue',
  已送达: 'olive',
};
