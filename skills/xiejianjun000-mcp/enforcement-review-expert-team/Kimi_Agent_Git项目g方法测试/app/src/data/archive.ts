// 档案管理模块数据 —— 锚定 design/archive.md
import { currentUser } from './currentUser';

export type Conclusion = '合格' | '整改' | '否决' | '待评';
export type BorrowState = '在库' | '借阅中';

export interface Archive {
  id: string;
  no: string;
  name: string;
  party: string;
  date: string;
  docs: number;
  conclusion: Conclusion;
  borrow: BorrowState;
  borrower?: string;
}

export const archives: Archive[] = [
  { id: 'a1', no: '娄环罚(冷)〔2026〕2号', name: '金竹山矿业废气超标案', party: '金竹山矿业有限公司', date: '2026-08-03', docs: 37, conclusion: '否决', borrow: '借阅中', borrower: currentUser.name },
  { id: 'a2', no: '娄环罚(冷)〔2026〕5号', name: '禾青镇页岩砖厂废气案', party: '禾青镇页岩砖厂', date: '2026-07-28', docs: 29, conclusion: '整改', borrow: '在库' },
  { id: 'a3', no: '娄环罚(冷)〔2026〕3号', name: '赢湖矿产品无证排污案', party: '赢湖矿产品有限公司', date: '2026-07-20', docs: 24, conclusion: '合格', borrow: '在库' },
  { id: 'a4', no: '娄环罚(冷)〔2026〕7号', name: '鑫顺建材堆场扬尘案', party: '鑫顺建材有限公司', date: '2026-08-05', docs: 18, conclusion: '待评', borrow: '在库' },
  { id: 'a5', no: '娄环罚(冷)〔2026〕9号', name: '瑞龙木艺厂粉尘案', party: '瑞龙木艺厂', date: '2026-08-03', docs: 21, conclusion: '待评', borrow: '借阅中', borrower: '王海' },
];

export const CONCL_CLS: Record<Conclusion, string> = {
  合格: 'olive', 整改: 'amber', 否决: 'red', 待评: 'aux',
};

export interface DocNode {
  name: string;
  pages?: number;
  missing?: boolean;
}

export interface DocCat {
  cat: string;
  count: number;
  docs: DocNode[];
}

// 74 类模板目录（按编号顺序，演示卷含部分文书）
export const docTree: DocCat[] = [
  { cat: '01 立案类（5）', count: 5, docs: [
    { name: '指定管辖通知书', pages: 2 }, { name: '立案审批表', pages: 1 }, { name: '立案决定书', pages: 2 },
    { name: '案件移送函', missing: true }, { name: '协查函', missing: true },
  ] },
  { cat: '02 调查类（20）', count: 20, docs: [
    { name: '现场检查勘察笔录', pages: 4 }, { name: '调查询问笔录', pages: 3 }, { name: '监测报告（废气）', pages: 6 },
    { name: '现场照片证据', pages: 8 }, { name: '取证设备校准记录', pages: 1 },
  ] },
  { cat: '03 裁量类（5）', count: 5, docs: [
    { name: '裁量权基准适用表', pages: 2 },
  ] },
  { cat: '04 告知类（12）', count: 12, docs: [
    { name: '行政处罚事先告知书', pages: 3 }, { name: '听证告知书', missing: true }, { name: '送达回证', pages: 1 },
  ] },
  { cat: '05 决定类（9）', count: 9, docs: [
    { name: '行政处罚决定书', pages: 4 }, { name: '责令改正决定书', pages: 2 },
  ] },
  { cat: '06 执行类（18）', count: 18, docs: [
    { name: '催告书', pages: 1 }, { name: '缴款凭证', pages: 1 }, { name: '执行情况记录', pages: 2 },
  ] },
  { cat: '07 归档类（4）', count: 4, docs: [
    { name: '卷宗目录', pages: 1 }, { name: '备考表', pages: 1 },
  ] },
];
