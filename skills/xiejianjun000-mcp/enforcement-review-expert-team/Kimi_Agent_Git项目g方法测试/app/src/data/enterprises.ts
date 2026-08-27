// 企业管理 mock 数据 —— 锚定 design/enterprises.md

export type Risk = 'over' | 'due' | 'normal';

export interface Overview {
  registered: number;
  key: number;
  over30: number;
  permitDue: number;
}

export const overview: Overview = {
  registered: 286,
  key: 41,
  over30: 12,
  permitDue: 7,
};

export interface CaseRec {
  date: string;
  type: string; // 立案/处罚/整改
  desc: string;
  status: string;
}

export interface Enterprise {
  id: string;
  name: string;
  risk: Risk;
  permitNo: string;
  industry: string;
  factors: string;
  openCases: number;
  aiNote: string;
  // 详情
  licenseFrom: string;
  licenseTo: string;
  cems: { d: string; v: number; over?: boolean }[]; // 近90天排放值
  electricity: { d: string; use: number; produce: number }[];
  cases: CaseRec[];
  credit: string;
  help: string[];
}

export const enterprises: Enterprise[] = [
  {
    id: 'jinzhushan',
    name: '金竹山矿业有限公司',
    risk: 'over',
    permitNo: '91431381MA4LXXXX1A',
    industry: '采矿 · 煤炭开采',
    factors: '烟尘 / SO₂ / NOx',
    openCases: 1,
    aiNote: '数据芯画像：近半年夜间用电与产量不匹配，存在旁路排放嫌疑。',
    licenseFrom: '2021-09-01',
    licenseTo: '2026-08-31',
    cems: [
      { d: '05-15', v: 38 }, { d: '05-30', v: 41 }, { d: '06-14', v: 86, over: true },
      { d: '06-28', v: 52 }, { d: '07-12', v: 93, over: true }, { d: '07-26', v: 47 },
      { d: '08-02', v: 121, over: true },
    ],
    electricity: [
      { d: '05月', use: 820, produce: 760 }, { d: '06月', use: 910, produce: 700 },
      { d: '07月', use: 1040, produce: 690 },
    ],
    cases: [
      { date: '2026-07-12', type: '立案', desc: 'CEMS 烟尘超标 2.1 倍', status: '调查中' },
      { date: '2026-08-02', type: '立案', desc: '第24次超标，拟处罚', status: '法制审核' },
    ],
    credit: 'B（较重失信）',
    help: ['2026-07 大气帮扶：建议安装备用除尘', '2026-08 帮扶：旁路排查整改中'],
  },
  {
    id: 'yinghu',
    name: '赢湖矿产品加工厂',
    risk: 'normal',
    permitNo: '91431381MA4LXXXX2B',
    industry: '建材 · 矿产品加工',
    factors: '颗粒物 / 噪声',
    openCases: 0,
    aiNote: '画像平稳：近 90 天无超标，用电与产量匹配度良好。',
    licenseFrom: '2022-03-01',
    licenseTo: '2027-02-28',
    cems: [
      { d: '05-15', v: 30 }, { d: '05-30', v: 33 }, { d: '06-14', v: 36 },
      { d: '06-28', v: 31 }, { d: '07-12', v: 34 }, { d: '07-26', v: 29 }, { d: '08-02', v: 32 },
    ],
    electricity: [
      { d: '05月', use: 410, produce: 400 }, { d: '06月', use: 430, produce: 420 }, { d: '07月', use: 450, produce: 440 },
    ],
    cases: [{ date: '2025-11-03', type: '整改', desc: '扬尘治理验收通过', status: '已结案' }],
    credit: 'A（信用良好）',
    help: ['2026-06 帮扶：厂界降噪完成'],
  },
  {
    id: 'heqing',
    name: '禾青镇页岩砖厂',
    risk: 'due',
    permitNo: '91431381MA4LXXXX3C',
    industry: '建材 · 砖瓦',
    factors: 'SO₂ / 烟尘',
    openCases: 1,
    aiNote: '证照将于 90 天内到期，建议提前启动延续申请。',
    licenseFrom: '2021-09-01',
    licenseTo: '2026-10-15',
    cems: [
      { d: '05-15', v: 44 }, { d: '05-30', v: 48 }, { d: '06-14', v: 51 },
      { d: '06-28', v: 49 }, { d: '07-12', v: 53 }, { d: '07-26', v: 55 }, { d: '08-02', v: 58 },
    ],
    electricity: [
      { d: '05月', use: 380, produce: 370 }, { d: '06月', use: 400, produce: 390 }, { d: '07月', use: 420, produce: 410 },
    ],
    cases: [{ date: '2026-08-08', type: '送达', desc: '处罚决定书送达截止', status: '待送达' }],
    credit: 'B（较重失信）',
    help: ['2026-07 帮扶：脱硫效率提升建议'],
  },
  {
    id: 'xinshun',
    name: '鑫顺建材有限公司',
    risk: 'normal',
    permitNo: '91431381MA4LXXXX4D',
    industry: '建材 · 水泥制品',
    factors: '颗粒物 / NOx',
    openCases: 1,
    aiNote: '卷查清提示：第74卷证据链核查中，监测报告采样时间待补正。',
    licenseFrom: '2022-06-01',
    licenseTo: '2027-05-31',
    cems: [
      { d: '05-15', v: 40 }, { d: '05-30', v: 42 }, { d: '06-14', v: 45 },
      { d: '06-28', v: 43 }, { d: '07-12', v: 47 }, { d: '07-26', v: 44 }, { d: '08-02', v: 46 },
    ],
    electricity: [
      { d: '05月', use: 520, produce: 510 }, { d: '06月', use: 540, produce: 530 }, { d: '07月', use: 560, produce: 550 },
    ],
    cases: [{ date: '2026-08-12', type: '讨论', desc: '集体讨论会待召开', status: '待办' }],
    credit: 'A（信用良好）',
    help: ['2026-06 帮扶：在线监测运维规范'],
  },
  {
    id: 'ruilong',
    name: '瑞龙木艺厂',
    risk: 'normal',
    permitNo: '91431381MA4LXXXX5E',
    industry: '木艺 · 加工',
    factors: 'VOCs / 颗粒物',
    openCases: 1,
    aiNote: '督察精提示：整改期限 8/20 到期，请跟进整改进度。',
    licenseFrom: '2023-01-01',
    licenseTo: '2027-12-31',
    cems: [
      { d: '05-15', v: 28 }, { d: '05-30', v: 30 }, { d: '06-14', v: 31 },
      { d: '06-28', v: 29 }, { d: '07-12', v: 33 }, { d: '07-26', v: 32 }, { d: '08-02', v: 30 },
    ],
    electricity: [
      { d: '05月', use: 220, produce: 215 }, { d: '06月', use: 230, produce: 225 }, { d: '07月', use: 240, produce: 235 },
    ],
    cases: [{ date: '2026-08-20', type: '整改', desc: '整改期限到期', status: '进行中' }],
    credit: 'B（较重失信）',
    help: ['2026-07 帮扶：VOCs 治理设施升级'],
  },
  {
    id: 'f1', name: '冷水江市长宏陶瓷', risk: 'normal', permitNo: '91431381MA4LXXXX6F', industry: '建材 · 陶瓷', factors: 'SO₂ / 烟尘', openCases: 0, aiNote: '画像平稳，建议维持常规巡检频次。',
    licenseFrom: '2022-04-01', licenseTo: '2027-03-31', cems: [], electricity: [], cases: [], credit: 'A', help: [],
  },
  {
    id: 'f2', name: '铎山金属制品厂', risk: 'over', permitNo: '91431381MA4LXXXX7G', industry: '金属制品', factors: 'NOx / 烟尘', openCases: 1, aiNote: '数据芯：近 30 天 3 次夜间排放异常抬升。',
    licenseFrom: '2021-11-01', licenseTo: '2026-10-31', cems: [], electricity: [], cases: [], credit: 'B', help: [],
  },
  {
    id: 'f3', name: '中连乡石料场', risk: 'normal', permitNo: '91431381MA4LXXXX8H', industry: '采矿 · 石料', factors: '颗粒物', openCases: 0, aiNote: '喷淋抑尘运行正常，无超标记录。',
    licenseFrom: '2023-02-01', licenseTo: '2028-01-31', cems: [], electricity: [], cases: [], credit: 'A', help: [],
  },
];

export const riskMeta: Record<Risk, { label: string; cls: string }> = {
  over: { label: '超标中', cls: 'red' },
  due: { label: '证照临期', cls: 'amber' },
  normal: { label: '正常', cls: 'olive' },
};

export const industries = ['全部', '采矿', '建材', '木艺', '金属制品'];
export const levels = ['全部', '重点', '一般'];
export const riskFilters = [
  { key: 'over', label: '超标中' },
  { key: 'due', label: '证照临期' },
  { key: 'hasCase', label: '有未结案' },
];
