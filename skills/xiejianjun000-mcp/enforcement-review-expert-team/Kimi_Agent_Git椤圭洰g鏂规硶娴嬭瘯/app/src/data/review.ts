// 案卷评查模块数据 —— 锚定 design/review.md（25 项一票否决）
export type VetoResult = 'pass' | 'hit' | 'na';

export interface VetoItem {
  no: number;
  name: string;
  keyword: string;
  law: string;
  result: VetoResult;
  extract?: string;
}

export interface VetoGroup {
  cat: string;
  items: VetoItem[];
}

export const VETO_GROUPS: VetoGroup[] = [
  {
    cat: '程序类（10）',
    items: [
      { no: 1, name: '立案管辖错误', keyword: '管辖 / 越权', law: '《行政处罚法》第 22 条', result: 'pass' },
      { no: 2, name: '超过追究时效', keyword: '2 年 / 时效', law: '《行政处罚法》第 36 条', result: 'pass' },
      { no: 3, name: '未告知听证权利', keyword: '听证 / 告知', law: '《行政处罚法》第 63 条', result: 'pass' },
      { no: 4, name: '陈述申辩权未保障', keyword: '陈述申辩', law: '《行政处罚法》第 45 条', result: 'pass' },
      { no: 5, name: '重大案件未集体审议', keyword: '集体讨论', law: '《环境行政处罚办法》第 52 条', result: 'pass' },
      { no: 6, name: '送达程序违法', keyword: '送达 / 签收', law: '《行政处罚法》第 61 条', result: 'pass' },
      { no: 7, name: '超期作出决定', keyword: '办案期限 / 90 日', law: '《环境行政处罚办法》第 55 条', result: 'pass' },
      { no: 8, name: '执法人员少于两人', keyword: '两人 / 执法证', law: '《行政处罚法》第 42 条', result: 'pass' },
      { no: 9, name: '听证期限不足', keyword: '听证 / 3 日', law: '《生态环境法典》第 112 条', result: 'hit', extract: '卷宗 P23《行政处罚事先告知书》送达回证显示：告知日期 8/1，听证申请期截止 8/4（不足 3 日法定时限）。' },
      { no: 10, name: '应回避未回避', keyword: '回避 / 利害关系', law: '《行政处罚法》第 43 条', result: 'na' },
    ],
  },
  {
    cat: '证据类（5）',
    items: [
      { no: 11, name: '主要证据缺失', keyword: '监测报告 / 笔录', law: '《环境行政处罚证据指南》', result: 'pass' },
      { no: 12, name: '监测数据无效', keyword: '资质 / 计量认证', law: '《计量法》', result: 'na' },
      { no: 13, name: '笔录无当事人签字', keyword: '签字确认', law: '《环境行政处罚办法》第 29 条', result: 'pass' },
      { no: 14, name: '证据未依法封存', keyword: '封存 / 登记', law: '《行政处罚法》第 56 条', result: 'pass' },
      { no: 15, name: '采样不规范', keyword: '采样 / 频次', law: '《监测技术规范》', result: 'na' },
    ],
  },
  {
    cat: '法律适用类（3）',
    items: [
      { no: 16, name: '法律适用错误', keyword: '条款引用', law: '生态环境法典衔接', result: 'pass' },
      { no: 17, name: '裁量明显不当', keyword: '裁量基准', law: '《湖南省裁量权基准 2021》', result: 'pass' },
      { no: 18, name: '新旧法适用冲突', keyword: '从旧兼从轻', law: '《立法法》第 93 条', result: 'na' },
    ],
  },
  {
    cat: '移送类（2）',
    items: [
      { no: 19, name: '应移未移公安', keyword: '涉刑 / 移送', law: '《移送涉嫌环境犯罪规定》', result: 'na' },
      { no: 20, name: '移送材料不全', keyword: '移送函 / 清单', law: '《移送规定》', result: 'na' },
    ],
  },
  {
    cat: '其他类（5）',
    items: [
      { no: 21, name: '文书格式不规范', keyword: '文号 / 印章', law: '《文书制作规范》', result: 'pass' },
      { no: 22, name: '案卷材料缺失', keyword: '目录 / 页码', law: '《评查细则 2024》', result: 'na' },
      { no: 23, name: '电子卷宗未归档', keyword: '归档 / 推送', law: '《评查细则 2024》', result: 'na' },
      { no: 24, name: '处罚决定未执行', keyword: '执行 / 催告', law: '《行政处罚法》第 72 条', result: 'pass' },
      { no: 25, name: '救济权利告知缺失', keyword: '复议 / 诉讼', law: '《行政处罚法》第 7 条', result: 'pass' },
    ],
  },
];

export const SOP_STAGES: { name: string; expert: string }[] = [
  { name: '预审分流', expert: '法眼通' },
  { name: '并行分析', expert: '数据芯 + 卷查清 + 法条通' },
  { name: '综合评估（一票否决）', expert: '卷查清' },
  { name: '文书生成', expert: '文书成' },
  { name: '归档推送', expert: '知识库' },
];
export const SOP_CURRENT = 2; // 综合评估

export interface ReviewCase {
  vol: number;
  name: string;
  no: string;
  status: '待评' | 'AI初评中' | '待人工复核' | '已完成';
  score?: number | null;
  denied?: boolean;
  progress?: number;
}

export const queue: ReviewCase[] = [
  { vol: 74, name: '鑫顺建材堆场案', no: '娄环罚(冷)〔2026〕7号', status: '待人工复核', denied: true, score: null },
  { vol: 75, name: '瑞龙木艺厂粉尘案', no: '娄环罚(冷)〔2026〕9号', status: 'AI初评中', progress: 45 },
  { vol: 72, name: '金竹山矿业废气案', no: '娄环罚(冷)〔2026〕2号', status: '已完成', denied: true, score: 0 },
  { vol: 70, name: '禾青镇页岩砖厂案', no: '娄环罚(冷)〔2026〕5号', status: '已完成', score: 88 },
];

export const RESULT_CLS: Record<VetoResult, string> = {
  pass: 'olive', hit: 'red', na: 'aux',
};
export const RESULT_LABEL: Record<VetoResult, string> = {
  pass: '通过', hit: '命中', na: '未涉及',
};
