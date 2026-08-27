/**
 * 右侧栏 4 区 mock 数据
 * 引用真实数据资产：
 * — 74 文书模板（eco-enforcement-review-team/skills/doc-panel/schemas/*.yaml）
 * — 25 项一票否决（review.ts VETO_GROUPS）
 * — 9 个 AI 专家
 */

import { currentUser } from './currentUser';

export type DocFormat = 'docx' | 'xlsx' | 'pdf';
export type DocStatus = 'ai-draft' | 'editing' | 'reviewing';
export type OfficeMode = 'read' | 'edit' | 'review';

export interface DocParagraph {
  id: number;
  text: string;
  aiModified?: boolean;
  aiRevision?: string;
  aiExpert?: string;
}

export interface AiSegment {
  paragraphId: number;
  expert: string;
  action: string;
  undoable: boolean;
}

export interface Annotation {
  id: string;
  author: string;
  role: 'human' | 'ai';
  content: string;
  time: string;
  resolved: boolean;
  replies: { author: string; role: 'human' | 'ai'; content: string; time: string }[];
}

export interface ActiveDoc {
  id: string;
  name: string;
  format: DocFormat;
  status: DocStatus;
  templateId: number;
  paragraphs: DocParagraph[];
  annotations: Annotation[];
  synced: boolean;
}

export interface GisOperation {
  id: string;
  time: string;
  expert: string;
  description: string;
  canUndo: boolean;
}

export interface HermesCycle {
  stages: { label: string; active: boolean }[];
}

export interface HermesLearning {
  id: string;
  source: string;
  insight: string;
  result: string;
  verified: 'verified' | 'verifying';
  sourceCaseId: string;
}

export interface WeeklyGrowth {
  learned: number;
  corrected: number;
  reused: number;
}

export interface ReviewTrend {
  weeks: string[];
  rates: number[];
}

export interface VetoDistribution {
  category: string;
  total: number;
  hit: number;
}

export interface ReviewAlert {
  pendingReview: number;
  nearDeadline: number;
}

export interface TemplateCategory {
  label: string;
  count: number;
  items: string[];
}

// ── ① Office：当前文档 ──────────────────────────

export const activeDoc: ActiveDoc = {
  id: 'case:JZS-2024-0038',
  name: '金竹山矿业案_行政处罚决定书_草稿.docx',
  format: 'docx',
  status: 'editing',
  templateId: 38,
  paragraphs: [
    { id: 1, text: '我厅（局）于 2026年7月15日 对你（单位）进行了调查，发现你（单位）实施了以下生态环境违法行为：' },
    { id: 2, text: 'CEMS数据显示，2026年7月1日至14日，二氧化硫排放多次超标。经核查，24次超标事件与24次"启动"工况标记一一对应，超标时段集中在夜间22:00至次日4:00。同期企业用电量骤降42%，与正常生产负荷不符，涉嫌通过工况标记造假规避超标记录。', aiModified: true, aiRevision: '原调查报告仅记录超标事实，未分析工况标记对应关系。', aiExpert: '文书成' },
    { id: 3, text: '以上事实，有以下主要证据证明：' },
    { id: 4, text: '1. 营业执照、法定代表人身份证复印件各1份 — 证明当事人主体资格\n2. CEMS工况标记历史数据 — 24次超标与24次"启动"标记1:1对应\n3. CEMS分钟级数据（2026.7.1-7.14）— SO₂超标5次、NOₓ超标16次、颗粒物超标3次\n4. DCS连续生产曲线 — 实际运行负荷与工况标记不一致\n5. 电力调度日志 — 企业用电量与实际运行状态对应关系', aiModified: true, aiExpert: '文书成' },
    { id: 5, text: '你（单位）的上述行为违反了《中华人民共和国生态环境法典》污染防治编·大气污染防治分编关于超标排放大气污染物的规定（原《大气污染防治法》第18条，已废止）。', aiModified: true, aiExpert: '法条通' },
    { id: 6, text: '我厅（局）于 2026年7月29日 以《行政处罚事先（听证）告知书》告知你（单位）陈述申辩权、听证权。' },
    { id: 7, text: '☑ 你（单位）在法定期限内未要求听证，视为放弃要求听证的权利。' },
    { id: 8, text: '你（单位）于 2026年7月30日 进行了陈述和申辩。当事人承认CEMS数据超标属实，但辩称超标系锅炉启停过程中脱硫设施响应延迟导致，非主观故意，请求从轻处罚。', aiModified: true, aiExpert: '文书成' },
    { id: 9, text: '我厅（局）充分听取后复核认为，对当事人提出的事实、理由和证据部分采纳。锅炉启停过程中确实存在脱硫设施响应延迟的客观情况，但企业未能提供启停期间采取有效污染防治措施的证明。在裁量时可酌情从轻5%。', aiModified: true, aiExpert: '文书成' },
    { id: 10, text: '依据《中华人民共和国生态环境法典》法律责任编关于超标排放大气污染物的处罚规定（原《大气污染防治法》第99条第3项，已废止），参照《湖南省生态环境保护行政处罚裁量权基准规定（2021版）》，我厅（局）决定对你（单位）处以罚款（大写）肆拾伍万元整。' },
  ],
  annotations: [
    {
      id: 'ann-001', author: '文书成', role: 'ai', content: '第2段新增"涉嫌通过工况标记造假"措辞，请核实是否符合实际违法情形。',
      time: '08:15', resolved: false,
      replies: [{ author: currentUser.name, role: 'human', content: '确认数据准确，采用。建议补充用电量数据来源。', time: '08:22' }],
    },
    {
      id: 'ann-002', author: currentUser.name, role: 'human', content: '罚款金额需核对自由裁量基准中的档位设置。',
      time: '08:25', resolved: true,
      replies: [{ author: '文书成', role: 'ai', content: '已按基准计算：50万 × 从轻5% = 47.5万，在45-50万档位内。', time: '08:26' }],
    },
    {
      id: 'ann-003', author: '文书成', role: 'ai', content: '建议增加责令停产整治的处罚种类，因超标持续时间达14天，属于情节较重。',
      time: '08:28', resolved: false,
      replies: [],
    },
  ],
  synced: true,
};

// 文书模板分类（用于空态"让 AI 起草"下拉）
export const templateCategories: TemplateCategory[] = [
  { label: '立案', count: 5, items: ['立案审批表', '不予立案审批表', '移送审批表', '指定管辖审批表', '回避审批表'] },
  { label: '调查取证', count: 20, items: ['现场检查（勘察）笔录（通用）', '现场检查（勘察）笔录（大气）', '调查询问笔录', '监测报告', '责令改正违法行为决定书'] },
  { label: '裁量', count: 5, items: ['行政处罚案件集体讨论记录', '行政处罚案件法制审核意见书', '行政处罚案件处理呈批表', '自由裁量理由说明表', '案审委会议纪要'] },
  { label: '告知听证', count: 12, items: ['行政处罚事先告知书', '行政处罚听证告知书', '行政处罚听证通知书', '行政处罚听证笔录', '行政处罚听证报告'] },
  { label: '处罚决定', count: 9, items: ['行政处罚决定书', '不予行政处罚决定书', '当场行政处罚决定书', '按日连续处罚决定书', '查封(扣押)决定书'] },
  { label: '执行归档', count: 22, items: ['送达回证', '延期分期缴纳罚款审批表', '行政处罚案件结案审批表', '结案报告', '行政强制执行申请书'] },
];

// ── ② GIS 操作记录 ───────────────────────────

export const gisOperations: GisOperation[] = [
  { id: 'gis-1', time: '10:24', expert: '数据芯', description: '在金竹山矿业排口添加超标标注（红色）', canUndo: true },
  { id: 'gis-2', time: '10:31', expert: '执法准', description: '规划复查路线：3 个点位，全程 18 公里', canUndo: true },
  { id: 'gis-3', time: '10:45', expert: '数据芯', description: '圈选金竹山矿区周边敏感点（半径 2km）', canUndo: true },
];

// ── ③ Hermes 记忆 ────────────────────────────

export const hermesCycle: HermesCycle = {
  stages: [
    { label: '经验积累', active: false },
    { label: '实践验证', active: true },
    { label: '规则沉淀', active: false },
    { label: '下次复用', active: false },
  ],
};

export const weeklyGrowth: WeeklyGrowth = {
  learned: 3,
  corrected: 1,
  reused: 56,
};

export const hermesLearnings: HermesLearning[] = [
  {
    id: 'mem-1', verified: 'verified',
    source: '金竹山矿业案后',
    insight: 'CEMS 夜间超标 + 用电骤降组合 = 旁路排放嫌疑',
    result: '已加入检查要点',
    sourceCaseId: 'case:JZS-2024-0038',
  },
  {
    id: 'mem-2', verified: 'verifying',
    source: '砖瓦企业普查',
    insight: '砖瓦企业听证期限易漏算',
    result: '已加入否决扫描重点提示',
    sourceCaseId: 'case:ZW-2024-0015',
  },
  {
    id: 'mem-3', verified: 'verified',
    source: '冷水江化工园区',
    insight: '化工企业 VOCs 无组织排放需同时查储罐、装卸、废水收集三环节',
    result: '已加入检查要点',
    sourceCaseId: 'case:HG-2024-0007',
  },
];

// ── ④ 评查看板 ────────────────────────────────

export const reviewStats = {
  total: 73,
  target: 100,
  passRate: 93.2,
  deniedCount: 1,
};

export const reviewTrend: ReviewTrend = {
  weeks: ['W27', 'W28', 'W29', 'W30', 'W31', 'W32', 'W33', 'W34', 'W35', 'W36', 'W37', 'W38'],
  rates: [91, 90, 92, 93, 94, 93, 92, 94, 93, 93, 94, 93],
};

export const vetoDist: VetoDistribution[] = [
  { category: '程序类', total: 10, hit: 4 },
  { category: '证据类', total: 5, hit: 1 },
  { category: '法律适用', total: 3, hit: 1 },
  { category: '移送处理', total: 4, hit: 0 },
  { category: '其他', total: 3, hit: 0 },
];

export const reviewAlerts: ReviewAlert = {
  pendingReview: 2,
  nearDeadline: 1,
};
