// 知识库模块数据 —— 锚定 design/knowledge.md
export interface LawCompare {
  old: string;
  neo: string;
}
// 10 部旧法 → 生态环境法典对应编章
export const lawCompare: LawCompare[] = [
  { old: '环境保护法', neo: '生态环境法典 · 总则编' },
  { old: '大气污染防治法', neo: '生态环境法典 · 污染防治编（大气）' },
  { old: '水污染防治法', neo: '生态环境法典 · 污染防治编（水）' },
  { old: '固体废物污染环境防治法', neo: '生态环境法典 · 污染防治编（固废）' },
  { old: '噪声污染防治法', neo: '生态环境法典 · 污染防治编（噪声）' },
  { old: '放射性污染防治法', neo: '生态环境法典 · 污染防治编（辐射）' },
  { old: '环境影响评价法', neo: '生态环境法典 · 生态保护编' },
  { old: '排污许可管理条例', neo: '生态环境法典 · 监督管理编' },
  { old: '行政处罚法（环保适用）', neo: '生态环境法典 · 法律责任编' },
  { old: '环境行政处罚办法', neo: '生态环境法典 · 法律责任编' },
];

export interface CodeChapter {
  name: string;
  count: string;
}
export const codeChapters: CodeChapter[] = [
  { name: '总则编', count: '约 120 条' },
  { name: '污染防治编', count: '约 520 条（大气/水/固废/噪声/辐射）' },
  { name: '生态保护编', count: '约 280 条' },
  { name: '监督管理编', count: '约 180 条' },
  { name: '法律责任编', count: '约 120 条' },
  { name: '附则', count: '约 22 条' },
];

export interface ProvinceReport {
  name: string;
  summary: string;
}
export const provinceReports: ProvinceReport[] = [
  { name: '湖南省', summary: '已完成地方性法规与法典衔接修改，重点调整处罚条款引用与裁量基准衔接。' },
  { name: '湖北省', summary: '衔接报告已完成，同步修订政府规章中引用的旧法条。' },
  { name: '广东省', summary: '发布衔接修改深度学习报告，梳理省级生态环保法规对照清单。' },
  { name: '浙江省', summary: '法规修改衔接方案已定稿，涉水与固废条款优先切换。' },
  { name: '江苏省', summary: '深度学习报告完成，建立条款映射表与模板校验规则。' },
  { name: '山东省', summary: '深度学习报告完成，重点核查行政处罚程序类条款。' },
  { name: '河南省', summary: '与湖北联合开展衔接研究，统一中部地区适用口径。' },
  { name: '江西省', summary: '中部八省衔接行动成员，已完成初步条款对照。' },
];

export interface BasisCard {
  title: string;
  desc: string;
}
export const basisCards: BasisCard[] = [
  { title: '案卷评查细则（2024 版）', desc: '全文检索入口 + 章节目录' },
  { title: '湖南省裁量权基准（2021 版）', desc: '29 张裁量表，按违法情形索引' },
  { title: '25 项一票否决清单', desc: '权威版全文，四类分组' },
  { title: '移送公安量化标准', desc: '重金属超标 3 倍 / 危废 3 吨入刑' },
  { title: '6 类案件评查框架', desc: '大气/水/固废/噪声/辐射/其他' },
  { title: '文书模板说明', desc: '74 类模板适用场景速查' },
];

export const recentList: string[] = [
  '生态环境法典 第 112 条（听证期限）',
  '湖南省裁量权基准 表 12',
  '25 项一票否决 · 程序类',
];

// 演示问答（MOCK）
export interface QA {
  q: string;
  a: string;
  cites: { text: string; src: string; status: string }[];
}
export const QA_DEMO: Record<string, QA> = {
  '砖厂超标': {
    q: '砖厂超标该罚多少？',
    a: '砖厂超标排放大气污染物，依据湖南省裁量权基准（2021 版）表 12「超标排放大气污染物」，结合超标倍数与整改态度在幅度内裁量。超标 1–2 倍一般处 10–20 万元，2 倍以上加重。',
    cites: [
      { text: '《湖南省生态环境行政处罚裁量权基准（2021 版）》表 12', src: '湖南省生态环境厅', status: '现行有效' },
      { text: '生态环境法典 · 污染防治编（大气）第 308 条', src: '生态环境法典', status: '2026-08-15 起施行' },
    ],
  },
  '法典': {
    q: '法典施行后旧案子怎么引法条？',
    a: '2026-08-15 生态环境法典施行后，新作出的处罚决定应引用法典条款；之前已立案但未作出决定的案件，原则上从新法，但处罚更轻的除外（从旧兼从轻）。平台文书模板已提前完成切换校验。',
    cites: [
      { text: '《立法法》第 93 条（从旧兼从轻）', src: '全国人民代表大会', status: '现行有效' },
      { text: '生态环境法典 · 附则', src: '生态环境法典', status: '2026-08-15 起施行' },
    ],
  },
};
